import asyncio
import sys
import os
import xml.etree.ElementTree as ET
import requests
import pandas as pd
import logging
from crawl4ai import AsyncWebCrawler
from tqdm.asyncio import tqdm

# --- CONFIGURATION ---
SITEMAP_URL = "https://support.fyi.app/hc/sitemap.xml" 
OUTPUT_FILE = "scraped_final_optimized.xlsx"
TEMP_CSV = "temp_data.csv"

# --- OPTIMIZATION SETTINGS ---
MAX_CONCURRENCY = 15
BATCH_SIZE = 100          # REDUCED from 500. Restart browser every 100 URLs to prevent lag.
BYPASS_CACHE = True
USE_MAGIC = True

# Delete old temp file if it exists
if os.path.exists(TEMP_CSV):
    os.remove(TEMP_CSV)

# --- SILENCE LOGS ---
logging.getLogger("crawl4ai").setLevel(logging.CRITICAL)
logging.getLogger("playwright").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# --- AGGRESSIVE CONSOLE FILTER ---
class Crawl4AISilencer:
    def __init__(self, original_stream):
        self.original_stream = original_stream

    def write(self, text):
        has_keywords = any(k in text for k in [
            "[INIT]", "[FETCH]", "[SCRAPE]", "[COMPLETE]", "[ERROR]",
            "Crawl4AI", "Traceback", "Call log", 
            "Unexpected error", "Page.goto", "waiting until",
            "Error: Failed" 
        ])
        has_symbols = any(s in text for s in ["↓", "◆", "●", "⏱", "×"])
        
        if has_keywords or has_symbols:
            self.original_stream.flush()
            return
        self.original_stream.write(text)

    def flush(self):
        self.original_stream.flush()

    def __getattr__(self, name):
        return getattr(self.original_stream, name)

sys.stdout = Crawl4AISilencer(sys.stdout)
sys.stderr = Crawl4AISilencer(sys.stderr)

def get_all_urls_recursive(start_url):
    urls_to_scrape = []
    sitemap_queue = [start_url]
    processed_sitemaps = set()
    session = requests.Session()
    
    while sitemap_queue:
        current_url = sitemap_queue.pop(0)
        if current_url in processed_sitemaps:
            continue
        processed_sitemaps.add(current_url)

        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = session.get(current_url, headers=headers, timeout=10)
            if response.status_code != 200: continue
            
            root = ET.fromstring(response.content)
            namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            locs = root.findall('.//sm:loc', namespace)
            
            for loc in locs:
                url = loc.text
                if url.endswith('.xml'):
                    sitemap_queue.append(url)
                else:
                    urls_to_scrape.append(url)
        except Exception:
            pass

    return list(set(urls_to_scrape))

async def process_batch(crawler, batch_urls):
    """Scrapes a list of URLs and returns results."""
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def limited_arun(url):
        async with semaphore:
            return await crawler.arun(
                url=url,
                magic=USE_MAGIC,
                bypass_cache=BYPASS_CACHE,
                delay_before_return_html=0.1,
                exclude_tags=['nav', 'footer', 'header', 'aside', 'svg'],
                remove_overlay_elements=True,
                process_iframes=False,
                timeout=60000,
                word_count_threshold=1
            )

    tasks = [limited_arun(url) for url in batch_urls]
    results = []
    
    # Process batch
    for future in tqdm(asyncio.as_completed(tasks), total=len(batch_urls), desc="Scraping Batch"):
        result = await future
        
        if result.success:
            results.append({
                "url": result.url,
                "title": result.metadata.get("title", "No Title"),
                "content": result.markdown[:10000] if result.markdown else "",
                "status": "Success"
            })
        else:
            results.append({
                "url": result.url,
                "title": "Error",
                "content": "",
                "status": "Fail"
            })
            
    return results

async def main():
    urls = get_all_urls_recursive(SITEMAP_URL)
    total_urls = len(urls)
    
    if total_urls == 0:
        return

    # Break URLs into smaller chunks (Batches)
    batches = [urls[i:i + BATCH_SIZE] for i in range(0, len(urls), BATCH_SIZE)]
    
    # Use a fresh browser for each batch to prevent slowdown
    for i, batch in enumerate(batches, 1):
        sys.stdout.write(f"\nStarting Batch {i}/{len(batches)} (Fresh Browser)...\n")
        
        # Create a NEW browser context for this batch
        async with AsyncWebCrawler(verbose=False, headless=True) as crawler:
            batch_results = await process_batch(crawler, batch)
        
        # Save results to CSV (Append mode)
        df_batch = pd.DataFrame(batch_results)
        
        # Check if file exists to write header only once
        file_exists = os.path.exists(TEMP_CSV)
        
        df_batch.to_csv(TEMP_CSV, mode='a', header=not file_exists, index=False)
        
        # Clear memory explicitly
        del batch_results
        del df_batch

    # Final conversion to Excel
    sys.stdout.write(f"\nProcessing Final File...\n")
    df_final = pd.read_csv(TEMP_CSV)
    
    # Clean content length just in case
    df_final['content'] = df_final['content'].astype(str).str[:32000]
    
    df_final.to_excel(OUTPUT_FILE, index=False)
    
    # Cleanup temp file
    if os.path.exists(TEMP_CSV):
        os.remove(TEMP_CSV)
        
    sys.stdout.write(f"\nSaved: {OUTPUT_FILE}\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.stdout.write("\nStopped by user.\n")