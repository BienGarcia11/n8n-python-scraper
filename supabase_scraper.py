"""
Supabase-Integrated Web Scraper
FastAPI application that processes URLs from url_queue table,
scrapes content, generates embeddings, and stores in documents table
"""

import asyncio
import time
import os
from datetime import datetime
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from supabase import create_client, Client
from dotenv import load_dotenv

# Import existing scraper and embedding generator
from versatile_scraper import VersatileScraper, WEBSITE_PRESETS
from embedding_generator import EmbeddingGenerator

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="Supabase Web Scraper",
    description="Processes URLs from queue and generates embeddings",
    version="1.0.0"
)

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", "8000"))

# Global variables for lazy initialization (set after app loads)
supabase = None
embedder = None

# Initialize components (with graceful degradation if env vars missing)
def initialize_components():
    """Initialize Supabase and OpenAI clients with graceful degradation"""
    global supabase, embedder
    
    # Initialize Supabase client
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("WARNING: SUPABASE_URL or SUPABASE_KEY not set - Supabase features disabled")
        supabase = None
    else:
        try:
            from supabase import create_client, Client
            try:
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            except TypeError as e:
                # Fallback: try initializing without options to avoid proxy parameter issue
                print(f"Warning: Using fallback Supabase initialization due to: {e}")
                from supabase import Client as SupabaseClient
                supabase = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)
            print("✓ Supabase client initialized")
        except Exception as e:
            print(f"ERROR: Failed to initialize Supabase client: {e}")
            supabase = None
    
    # Initialize embedding generator
    if not OPENAI_API_KEY:
        print("WARNING: OPENAI_API_KEY not set - embedding generation disabled")
        embedder = None
    else:
        try:
            from embedding_generator import EmbeddingGenerator
            embedder = EmbeddingGenerator(api_key=OPENAI_API_KEY)
            print("✓ Embedding generator initialized")
        except Exception as e:
            print(f"ERROR: Failed to initialize embedding generator: {e}")
            embedder = None

# Initialize components after app loads
initialize_components()

# Batch size for parallel processing
BATCH_SIZE = 3
# Maximum retry attempts
MAX_RETRIES = 3
# Backoff times in seconds
BACKOFF_TIMES = [30, 60, 120]


class ScrapeRequest(BaseModel):
    """Request model for scrape endpoint"""
    batch_size: Optional[int] = BATCH_SIZE


class ScrapeResponse(BaseModel):
    """Response model for scrape endpoint"""
    success: bool
    message: str
    total_processed: int
    successful: int
    failed: int
    total_chunks_inserted: int
    total_chunks_deleted: int
    processing_time: str
    refreshed_urls: int
    new_urls: int
    details: List[Dict]


def update_url_status(url_id: int, status: str, error_message: str = None) -> bool:
    """Update URL status in url_queue table"""
    try:
        update_data = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if status == "completed":
            update_data["processed_at"] = datetime.utcnow().isoformat()
        
        if error_message:
            update_data["error_message"] = error_message
        
        response = supabase.table("url_queue").update(update_data).eq("id", url_id).execute()
        return True
    except Exception as e:
        print(f"Error updating URL {url_id} status: {e}")
        return False


def delete_existing_documents(url: str) -> int:
    """Delete all documents for a given URL (Option A: Full Refresh)"""
    try:
        # First, check if any documents exist for this URL
        check_response = supabase.table("documents").select("id").eq("url", url).execute()
        existing_count = len(check_response.data) if check_response.data else 0
        
        if existing_count > 0:
            print(f"  Deleting {existing_count} existing chunks for {url}...")
            # Delete all documents for this URL
            delete_response = supabase.table("documents").delete().eq("url", url).execute()
            print(f"  ✓ Deleted {existing_count} old chunks")
            return existing_count
        
        return 0
    except Exception as e:
        print(f"  ✗ Error deleting existing documents: {e}")
        return 0


def insert_documents(chunks_with_embeddings: List[Dict], scraped_data: Dict) -> int:
    """Insert document chunks with embeddings into documents table"""
    try:
        inserted_count = 0
        
        for chunk_data in chunks_with_embeddings:
            # Prepare metadata
            metadata = {
                "url": scraped_data.get("url", ""),
                "title": scraped_data.get("metadata", {}).get("title", ""),
                "author": scraped_data.get("metadata", {}).get("author", ""),
                "publication_date": scraped_data.get("metadata", {}).get("publication_date", ""),
                "scraped_at": scraped_data.get("scraped_at", datetime.utcnow().isoformat()),
                "website_type": scraped_data.get("scraper_config", "default"),
                "chunk_index": chunk_data.get("chunk_id", 0),
                "total_chunks": len(chunks_with_embeddings)
            }
            
            # Prepare document record
            document = {
                "content": chunk_data.get("text", ""),
                "metadata": metadata,
                "embedding": chunk_data.get("embedding", []),
                "url": scraped_data.get("url", ""),
                "title": scraped_data.get("metadata", {}).get("title", ""),
                "chunk_index": chunk_data.get("chunk_id", 0),
                "total_chunks": len(chunks_with_embeddings)
            }
            
            # Insert document
            response = supabase.table("documents").insert(document).execute()
            inserted_count += 1
        
        print(f"  ✓ Inserted {inserted_count} chunks into documents table")
        return inserted_count
    
    except Exception as e:
        print(f"  ✗ Error inserting documents: {e}")
        raise


