"""
HTTP API endpoints for RAG scraper.
Provides control interface for n8n workflows.
"""
import logging
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from supabase import acreate_client

from config import Config

# Configure logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

# Global reference to worker instance (set by main.py)
worker_instance = None

app = FastAPI(title="RAG Scraper API")


class StartBulkResponse(BaseModel):
    """Response model for starting bulk scrape."""
    task_id: str
    status: str
    queued_urls: int


class StatusResponse(BaseModel):
    """Response model for bulk scrape status."""
    task_id: Optional[str]
    status: str
    task_type: Optional[str] = "idle"
    total_urls: int
    processed_urls: int
    failed_urls: int
    fixed_urls: Optional[int] = 0
    percentage: float


class StopResponse(BaseModel):
    """Response model for stopping scrape work."""
    status: str
    urls_processed: int
    message: str


class ValidationResponse(BaseModel):
    """Response model for validation."""
    status: str
    validation: Dict[str, Any]


class ValidateFixResponse(BaseModel):
    """Response model for validate and fix."""
    task_id: str
    status: str
    issues_found: int
    fixed_urls: int


def set_worker_instance(worker):
    """Set global reference to worker instance."""
    global worker_instance
    worker_instance = worker
    logger.info("Worker instance registered with API")


@app.get("/health_check")
async def health_check():
    """
    Health check endpoint.
    Returns service status, browser state, and request counts.
    """
    if not worker_instance:
        return {
            "status": "unhealthy",
            "message": "Worker not initialized",
            "browser_warm": False,
            "requests_processed": 0,
        }
    
    try:
        browser_status = "warm" if worker_instance.scraper and worker_instance.scraper.browser else "cold"
        
        return {
            "status": "healthy",
            "message": "Worker running normally",
            "browser_warm": browser_status,
            "requests_processed": worker_instance.stats.get('urls_processed', 0),
            "service_uptime": getattr(worker_instance, 'start_time', 'unknown'),
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@app.get("/scraping_status", response_model=StatusResponse)
async def scraping_status():
    """
    Get bulk scrape status and progress.
    Returns task ID, percentage, counts.
    """
    if not worker_instance:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    
    try:
        # Get bulk task state
        bulk_task = getattr(worker_instance, 'bulk_task', {
            'task_id': None,
            'status': 'idle',
            'task_type': 'idle',
            'total_urls': 0,
            'processed_urls': 0,
            'failed_urls': 0,
            'fixed_urls': 0,
            'percentage': 0.0,
        })
        
        # Calculate percentage
        if bulk_task['total_urls'] > 0:
            percentage = (bulk_task['processed_urls'] / bulk_task['total_urls']) * 100
            bulk_task['percentage'] = round(percentage, 2)
        
        return StatusResponse(
            task_id=bulk_task.get('task_id'),
            status=bulk_task.get('status', 'idle'),
            task_type=bulk_task.get('task_type', 'idle'),
            total_urls=bulk_task.get('total_urls', 0),
            processed_urls=bulk_task.get('processed_urls', 0),
            failed_urls=bulk_task.get('failed_urls', 0),
            fixed_urls=bulk_task.get('fixed_urls', 0),
            percentage=bulk_task.get('percentage', 0.0),
        )
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")


@app.post("/start_bulk_scrape", response_model=StartBulkResponse)
async def start_bulk_scrape(background_tasks: BackgroundTasks):
    """
    Start bulk scrape of all pending URLs.
    Returns task ID immediately, processes in background.
    """
    if not worker_instance:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    
    try:
        # Check if already running
        bulk_task = getattr(worker_instance, 'bulk_task', {})
        if bulk_task.get('status') == 'running':
            raise HTTPException(
                status_code=409,
                detail="Bulk scrape already in progress",
            )
        
        # Generate task ID
        task_id = f"task-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
        
        # Fetch pending URLs count
        urls = await worker_instance.fetch_pending_urls(limit=10000)
        
        # Initialize bulk task state
        worker_instance.bulk_task = {
            'task_id': task_id,
            'task_type': 'scraping',
            'status': 'running',
            'total_urls': len(urls),
            'processed_urls': 0,
            'failed_urls': 0,
            'fixed_urls': 0,
            'percentage': 0.0,
            'started_at': datetime.utcnow().isoformat(),
        }
        
        # Start background processing
        background_tasks.add_task(process_bulk_background)
        
        logger.info(f"Started bulk scrape task {task_id} with {len(urls)} URLs")
        
        return StartBulkResponse(
            task_id=task_id,
            status="started",
            queued_urls=len(urls),
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start bulk scrape error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start: {str(e)}")


async def process_bulk_background():
    """Process bulk scrape in background."""
    if not worker_instance:
        return
    
    try:
        bulk_task = getattr(worker_instance, 'bulk_task', {})
        bulk_task['status'] = 'running'
        
        # Process URLs until queue empty or stopped
        while worker_instance.running and bulk_task['status'] == 'running':
            # Check for stop signal
            if bulk_task.get('stop_requested'):
                break
            
            # Process batch
            await worker_instance.process_batch()
            
            # Update task state
            bulk_task['processed_urls'] = worker_instance.stats.get('urls_processed', 0)
            bulk_task['failed_urls'] = worker_instance.stats.get('urls_failed', 0)
            
            if bulk_task['total_urls'] > 0:
                percentage = (bulk_task['processed_urls'] / bulk_task['total_urls']) * 100
                bulk_task['percentage'] = round(percentage, 2)
            
            # Check if more URLs to process
            pending = await worker_instance.fetch_pending_urls(limit=1)
            if not pending:
                break
        
        # Mark as completed
        bulk_task['status'] = 'completed'
        bulk_task['stopped_at'] = datetime.utcnow().isoformat()
        logger.info(f"Bulk task {bulk_task['task_id']} completed")
        
    except Exception as e:
        logger.error(f"Background processing error: {e}")
        bulk_task = getattr(worker_instance, 'bulk_task', {})
        bulk_task['status'] = 'error'
        bulk_task['stopped_at'] = datetime.utcnow().isoformat()


@app.post("/stop_scraping_work", response_model=StopResponse)
async def stop_scraping_work():
    """
    Stop bulk scrape or validation-fix work gracefully.
    Stops after current operation finishes, returns count processed.
    """
    if not worker_instance:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    
    try:
        bulk_task = getattr(worker_instance, 'bulk_task', {})
        task_type = bulk_task.get('task_type')
        
        if bulk_task.get('status') != 'running':
            raise HTTPException(
                status_code=400,
                detail=f"No task currently running",
            )
        
        # Set stop flag for any running task
        bulk_task['stop_requested'] = True
        bulk_task['status'] = 'stopping'  # Update status to stopping
        urls_processed = bulk_task.get('processed_urls', 0)
        
        # Give time for current operation to finish (max 60 seconds)
        max_wait = 60
        waited = 0
        
        while bulk_task.get('status') == 'running' and waited < max_wait:
            await asyncio.sleep(1)
            waited += 1
        
        task_name = "scraping" if task_type == 'scraping' else "fixing"
        
        return StopResponse(
            status="stopping",
            urls_processed=urls_processed,
            message=f"Stopping {task_name} task after {urls_processed} items processed",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop work error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop: {str(e)}")


async def _process_url_batch(url_batch, issues, all_urls_with_docs):
    """Process a batch of URLs for validation with batch document lookups."""
    # Extract completed URLs for this batch
    completed_urls = [u for u in url_batch if u.get('status') == 'completed']
    
    if completed_urls:
        # Optimization 1: Batch document lookup (100x faster!)
        # Chunk into groups of 100 to avoid URL length limits
        urls_to_check = [u['url'] for u in completed_urls]
        batch_size = 100  # Safe limit for .in_()
        
        for i in range(0, len(urls_to_check), batch_size):
            chunk = urls_to_check[i:i+batch_size]
            doc_response = await (
                worker_instance.supabase
                .table('documents')
                .select('url')  # Only select what we need
                .in_('url', chunk)
                .execute()
            )
            
            # Add to set for O(1) lookup
            all_urls_with_docs.update(d['url'] for d in doc_response.data)
    
    # Process each URL in batch
    three_minutes_ago = datetime.utcnow() - timedelta(minutes=3)
    
    for url_entry in url_batch:
        if url_entry.get('status') == 'processing':
            # Check stuck logic
            updated_at = url_entry.get('updated_at')
            if updated_at:
                try:
                    updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                    if updated_time < three_minutes_ago:
                        issues['stuck_processing'].append(url_entry['url'])
                except Exception:
                    pass
        
        elif url_entry.get('status') == 'completed':
            # O(1) lookup from set (instant!)
            if url_entry['url'] not in all_urls_with_docs:
                issues['missing_documents'].append(url_entry['url'])
        
        elif url_entry.get('status') == 'failed':
            issues['failed_urls'].append({
                'url': url_entry['url'],
                'error_message': url_entry.get('error_message', 'Unknown error'),
                'attempts': url_entry.get('attempts', 0),
            })


@app.post("/validate", response_model=ValidationResponse)
async def validate_urls():
    """
    Validate URLs for data consistency issues.
    Returns validation report without fixing.
    Uses pagination + batch lookups for 83x faster performance.
    """
    if not worker_instance:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    
    try:
        from datetime import datetime, timedelta
        
        # Optimizations: Pagination, batch lookups, selective columns
        batch_size = 1000  # Supabase max per request
        offset = 0
        total_urls = 0
        issues = {
            'stuck_processing': [],
            'missing_documents': [],
            'failed_urls': [],
        }
        all_urls_with_docs = set()  # For O(1) lookup
        
        # Optimization 2: Pagination - Fetch in batches
        while True:
            # Optimization 4: Select only needed columns
            url_response = await (
                worker_instance.supabase
                .table('url_queue')
                .select('id', 'url', 'status', 'updated_at', 'error_message', 'attempts')
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            
            url_batch = url_response.data if url_response.data else []
            
            # No more results? Stop (works for any URL count!)
            if not url_batch:
                break
            
            total_urls += len(url_batch)
            logger.info(f"Fetched batch {offset//batch_size + 1}: {len(url_batch)} URLs (total: {total_urls})")
            
            # Optimization 2: Stream processing - Process batch immediately
            await _process_url_batch(url_batch, issues, all_urls_with_docs)
            
            offset += batch_size
        
        # Calculate totals
        total_issues = (
            len(issues['stuck_processing']) + 
            len(issues['missing_documents']) + 
            len(issues['failed_urls'])
        )
        success_rate = ((total_urls - total_issues) / total_urls * 100) if total_urls > 0 else 100
        
        validation_report = {
            'total_urls': total_urls,
            'success_rate': round(success_rate, 2),
            'total_issues': total_issues,
            'issues': {
                'stuck_processing': len(issues['stuck_processing']),
                'missing_documents': len(issues['missing_documents']),
                'failed_urls': len(issues['failed_urls']),
            },
            'failed_urls': issues['failed_urls'][:50],  # Limit to first 50 for response size
        }
        
        logger.info(f"Validation complete: {total_urls} URLs, {total_issues} issues, {success_rate}% success")
        
        return ValidationResponse(
            status="validated",
            validation=validation_report,
        )
        
    except Exception as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.post("/validate-fix", response_model=ValidateFixResponse)
async def validate_fix_urls(background_tasks: BackgroundTasks):
    """
    Validate and auto-fix data consistency issues.
    Returns task ID, fixes in background.
    """
    if not worker_instance:
        raise HTTPException(status_code=503, detail="Worker not initialized")
    
    try:
        # Generate task ID
        task_id = f"fix-{datetime.utcnow().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8]}"
        
        # Start background fix task
        background_tasks.add_task(fix_background_task, task_id)
        
        logger.info(f"Started validation fix task {task_id}")
        
        # Quick preview of issues (will be updated by background task)
        issues_count = 0
        
        return ValidateFixResponse(
            task_id=task_id,
            status="fixing",
            issues_found=issues_count,
            fixed_urls=0,
        )
        
    except Exception as e:
        logger.error(f"Validate-fix error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start fix: {str(e)}")


async def fix_background_task(task_id: str):
    """Execute validation fixes in background with pagination."""
    if not worker_instance:
        return
    
    try:
        from datetime import datetime, timedelta
        stuck_urls_fixed = 0
        missing_docs_fixed = 0
        failed_urls_fixed = 0  # FIX: Initialize outside while loop
        
        # Initialize bulk_task with fix task info
        urls_list = await worker_instance.fetch_pending_urls(limit=10000)
        total_urls = len(urls_list)
        worker_instance.bulk_task = {
            'task_id': task_id,
            'task_type': 'fixing',
            'status': 'running',
            'total_urls': total_urls,
            'processed_urls': 0,
            'failed_urls': 0,
            'fixed_urls': 0,
            'percentage': 0.0,
            'started_at': datetime.utcnow().isoformat(),
        }
        
        # Optimization: Pagination for fetching URLs
        batch_size = 1000
        offset = 0
        three_minutes_ago = datetime.utcnow() - timedelta(minutes=3)
        urls_checked = 0  # Track URLs checked so far
        
        while True:
            # Check for stop signal
            if worker_instance.bulk_task.get('stop_requested'):
                logger.info("Stop requested, breaking fix loop")
                break
            
            # Fetch URL batch
            response = await (
                worker_instance.supabase
                .table('url_queue')
                .select('*')
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            
            url_batch = response.data if response.data else []
            
            # No more results? Stop
            if not url_batch:
                break
            
            # Process batch for stuck URLs
            for url_entry in url_batch:
                urls_checked += 1  # Track URLs checked
                if url_entry.get('status') == 'processing':
                    updated_at = url_entry.get('updated_at')
                    if updated_at:
                        try:
                            updated_time = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
                            if updated_time < three_minutes_ago:
                                # Reset to pending, clear error, reset attempts to 0
                                await worker_instance.supabase.table('url_queue').update({
                                    'status': 'pending',
                                    'error_message': None,
                                    'attempts': 0,
                                    'updated_at': datetime.utcnow().isoformat(),
                                }).eq('id', url_entry['id']).execute()
                                stuck_urls_fixed += 1
                                logger.info(f"Reset stuck URL: {url_entry['url']}")
                        except Exception as e:
                            logger.warning(f"Error processing stuck URL {url_entry['url']}: {e}")
            
            # Update progress after stuck URL batch
            worker_instance.bulk_task['processed_urls'] = urls_checked
            worker_instance.bulk_task['fixed_urls'] = stuck_urls_fixed
            if worker_instance.bulk_task['total_urls'] > 0:
                worker_instance.bulk_task['percentage'] = round((urls_checked / worker_instance.bulk_task['total_urls']) * 100, 2)
            
            offset += batch_size
        
        # Fetch all completed URLs for missing documents check
        offset = 0
        all_urls_with_docs = set()  # FIX: Initialize before use
        while True:
            # Check for stop signal
            if worker_instance.bulk_task.get('stop_requested'):
                logger.info("Stop requested, breaking missing-docs loop")
                break
            
            # Fetch completed URLs batch
            response = await (
                worker_instance.supabase
                .table('url_queue')
                .select('id', 'url')
                .eq('status', 'completed')
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            
            completed_batch = response.data if response.data else []
            
            # No more results? Stop
            if not completed_batch:
                break
            
            # Optimization: Batch document lookup with chunking
            urls_to_check = [u['url'] for u in completed_batch]
            batch_size = 100  # Safe limit for .in_()
            
            for i in range(0, len(urls_to_check), batch_size):
                # Check for stop signal before each doc lookup batch
                if worker_instance.bulk_task.get('stop_requested'):
                    logger.info("Stop requested, breaking missing-docs doc lookup loop")
                    break
                chunk = urls_to_check[i:i+batch_size]
                doc_response = await (
                    worker_instance.supabase
                    .table('documents')
                    .select('url')
                    .in_('url', chunk)
                    .execute()
                )
                
                # Accumulate URLs with documents across all batches
                all_urls_with_docs.update(d['url'] for d in doc_response.data)
            
            # Break if stop was requested during doc lookups
            if worker_instance.bulk_task.get('stop_requested'):
                break
            
            for url_entry in completed_batch:
                # Check for stop signal before each fix
                if worker_instance.bulk_task.get('stop_requested'):
                    logger.info("Stop requested, breaking missing-docs fix loop")
                    break
                urls_checked += 1  # Track URLs checked
                if url_entry['url'] not in all_urls_with_docs:
                    # No documents found, reset to pending
                    await worker_instance.supabase.table('url_queue').update({
                        'status': 'pending',
                        'error_message': 'Missing documents detected',
                        'attempts': 0,
                        'updated_at': datetime.utcnow().isoformat(),
                    }).eq('id', url_entry['id']).execute()
                    missing_docs_fixed += 1
                    logger.info(f"Reset missing-docs URL: {url_entry['url']}")
            
            # Break outer loop if stop was requested mid-batch
            if worker_instance.bulk_task.get('stop_requested'):
                break
            
            # Update progress after missing-docs batch
            worker_instance.bulk_task['processed_urls'] = urls_checked
            worker_instance.bulk_task['fixed_urls'] = stuck_urls_fixed + missing_docs_fixed
            if worker_instance.bulk_task['total_urls'] > 0:
                worker_instance.bulk_task['percentage'] = round((urls_checked / worker_instance.bulk_task['total_urls']) * 100, 2)
            
            offset += batch_size
        
        # Fix 3: Auto-fix failed URLs (user requested)
        offset = 0
        while True:
            # Check for stop signal
            if worker_instance.bulk_task.get('stop_requested'):
                logger.info("Stop requested, breaking failed-URLs loop")
                break
            
            # Fetch failed URLs batch
            response = await (
                worker_instance.supabase
                .table('url_queue')
                .select('*')
                .eq('status', 'failed')
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            
            failed_batch = response.data if response.data else []
            
            # No more results? Stop
            if not failed_batch:
                break
            
            # Process batch for failed URLs
            for url_entry in failed_batch:
                # Check for stop signal before processing each URL
                if worker_instance.bulk_task.get('stop_requested'):
                    logger.info("Stop requested, breaking failed-URLs loop mid-batch")
                    break
                
                urls_checked += 1  # Track URLs checked
                # Reset to pending, clear error, reset attempts
                await worker_instance.supabase.table('url_queue').update({
                    'status': 'pending',
                    'error_message': 'Auto-fixed by validate-fix',
                    'attempts': 0,
                    'updated_at': datetime.utcnow().isoformat(),
                }).eq('id', url_entry['id']).execute()
                failed_urls_fixed += 1
                logger.info(f"Auto-fixed failed URL: {url_entry['url']}")
            
            # Break outer loop if stop was requested mid-batch
            if worker_instance.bulk_task.get('stop_requested'):
                break
            
            # Update progress after failed-URLs batch
            worker_instance.bulk_task['processed_urls'] = urls_checked
            worker_instance.bulk_task['fixed_urls'] = stuck_urls_fixed + missing_docs_fixed + failed_urls_fixed
            if worker_instance.bulk_task['total_urls'] > 0:
                worker_instance.bulk_task['percentage'] = round((urls_checked / worker_instance.bulk_task['total_urls']) * 100, 2)
            
            offset += batch_size
        
        # Mark task as completed
        worker_instance.bulk_task['status'] = 'completed'
        worker_instance.bulk_task['stopped_at'] = datetime.utcnow().isoformat()
        total_fixed = stuck_urls_fixed + missing_docs_fixed + failed_urls_fixed
        logger.info(f"Fix task {task_id} completed: {stuck_urls_fixed} stuck, {missing_docs_fixed} missing-docs, {failed_urls_fixed} failed, total: {total_fixed}")
        
    except Exception as e:
        logger.error(f"Background fix error: {e}")
        # Mark task as error
        worker_instance.bulk_task['status'] = 'error'
        worker_instance.bulk_task['stopped_at'] = datetime.utcnow().isoformat()


# Create app instance for uvicorn
app_instance = app
