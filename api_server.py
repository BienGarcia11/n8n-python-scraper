import os
import asyncio
import uuid
from typing import Dict, Any, Optional
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
REDIS_URL = os.getenv('REDIS_URL')  # Optional Redis for caching
MAX_BULK_URLS = int(os.getenv('MAX_BULK_URLS', '100'))
PORT = int(os.getenv('PORT', '8000'))

# Validate required environment variables
if not all([SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY]):
    raise ValueError("Missing required environment variables: SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY")

# Initialize FastAPI app
app = FastAPI(title="Bulk Web Scraper for RAG", version="1.0.0")

# Initialize scraper
scraper = WebScraper(SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY, REDIS_URL)

# Global state for background tasks with task_id system
task_status: Dict[str, Dict[str, Any]] = {}

# Task type enum
from enum import Enum

class TaskType(str, Enum):
    BULK_SCRAPE = "bulk_scrape"
    VALIDATE_FIX = "validate_fix"


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


class ResetRequest(BaseModel):
    reset_all: bool = False
    status: Optional[str] = None  # 'completed', 'failed', 'processing', or None (all)


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
            "task_type": TaskType.BULK_SCRAPE,
            "status": "running",
            "started_at": asyncio.get_event_loop().time(),
            "processed": 0,
            "failed": 0,
            "cancelled": False
        }
        
        # Get total count of pending URLs
        total_count = scraper.get_total_pending_count()
        
        if total_count == 0:
            print("No pending URLs to process")
            task_status[task_id]["status"] = "completed"
            task_status[task_id]["message"] = "No pending URLs to process"
            return
            
        print(f"Starting bulk scrape for {total_count} URLs (Task: {task_id})")
        task_status[task_id]["total_urls"] = total_count
        
        # Process URLs in batches of 30 with browser restarts
        results = await scraper.process_urls_batched(max_concurrent=3, batch_size=30)
        
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
            "task_type": TaskType.VALIDATE_FIX,
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
@app.get("/health_check")
async def health_check():
    """Return service status with browser health info."""
    browser_ready = scraper.context is not None
    return {
        "status": "healthy",
        "service": "bulk-web-scraper",
        "version": "1.0.0",
        "browser_warm": browser_ready,
        "request_count": scraper.request_count,
        "restarts_pending": scraper.request_count >= scraper.browser_restart_interval
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


@app.get("/scraping_status")
async def scraping_status():
    """
    Check the status of the queue and current job.
    Returns task_id and detailed progress.
    Runs in thread pool to avoid blocking other requests.
    """
    from supabase import create_client
    from datetime import datetime
    
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
    current_task_type = None
    task_progress_info = None
    
    # Prioritize validate-fix tasks over bulk scrape (show more recent)
    for tid, tinfo in task_status.items():
        if tinfo.get("status") == "running":
            task_type = tinfo.get("task_type")
            
            # If validate-fix is running, show that (higher priority)
            if task_type == TaskType.VALIDATE_FIX:
                current_task_id = tid
                current_task_type = task_type
                total_issues = tinfo.get("total_issues", 0)
                fixed = tinfo.get("fixed", 0)
                task_progress_info = {
                    "task_type": "validate_fix",
                    "total_issues": total_issues,
                    "fixed": fixed,
                    "failed": tinfo.get("failed", 0),
                    "status": tinfo.get("status"),
                    "progress": int((fixed / total_issues * 100)) if total_issues > 0 else 0
                }
                break
            
            # Otherwise show bulk scrape
            elif task_type == TaskType.BULK_SCRAPE:
                if current_task_id is None:  # Only if no validate-fix running
                    current_task_id = tid
                    current_task_type = task_type
                    total_urls = tinfo.get("total_urls", 0)
                    processed = tinfo.get("processed", 0)
                    task_progress_info = {
                        "task_type": "bulk_scrape",
                        "total_urls": total_urls,
                        "processed": processed,
                        "failed": tinfo.get("failed", 0),
                        "status": tinfo.get("status"),
                        "progress": int((processed / total_urls * 100)) if total_urls > 0 else 0
                    }
    
    running = current_task_id is not None
    
    return {
        "running": running,
        "task_id": current_task_id,
        "task_type": current_task_type.value if current_task_type else None,
        "progress": task_progress_info.get("progress", 0) if task_progress_info else 0,
        "processed": task_progress_info.get("processed", 0) if task_progress_info else task_progress_info.get("fixed", 0),
        "failed": task_progress_info.get("failed", 0) if task_progress_info else 0,
        "pending_count": counts['pending'],
        "processing_count": counts['processing'],
        "completed_count": counts['completed'],
        "failed_count": counts['failed']
    }


@app.get("/validate")
async def validate():
    """
    Run validation checks on scraped data.
    Detects:
    - Phantom Completions: URLs in url_queue marked 'completed' but missing from documents
    - Missing Embeddings: Documents where content exists but embedding is NULL
    - Stuck URLs: URLs stuck in 'processing' status for > 1 hour
    
    Runs in thread pool to avoid blocking other requests.
    """
    from supabase import create_client
    from datetime import datetime
    
    # Run blocking validation in thread pool to avoid blocking event loop
    issues = await asyncio.to_thread(scraper.validate_data)
    
    # Get queue stats for additional info
    def get_queue_stats():
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        total_urls = supabase.table('url_queue').select('id', count='exact').execute()
        completed = supabase.table('url_queue').select('id', count='exact').eq('status', 'completed').execute()
        documents = supabase.table('documents').select('id', count='exact').execute()
        return {
            'total_urls': total_urls.count if hasattr(total_urls, 'count') else 0,
            'completed': completed.count if hasattr(completed, 'count') else 0,
            'documents': documents.count if hasattr(documents, 'count') else 0
        }
    
    stats = await asyncio.to_thread(get_queue_stats)
    
    total_issues = len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    total_urls = stats['total_urls']
    completed = stats['completed']
    
    # Calculate success rate
    success_rate = int((completed / total_urls * 100)) if total_urls > 0 else 0
    
    # Determine overall status
    if total_issues == 0:
        overall_status = "healthy"
    elif total_issues < 10:
        overall_status = "minor issues"
    elif total_issues < 100:
        overall_status = "moderate issues"
    else:
        overall_status = "critical"
    
    return {
        "overall_status": overall_status,
        "total_urls_in_queue": total_urls,
        "success_rate": success_rate,
        "missing_documents": len(issues['phantom_completions']),
        "stuck_in_processing": len(issues['stuck_urls']),
        "status_breakdown": {
            "phantom_completions": len(issues['phantom_completions']),
            "missing_embeddings": len(issues['missing_embeddings']),
            "stuck_urls": len(issues['stuck_urls'])
        },
        "total_issues": total_issues,
        "validation_timestamp": datetime.utcnow().isoformat(),
        "details": {
            "phantom_completions": issues['phantom_completions'],
            "missing_embeddings": issues['missing_embeddings'],
            "stuck_urls": issues['stuck_urls']
        }
    }


@app.post("/validate-fix")
async def validate_fix(background_tasks: BackgroundTasks):
    """
    Attempt to automatically fix validation errors.
    Returns immediately with validation results, fixes in background.
    - For phantom completions: Re-scrape, generate embedding, and insert
    - For missing embeddings: Retrieve content, generate embedding, and update the row
    - For stuck URLs: Reset to pending status
    """
    issues = scraper.validate_data()
    
    # Create task ID
    task_id = str(uuid.uuid4())
    
    # Start background task for fixing
    background_tasks.add_task(run_validation_fixes, task_id, issues)
    
    # Return validation results immediately
    total_issues = len(issues['phantom_completions']) + len(issues['missing_embeddings']) + len(issues['stuck_urls'])
    
    # Count what will be fixed
    phantom_to_fix = len(issues['phantom_completions'])
    missing_to_fix = len(issues['missing_embeddings'])
    stuck_to_fix = len(issues['stuck_urls'])
    
    return {
        "status": "fix_started",
        "message": "Validation fixes started in background",
        "validation_result": {
            "overall_status": "fixing",
            "total_urls_in_queue": 0,  # Would need additional query
            "success_rate": 0,
            "total_issues": total_issues,
            "missing_documents": phantom_to_fix,
            "stuck_in_processing": stuck_to_fix,
            "status_breakdown": {
                "phantom_completions": phantom_to_fix,
                "missing_embeddings": missing_to_fix,
                "stuck_urls": stuck_to_fix
            }
        },
        "fixed_urls": 0,
        "stuck_urls_fixed": stuck_to_fix,
        "missing_document_urls_fixed": phantom_to_fix,
        "bulk_scrape_task": {
            "status": "pending",
            "task_id": task_id,
            "pending_count": phantom_to_fix  # Will be rescraped
        }
    }


@app.post("/reset_to_pending", response_model=ResetResponse)
async def reset_to_pending(request: Optional[ResetRequest] = None):
    """
    Reset URLs in the queue back to 'pending' status.
    
    Parameters (optional):
    - reset_all: If True, resets all statuses to 'pending'
    - status: Specific status to reset ('completed', 'failed', 'processing')
    - If neither provided, defaults to 'failed' and 'processing'
    
    Runs in thread pool to avoid blocking other requests.
    """
    from supabase import create_client
    
    # Parse request body
    if request is None:
        request = ResetRequest()
    
    # Run blocking database operations in thread pool
    def reset_urls():
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Determine which URLs to reset
        if request.reset_all:
            # Reset ALL URLs
            statuses_to_reset = ['completed', 'failed', 'processing']
        elif request.status:
            # Reset specific status
            statuses_to_reset = [request.status]
        else:
            # Default: reset failed and processing
            statuses_to_reset = ['failed', 'processing']
        
        # Count URLs to reset
        total_count = 0
        for status_val in statuses_to_reset:
            count_result = supabase.table('url_queue').select('id', count='exact').eq('status', status_val).execute()
            total_count += (count_result.count if hasattr(count_result, 'count') else 0)
        
        # Reset URLs
        for status_val in statuses_to_reset:
            supabase.table('url_queue').update({
                'status': 'pending',
                'updated_at': 'now()'
            }).eq('status', status_val).execute()
        
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
    Sets cancel flag on scraper to stop processing immediately.
    """
    # Set cancel flag on scraper instance
    scraper.cancel_requested = True
    
    # Find running tasks and mark them as cancelled
    cancelled_count = 0
    for tid, tinfo in task_status.items():
        if tinfo.get("status") == "running":
            task_status[tid]["cancelled"] = True
            task_status[tid]["status"] = "stopped"
            cancelled_count += 1
            print(f"✓ Marked task {tid} for cancellation")
    
    if cancelled_count == 0:
        print("No active scraping process found")
        return StopResponse(
            message="No scraping process is currently active",
            success=False
        )
    
    print(f"✓ Requested cancellation for {cancelled_count} task(s)")
    return StopResponse(
        message=f"Requested cancellation for {cancelled_count} task(s)",
        success=True
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
