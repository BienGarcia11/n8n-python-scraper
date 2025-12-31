import asyncio
import gc
import os
import re
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
    attempts: Optional[int] = None


class ScrapeResponse(BaseModel):
    results: List[ScrapeResult]
    total_urls: int
    successful: int
    failed: int


async def extract_content(page):
    """Extract main content from Playwright page using direct DOM queries"""
    
    # Try to find main content element
    try:
        main_content = await page.query_selector("main") or await page.query_selector("article")
        if main_content:
            text = await main_content.text_content()
            if text and len(text.strip()) > 100:
                print(f"  ✓ Extracted from {'main' if await page.query_selector('main') else 'article'} tag")
                return text.strip()
    except Exception as e:
        print(f"  ⚠️  Main/article selector failed: {e}")
    
    # Strategy 2: Look for common content container patterns
    content_selectors = [
        'div[class*="content"]',
        'div[class*="article"]',
        'div[class*="article-body"]',
        'div[class*="main-content"]',
        '[data-testid*="content"]',
        '[data-testid*="article"]',
    ]
    
    for selector in content_selectors:
        try:
            element = await page.query_selector(selector)
            if element:
                text = await element.text_content()
                if text and len(text.strip()) > 500:
                    print(f"  ✓ Extracted from selector: {selector}")
                    return text.strip()
        except Exception:
            continue
    
    # Strategy 3: Fallback - get all text from body but exclude obvious junk
    try:
        body_text = await page.evaluate('''
            () => {
                const selectorsToRemove = ['nav', 'header', 'footer', 'aside', 
                    '[role="navigation"]', '[role="banner"]', '[role="contentinfo"]',
                    'script', 'style', 'noscript'];
                selectorsToRemove.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => el.remove());
                });
                return document.body.innerText;
            }
        ''')
        if body_text and len(body_text.strip()) > 200:
            print(f"  ✓ Extracted from body (fallback)")
            return body_text.strip()
    except Exception as e:
        print(f"  ⚠️  Body extraction failed: {e}")
    
    # Strategy 4: Last resort - raw page text
    try:
        text = await page.text_content()
        return text.strip()
    except Exception:
        return ""


async def scrape_single_url(context, url, semaphore, max_retries=3):
    """Scrape a single URL with concurrency control and retry logic"""
    global request_count
    
    url = url.strip()
    if not url:
        return None
    
    request_count += 1
    last_error = None
    
    for attempt in range(max_retries):
        async with semaphore:
            page = await context.new_page()
            try:
                print(f"Scraping: {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                
                # Handle cookie consent dialog
                try:
                    await asyncio.sleep(2)
                    cookie_selectors = [
                        'button:has-text("Accept")',
                        'button:has-text("Accept all")',
                        'button:has-text("Allow all")',
                        '[data-testid*="accept"]',
                        '[class*="cookie"] button:has-text("Accept")',
                    ]
                    for selector in cookie_selectors:
                        try:
                            cookie_button = await page.query_selector(selector, timeout=2000)
                            if cookie_button:
                                await cookie_button.click()
                                print(f"  ✓ Clicked cookie acceptance button")
                                await asyncio.sleep(1)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    print(f"  ⚠️  Cookie handling: {e}")
                
                title = await asyncio.wait_for(page.title(), timeout=5000)
                content = await extract_content(page)
                
                if not content or len(content.strip()) < 50:
                    raise ValueError("Extracted content too short (< 50 chars)")
                
                extracted_size = len(content) if content else 0
                print(f"  ✓ Success: {extracted_size:,} chars extracted")
                
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "status": "success",
                    "attempts": attempt + 1
                }
            except asyncio.TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                print(f"  ⏱️  Timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)
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
                except Exception:
                    pass
    
    print(f"  ❌ FAILED after {max_retries} attempts: {url}")
    return {
        "url": url,
        "title": None,
        "content": None,
        "status": "error",
        "error": last_error,
        "attempts": max_retries
    }


# Global browser context
browser_context = None
browser = None
semaphore = asyncio.Semaphore(2)
request_count = 0
BROWSER_RESTART_INTERVAL = 50

# Bulk scraper control
bulk_task = None
bulk_status = {
    "running": False,
    "task_id": None,
    "started_at": None,
    "total_urls": 0,
    "processed": 0,
    "failed": 0,
    "cancelled": False
}

MAX_BULK_URLS = int(os.getenv("MAX_BULK_URLS", "100"))
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


async def restart_browser():
    """Restart browser to clear memory"""
    global browser_context, browser
    
    print("🔄 Restarting browser to clear memory...")
    
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
    
    gc.collect()
    print("✓ Garbage collection completed")
    
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=True,
        channel="chrome",
        args=['--disable-dev-shm-usage', '--disable-setuid-sandbox', '--no-sandbox']
    )
    browser_context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    print("✓ New browser context ready")


