import asyncio
import argparse
import requests
from playwright.async_api import async_playwright
import html2text


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
            html_content = await page.content()
            title = await page.title()
            
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            markdown_content = h.handle(html_content)
            
            return {
                "url": url,
                "title": title,
                "content": markdown_content,
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
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
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
