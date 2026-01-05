import os
import asyncio
import uuid
from typing import Dict, Any
from fastapi import FastAPI, BackgroundTasks, HTTPException
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

# Global state for background tasks with task_id system
task_status: Dict[str, Dict[str, Any]] = {}


# Request/Response Models
class HealthCheckResponse(BaseModel):
    status: str
    service: str
    version: str


class BulkScrapeResponse(BaseModel):
    task_id: str
    status: str
    urls_queued: int
    message: str


class ScrapingStatusResponse(BaseModel):
    is_scraping: bool
    current_task_id: str | None
    pending_count: int
    processing_count: int
    completed_count: int
    failed_count: int
    task_progress: Dict[str, Any] | None


class ValidationResponse(BaseModel):
    phantom_completions: list
    missing_embeddings: list
    stuck_urls: list
    total_issues: int


class ValidationFixResponse(BaseModel):
    message: str
    phantom_completions: list
    missing_embeddings: list
    stuck_urls: list
    total_issues: int


class ResetResponse(BaseModel):
    message: str
    reset_count: int


class StopResponse(BaseModel):
    message: str
    success: bool


# Background task function
async def run_bulk_scrape(task_id: str):
    """Background task to process pending URLs."""
    try:
        # Initialize task status
        task_status[task_id] = {
            "status": "running",
            "started_at": asyncio.get_event_loop().time(),
            "processed": 0,
            "failed": 0,
            "cancelled": False
        }
        
        # Get pending URLs
        urls = scraper.get_pending_urls(limit=MAX_BULK_URLS)
        
        if not urls:
            print("No pending URLs to process")
            task_status[task_id]["status"] = "completed"
            task_status[task_id]["message"] = "No pending URLs to process"
            return
            
        print(f"Starting bulk scrape for {len(urls)} URLs (Task: {task_id})")
        task_status[task_id]["total_urls"] = len(urls)
        
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
        
        # Update task status
        task_status[task_id]["processed"] = len(results['success'])
        task_status[task_id]["failed"] = len(results['failed'])
        task_status[task_id]["status"] = "completed"
        task_status[task_id]["message"] = f"Completed: {len(results['success'])} success, {len(results['failed'])} failed"
        
        print(f"Bulk scrape completed (Task: {task_id}): {len(results['success'])} success, {len(results['failed'])} failed")
        
    except Exception as e:
        print(f"Error in bulk scrape (Task: {task_id}): {e}")
        if task_id in task_status:
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["error"] = str(e)
    finally:
        # Cleanup old task statuses (keep only last 10)
        if len(task_status) > 10:
            oldest_tasks = sorted(task_status.keys())[:-10]
            for old_id in oldest_tasks:
                del task_status[old_id]


# Background task for validation fixes
async def run_validation_fixes(task_id: str, issues: Dict[str, Any]):
    """Background task to process validation fixes."""
    try:
        # Initialize task status
        task_status[task_id] = {
            "status": "running",
            "started_at": asyncio.get_event_loop().time(),
            "fixed": 0,
            "failed": 0,
            "cancelled": False
        }
        
        print(f"Starting validation fixes (Task: {task_id})")
        
        results = await scraper.fix_validation_issues(issues)
        
        # Update task status
        task_status[task_id]["fixed"] = results['fixed']
        task_status[task_id]["failed"] = results['failed']
        task_status[task_id]["status"] = "completed"
        
        print(f"Validation fixes completed (Task: {task_id}): {results['fixed']} fixed, {results['failed']} failed")
        
    except Exception as e:
        print(f"Error in validation fixes (Task: {task_id}): {e}")
        if task_id in task_status:
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["error"] = str(e)
    finally:
        # Cleanup old task statuses
        if len(task_status) > 10:
            oldest_tasks = sorted(task_status.keys())[:-10]
            for old_id in oldest_tasks:
                del task_status[old_id]


# Startup event - initialize browser
@app.on_event("startup")
async def startup_event():
    """Initialize browser on startup."""
    try:
        await scraper.get_browser_context()
        print("✅ Browser initialized on startup")
    except Exception as e:
        print(f"⚠️  Warning: Browser initialization failed on startup: {e}")