async def process_single_url(url_data: Dict) -> Dict:
    """Process a single URL: scrape, generate embeddings, save to database"""
    url = url_data["url"]
    url_id = url_data["id"]
    attempt = url_data.get("attempts", 0) + 1
    
    print(f"\n[URL {url_id}] Processing: {url}")
    print(f"[URL {url_id}] Attempt {attempt}/{MAX_RETRIES}")
    
    try:
        # Determine website type and configuration
        website_type = "xero"  # Default to xero, can be made configurable
        config = WEBSITE_PRESETS.get(website_type, WEBSITE_PRESETS['blog'])
        
        # Scrape URL
        print(f"[URL {url_id}] Scraping...")
        scraper = VersatileScraper(url, config)
        scraped_data = await scraper.scrape()
        
        # Generate embeddings
        print(f"[URL {url_id}] Generating embeddings...")
        chunks = embedder.chunk_text(
            scraped_data["full_text"],
            chunk_size=800,
            overlap=100
        )
        
        chunks_with_embeddings = embedder.generate_embeddings_batch(chunks, batch_size=20)
        
        # Delete existing documents (Full Refresh strategy)
        deleted_count = delete_existing_documents(url)
        
        # Insert new documents
        inserted_count = insert_documents(chunks_with_embeddings, scraped_data)
        
        # Update URL status to completed
        update_url_status(url_id, "completed")
        
        print(f"[URL {url_id}] ✓ SUCCESS - Processed {inserted_count} chunks (deleted {deleted_count} old)")
        
        return {
            "url": url,
            "status": "completed",
            "chunks": inserted_count,
            "deleted_chunks": deleted_count,
            "attempts": attempt,
            "error": None
        }
    
    except Exception as e:
        error_message = str(e)
        print(f"[URL {url_id}] ✗ FAILED: {error_message}")
        
        # Check if we should retry
        if attempt < MAX_RETRIES:
            backoff_time = BACKOFF_TIMES[min(attempt - 1, len(BACKOFF_TIMES) - 1)]
            print(f"[URL {url_id}] Retrying in {backoff_time} seconds...")
            
            # Update attempts count
            update_url_status(url_id, "pending", f"Attempt {attempt} failed: {error_message}")
            
            # Wait for backoff
            await asyncio.sleep(backoff_time)
            
            # Retry
            return await process_single_url({
                **url_data,
                "attempts": attempt
            })
        else:
            # Max retries reached, mark as failed
            update_url_status(url_id, "failed", f"Failed after {MAX_RETRIES} attempts: {error_message}")
            
            return {
                "url": url,
                "status": "failed",
                "chunks": 0,
                "deleted_chunks": 0,
                "attempts": attempt,
                "error": error_message
            }


async def process_batch(batch_size: int = BATCH_SIZE) -> Dict:
    """Process a batch of URLs from url_queue"""
    print(f"\n{'='*60}")
    print(f"FETCHING BATCH (size: {batch_size})")
    print(f"{'='*60}")
    
    # Fetch pending URLs
    response = supabase.table("url_queue").select("*").eq("status", "pending").limit(batch_size).execute()
    pending_urls = response.data if response.data else []
    
    if not pending_urls:
        print("No pending URLs found in queue")
        return {
            "total_processed": 0,
            "successful": 0,
            "failed": 0,
            "total_chunks_inserted": 0,
            "total_chunks_deleted": 0,
            "processing_time": "0s",
            "refreshed_urls": 0,
            "new_urls": 0,
            "details": []
        }
    
    print(f"Found {len(pending_urls)} pending URLs")
    
    # Update status to processing
    url_ids = [url["id"] for url in pending_urls]
    for url_id in url_ids:
        update_url_status(url_id, "processing")
    
    # Process URLs in parallel
    print(f"\nProcessing {len(pending_urls)} URLs in parallel...")
    results = await asyncio.gather(*[
        process_single_url(url_data) 
        for url_data in pending_urls
    ])
    
    # Calculate statistics
    successful = sum(1 for r in results if r["status"] == "completed")
    failed = sum(1 for r in results if r["status"] == "failed")
    total_chunks_inserted = sum(r["chunks"] for r in results)
    total_chunks_deleted = sum(r["deleted_chunks"] for r in results)
    refreshed_urls = sum(1 for r in results if r["deleted_chunks"] > 0)
    new_urls = sum(1 for r in results if r["deleted_chunks"] == 0 and r["status"] == "completed")
    
    return {
        "total_processed": len(pending_urls),
        "successful": successful,
        "failed": failed,
        "total_chunks_inserted": total_chunks_inserted,
        "total_chunks_deleted": total_chunks_deleted,
        "processing_time": "0s",
        "refreshed_urls": refreshed_urls,
        "new_urls": new_urls,
        "details": results
    }


