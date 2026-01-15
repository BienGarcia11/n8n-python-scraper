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
OUTPUT_CSV = "scraped_data.csv"      # Used for pipeline
OUTPUT_XLSX = "scraped_data.xlsx"    # Used for viewing

MAX_CONCURRENCY = 15
BATCH_SIZE = 100
BYPASS_CACHE = True
USE_MAGIC = True

# Delete old temp files if they exist
if os.path.exists(OUTPUT_CSV):
    os.remove(OUTPUT_CSV)
if os.path.exists(OUTPUT_XLSX):
    os.remove(OUTPUT_XLSX)

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

# --- SCRAPER LOGIC ---
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
    
    for future in tqdm(asyncio.as_completed(tasks), total=len(batch_urls), desc="Scraping Batch"):
        result = await future
        
        if result.success:
            results.append({
                "url": result.url,
                "title": result.metadata.get("title", "No Title"),
                "content": result.markdown, 
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

async def run_scraper():
    """Main function to be called by manager.py"""
    sys.stdout.write("Worker: Starting Scraper...\n")
    
    # Check if file exists to write header
    file_exists = os.path.exists(OUTPUT_CSV)
    if file_exists:
        os.remove(OUTPUT_CSV) # Start fresh

    urls = get_all_urls_recursive(SITEMAP_URL)
    total_urls = len(urls)
    
    if total_urls == 0:
        return None

    batches = [urls[i:i + BATCH_SIZE] for i in range(0, len(urls), BATCH_SIZE)]
    
    for i, batch in enumerate(batches, 1):
        sys.stdout.write(f"\nWorker: Batch {i}/{len(batches)}...\n")
        
        async with AsyncWebCrawler(verbose=False, headless=True) as crawler:
            batch_results = await process_batch(crawler, batch)
        
        df_batch = pd.DataFrame(batch_results)
        
        # Append to CSV
        df_batch.to_csv(OUTPUT_CSV, mode='a', header=not file_exists, index=False)
        file_exists = True 
        
        del batch_results
        del df_batch

    # Final Step: Save Excel copy for user viewing
    sys.stdout.write(f"\nWorker: Finalizing files...\n")
    df_final = pd.read_csv(OUTPUT_CSV)
    
    # 1. Save Excel (Truncated for viewing safety)
    df_view = df_final.copy()
    df_view['content'] = df_view['content'].astype(str).str[:32000]
    df_view.to_excel(OUTPUT_XLSX, index=False)
    
    # 2. Keep CSV full (No truncation for DB)
    # The CSV already has full content, nothing needed here.
    
    sys.stdout.write(f"Worker: Done. Saved CSV and Excel.\n")
    return OUTPUT_CSV

if __name__ == "__main__":
    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        sys.stdout.write("\nStopped by user.\n")