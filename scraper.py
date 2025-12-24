import asyncio
import argparse
import requests
from playwright.async_api import async_playwright
import html2text
import trafilatura


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
            
            # Get the fully rendered HTML (after JS execution)
            html_content = await page.content()
            title = await page.title()
            
            # Extract main content using trafilatura
            content = extract_content(html_content)
            
            # Log content size for debugging
            original_size = len(html_content)
            extracted_size = len(content) if content else 0
            print(f"  Content: {original_size:,} chars -> {extracted_size:,} chars ({100-int(extracted_size/original_size*100) if original_size > 0 else 0}% reduction)")
            
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


async def scrape_urls_async(urls, max_concurrent=5):
    """Scrape multiple URLs concurrently"""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async with async_playwright() as p:
        # Use pre-installed Chrome on GitHub runners (no browser download needed)
        browser = await p.chromium.launch(headless=True, channel="chrome")
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        tasks = [scrape_single_url(context, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks)
        
        await browser.close()
    
    return [r for r in results if r is not None]


def main():
    parser = argparse.ArgumentParser(description="Async web scraper with Playwright")
    parser.add_argument("--url", required=True, help="Comma-separated URLs to scrape")
    parser.add_argument("--callback_url", required=False, help="n8n callback URL")
    parser.add_argument("--concurrency", type=int, default=5, help="Max concurrent pages (default: 5)")
    args = parser.parse_args()
    
    urls = [u.strip() for u in args.url.split(',') if u.strip()]
    print(f"Scraping {len(urls)} URLs with concurrency={args.concurrency}")
    
    results = asyncio.run(scrape_urls_async(urls, args.concurrency))
    
    successful = len([r for r in results if r["status"] == "success"])
    failed = len(results) - successful
    print(f"Completed: {successful} success, {failed} failed")
    
    # Calculate total content reduction
    total_content = sum(len(r.get("content", "") or "") for r in results)
    print(f"Total content size: {total_content:,} characters")
    
    if args.callback_url:
        print(f"Sending results to callback...")
        try:
            response = requests.post(
                args.callback_url,
                json={"results": results},
                timeout=120
            )
            print(f"Callback response: {response.status_code}")
        except Exception as e:
            print(f"Callback failed: {e}")
    else:
        print("No callback URL provided. First result preview:")
        if results and results[0].get("content"):
            print(results[0]["content"][:500] + "...")


if __name__ == "__main__":
    main()