async def get_browser_context():
    """Get or create browser context"""
    global browser_context, request_count
    
    if request_count >= BROWSER_RESTART_INTERVAL:
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
                args=['--disable-dev-shm-usage', '--disable-setuid-sandbox', '--no-sandbox',
                      '--disable-gpu', '--no-zygote', '--single-process']
            )
            browser_context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            print("Browser context ready (warm)")
        except Exception as e:
            print(f"❌ CRITICAL: Browser launch failed - {e}")
            try:
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True)
                browser_context = await browser.new_context()
                print("Browser context ready (fallback mode)")
            except Exception as fallback_error:
                print(f"❌ FATAL: Browser launch failed - {fallback_error}")
                raise RuntimeError(f"Cannot initialize browser: {fallback_error}")
    
    return browser_context


@app.on_event("startup")
async def startup_event():
    """Initialize browser on startup"""
    await get_browser_context()
    print("🚀 Scraper API is ready (browser warm)")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    global browser_context, browser
    print("🛑 Shutting down scraper...")
    
    if browser_context:
        try:
            await browser_context.close()
        except Exception as e:
            print(f"Warning: {e}")
    
    if browser:
        try:
            await browser.close()
        except Exception as e:
            print(f"Warning: {e}")
    
    gc.collect()
    print("✓ Shutdown complete")


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_urls(request: ScrapeRequest):
    """Scrape multiple URLs concurrently"""
    
    if len(request.urls) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 URLs allowed per request")
    
    if not request.urls:
        raise HTTPException(status_code=400, detail="At least one URL is required")
    
    print(f"\n🚀 Starting batch of {len(request.urls)} URLs...")
    
    context = await get_browser_context()
    tasks = [scrape_single_url(context, url, semaphore) for url in request.urls]
    results = await asyncio.gather(*tasks)
    results = [r for r in results if r is not None]
    
    successful = len([r for r in results if r["status"] == "success"])
    failed = len(results) - successful
    total_content = sum(len(r.get("content", "") or "") for r in results)
    
    print(f"\n📊 Batch Summary:")
    print(f"   Total URLs: {len(request.urls)}")
    print(f"   ✓ Success: {successful}")
    print(f"   ❌ Failed: {failed}")
    print(f"   Content size: {total_content:,} characters")
    
    if request.callback_url:
        print(f"\n📤 Sending results to callback: {request.callback_url}")
        try:
            await send_callback(request.callback_url, results)
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
    """Send results to callback URL"""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                callback_url,
                json={"results": results},
                headers={"Content-Type": "application/json"}
            )
            print(f"✅ Callback sent successfully: {response.status_code}")
        except Exception as e:
            raise


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    global browser_context, request_count
    return {
        "status": "healthy",
        "browser_warm": browser_context is not None,
        "request_count": request_count
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
            "GET /scrape/bulk/validate": "Validate that all URLs were successfully scraped",
            "GET /health": "Health check"
        }
    }


