
import sys
import argparse
import requests
from playwright.sync_api import sync_playwright
import html2text

def scrape(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a generic user agent to avoid basic blocking
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()
        try:
            print(f"Navigating to {url}...")
            page.goto(url, timeout=60000, wait_until="networkidle")
            
            # Simple content extraction: get the processed HTML
            html_content = page.content()
            
            # Convert to Markdown for RAG-friendliness
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = True
            markdown_content = h.handle(html_content)
            
            return markdown_content
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            return None
        finally:
            browser.close()

def main():
    parser = argparse.ArgumentParser(description="Scrape a web page using Playwright.")
    parser.add_argument("--url", required=True, help="The URL to scrape")
    parser.add_argument("--callback_url", required=False, help="The n8n webhook URL to send data back to")
    
    args = parser.parse_args()
    
    content = scrape(args.url)
    
    if content:
        print("Successfully scraped content.")
        payload = {
            "url": args.url,
            "content": content
        }
        
        if args.callback_url:
            print(f"Sending data to callback URL: {args.callback_url}")
            try:
                response = requests.post(args.callback_url, json=payload)
                print(f"Callback response: {response.status_code} {response.text}")
            except Exception as e:
                print(f"Failed to send data to callback: {e}")
        else:
            # If no callback, just print a snippet to stdout
            print("No callback URL provided. Content snippet:")
            print(content[:500] + "...")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
