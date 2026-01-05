import os
import asyncio
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from scraper import WebScraper

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MAX_BULK_URLS = int(os.getenv('MAX_BULK_URLS', '100'))
PORT = int(os.getenv('PORT', '8000'))

# Validate required environment variables
if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
    raise ValueError("Missing required environment variables: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY")

# Initialize FastAPI app
app = FastAPI(title="Bulk Web Scraper for RAG", version="1.0.0")

# Initialize scraper
scraper = WebScraper(SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY)

# Global state for background task
scraping_task = None
scraping_active = False


# Request/Response Models
class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str


class BulkScrapeResponse(BaseModel):
    message: str
    urls_queued: int


class ScrapingStatusResponse(BaseModel):
    is_scraping: bool
    pending_count: int
    processing_count: int
    completed_count: int
    failed_count: int


class ValidationResponse(BaseModel):
    phantom_completions: list
    missing_embeddings: list
    stuck_urls: list
    total_issues: int


class ValidationFixResponse(BaseModel):
    fixed: int
    failed: int


class ResetResponse(BaseModel):
    message: str
    reset_count: int


class StopResponse(BaseModel):
    message: str
    success: bool


# Background task function
async def run_bulk_scrape():
    """Background task to process pending URLs."""
    global scraping_active, scraping_task
    
    try:
        scraping_active = True
        
        # Get pending URLs
        urls = scraper.get_pending_urls(limit=MAX_BULK_URLS)
        
        if not urls:
            print("No pending URLs to process")
            return
            
        print(f"Starting bulk scrape for {len(urls)} URLs")
        
        # Update all URLs to 'processing' status
        for url in urls:
            scraper.update_url_status(url, 'processing')
        
        # Process URLs concurrently (3 at a time)
        results = await scraper.process_urls(urls, max_concurrent=3)
        
        # Update status based on results
        for url in results['success']:
            scraper.update_url_status(url, 'completed')
        for url in results['failed']:
            scraper.update_url_status(url, 'failed')
        
        print(f"Bulk scrape completed: {len(results['success'])} success, {len(results['failed'])} failed")
        
    except Exception as e:
        print(f"Error in bulk scrape: {e}")
    finally:
        scraping_active = False


# Root endpoint - Show all available endpoints
@app.get("/")
async def root():
    """Show all available API endpoints."""
    return {
        "service": "Bulk Web Scraper for RAG",
        "version": "1.0.0",
        "endpoints": [
            {
                "path": "/health_check",
                "method": "GET",
                "description": "Return service status"
            },
            {
                "path": "/start_bulk_scrape",
                "method": "POST",
                "description": "Begin scraping job (processes in background)"
            },
            {
                "path": "/scraping_status",
                "method": "GET",
                "description": "Check queue and job status"
            },
            {
                "path": "/validate",
                "method": "GET",
                "description": "Run validation checks on scraped data"
            },
            {
                "path": "/validate-fix",
                "method": "POST",
                "description": "Fix validation errors (runs in background, returns immediately)"
            },
            {
                "path": "/reset_to_pending",
                "method": "POST",
                "description": "Reset URLs to pending status"
            },
            {
                "path": "/stop_scraping_work",
                "method": "POST",
                "description": "Stop active scraping processes"
            }
        ]
    }


# API Endpoints
@app.get("/health_check", response_model=HealthCheckResponse)
async def health_check():
    """Return service status."""
    return {
        "status": "healthy",
        "service": "bulk-web-scraper",
        "version": "1.0.0"
    }


@app.post("/start_bulk_scrape", response_model=BulkScrapeResponse)
async def start_bulk_scrape(background_tasks: BackgroundTasks):
    """
    Begin the scraping job.
    Responds immediately to n8n, processes in background.
    """
    global scraping_active, scraping_task
    
    if scraping_active:
        raise HTTPException(status_code=409, detail="Scraping is already in progress")
    
    # Get pending URLs to report count
    urls = scraper.get_pending_urls(limit=MAX_BULK_URLS)
    
    if not urls:
        return BulkScrapeResponse(
            message="No pending URLs to process",
            urls_queued=0
        )
    
    # Start background task
    background_tasks.add_task(run_bulk_scrape)
    
    return BulkScrapeResponse(
        message=f"Bulk scrape started for {len(urls)} URLs",
        urls_queued=len(urls)
    )