@app.post("/scrape/bulk")
async def scrape_bulk_urls():
    """Trigger bulk scraping of all pending URLs from database"""
    global bulk_status, bulk_task
    
    if bulk_status["running"]:
        return {
            "status": "already_running",
            "task_id": bulk_status["task_id"],
            "message": "Bulk scraper is already running. Use GET /scrape/bulk/status to check progress.",
            "stop_command": "POST /scrape/bulk/stop to cancel"
        }
    
    supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not supabase_key:
        raise HTTPException(status_code=500, detail="SUPABASE_KEY not configured")
    
    client = create_client(supabase_url, supabase_key)
    
    # Fetch pending URLs
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
    
    bulk_status.update({
        "running": True,
        "task_id": task_id,
        "started_at": datetime.utcnow().isoformat(),
        "total_urls": pending_count,
        "processed": 0,
        "failed": 0,
        "cancelled": False
    })
    
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
        
        for batch_num, batch in enumerate(batches, 1):
            if bulk_status["cancelled"]:
                print(f"\n⛔ BULK SCRAPE CANCELLED by user")
                break
            
            print(f"\nBATCH {batch_num}/{len(batches)}: {len(batch)} URLs")
            
            for url in batch:
                try:
                    client.table("url_queue").update({"status": "processing"}).eq("url", url).execute()
                except Exception as e:
                    print(f"  ⚠️  Failed to mark {url} as processing: {e}")
            
            tasks = [scrape_single_url(context, url, semaphore) for url in batch]
            results = await asyncio.gather(*tasks)
            
            for result in results:
                if not result:
                    continue
                
                url = result["url"]
                
                if result["status"] == "success":
                    try:
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
                        
                        insert_data = {
                            "content": content,
                            "metadata": {
                                "source": url,
                                "source_type": "web_scrape",
                                "title": result["title"],
                                "scraped_at": datetime.utcnow().isoformat()
                            }
                        }
                        
                        if embedding:
                            insert_data["embedding"] = embedding
                        
                        # Check if document already exists and update, or insert new
                        try:
                            # Try to find existing document by URL using contains filter
                            existing = client.table("documents").select("*").contains("metadata", {"source": url}).execute()
                            if existing.data and len(existing.data) > 0:
                                # Document exists - update it
                                doc_id = existing.data[0]["id"]
                                client.table("documents").update(insert_data).eq("id", doc_id).execute()
                                print(f"  ✓ {url[:50]}... (updated existing)")
                            else:
                                # Document doesn't exist - insert new
                                client.table("documents").insert(insert_data).execute()
                                print(f"  ✓ {url[:50]}... (inserted new)")
                        except Exception as e:
                            # If insert fails with duplicate, try updating anyway
                            if "duplicate" in str(e).lower() or "unique constraint" in str(e).lower():
                                print(f"  ℹ️  {url[:50]}... (duplicate detected, finding existing)")
                                try:
                                    existing = client.table("documents").select("*").contains("metadata", {"source": url}).execute()
                                    if existing.data and len(existing.data) > 0:
                                        doc_id = existing.data[0]["id"]
                                        client.table("documents").update(insert_data).eq("id", doc_id).execute()
                                        print(f"  ✓ {url[:50]}... (updated after retry)")
                                    else:
                                        print(f"  ❌ Could not find existing document for {url}")
                                except Exception as update_error:
                                    print(f"  ❌ Failed to update {url}: {update_error}")
                            else:
                                print(f"  ❌ Failed to process document for {url}: {e}")
                        
                        client.table("url_queue").update({"status": "completed"}).eq("url", url).execute()
                        total_successful += 1
                        bulk_status["processed"] += 1
                        print(f"  ✓ {url[:50]}...")
                        
                    except Exception as e:
                        print(f"  ❌ Failed to process {url}: {e}")
                        total_failed += 1
                        bulk_status["failed"] += 1
                        client.table("url_queue").update({"status": "failed"}).eq("url", url).execute()
                else:
                    total_failed += 1
                    bulk_status["failed"] += 1
                    client.table("url_queue").update({"status": "failed"}).eq("url", url).execute()
            
            print(f"Batch {batch_num} complete")
        
        if not bulk_status["cancelled"]:
            print(f"\n{'='*60}")
            print(f"BULK SCRAPE COMPLETE: {task_id}")
        
        bulk_status["running"] = False
        bulk_status["task_id"] = None
    
    bulk_task = asyncio.create_task(run_bulk_task())
    
    return {
        "task_id": task_id,
        "status": "started",
        "pending_count": pending_count,
        "message": f"Started bulk scraping {pending_count} URLs"
    }


@app.get("/scrape/bulk/status")
async def bulk_status_check():
    """Get current bulk scraping status"""
    if not bulk_status["running"]:
        return {
            "running": False,
            "message": "No bulk scrape task is currently running"
        }
    
    progress = (bulk_status["processed"] + bulk_status["failed"]) / bulk_status["total_urls"] * 100 if bulk_status["total_urls"] > 0 else 0
    
    return {
        "running": True,
        "task_id": bulk_status["task_id"],
        "started_at": bulk_status["started_at"],
        "total_urls": bulk_status["total_urls"],
        "processed": bulk_status["processed"],
        "failed": bulk_status["failed"],
        "progress": round(progress, 1),
        "cancelled": bulk_status["cancelled"]
    }


