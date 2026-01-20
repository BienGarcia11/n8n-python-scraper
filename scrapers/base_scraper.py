"""
Base scraper class with common functionality for all sitemap scrapers.
"""
import asyncio
import xml.etree.ElementTree as ET
import requests
import pandas as pd
from abc import ABC, abstractmethod
from crawl4ai import AsyncWebCrawler
from tqdm.asyncio import tqdm
from logger_config import setup_logger
import os


class BaseScraper(ABC):
    """Base class for sitemap-based scrapers with common functionality."""
    
    def __init__(
        self,
        sitemap_url: str,
        output_file: str = "scraped_data.csv",
        max_concurrency: int = 3,
        batch_size: int = 15,
        bypass_cache: bool = True,
        use_magic: bool = True,
        max_retries: int = 3,
        retry_delay: int = 2
    ):
        """
        Initialize the base scraper.
        
        Args:
            sitemap_url: URL of the sitemap to scrape
            output_file: Path to output CSV file
            max_concurrency: Maximum concurrent requests
            batch_size: Number of URLs to process per batch
            bypass_cache: Whether to bypass cache
            use_magic: Whether to use crawl4ai's magic mode
            max_retries: Maximum number of retry attempts for failed URLs
            retry_delay: Delay in seconds between retry attempts
        """
        self.sitemap_url = sitemap_url
        self.output_file = output_file
        self.max_concurrency = max_concurrency
        self.batch_size = batch_size
        self.bypass_cache = bypass_cache
        self.use_magic = use_magic
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = setup_logger(self.__class__.__name__)
        
        # Delete old file if exists
        if os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
                self.logger.info(f"Deleted old output file: {self.output_file}")
            except Exception as e:
                self.logger.warning(f"Could not delete old output file: {e}")
    
    def get_all_urls_recursive(self, start_url: str):
        """
        Recursively fetch all URLs from sitemap and sub-sitemaps.
        
        Args:
            start_url: Starting sitemap URL
            
        Returns:
            List of URLs to scrape
        """
        urls_to_scrape = []
        sitemap_queue = [start_url]
        processed_sitemaps = set()
        session = requests.Session()
        
        self.logger.info(f"Fetching sitemaps starting from: {start_url}")
        
        while sitemap_queue:
            current_url = sitemap_queue.pop(0)
            if current_url in processed_sitemaps:
                continue
            processed_sitemaps.add(current_url)

            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = session.get(current_url, headers=headers, timeout=10)
                if response.status_code != 200: 
                    self.logger.warning(f"Failed to fetch sitemap: {current_url} (Status: {response.status_code})")
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
                self.logger.error(f"Error processing sitemap {current_url}: {e}")
                pass

        return list(set(urls_to_scrape))
    
    def should_scrape_url(self, url: str) -> bool:
        """
        Determine if a URL should be scraped.
        Override in subclasses for custom URL filtering.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL should be scraped, False otherwise
        """
        return True
    
    def get_crawler_params(self) -> dict:
        """
        Get crawl4ai parameters.
        Override in subclasses for custom crawler configuration.
        
        Returns:
            Dictionary of crawler parameters
        """
        return {
            'magic': self.use_magic,
            'bypass_cache': self.bypass_cache,
            'delay_before_return_html': 0.1,
            'exclude_tags': ['nav', 'footer', 'header', 'aside', 'svg'],
            'remove_overlay_elements': True,
            'process_iframes': False,
            'timeout': 60000,
            'word_count_threshold': 1
        }
    
    def extract_content(self, result) -> dict:
        """
        Extract content from crawl result.
        Override in subclasses for custom extraction logic.
        
        Args:
            result: crawl4ai result object
            
        Returns:
            Dictionary with extracted data (url, title, content, status)
        """
        return {
            "url": result.url,
            "title": result.metadata.get("title", "No Title"),
            "content": result.markdown,
            "status": "Success"
        }
    
    async def process_batch(self, crawler, batch_urls, return_failed=False):
        """
        Process a batch of URLs with concurrency limiting and immediate retry logic.
        
        Args:
            crawler: AsyncWebCrawler instance
            batch_urls: List of URLs to process
            return_failed: If True, return list of failed URLs for retry
            
        Returns:
            Tuple of (List of extraction results, List of failed URLs if return_failed=True)
        """
        semaphore = asyncio.Semaphore(self.max_concurrency)
        failed_urls = []

        async def limited_arun(url):
            async with semaphore:
                # Check if URL should be scraped
                if not self.should_scrape_url(url):
                    self.logger.debug(f"Skipping URL: {url}")
                    return {
                        "url": url,
                        "title": "Skipped",
                        "content": "",
                        "status": "Skipped"
                    }
                
                # Retry logic: attempt up to max_retries times
                for attempt in range(self.max_retries):
                    try:
                        # Get crawler parameters
                        params = self.get_crawler_params()
                        
                        result = await crawler.arun(url=url, **params)
                        return self.extract_content(result)
                        
                    except Exception as e:
                        if attempt < self.max_retries - 1:
                            self.logger.warning(f"Retry {attempt + 1}/{self.max_retries} for {url} after error: {e}")
                            await asyncio.sleep(self.retry_delay)
                        else:
                            self.logger.error(f"Crawl failed for {url} after {self.max_retries} attempts: {e}")
                
                # If we get here, all retries failed
                return {
                    "url": url,
                    "title": "Error",
                    "content": "",
                    "status": "Fail"
                }

        tasks = [limited_arun(url) for url in batch_urls]
        results = []
        
        for future in tqdm(asyncio.as_completed(tasks), total=len(batch_urls), desc="Scraping Batch"):
            result = await future
            results.append(result)
            
            # Track failed URLs for potential retry
            if result['status'] == 'Fail':
                failed_urls.append(result['url'])
            
        if return_failed:
            return results, failed_urls
        return results
    
    async def run(self):
        """
        Main entry point to run the scraper with hybrid retry approach.
        
        Returns:
            Path to output CSV file, or None if no URLs found
        """
        self.logger.info("Starting Scraper Job...")
        
        # Start fresh
        if os.path.exists(self.output_file):
            os.remove(self.output_file)

        # Get all URLs from sitemap
        urls = self.get_all_urls_recursive(self.sitemap_url)
        
        # Filter URLs based on subclass logic
        urls = [url for url in urls if self.should_scrape_url(url)]
        
        total_urls = len(urls)
        self.logger.info(f"Found {total_urls} URLs to scrape.")
        
        if total_urls == 0:
            self.logger.warning("No URLs found. Exiting scraper.")
            return None

        # Process in batches
        batches = [urls[i:i + self.batch_size] for i in range(0, len(urls), self.batch_size)]
        file_exists = False
        all_failed_urls = []
        
        for i, batch in enumerate(batches, 1):
            self.logger.info(f"Processing Batch {i}/{len(batches)} ({len(batch)} URLs)...")
            
            async with AsyncWebCrawler(verbose=True, headless=True) as crawler:
                batch_results, failed_urls = await self.process_batch(crawler, batch, return_failed=True)
            
            df_batch = pd.DataFrame(batch_results)
            df_batch.to_csv(self.output_file, mode='a', header=not file_exists, index=False)
            file_exists = True 
            
            self.logger.info(f"Batch {i} complete. Appended {len(batch_results)} rows. Failed: {len(failed_urls)}")
            
            # Track failed URLs for final retry
            all_failed_urls.extend(failed_urls)
            
            # Cleanup
            del batch_results
            del df_batch

        # --- FINAL RETRY PASS ---
        if all_failed_urls:
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"Final Retry Pass: {len(all_failed_urls)} failed URLs to retry...")
            self.logger.info(f"{'='*50}\n")
            
            # Remove duplicates and limit batch size for final retry
            all_failed_urls = list(set(all_failed_urls))
            retry_batches = [all_failed_urls[i:i + self.batch_size] for i in range(0, len(all_failed_urls), self.batch_size)]
            
            retry_success_count = 0
            for i, batch in enumerate(retry_batches, 1):
                self.logger.info(f"Final Retry Batch {i}/{len(retry_batches)} ({len(batch)} URLs)...")
                
                async with AsyncWebCrawler(verbose=True, headless=True) as crawler:
                    batch_results = await self.process_batch(crawler, batch)
                
                # Only save successful results from retry
                retry_success = [r for r in batch_results if r['status'] == 'Success']
                retry_success_count += len(retry_success)
                
                if retry_success:
                    df_retry = pd.DataFrame(retry_success)
                    df_retry.to_csv(self.output_file, mode='a', header=False, index=False)
                    self.logger.info(f"Retry Batch {i} recovered {len(retry_success)} URLs.")
                
                # Cleanup
                del batch_results
                if 'df_retry' in locals():
                    del df_retry
            
            # Update CSV to remove failed entries that were successfully retried
            if retry_success_count > 0:
                self.logger.info(f"\nUpdating CSV to replace failed entries with successful retries...")
                df = pd.read_csv(self.output_file)
                
                # For each successfully retried URL, remove the failed entry (keep the successful one)
                successful_retry_urls = [r['url'] for r in retry_success]
                df = df[~((df['url'].isin(successful_retry_urls)) & (df['status'] == 'Fail'))]
                
                df.to_csv(self.output_file, index=False)
                self.logger.info(f"CSV updated. Removed duplicate failed entries for {retry_success_count} successfully retried URLs.")
            
            # Summary
            self.logger.info(f"\n{'='*50}")
            self.logger.info(f"Final Retry Summary:")
            self.logger.info(f"  Total retried: {len(all_failed_urls)}")
            self.logger.info(f"  Successfully recovered: {retry_success_count}")
            self.logger.info(f"  Still failed: {len(all_failed_urls) - retry_success_count}")
            self.logger.info(f"{'='*50}\n")
        else:
            self.logger.info("All URLs scraped successfully! No retries needed.")

        self.logger.info(f"Scraping Job Complete. Saved to {self.output_file}")
        return self.output_file