async def process_all_urls(batch_size: int = BATCH_SIZE) -> Dict:
    """Process all pending URLs in batches"""
    start_time = time.time()
    
    print(f"\n{'='*60}")
    print("STARTING FULL QUEUE PROCESSING")
    print(f"{'='*60}")
    
    total_stats = {
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "total_chunks_inserted": 0,
        "total_chunks_deleted": 0,
        "processing_time": "0s",
        "refreshed_urls": 0,
        "new_urls": 0,
        "details": []
    }
    
    batch_num = 0
    while True:
        batch_num += 1
        print(f"\n{'#'*60}")
        print(f"BATCH #{batch_num}")
        print(f"{'#'*60}")
        
        # Process a batch
        batch_result = await process_batch(batch_size)
        
        # Update total statistics
        total_stats["total_processed"] += batch_result["total_processed"]
        total_stats["successful"] += batch_result["successful"]
        total_stats["failed"] += batch_result["failed"]
        total_stats["total_chunks_inserted"] += batch_result["total_chunks_inserted"]
        total_stats["total_chunks_deleted"] += batch_result["total_chunks_deleted"]
        total_stats["refreshed_urls"] += batch_result["refreshed_urls"]
        total_stats["new_urls"] += batch_result["new_urls"]
        total_stats["details"].extend(batch_result["details"])
        
        # Check if there are more pending URLs
        if batch_result["total_processed"] == 0:
            print(f"\nNo more pending URLs. Processing complete.")
            break
        
        # Small delay between batches
        if batch_result["total_processed"] > 0:
            print(f"\nWaiting 2 seconds before next batch...")
            await asyncio.sleep(2)
    
    # Calculate total processing time
    total_time = time.time() - start_time
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)
    total_stats["processing_time"] = f"{minutes}m {seconds}s"
    
    # Print final summary
    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total URLs processed: {total_stats['total_processed']}")
    print(f"Successful: {total_stats['successful']}")
    print(f"Failed: {total_stats['failed']}")
    print(f"Total chunks inserted: {total_stats['total_chunks_inserted']}")
    print(f"Total chunks deleted: {total_stats['total_chunks_deleted']}")
    print(f"Refreshed URLs: {total_stats['refreshed_urls']}")
    print(f"New URLs: {total_stats['new_urls']}")
    print(f"Processing time: {total_stats['processing_time']}")
    print(f"{'='*60}\n")
    
    return total_stats


@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "service": "Supabase Web Scraper",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint - lightweight, no database required"""
    try:
        # Check if Supabase client is initialized (but don't query database)
        if not supabase or not SUPABASE_URL or not SUPABASE_KEY:
            raise Exception("Supabase not configured")
        
        return {
            "status": "healthy",
            "service": "Supabase Web Scraper",
            "version": "1.0.0",
            "supabase_url_configured": bool(SUPABASE_URL),
            "openai_key_configured": bool(OPENAI_API_KEY)
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


@app.post("/scrape")
async def scrape_endpoint(request: ScrapeRequest = None) -> ScrapeResponse:
    """Main endpoint to start scraping all pending URLs from queue"""
    try:
        # Use provided batch_size or default
        batch_size = request.batch_size if request else BATCH_SIZE
        
        # Process all URLs
        result = await process_all_urls(batch_size)
        
        return ScrapeResponse(
            success=True,
            message="Scraping completed successfully",
            **result
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error during scraping: {str(e)}",
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "total_chunks_inserted": 0,
                "total_chunks_deleted": 0,
                "processing_time": "0s",
                "refreshed_urls": 0,
                "new_urls": 0,
                "details": []
            }
        )


@app.post("/scrape-batch")
async def scrape_batch_endpoint(request: ScrapeRequest) -> ScrapeResponse:
    """Process a single batch of URLs (for testing)"""
    try:
        # Process one batch only
        batch_result = await process_batch(request.batch_size)
        
        return ScrapeResponse(
            success=True,
            message="Batch processed successfully",
            **batch_result
        )
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Error during batch processing: {str(e)}",
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "total_chunks_inserted": 0,
                "total_chunks_deleted": 0,
                "processing_time": "0s",
                "refreshed_urls": 0,
                "new_urls": 0,
                "details": []
            }
        )


@app.get("/queue/status")
async def queue_status():
    """Get status of URL queue"""
    try:
        # Get counts by status
        pending_response = supabase.table("url_queue").select("id", count="exact").eq("status", "pending").execute()
        processing_response = supabase.table("url_queue").select("id", count="exact").eq("status", "processing").execute()
        completed_response = supabase.table("url_queue").select("id", count="exact").eq("status", "completed").execute()
        failed_response = supabase.table("url_queue").select("id", count="exact").eq("status", "failed").execute()
        
        return {
            "pending": pending_response.count if hasattr(pending_response, 'count') else 0,
            "processing": processing_response.count if hasattr(processing_response, 'count') else 0,
            "completed": completed_response.count if hasattr(completed_response, 'count') else 0,
            "failed": failed_response.count if hasattr(failed_response, 'count') else 0
        }
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