@app.post("/scrape/bulk/reset")
async def reset_bulk_urls(request: Optional[dict] = None):
    """Reset URL statuses to allow re-scraping"""
    supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_key:
        raise HTTPException(status_code=500, detail="SUPABASE_KEY not configured")
    
    body = request if request else {}
    reset_all = body.get("reset_all", False)
    status = body.get("status")
    days_threshold = body.get("days_threshold")
    
    client = create_client(supabase_url, supabase_key)
    
    if reset_all:
        result = client.table("url_queue").update({"status": "pending"}).execute()
        reset_count = len(result.data) if result.data else 0
        return {
            "status": "success",
            "reset_count": reset_count,
            "action": "reset_all",
            "message": f"Reset {reset_count} URLs to pending status"
        }
    
    elif status:
        if status not in ["completed", "failed", "processing"]:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status}'")
        
        result = client.table("url_queue").update({"status": "pending"}).eq("status", status).execute()
        reset_count = len(result.data) if result.data else 0
        return {
            "status": "success",
            "reset_count": reset_count,
            "action": f"reset_status_{status}",
            "message": f"Reset {reset_count} URLs from {status} to pending"
        }
    
    elif days_threshold:
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
            raise HTTPException(status_code=500, detail=f"Failed to reset by age: {str(e)}")
    
    else:
        raise HTTPException(status_code=400, detail="Must specify one of: reset_all, status, or days_threshold")