# Shutdown event - cleanup resources
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("🛑 Shutting down scraper...")
    try:
        await scraper.cleanup()
        print("✅ Browser closed")
    except Exception as e:
        print(f"⚠️  Warning: Browser cleanup failed: {e}")
    
    # Clean up task statuses
    task_status.clear()
    print("✅ Shutdown complete")


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
                "description": "Begin scraping job (processes in background, returns task_id)"
            },
            {
                "path": "/scraping_status",
                "method": "GET",
                "description": "Check queue and job status (includes task_id)"
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
    Begin scraping job.
    Responds immediately to n8n, processes in background.
    Returns task_id for tracking.
    """
    # Check for running tasks
    running_tasks = [tid for tid, tinfo in task_status.items() if tinfo.get("status") == "running"]
    if running_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"Scraping is already in progress (Task ID: {running_tasks[0]})"
        )
    
    # Get pending URLs to report count
    urls = scraper.get_pending_urls(limit=MAX_BULK_URLS)
    
    if not urls:
        return BulkScrapeResponse(
            task_id=str(uuid.uuid4()),
            status="completed",
            urls_queued=0,
            message="No pending URLs to process"
        )
    
    # Create task ID
    task_id = str(uuid.uuid4())
    
    # Start background task
    background_tasks.add_task(run_bulk_scrape, task_id)
    
    return BulkScrapeResponse(
        task_id=task_id,
        status="started",
        urls_queued=len(urls),
        message=f"Bulk scrape started for {len(urls)} URLs"
    )


@app.get("/scraping_status", response_model=ScrapingStatusResponse)
async def scraping_status():
    """
    Check the status of the queue and current job.
    Returns task_id and detailed progress.
    Runs in thread pool to avoid blocking other requests.
    """
    from supabase import create_client
    
    # Run blocking database queries in thread pool
    def get_counts():
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        pending = supabase.table('url_queue').select('id', count='exact').eq('status', 'pending').execute()
        processing = supabase.table('url_queue').select('id', count='exact').eq('status', 'processing').execute()
        completed = supabase.table('url_queue').select('id', count='exact').eq('status', 'completed').execute()
        failed = supabase.table('url_queue').select('id', count='exact').eq('status', 'failed').execute()
        return {
            'pending': pending.count if hasattr(pending, 'count') else 0,
            'processing': processing.count if hasattr(processing, 'count') else 0,
            'completed': completed.count if hasattr(completed, 'count') else 0,
            'failed': failed.count if hasattr(failed, 'count') else 0
        }
    
    counts = await asyncio.to_thread(get_counts)
    
    # Find current running task
    current_task_id = None
    task_progress_info = None
    for tid, tinfo in task_status.items():
        if tinfo.get("status") == "running":
            current_task_id = tid
            task_progress_info = {
                "total_urls": tinfo.get("total_urls", 0),
                "processed": tinfo.get("processed", 0),
                "failed": tinfo.get("failed", 0),
                "status": tinfo.get("status")
            }
            break
    
    is_scraping = current_task_id is not None
    
    return ScrapingStatusResponse(
        is_scraping=is_scraping,
        current_task_id=current_task_id,
        pending_count=counts['pending'],
        processing_count=counts['processing'],
        completed_count=counts['completed'],
        failed_count=counts['failed'],
        task_progress=task_progress_info
    )


@app.get("/validate", response_model=ValidationResponse)
async def validate():
    """
    Run validation checks on scraped data.
    Detects:
    - Phantom Completions: URLs in url_queue marked 'completed' but missing from documents
    - Missing Embeddings: Documents where content exists but embedding is NULL
    - Stuck URLs: URLs stuck in 'processing' status for > 1 hour
    
    Runs in thread pool to avoid blocking other requests.
    """
    # Run blocking validation in thread pool to avoid blocking event loop
    issues = await asyncio.to_thread(scraper.validate_data)
    
    total_issues = len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    
    return ValidationResponse(
        phantom_completions=issues['phantom_completions'],
        missing_embeddings=issues['missing_embeddings'],
        stuck_urls=issues['stuck_urls'],
        total_issues=total_issues
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
    
    # Create task ID
    task_id = str(uuid.uuid4())
    
    # Start background task for fixing
    background_tasks.add_task(run_validation_fixes, task_id, issues)
    
    # Return validation results immediately
    total_issues = len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    
    return ValidationFixResponse(
        message="Validation fixes started in background",
        phantom_completions=issues['phantom_completions'],
        missing_embeddings=issues['missing_embeddings'],
        stuck_urls=issues['stuck_urls'],
        total_issues=total_issues
    )


@app.post("/reset_to_pending", response_model=ResetResponse)
async def reset_to_pending():
    """
    Reset URLs in the queue back to 'pending' status.
    Resets all 'failed' and 'processing' URLs to 'pending'.
    Runs in thread pool to avoid blocking other requests.
    """
    from supabase import create_client
    
    # Run blocking database operations in thread pool
    def reset_urls():
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
        
        return total_count
    
    reset_count = await asyncio.to_thread(reset_urls)
    
    return ResetResponse(
        message=f"Reset {reset_count} URLs to pending status",
        reset_count=reset_count
    )


@app.post("/stop_scraping_work", response_model=StopResponse)
async def stop_scraping_work():
    """
    Immediately terminate any active scraping processes.
    """
    # Find running tasks and mark them as cancelled
    cancelled_count = 0
    for tid, tinfo in task_status.items():
        if tinfo.get("status") == "running":
            task_status[tid]["cancelled"] = True
            cancelled_count += 1
            print(f"Marked task {tid} for cancellation")
    
    if cancelled_count == 0:
        return StopResponse(
            message="No scraping process is currently active",
            success=False
        )
    
    return StopResponse(
        message=f"Requested cancellation for {cancelled_count} task(s)",
        success=True
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
