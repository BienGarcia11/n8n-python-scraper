import asyncio
import gc
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import httpx
from playwright.async_api import async_playwright
import html2text
import trafilatura

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
semaphore = asyncio.Semaphore(5)  # Max concurrent requests
request_count = 0  # Track total requests for periodic cleanup
BROWSER_RESTART_INTERVAL = 50  # Restart browser every 50 requests


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
        print("Browser context ready (warm)")
    
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
            "POST /scrape": "Scrape URLs",
            "GET /health": "Health check"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