@app.get("/scraping_status", response_model=ScrapingStatusResponse)
async def scraping_status():
    """
    Check the status of the queue and current job.
    """
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Get counts from url_queue
    pending = supabase.table('url_queue').select('id', count='exact').eq('status', 'pending').execute()
    processing = supabase.table('url_queue').select('id', count='exact').eq('status', 'processing').execute()
    completed = supabase.table('url_queue').select('id', count='exact').eq('status', 'completed').execute()
    failed = supabase.table('url_queue').select('id', count='exact').eq('status', 'failed').execute()
    
    return ScrapingStatusResponse(
        is_scraping=scraping_active,
        pending_count=pending.count if hasattr(pending, 'count') else 0,
        processing_count=processing.count if hasattr(processing, 'count') else 0,
        completed_count=completed.count if hasattr(completed, 'count') else 0,
        failed_count=failed.count if hasattr(failed, 'count') else 0
    )


@app.get("/validate", response_model=ValidationResponse)
async def validate():
    """
    Run validation checks on the scraped data.
    Detects:
    - Phantom Completions: URLs in url_queue marked 'completed' but missing from documents
    - Missing Embeddings: Documents where content exists but embedding is NULL
    - Stuck URLs: URLs stuck in 'processing' status for > 1 hour
    """
    issues = scraper.validate_data()
    
    return ValidationResponse(
        phantom_completions=issues['phantom_completions'],
        missing_embeddings=issues['missing_embeddings'],
        stuck_urls=issues['stuck_urls'],
        total_issues=len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    )


@app.post("/validate-fix")
async def validate_fix(background_tasks: BackgroundTasks):
    """
    Attempt to automatically fix validation errors.
    Returns immediately with validation results, fixes in background.
    - For phantom completions: Re-scrape, generate embedding, and insert
    - For missing embeddings: Retrieve content, generate embedding, and update the row
    """
    issues = scraper.validate_data()
    
    # Start background task for fixing
    background_tasks.add_task(run_validation_fixes, issues)
    
    # Return validation results immediately
    return {
        "message": "Validation fixes started in background",
        "phantom_completions": issues['phantom_completions'],
        "missing_embeddings": issues['missing_embeddings'],
        "stuck_urls": issues['stuck_urls'],
        "total_issues": len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    }


async def run_validation_fixes(issues: Dict[str, Any]):
    """Background task to process validation fixes."""
    global scraping_active
    
    try:
        scraping_active = True
        results = await scraper.fix_validation_issues(issues)
        print(f"Validation fixes completed: {results['fixed']} fixed, {results['failed']} failed")
    except Exception as e:
        print(f"Error in validation fixes: {e}")
    finally:
        scraping_active = False


@app.post("/reset_to_pending", response_model=ResetResponse)
async def reset_to_pending():
    """
    Reset URLs in the queue back to 'pending' status.
    Resets all 'failed' and 'processing' URLs to 'pending'.
    """
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    # Count URLs to reset
    failed_count = supabase.table('url_queue').select('id', count='exact').eq('status', 'failed').execute()
    processing_count = supabase.table('url_queue').select('id', count='exact').eq('status', 'processing').execute()
    
    total_count = (failed_count.count if hasattr(failed_count, 'count') else 0) + \
                  (processing_count.count if hasattr(processing_count, 'count') else 0)
    
    # Reset failed URLs
    supabase.table('url_queue').update({
        'status': 'pending',
        'updated_at': 'now()'
    }).eq('status', 'failed').execute()
    
    # Reset processing URLs
    supabase.table('url_queue').update({
        'status': 'pending',
        'updated_at': 'now()'
    }).eq('status', 'processing').execute()
    
    return ResetResponse(
        message=f"Reset {total_count} URLs to pending status",
        reset_count=total_count
    )


@app.post("/stop_scraping_work", response_model=StopResponse)
async def stop_scraping_work():
    """
    Immediately terminate any active scraping processes.
    """
    global scraping_active
    
    if not scraping_active:
        return StopResponse(
            message="No scraping process is currently active",
            success=False
        )
    
    scraping_active = False
    
    return StopResponse(
        message="Scraping process termination requested",
        success=True
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
