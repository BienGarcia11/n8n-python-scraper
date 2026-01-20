import asyncio
import sys
import os
import xml.etree.ElementTree as ET
import requests
import pandas as pd
import logging
from crawl4ai import AsyncWebCrawler
from tqdm.asyncio import tqdm
from logger_config import setup_logger

# --- LOGGER SETUP ---
logger = setup_logger("Worker")

# --- CONFIGURATION ---
SITEMAP_URL = "https://support.fyi.app/hc/sitemap.xml" 
OUTPUT_FILE = "scraped_data.csv" # Only CSV now

MAX_CONCURRENCY = 3      # Changed from 15 to 3. Save memory.
BATCH_SIZE = 15           # Changed from 100 to 15.
BYPASS_CACHE = True
USE_MAGIC = True

# Delete old file if exists
if os.path.exists(OUTPUT_FILE):
    try:
        os.remove(OUTPUT_FILE)
        logger.info(f"Deleted old output file: {OUTPUT_FILE}")
    except Exception as e:
        logger.warning(f"Could not delete old output file: {e}")

# --- SCRAPER LOGIC ---
def get_all_urls_recursive(start_url):
    urls_to_scrape = []
    sitemap_queue = [start_url]
    processed_sitemaps = set()
    session = requests.Session()
    
    logger.info(f"Fetching sitemaps starting from: {start_url}")
    
    while sitemap_queue:
        current_url = sitemap_queue.pop(0)
        if current_url in processed_sitemaps:
            continue
        processed_sitemaps.add(current_url)

        try:
            # logger.info(f"Reading sitemap: {current_url}")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = session.get(current_url, headers=headers, timeout=10)
            if response.status_code != 200: 
                logger.warning(f"Failed to fetch sitemap: {current_url} (Status: {response.status_code})")
                continue
            
            root = ET.fromstring(response.content)
            namespace = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            locs = root.findall('.//sm:loc', namespace)
            
            for loc in locs:
                url = loc.text
                if url.endswith('.xml'):
                    sitemap_queue.append(url)
                else:
                    urls_to_scrape.append(url)
        except Exception as e:
            logger.error(f"Error processing sitemap {current_url}: {e}")
            pass

    return list(set(urls_to_scrape))

async def process_batch(crawler, batch_urls):
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def limited_arun(url):
        async with semaphore:
            try:
                result = await crawler.arun(
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
                return result
            except Exception as e:
                logger.error(f"Crawl failed for {url}: {e}")
                # Create a dummy result object or return None to handle gracefully
                # For now returning None and handling below
                return None

    tasks = [limited_arun(url) for url in batch_urls]
    results = []
    
    # Using asyncio.as_completed for progress, but we need to match results to URLs if subsequent logic depended on order.
    # Here we just append to list, so order doesn't strictly matter for the CSV.
    for future in tqdm(asyncio.as_completed(tasks), total=len(batch_urls), desc="Scraping Batch"):
        result = await future
        
        if result and result.success:
            results.append({
                "url": result.url,
                "title": result.metadata.get("title", "No Title"),
                "content": result.markdown, # No truncation limit
                "status": "Success"
            })
        else:
            # Try to recover URL from result if possible, otherwise generic error
            url_ref = result.url if result else "Unknown"
            results.append({
                "url": url_ref,
                "title": "Error",
                "content": "",
                "status": "Fail"
            })
            
    return results

async def run_scraper():
    """Main function to be called by manager.py"""
    logger.info("Starting Scraper Job...")
    
    file_exists = os.path.exists(OUTPUT_FILE)
    if file_exists:
        os.remove(OUTPUT_FILE) # Start fresh

    urls = get_all_urls_recursive(SITEMAP_URL)
    total_urls = len(urls)
    logger.info(f"Found {total_urls} URLs to scrape.")
    
    if total_urls == 0:
        logger.warning("No URLs found. Exiting scraper.")
        return None

    batches = [urls[i:i + BATCH_SIZE] for i in range(0, len(urls), BATCH_SIZE)]
    
    for i, batch in enumerate(batches, 1):
        logger.info(f"Processing Batch {i}/{len(batches)} ({len(batch)} URLs)...")
        
        async with AsyncWebCrawler(verbose=True, headless=True) as crawler:
            batch_results = await process_batch(crawler, batch)
        
        df_batch = pd.DataFrame(batch_results)
        df_batch.to_csv(OUTPUT_FILE, mode='a', header=not file_exists, index=False)
        file_exists = True 
        
        logger.info(f"Batch {i} complete. Appended {len(batch_results)} rows.")
        
        del batch_results
        del df_batch

    logger.info(f"Scraping Job Complete. Saved to {OUTPUT_FILE}")
    return OUTPUT_FILE

if __name__ == "__main__":
    try:
        asyncio.run(run_scraper())
    except KeyboardInterrupt:
        logger.info("Stopped by user.")