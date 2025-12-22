
import sys
import argparse
import requests
import json
from playwright.sync_api import sync_playwright
import html2text

def scrape_urls(urls):
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a generic user agent to avoid basic blocking
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        
        for url in urls:
            url = url.strip()
            if not url:
                continue
                
            page = context.new_page()
            try:
                print(f"Navigating to {url}...")
                page.goto(url, timeout=30000, wait_until="networkidle")
                
                # Simple content extraction: get the procesed HTML
                html_content = page.content()
                
                # Convert to Markdown for RAG-friendliness
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                markdown_content = h.handle(html_content)
                
                results.append({
                    "url": url,
                    "content": markdown_content,
                    "status": "success"
                })
            except Exception as e:
                print(f"Error scraping {url}: {e}")
                results.append({
                    "url": url,
                    "content": None,
                    "status": "error",
                    "error": str(e)
                })
            finally:
                page.close()
        
        browser.close()
    return results

def main():
    parser = argparse.ArgumentParser(description="Scrape web pages using Playwright.")
    parser.add_argument("--url", required=True, help="The URL(s) to scrape. Can be a single URL or comma-separated list.")
    parser.add_argument("--callback_url", required=False, help="The n8n webhook URL to send data back to")
    
    args = parser.parse_args()
    
    # Handle comma-separated URLs
    urls = [u for u in args.url.split(',') if u.strip()]
    
    results = scrape_urls(urls)
    
    if results:
        print(f"Successfully scraped {len(results)} pages.")
        payload = {
            "results": results
        }
        
        if args.callback_url:
            print(f"Sending batch data to callback URL: {args.callback_url}")
            try:
                # Use a larger timeout for batch payloads
                response = requests.post(args.callback_url, json=payload, timeout=30)
                print(f"Callback response: {response.status_code} {response.text}")
            except Exception as e:
                print(f"Failed to send data to callback: {e}")
        else:
            # If no callback, print first result snippet
            print("No callback URL provided. First result snippet:")
            if results and results[0].get("content"):
                 print(results[0]["content"][:500] + "...")
    else:
        print("No results generated.")
        sys.exit(1)

if __name__ == "__main__":
    main()
