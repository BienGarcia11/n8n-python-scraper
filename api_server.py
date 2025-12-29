import asyncio
import gc
import os
import traceback
import uuid
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
from playwright.async_api import async_playwright
import html2text
import trafilatura
from supabase import create_client
from openai import OpenAI

# v2 - fix for 10000 URL limit
app = FastAPI(title="Web Scraper API", version="1.0.0")


class ScrapeRequest(BaseModel):
    urls: List[str]
    callback_url: Optional[str] = None


class ScrapeResult(BaseModel):
    url: str
    title: Optional[str]
    content: Optional[str]
    status: str
    error: Optional[str] = None
    attempts: Optional[int] = None  # Number of retry attempts


class ScrapeResponse(BaseModel):
    results: List[ScrapeResult]
    total_urls: int
    successful: int
    failed: int


def extract_content(html_content):
    """Extract main content using trafilatura, fallback to html2text"""
    
    # Try trafilatura first - it handles most sites well
    extracted = trafilatura.extract(
        html_content,
        include_links=True,
        include_formatting=True,
        include_tables=True,
        no_fallback=False,
    )
    
    # If trafilatura extracted meaningful content, use it
    if extracted and len(extracted.strip()) > 200:
        return extracted
    
    # Fallback to html2text for pages trafilatura can't parse
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0  # Don't wrap lines
    
    fallback_content = h.handle(html_content)
    
    # Basic cleanup for fallback
    lines = fallback_content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip common junk patterns
        if stripped and not any([
            stripped.startswith('Skip to'),
            stripped.startswith('Cookie'),
            stripped.startswith('Accept all'),
            'privacy policy' in stripped.lower(),
            'terms of service' in stripped.lower(),
            len(stripped) < 3,
        ]):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