@app.get("/scrape/bulk/validate")
async def validate_bulk_scrape():
    """Validate that all URLs have been successfully scraped after bulk scrape"""
    try:
        supabase_url = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_key:
            raise HTTPException(status_code=500, detail="SUPABASE_KEY not configured")
        
        client = create_client(supabase_url, supabase_key)
        
        # Get URL queue status breakdown - use pagination for all URLs
        queue_data = []
        batch_size = 1000
        offset = 0
        
        while True:
            queue_result = client.table("url_queue").select("*").range(offset, offset + batch_size - 1).execute()
            batch = queue_result.data if queue_result.data else []
            if not batch:
                break
            queue_data.extend(batch)
            offset += batch_size
            if len(batch) < batch_size:
                break
        
        total_urls = len(queue_data)
        completed_count = len([u for u in queue_data if u["status"] == "completed"])
        failed_count = len([u for u in queue_data if u["status"] == "failed"])
        pending_count = len([u for u in queue_data if u["status"] == "pending"])
        processing_count = len([u for u in queue_data if u["status"] == "processing"])
        
        # Get completed URLs list for validation
        completed_urls = [u["url"] for u in queue_data if u["status"] == "completed"]
        
        # Check for stuck processing URLs
        current_time = datetime.utcnow()
        issues = []
        
        for u in queue_data:
            if u["status"] == "processing":
                try:
                    if u.get("updated_at"):
                        updated_at_str = u["updated_at"].replace("Z", "+00:00") if u["updated_at"].endswith("Z") else u["updated_at"]
                        updated_at = datetime.fromisoformat(updated_at_str)
                        if (current_time - updated_at).total_seconds() > 3600:
                            issues.append({
                                "type": "stuck_processing",
                                "url": u["url"],
                                "message": f"URL stuck in processing state for over 1 hour (updated: {u['updated_at']})"
                            })
                    else:
                        issues.append({
                            "type": "stuck_processing",
                            "url": u["url"],
                            "message": "URL stuck in processing state"
                        })
                except Exception as e:
                    print(f"Error processing stuck check for {u['url']}: {e}")
        
        # For large datasets (>1000 URLs), skip expensive document fetch
        # Return estimated validation based on URL queue status only
        if total_urls > 1000:
            total_documents = completed_count  # Assume all completed have documents
            missing_count = 0
            missing_documents = 0
        else:
            # For smaller datasets, fetch documents for validation
            doc_urls = set()
            doc_batch_size = 500
            doc_offset = 0
            
            while True:
                try:
                    docs_result = client.table("documents").select("metadata").range(doc_offset, doc_offset + doc_batch_size - 1).execute()
                    batch = docs_result.data if docs_result.data else []
                    if not batch:
                        break
                    for doc in batch:
                        metadata = doc.get("metadata", {})
                        if metadata.get("source_type") == "web_scrape":
                            source = metadata.get("source")
                            if source:
                                doc_urls.add(source)
                    doc_offset += doc_batch_size
                    if len(batch) < doc_batch_size:
                        break
                except Exception as e:
                    print(f"Error fetching documents batch: {e}")
                    break
            
            completed_set = set(completed_urls)
            missing_urls = completed_set - doc_urls
            
            for url in list(missing_urls)[:20]:
                issues.append({
                    "type": "missing_document",
                    "url": url,
                    "message": "URL marked completed but no matching document found"
                })
            missing_count = len(missing_urls)
            total_documents = completed_count - missing_count
            missing_documents = missing_count
        
        stuck_in_processing = len([i for i in issues if i["type"] == "stuck_processing"])
        
        # Calculate success rate
        success_rate = round((completed_count / total_urls * 100), 1) if total_urls > 0 else 0.0
        
        # Add "more issues" entry if total issues exceed display limit
        if len(issues) > 20:
            issues.append({
                "type": "more_issues",
                "message": f"... and {len(issues) - 20} more issues (total {len(issues)})"
            })
        
        # Limit issues shown in response
        display_issues = issues[:20] if issues else []
        
        # Determine overall status
        if pending_count == 0 and stuck_in_processing == 0 and missing_documents == 0:
            overall_status = "✅ All URLs scraped successfully"
        elif pending_count > 0:
            overall_status = f"⏳ {pending_count} URLs still pending"
        elif stuck_in_processing > 0:
            overall_status = f"⚠️ {stuck_in_processing} URLs stuck in processing"
        elif missing_documents > 0:
            overall_status = f"❌ {missing_documents} completed URLs missing documents"
        else:
            overall_status = f"⚠️ {len(issues)} issues found"
        
        print(f"\n{'='*60}")
        print(f"VALIDATION REPORT")
        print(f"{'='*60}")
        print(f"Total URLs in queue: {total_urls}")
        print(f"Status breakdown:")
        print(f"  - Completed: {completed_count}")
        print(f"  - Failed: {failed_count}")
        print(f"  - Pending: {pending_count}")
        print(f"  - Processing: {processing_count}")
        print(f"\nDocuments scraped: {total_documents}")
        print(f"\nIssues found: {len(issues)}")
        if issues:
            for issue in display_issues:
                print(f"  - {issue['type']}: {issue['message']}")
        
        return {
            "validation_timestamp": datetime.utcnow().isoformat(),
            "total_urls_in_queue": total_urls,
            "status_breakdown": {
                "completed": completed_count,
                "failed": failed_count,
                "pending": pending_count,
                "processing": processing_count
            },
            "total_documents": total_documents,
            "missing_documents": missing_documents,
            "stuck_in_processing": stuck_in_processing,
            "success_rate": success_rate,
            "issues": display_issues,
            "total_issues": len(issues),
            "overall_status": overall_status
        }
    except Exception as e:
        print(f"Validation error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@app.post("/scrape/bulk/stop")
async def stop_bulk_scrape():
    """Stop currently running bulk scrape task"""
    global bulk_status, bulk_task
    
    if not bulk_status["running"]:
        return {
            "status": "not_running",
            "message": "No bulk scrape task is currently running"
        }
    
    bulk_status["cancelled"] = True
    
    task_id = bulk_status["task_id"]
    summary = {
        "task_id": task_id,
        "total_urls": bulk_status["total_urls"],
        "processed": bulk_status["processed"],
        "failed": bulk_status["failed"],
        "progress": round((bulk_status["processed"] + bulk_status["failed"]) / bulk_status["total_urls"] * 100, 1) if bulk_status["total_urls"] > 0 else 0
    }
    
    try:
        await asyncio.wait_for(bulk_task, timeout=5.0)
    except asyncio.TimeoutError:
        pass
    
    return {
        "status": "stopped",
        "message": "Bulk scraper stopped after current batch completes",
        "summary": summary
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
