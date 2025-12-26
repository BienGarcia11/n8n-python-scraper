import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import requests
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


async def scrape_single_url(context, url, semaphore):
    """Scrape a single URL with concurrency control"""
    async with semaphore:
        url = url.strip()
        if not url:
            return None
        
        page = await context.new_page()
        try:
            print(f"Scraping: {url}")
            await page.goto(url, timeout=30000, wait_until="networkidle")
            
            # Get fully rendered HTML (after JS execution)
            html_content = await page.content()
            title = await page.title()
            
            # Extract main content using trafilatura
            content = extract_content(html_content)
            
            # Log content size for debugging
            original_size = len(html_content)
            extracted_size = len(content) if content else 0
            print(f"  Content: {original_size:,} chars -> {extracted_size:,} chars")
            
            return {
                "url": url,
                "title": title,
                "content": content,
                "status": "success"
            }
        except Exception as e:
            print(f"Error: {url} - {e}")
            return {
                "url": url,
                "title": None,
                "content": None,
                "status": "error",
                "error": str(e)
            }
        finally:
            await page.close()


# Global browser context (keep warm)
browser_context = None
semaphore = asyncio.Semaphore(5)  # Max concurrent requests


async def get_browser_context():
    """Get or create browser context (keep warm)"""
    global browser_context
    
    if browser_context is None:
        print("Initializing browser context (cold start)...")
        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome"  # Use Chrome if available, otherwise Chromium
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
    global browser_context
    if browser_context:
        await browser_context.close()
        print("Browser context closed")


@app.post("/scrape", response_model=ScrapeResponse)
async def scrape_urls(request: ScrapeRequest):
    """
    Scrape multiple URLs concurrently
    
    - **urls**: List of URLs to scrape (max 100)
    - **callback_url**: Optional URL to send results to (async)
    """
    
    if len(request.urls) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 URLs allowed per request")
    
    if not request.urls:
        raise HTTPException(status_code=400, detail="At least one URL is required")
    
    print(f"Scraping {len(request.urls)} URLs...")
    
    context = await get_browser_context()
    tasks = [scrape_single_url(context, url, semaphore) for url in request.urls]
    results = await asyncio.gather(*tasks)
    
    # Filter out None results
    results = [r for r in results if r is not None]
    
    successful = len([r for r in results if r["status"] == "success"])
    failed = len(results) - successful
    
    print(f"Completed: {successful} success, {failed} failed")
    
    # Calculate total content
    total_content = sum(len(r.get("content", "") or "") for r in results)
    print(f"Total content size: {total_content:,} characters")
    
    # Send callback if provided (non-blocking)
    if request.callback_url:
        print(f"Sending results to callback: {request.callback_url}")
        try:
            asyncio.create_task(
                send_callback(request.callback_url, results)
            )
        except Exception as e:
            print(f"Callback failed to schedule: {e}")
    
    return ScrapeResponse(
        results=results,
        total_urls=len(request.urls),
        successful=successful,
        failed=failed
    )


async def send_callback(callback_url: str, results: list):
    """Send results to callback URL asynchronously"""
    try:
        response = requests.post(
            callback_url,
            json={"results": results},
            timeout=120
        )
        print(f"Callback response: {response.status_code}")
    except Exception as e:
        print(f"Callback failed: {e}")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    global browser_context
    return {
        "status": "healthy",
        "browser_warm": browser_context is not None
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