async def scrape_single_url(context, url, semaphore, max_retries=3):
    """Scrape a single URL with concurrency control and retry logic"""
    global request_count
    
    url = url.strip()
    if not url:
        return None
    
    request_count += 1  # Track requests for periodic cleanup
    
    # Retry logic
    last_error = None
    for attempt in range(max_retries):
        async with semaphore:
            page = await context.new_page()
            try:
                print(f"Scraping: {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                
                # Get fully rendered HTML (after JS execution) with timeout
                html_content = await asyncio.wait_for(page.content(), timeout=30000)
                title = await asyncio.wait_for(page.title(), timeout=5000)
                
                # Extract main content using trafilatura
                content = extract_content(html_content)
                
                # Validate we got actual content (not just junk)
                if not content or len(content.strip()) < 50:
                    raise ValueError("Extracted content too short (< 50 chars)")
                
                # Log content size for debugging
                original_size = len(html_content)
                extracted_size = len(content) if content else 0
                print(f"  ✓ Success: {original_size:,} chars -> {extracted_size:,} chars")
                
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "status": "success",
                    "attempts": attempt + 1
                }
            except asyncio.TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                print(f"  ⏱️ Timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
            except ValueError as e:
                last_error = f"Validation: {str(e)}"
                print(f"  ❌ Validation failed on attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
            except Exception as e:
                last_error = str(e)
                print(f"  ❌ Error on attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
            finally:
                try:
                    await page.close()
                except Exception as e:
                    print(f"Warning: Failed to close page - {e}")
    
    # All retries failed
    print(f"  ❌ FAILED after {max_retries} attempts: {url}")
    return {
        "url": url,
        "title": None,
        "content": None,
        "status": "error",
        "error": last_error,
        "attempts": max_retries
    }


# Global browser context (keep warm)
browser_context = None
browser = None  # Keep track of browser instance
semaphore = asyncio.Semaphore(2)  # Max concurrent requests (reduced from 5 to save memory)
request_count = 0  # Track total requests for periodic cleanup
BROWSER_RESTART_INTERVAL = 50  # Restart browser every 50 requests

# Bulk scraper control
bulk_task = None  # Track current bulk scrape task
bulk_status = {
    "running": False,
    "task_id": None,
    "started_at": None,
    "total_urls": 0,
    "processed": 0,
    "failed": 0,
    "cancelled": False
}
# Load configurable settings from environment variables
MAX_BULK_URLS = int(os.getenv("MAX_BULK_URLS", "100"))  # Safety limit: maximum URLs per bulk scrape
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")  # OpenAI embedding model


async def restart_browser():
    """Restart browser to clear memory leaks"""
    global browser_context, browser
    
    print("🔄 Restarting browser to clear memory...")
    
    # Close old context and browser
    if browser_context:
        try:
            await browser_context.close()
            print("✓ Old browser context closed")
        except Exception as e:
            print(f"Warning: Failed to close browser context - {e}")
    
    if browser:
        try:
            await browser.close()
            print("✓ Old browser closed")
        except Exception as e:
            print(f"Warning: Failed to close browser - {e}")
    
    # Force garbage collection to free memory
    gc.collect()
    print("✓ Garbage collection completed")
    
    # Start new browser
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        channel="chrome",
        args=[
            '--disable-dev-shm-usage',
            '--disable-setuid-sandbox',
            '--no-sandbox'
        ]
    )
    browser_context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    print("✓ New browser context ready")


async def get_browser_context():
    """Get or create browser context with periodic restarts"""
    global browser_context, request_count
    
    # Check if browser needs restart
    if request_count >= BROWSER_RESTART_INTERVAL:
        print(f"🔄 Request count {request_count}, triggering browser restart...")
        await restart_browser()
        request_count = 0
        return browser_context
    
    if browser_context is None:
        print("Initializing browser context (cold start)...")
        try:
            p = await async_playwright().start()
            browser = await p.chromium.launch(
                headless=True,
                channel="chrome",
                args=[
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                    '--no-sandbox',
                    '--disable-gpu',
                    '--no-zygote',
                    '--single-process'  # Single process to reduce memory usage
                ]
            )
            browser_context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            print("Browser context ready (warm)")
        except Exception as e:
            print(f"❌ CRITICAL: Browser launch failed - {e}")
            # Try fallback without Chrome args
            try:
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True)
                browser_context = await browser.new_context()
                print("Browser context ready (fallback mode)")
            except Exception as fallback_error:
                print(f"❌ FATAL: Browser launch failed completely - {fallback_error}")
                raise RuntimeError(f"Cannot initialize browser: {fallback_error}")
    
    return browser_context


@app.on_event("startup")
async def startup_event():
    """Initialize browser on startup to keep warm"""
    await get_browser_context()
    print("🚀 Scraper API is ready (browser warm)")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global browser_context, browser
    print("🛑 Shutting down scraper...")
    
    # Close browser context
    if browser_context:
        try:
            await browser_context.close()
            print("✓ Browser context closed")
        except Exception as e:
            print(f"Warning: Failed to close browser context - {e}")
    
    # Close browser
    if browser:
        try:
            await browser.close()
            print("✓ Browser closed")
        except Exception as e:
            print(f"Warning: Failed to close browser - {e}")
    
    # Force final garbage collection
    gc.collect()
    print("✓ Final garbage collection completed")
    print("✓ Shutdown complete")


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_urls(request: ScrapeRequest):
    """
    Scrape multiple URLs concurrently with retry logic
    
    - **urls**: List of URLs to scrape (max 100)
    - **callback_url**: Optional URL to send results to (async)
    
    **Features:**
    - Automatic retry (3 attempts) for failed URLs
    - Exponential backoff on timeouts
    - Content validation (minimum 50 chars)
    - Detailed attempt logging
    """
    
    if len(request.urls) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 URLs allowed per request")
    
    if not request.urls:
        raise HTTPException(status_code=400, detail="At least one URL is required")
    
    print(f"\n🚀 Starting batch of {len(request.urls)} URLs...")
    print(f"   Concurrency limit: {semaphore._value} (max 5 parallel)")
    
    context = await get_browser_context()
    tasks = [scrape_single_url(context, url, semaphore) for url in request.urls]
    results = await asyncio.gather(*tasks)
    
    # Filter out None results
    results = [r for r in results if r is not None]
    
    successful = len([r for r in results if r["status"] == "success"])
    failed = len(results) - successful
    
    # Calculate total content
    total_content = sum(len(r.get("content", "") or "") for r in results)
    
    print(f"\n📊 Batch Summary:")
    print(f"   Total URLs: {len(request.urls)}")
    print(f"   ✓ Success: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   Content size: {total_content:,} characters")
    
    # Log failed URLs for retry tracking
    failed_urls = [r["url"] for r in results if r["status"] == "error"]
    if failed_urls:
        print(f"\n⚠️ Failed URLs (will be retried):")
        for url in failed_urls:
            error_info = next(r["error"] for r in results if r["url"] == url)
            print(f"   - {url}")
            print(f"     Error: {error_info}")
    
    # Send callback if provided (async, awaited)
    if request.callback_url:
        print(f"\n📤 Sending results to callback: {request.callback_url}")
        try:
            await send_callback(request.callback_url, results)
            print("✅ Callback completed successfully")
        except Exception as e:
            print(f"❌ Callback failed: {e}")
            raise
    
    return ScrapeResponse(
        results=results,
        total_urls=len(request.urls),
        successful=successful,
        failed=failed
    )


async def send_callback(callback_url: str, results: list):
    """Send results to callback URL asynchronously using httpx"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            print(f"POST to callback: {callback_url}")
            response = await client.post(
                callback_url,
                json={"results": results},
                headers={"Content-Type": "application/json"}
            )
            print(f"✅ Callback sent successfully: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return response
        except httpx.TimeoutException as e:
            print(f"❌ Callback timeout: {e}")
            raise
        except httpx.HTTPStatusError as e:
            print(f"❌ Callback HTTP error: {e.response.status_code}")
            print(f"   Response: {e.response.text[:500]}")
            raise
        except Exception as e:
            print(f"❌ Callback failed: {e}")
            raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    global browser_context, request_count
    return {
        "status": "healthy",
        "browser_warm": browser_context is not None,
        "request_count": request_count,
        "restarts_pending": request_count >= BROWSER_RESTART_INTERVAL
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Web Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "POST /scrape": "Scrape URLs (batch)",
            "POST /scrape/bulk": "Scrape all pending URLs (bulk)",
            "GET /scrape/bulk/status": "Check bulk scrape progress",
            "POST /scrape/bulk/stop": "Stop running bulk scrape",
            "POST /scrape/bulk/reset": "Reset URL statuses for re-scraping",
            "GET /health": "Health check"
        },
        "safety_limits": {
            "max_bulk_urls": MAX_BULK_URLS,
            "max_concurrent": 2,
            "batch_size": 3
        }
    }


@app.post("/scrape/bulk")
async def scrape_bulk_urls():
    """
    Trigger bulk scraping of all pending URLs from database
    
    This endpoint:
    1. Fetches all pending URLs from Supabase
    2. Scrapes them in batches with retry logic
    3. Imports content with embeddings to documents table
    4. Updates URL statuses to completed
    
    Runs asynchronously and returns immediately with a task ID.
    
    **Safety Controls:**
    - Maximum 100 URLs per run (configurable)
    - Check current status before starting
    - Can be stopped via POST /scrape/bulk/stop
    
    Returns:
    - task_id: Unique identifier for this bulk job
    - pending_count: Number of URLs to scrape
    - status: "started" | "running" | "completed"
    """
    
    global bulk_status, bulk_task
    
    # Check if already running
    if bulk_status["running"]:
        return {
            "status": "already_running",
            "task_id": bulk_status["task_id"],
            "message": "Bulk scraper is already running. Use GET /scrape/bulk/status to check progress.",
            "stop_command": "POST /scrape/bulk/stop to cancel"
        }
    
    # Environment variables
    supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not supabase_key:
        raise HTTPException(status_code=500, detail="SUPABASE_KEY not configured")
    
    # Connect to Supabase
    client = create_client(supabase_url, supabase_key)
    
    # Fetch pending URLs (with safety limit)
    # Supabase limits .limit() to 1000, so we need to fetch in batches
    pending_urls = []
    batch_size = 1000
    offset = 0
    while len(pending_urls) < MAX_BULK_URLS:
        result = client.table("url_queue").select("*").eq("status", "pending").range(offset, offset + batch_size - 1).execute()
        batch = result.data if result.data else []
        if not batch:
            break
        pending_urls.extend(batch)
        offset += batch_size
        # Safety check: don't exceed MAX_BULK_URLS
        if len(pending_urls) >= MAX_BULK_URLS:
            pending_urls = pending_urls[:MAX_BULK_URLS]
            break
    
    if not pending_urls:
        return {
            "task_id": str(uuid.uuid4()),
            "status": "completed",
            "pending_count": 0,
            "message": "No pending URLs to scrape"
        }
    
    task_id = str(uuid.uuid4())
    pending_count = len(pending_urls)
    
    # Update bulk status
    bulk_status.update({
        "running": True,
        "task_id": task_id,
        "started_at": datetime.utcnow().isoformat(),
        "total_urls": pending_count,
        "processed": 0,
        "failed": 0,
        "cancelled": False
    })
    
    # Create background task closure
    async def run_bulk_task():
        nonlocal client, openai_key
        context = await get_browser_context()
        batch_size = 3
        urls = [u["url"] for u in pending_urls]
        batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]
        total_successful = 0
        total_failed = 0
        
        print(f"\n{'='*60}")
        print(f"BULK SCRAPE TASK: {task_id}")
        print(f"Pending URLs: {pending_count}")
        print(f"Safety limit: {MAX_BULK_URLS} URLs per run")
        
        for batch_num, batch in enumerate(batches, 1):
            # Check if cancelled
            if bulk_status["cancelled"]:
                print(f"\n⛔ BULK SCRAPE CANCELLED by user")
                print(f"Processed: {total_successful}/{pending_count} URLs")
                break
            
            print(f"\nBATCH {batch_num}/{len(batches)}: {len(batch)} URLs")
            
            # Mark as processing
            for url in batch:
                try:
                    client.table("url_queue").update({"status": "processing"}).eq("url", url).execute()
                except Exception as e:
                    print(f"  ⚠️  Failed to mark {url} as processing: {e}")
            
            # Scrape batch
            tasks = [scrape_single_url(context, url, semaphore) for url in batch]
            results = await asyncio.gather(*tasks)
            
            # Process results
            for result in results:
                if not result:
                    continue
                
                url = result["url"]
                
                if result["status"] == "success":
                    try:
                        # Generate embedding
                        content = result["content"]
                        embedding = None
                        
                        if openai_key:
                            try:
                                openai_client = OpenAI(api_key=openai_key)
                                response = openai_client.embeddings.create(
                                    model=EMBEDDING_MODEL,
                                    input=content[:8191]
                                )
                                embedding = response.data[0].embedding
                            except Exception as e:
                                print(f"  ⚠️  Embedding failed: {e}")
                        
                        # Insert or update document (upsert - prevents duplicates)
                        insert_data = {
                            "content": content,
                            "source": url,  # Separate column for uniqueness constraint
                            "metadata": {
                                "source": url,
                                "source_type": "web_scrape",
                                "title": result["title"],
                                "scraped_at": datetime.utcnow().isoformat(),
                                "updated_at": datetime.utcnow().isoformat()  # Track updates
                            }
                        }
                        
                        if embedding:
                            insert_data["embedding"] = embedding
                        else:
                            insert_data["metadata"]["no_embedding"] = True
                        
                        # Use upsert to update existing documents instead of creating duplicates
                        client.table("documents").upsert(insert_data, on_conflict="source").execute()
                        
                        # Mark as completed (status only, content is in documents table)
                        client.table("url_queue").update({
                            "status": "completed"
                        }).eq("url", url).execute()
                        
                        total_successful += 1
                        bulk_status["processed"] += 1
                        print(f"  ✓ {url[:50]}...")
                        
                    except Exception as e:
                        print(f"  ❌ Failed to process {url}: {e}")
                        total_failed += 1
                        bulk_status["failed"] += 1
                        client.table("url_queue").update({"status": "failed"}).eq("url", url).execute()
                else:
                    # Mark as failed
                    total_failed += 1
                    bulk_status["failed"] += 1
                    client.table("url_queue").update({"status": "failed"}).eq("url", url).execute()
                    print(f"  ❌ {url[:50]}... - {result.get('error', 'Unknown error')}")
            
            print(f"Batch {batch_num} complete: {sum(1 for r in results if r and r['status'] == 'success')} success")
        
        # Reset status after completion
        if not bulk_status["cancelled"]:
            print(f"\n{'='*60}")
            print(f"BULK SCRAPE COMPLETE: {task_id}")
            print(f"Total: {pending_count}")
            print(f"Success: {total_successful}")
            print(f"Failed: {total_failed}")
            print(f"Success rate: {total_successful/pending_count*100:.1f}%")
        
        bulk_status["running"] = False
        bulk_status["task_id"] = None
    
    # Run background task
    bulk_task = asyncio.create_task(run_bulk_task())
    
    return {
        "task_id": task_id,
        "status": "started",
        "pending_count": pending_count,
        "message": f"Started bulk scraping {pending_count} URLs",
        "safety_limit": f"Max {MAX_BULK_URLS} URLs per run",
        "note": "This task runs asynchronously. Check Railway logs for progress."
    }


@app.get("/scrape/bulk/status")
async def bulk_status_check():
    """
    Get current bulk scraping status
    
    Returns:
    - running: True/False if bulk scraper is active
    - task_id: Current task ID
    - started_at: When task started
    - total_urls: Total URLs to process
    - processed: URLs processed so far
    - failed: URLs failed so far
    - progress: Percentage complete
    - cancelled: If task was cancelled
    """
    if not bulk_status["running"]:
        return {
            "running": False,
            "message": "No bulk scrape task is currently running",
            "start_command": "POST /scrape/bulk to start"
        }
    
    # Calculate progress
    progress = (bulk_status["processed"] + bulk_status["failed"]) / bulk_status["total_urls"] * 100 if bulk_status["total_urls"] > 0 else 0
    
    return {
        "running": True,
        "task_id": bulk_status["task_id"],
        "started_at": bulk_status["started_at"],
        "total_urls": bulk_status["total_urls"],
        "processed": bulk_status["processed"],
        "failed": bulk_status["failed"],
        "progress": round(progress, 1),
        "cancelled": bulk_status["cancelled"],
        "stop_command": "POST /scrape/bulk/stop to cancel"
    }


@app.post("/scrape/bulk/reset")
async def reset_bulk_urls(request: Optional[dict] = None):
    """
    Reset URL statuses to allow re-scraping
    
    This endpoint allows flexible URL status resets for maintenance.
    
    **Options:**
    - reset_all: true/false - Reset ALL URLs to pending
    - status: "completed"/"failed"/"processing" - Reset specific status  
    - days_threshold: Number of days (reset URLs older than this)
    
    **Examples:**
    ```json
    // Reset all URLs older than 14 days
    {"reset_all": false, "days_threshold": 14}
    
    // Reset all "completed" URLs
    {"reset_all": false, "status": "completed"}
    
    // Reset ALL URLs regardless of age or status
    {"reset_all": true}
    ```
    
    Returns:
    - reset_count: Number of URLs reset
    - details: Which statuses were affected
    """
    
    supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_key:
        raise HTTPException(status_code=500, detail="SUPABASE_KEY not configured")
    
    # Parse request body
    body = request if request else {}
    reset_all = body.get("reset_all", False)
    status = body.get("status")
    days_threshold = body.get("days_threshold")
    
    client = create_client(supabase_url, supabase_key)
    
    if reset_all:
        # Reset ALL URLs to pending
        result = client.table("url_queue").update({"status": "pending"}).execute()
        reset_count = len(result.data) if result.data else 0
        return {
            "status": "success",
            "reset_count": reset_count,
            "action": "reset_all",
            "message": f"Reset {reset_count} URLs to pending status"
        }
    
    elif status:
        # Reset specific status (completed/failed/processing)
        if status not in ["completed", "failed", "processing"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid status '{status}'. Must be 'completed', 'failed', or 'processing'"
            )
        
        result = client.table("url_queue").update({"status": "pending"}).eq("status", status).execute()
        reset_count = len(result.data) if result.data else 0
        return {
            "status": "success",
            "reset_count": reset_count,
            "action": f"reset_status_{status}",
            "message": f"Reset {reset_count} URLs from {status} to pending"
        }
    
    elif days_threshold:
        # Reset URLs older than X days (by inserted_at or updated_at)
        try:
            result = client.table("url_queue").update({"status": "pending"}).lt("updated_at", datetime.utcnow() - timedelta(days=days_threshold)).execute()
            reset_count = len(result.data) if result.data else 0
            return {
                "status": "success",
                "reset_count": reset_count,
                "action": f"reset_older_than_{days_threshold}_days",
                "message": f"Reset {reset_count} URLs older than {days_threshold} days to pending"
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, 
                detail=f"Failed to reset by age: {str(e)}"
            )
    
    else:
        raise HTTPException(
            status_code=400,
            detail="Must specify one of: reset_all, status, or days_threshold"
        )


@app.post("/scrape/bulk/stop")
async def stop_bulk_scrape():
    """
    Stop currently running bulk scrape task
    
    This will:
    1. Mark current task as cancelled
    2. Stop processing after current batch completes
    3. URLs marked as 'processing' will stay in that state
    4. Return summary of what was processed
    
    Returns:
    - status: "stopped" or "not_running"
    - task_id: Task that was stopped
    - summary: What was processed before stop
    """
    global bulk_status, bulk_task
    
    if not bulk_status["running"]:
        return {
            "status": "not_running",
            "message": "No bulk scrape task is currently running"
        }
    
    # Mark as cancelled
    bulk_status["cancelled"] = True
    
    # Get summary before reset
    task_id = bulk_status["task_id"]
    summary = {
        "task_id": task_id,
        "total_urls": bulk_status["total_urls"],
        "processed": bulk_status["processed"],
        "failed": bulk_status["failed"],
        "progress": round((bulk_status["processed"] + bulk_status["failed"]) / bulk_status["total_urls"] * 100, 1) if bulk_status["total_urls"] > 0 else 0
    }
    
    # Wait for task to finish gracefully (up to 5 seconds)
    try:
        await asyncio.wait_for(bulk_task, timeout=5.0)
    except asyncio.TimeoutError:
        print(f"⚠️ Task stop timeout - force cancelling")
    
    return {
        "status": "stopped",
        "message": "Bulk scraper stopped after current batch completes",
        "summary": summary,
        "note": "URLs in 'processing' status will remain and can be retried"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
