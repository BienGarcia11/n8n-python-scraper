"""
Bulk Scraper Service - Railway Deployment
Standalone service for bulk scraping all pending URLs
"""
import asyncio
import os
import sys
import uuid
import traceback
from datetime import datetime
from typing import List, Dict, Any
import httpx
from supabase import create_client
from openai import OpenAI
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Import scraper functions
from scraper import scrape_url, extract_content

app = FastAPI(title="Bulk Scraper Service", version="1.0.0")


class BulkScrapeResponse(BaseModel):
    task_id: str
    status: str
    pending_count: int
    message: str
    note: str


class StatusResponse(BaseModel):
    task_id: str
    status: str
    total_urls: int
    successful: int
    failed: int
    progress: float


# Store task status (in production, use Redis/database)
task_status: Dict[str, Dict[str, Any]] = {}


def get_supabase_client():
    """Get Supabase client"""
    supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_key:
        raise ValueError("SUPABASE_KEY environment variable is required")
    
    return create_client(supabase_url, supabase_key)


def fetch_pending_urls(client) -> List[Dict[str, Any]]:
    """Fetch all pending URLs from database"""
    result = client.table("url_queue").select("*").eq("status", "pending").execute()
    return result.data if result.data else []


def generate_embedding(content: str) -> List[float] | None:
    """Generate OpenAI embedding for content"""
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not openai_key:
        print("  ⚠️  OpenAI API key not set, skipping embeddings")
        return None
    
    try:
        client = OpenAI(api_key=openai_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=content[:8191]  # OpenAI limit
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"  ⚠️  Embedding failed: {e}")
        return None


def insert_document(client, url: str, content: str, title: str, embedding: List[float] | None):
    """Insert document into database with embedding"""
    metadata = {
        "source": url,
        "source_type": "web_scrape",
        "title": title,
        "scraped_at": datetime.utcnow().isoformat()
    }
    
    insert_data = {"content": content, "metadata": metadata}
    
    if embedding:
        insert_data["embedding"] = embedding
    else:
        metadata["no_embedding"] = True
    
    client.table("documents").insert(insert_data).execute()


def update_url_status(client, url: str, status: str):
    """Update URL status in queue - only update status, content goes to documents table"""
    update_data = {"status": status}
    
    client.table("url_queue").update(update_data).eq("url", url).execute()


async def run_bulk_scrape_task(task_id: str, pending_urls: List[Dict[str, Any]]):
    """Run bulk scraping in background"""
    global task_status
    
    try:
        client = get_supabase_client()
        total_urls = len(pending_urls)
        batch_size = 3
        urls = [u["url"] for u in pending_urls]
        batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]
        
        # Initialize task status
        task_status[task_id] = {
            "status": "running",
            "total_urls": total_urls,
            "successful": 0,
            "failed": 0,
            "progress": 0.0,
            "started_at": datetime.utcnow().isoformat()
        }
        
        print(f"\n{'='*60}")
        print(f"BULK SCRAPE TASK: {task_id}")
        print(f"{'='*60}")
        print(f"Pending URLs: {total_urls}")
        print(f"Batch size: {batch_size}")
        print(f"Total batches: {len(batches)}")
        
        total_successful = 0
        total_failed = 0
        
        for batch_num, batch in enumerate(batches, 1):
            print(f"\nBATCH {batch_num}/{len(batches)}: {len(batch)} URLs")
            
            # Mark as processing
            for url in batch:
                try:
                    update_url_status(client, url, "processing")
                except Exception as e:
                    print(f"  ⚠️  Failed to mark {url} as processing: {e}")
            
            # Scrape batch
            for url in batch:
                try:
                    print(f"  Scraping: {url[:60]}...")
                    
                    # Scrape URL
                    result = scrape_url(url)
                    
                    if result and result["status"] == "success":
                        content = result["content"]
                        title = result["title"]
                        
                        # Generate embedding
                        embedding = generate_embedding(content)
                        
                        # Insert document
                        insert_document(client, url, content, title, embedding)
                        
                        # Mark as completed (status only, content is in documents table)
                        update_url_status(client, url, "completed")
                        
                        total_successful += 1
                        print(f"    ✓ Success: {len(content):,} chars")
                        
                    else:
                        # Mark as failed
                        error = result.get("error", "Unknown error") if result else "Scraping failed"
                        update_url_status(client, url, "failed")
                        total_failed += 1
                        print(f"    ❌ Failed: {error}")
                
                except Exception as e:
                    print(f"    ❌ Error: {e}")
                    update_url_status(client, url, "failed")
                    total_failed += 1
            
            # Update progress
            processed = batch_num * batch_size
            progress = min((processed / total_urls) * 100, 100.0)
            task_status[task_id]["progress"] = progress
            task_status[task_id]["successful"] = total_successful
            task_status[task_id]["failed"] = total_failed
            
            print(f"  Batch {batch_num} complete: {batch_size} processed")
            print(f"  Progress: {progress:.1f}% ({processed}/{total_urls})")
        
        # Final status
        task_status[task_id]["status"] = "completed"
        task_status[task_id]["progress"] = 100.0
        task_status[task_id]["completed_at"] = datetime.utcnow().isoformat()
        
        print(f"\n{'='*60}")
        print(f"BULK SCRAPE COMPLETE: {task_id}")
        print(f"{'='*60}")
        print(f"Total: {total_urls}")
        print(f"Success: {total_successful}")
        print(f"Failed: {total_failed}")
        print(f"Success rate: {total_successful/total_urls*100:.1f}%")
        
    except Exception as e:
        print(f"\n❌ BULK SCRAPE FAILED: {task_id}")
        print(f"Error: {e}")
        traceback.print_exc()
        
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["error"] = str(e)
        task_status[task_id]["completed_at"] = datetime.utcnow().isoformat()


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Bulk Scraper Service",
        "version": "1.0.0",
        "endpoints": {
            "POST /scrape": "Start bulk scraping",
            "GET /status/{task_id}": "Check task status"
        }
    }


@app.post("/scrape", response_model=BulkScrapeResponse)
async def start_bulk_scrape(background_tasks: BackgroundTasks):
    """
    Start bulk scraping of all pending URLs
    
    Returns immediately with task ID.
    Scraping runs in background until all URLs are processed.
    """
    try:
        client = get_supabase_client()
        pending_urls = fetch_pending_urls(client)
        
        if not pending_urls:
            return BulkScrapeResponse(
                task_id=str(uuid.uuid4()),
                status="completed",
                pending_count=0,
                message="No pending URLs to scrape",
                note="Add URLs to url_queue table first"
            )
        
        task_id = str(uuid.uuid4())
        pending_count = len(pending_urls)
        
        # Start background task
        background_tasks.add_task(run_bulk_scrape_task, task_id, pending_urls)
        
        return BulkScrapeResponse(
            task_id=task_id,
            status="started",
            pending_count=pending_count,
            message=f"Started bulk scraping {pending_count} URLs",
            note=f"Task runs in background. Check status: GET /status/{task_id}"
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/status/{task_id}", response_model=StatusResponse)
async def get_task_status(task_id: str):
    """Get status of bulk scraping task"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail="Task not found")
    
    status = task_status[task_id]
    return StatusResponse(
        task_id=task_id,
        status=status["status"],
        total_urls=status["total_urls"],
        successful=status["successful"],
        failed=status["failed"],
        progress=status["progress"]
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "active_tasks": len(task_status),
        "service": "bulk_scraper"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
