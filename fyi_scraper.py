import asyncio
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import argparse
from dataclasses import dataclass
import re
import gc
import logging
from contextlib import asynccontextmanager

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
import httpx
from supabase import create_client, Client
import openai
from openai import RateLimitError, APIError
from dotenv import load_dotenv
import os
from tqdm.asyncio import tqdm
from tqdm import tqdm as tqdm_sync
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


@dataclass
class ScrapeResult:
    """Result of a scraping attempt"""
    url: str
    success: bool
    data: Optional[Dict] = None
    error: Optional[str] = None


class ConnectionManager:
    """Manages database and API connections with automatic retry"""
    
    def __init__(self):
        self._supabase = None
        self._openai_client = None
        self._last_reconnect = time.time()
        self._reconnect_interval = 300  # Reconnect every 5 minutes
    
    def get_supabase(self) -> Client:
        """Get Supabase client, reconnect if needed"""
        current_time = time.time()
        if self._supabase is None or (current_time - self._last_reconnect) > self._reconnect_interval:
            logger.info("Creating new Supabase connection")
            self._supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            self._last_reconnect = current_time
        return self._supabase
    
    def get_openai(self):
        """Get OpenAI client"""
        if self._openai_client is None:
            openai.api_key = OPENAI_API_KEY
            self._openai_client = openai
        return self._openai_client


# Global connection manager
conn_manager = ConnectionManager()


class TextChunker:
    """Smart text chunking for RAG systems with memory optimization"""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_by_headers(self, text: str, metadata: Dict) -> List[Dict]:
        """Split text by headers for semantic chunking"""
        chunks = []
        lines = text.split('\n')
        current_chunk = []
        current_header = None
        
        for line in lines:
            is_header = (
                line.strip().isupper() and len(line.strip()) < 100 or
                line.strip().startswith('#') or
                (len(line.strip()) < 80 and line.strip() and 
                 line.strip()[0].isupper() and ':' not in line[:20])
            )
            
            if is_header and len(current_chunk) > 0:
                chunk_text = '\n'.join(current_chunk).strip()
                if len(chunk_text) > 50:
                    chunks.append({
                        'text': chunk_text,
                        'header': current_header,
                        'metadata': metadata.copy()
                    })
                
                current_chunk = [line]
                current_header = line.strip()
            else:
                current_chunk.append(line)
        
        if current_chunk:
            chunk_text = '\n'.join(current_chunk).strip()
            if len(chunk_text) > 50:
                chunks.append({
                    'text': chunk_text,
                    'header': current_header,
                    'metadata': metadata.copy()
                })
        
        return chunks
    
    def chunk_by_size(self, text: str, metadata: Dict) -> List[Dict]:
        """Split text into fixed-size chunks with overlap"""
        chunks = []
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        current_chunk = []
        current_size = 0
        
        for sentence in sentences:
            sentence_size = len(sentence)
            
            if current_size + sentence_size > self.chunk_size and current_chunk:
                chunk_text = ' '.join(current_chunk)
                chunks.append({
                    'text': chunk_text,
                    'metadata': metadata.copy()
                })
                
                overlap_text = ' '.join(current_chunk[-3:])
                if len(overlap_text) <= self.chunk_overlap:
                    current_chunk = current_chunk[-3:]
                    current_size = len(overlap_text)
                else:
                    current_chunk = []
                    current_size = 0
            
            current_chunk.append(sentence)
            current_size += sentence_size
        
        if current_chunk:
            chunk_text = ' '.join(current_chunk)
            if len(chunk_text) > 50:
                chunks.append({
                    'text': chunk_text,
                    'metadata': metadata.copy()
                })
        
        return chunks
    
    def chunk_text(self, text: str, metadata: Dict, method: str = 'hybrid') -> List[Dict]:
        """Chunk text using specified method"""
        try:
            if method == 'header':
                chunks = self.chunk_by_headers(text, metadata)
            elif method == 'size':
                chunks = self.chunk_by_size(text, metadata)
            else:  # hybrid
                header_chunks = self.chunk_by_headers(text, metadata)
                final_chunks = []
                for chunk in header_chunks:
                    if len(chunk['text']) > self.chunk_size * 2:
                        sub_chunks = self.chunk_by_size(chunk['text'], chunk['metadata'])
                        final_chunks.extend(sub_chunks)
                    else:
                        final_chunks.append(chunk)
                chunks = final_chunks
            
            for i, chunk in enumerate(chunks):
                chunk['metadata']['chunk_index'] = i
                chunk['metadata']['total_chunks'] = len(chunks)
                if 'header' in chunk:
                    chunk['metadata']['section_header'] = chunk['header']
            
            return chunks
        except Exception as e:
            logger.error(f"Error in chunking: {e}", exc_info=True)
            # Return single chunk as fallback
            return [{
                'text': text[:self.chunk_size],
                'metadata': {**metadata, 'chunk_index': 0, 'total_chunks': 1}
            }]


class FYISupportScraper:
    """Production-ready scraper with comprehensive error handling"""
    
    def __init__(self, sitemap_url: str, parallel_limit: int = 5,
                 chunk_size: int = 1000, chunk_overlap: int = 200,
                 chunking_method: str = 'hybrid', max_retries: int = 3):
        self.sitemap_url = sitemap_url
        self.target_class = "lt-article-container__column lt-article-container__article"
        self.urls: List[str] = []
        self.verified_structure = False
        self.parallel_limit = parallel_limit
        self.failed_urls: List[str] = []
        
        self.chunker = TextChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        self.chunking_method = chunking_method
        self.max_retries = max_retries
        
        # Rate limiting
        self.embedding_semaphore = asyncio.Semaphore(50)  # Max 50 concurrent embedding requests
        self.last_embedding_time = 0
        self.min_embedding_interval = 0.02  # 20ms between requests
        
    async def fetch_sitemap(self) -> List[str]:
        """Fetch and parse sitemap XML to extract article URLs"""
        logger.info(f"Fetching sitemap: {self.sitemap_url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(self.sitemap_url)
                response.raise_for_status()
                
                root = ET.fromstring(response.content)
                namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
                urls = [
                    loc.text for loc in root.findall('.//ns:loc', namespace)
                    if loc.text and '/articles/' in loc.text
                ]
                
                self.urls = urls
                logger.info(f"Found {len(urls)} article URLs in sitemap")
                return urls
                
            except Exception as e:
                logger.error(f"Error fetching sitemap: {e}", exc_info=True)
                return []
    
    async def verify_structure(self, sample_size: int = 10) -> bool:
        """Verify HTML structure across sample URLs"""
        logger.info(f"Verifying structure across {sample_size} sample URLs")
        
        if not self.urls:
            await self.fetch_sitemap()
        
        sample_urls = self.urls[:sample_size] if len(self.urls) >= sample_size else self.urls
        
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            extra_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--disable-extensions",
                "--disable-background-networking",
                "--mute-audio"
            ]
        )
        
        run_config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_for="css:.lt-article-container__article",
            page_timeout=20000,
            delay_before_return_html=0.1,
        )
        
        structure_verified_count = 0
        
        async with AsyncWebCrawler(config=browser_config) as crawler:
            async def verify_single(url: str) -> bool:
                try:
                    result = await crawler.arun(url=url, config=run_config)
                    if result.success and 'lt-article-container__article' in result.html:
                        return True
                    return False
                except Exception as e:
                    logger.warning(f"Verification failed for {url}: {e}")
                    return False
            
            semaphore = asyncio.Semaphore(self.parallel_limit)
            
            async def verify_with_semaphore(url: str) -> bool:
                async with semaphore:
                    result = await verify_single(url)
                await asyncio.sleep(0.3)  # Delay OUTSIDE semaphore
                return result
            
            tasks = [verify_with_semaphore(url) for url in sample_urls]
            results = []
            
            for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), 
                           desc="Verifying structure", unit="url"):
                result = await coro
                results.append(result)
                if result:
                    structure_verified_count += 1
        
        success_rate = (structure_verified_count / len(sample_urls)) * 100
        logger.info(f"Structure verification: {structure_verified_count}/{len(sample_urls)} ({success_rate:.1f}%)")
        
        self.verified_structure = success_rate >= 80
        return self.verified_structure
    
    async def scrape_url(self, url: str, crawler: AsyncWebCrawler) -> ScrapeResult:
        """Scrape a single URL with proper cleanup"""
        soup = None
        try:
            run_config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS,
                wait_for="css:.lt-article-container__article",
                page_timeout=20000,
                delay_before_return_html=0.1,
                process_iframes=False,
                remove_overlay_elements=True,
                screenshot=False,
                pdf=False,
            )
            
            result = await crawler.arun(url=url, config=run_config)
            
            if not result.success:
                return ScrapeResult(url=url, success=False, error=result.error_message)
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(result.html, 'html.parser')
            
            article_container = soup.find(class_='lt-article-container__article')
            
            if not article_container:
                return ScrapeResult(url=url, success=False, error="Article container not found")
            
            title_elem = soup.find('h1') or soup.find(class_='article-title')
            title = title_elem.get_text(strip=True) if title_elem else "Untitled"
            
            content_text = article_container.get_text(separator='\n', strip=True)
            
            base_metadata = {
                'url': url,
                'title': title,
                'source': 'FYI Support',
                'sitemap': self.sitemap_url,
                'scraped_at': datetime.now().isoformat(),
            }
            
            breadcrumb = soup.find(class_='breadcrumbs')
            if breadcrumb:
                base_metadata['category'] = breadcrumb.get_text(strip=True)
            
            # Clean up BeautifulSoup object immediately
            del soup
            soup = None
            
            chunks = self.chunker.chunk_text(content_text, base_metadata, method=self.chunking_method)
            
            # Clear content_text from memory
            del content_text
            
            data = {
                'chunks': chunks,
                'title': title,
                'url': url,
                'total_chunks': len(chunks)
            }
            
            return ScrapeResult(url=url, success=True, data=data)
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}", exc_info=True)
            return ScrapeResult(url=url, success=False, error=str(e))
        finally:
            # Ensure cleanup
            if soup is not None:
                del soup
            gc.collect()
    
    async def generate_embeddings_batch_with_retry(self, texts: List[str], retry_count: int = 0) -> List[Optional[List[float]]]:
        """Generate embeddings in batch with retry logic and rate limiting"""
        async with self.embedding_semaphore:
            # Rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_embedding_time
            if time_since_last < self.min_embedding_interval:
                await asyncio.sleep(self.min_embedding_interval - time_since_last)
            
            try:
                client = conn_manager.get_openai()
                response = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=[text[:8000] for text in texts]
                )
                self.last_embedding_time = time.time()
                return [item.embedding for item in response.data]
                
            except RateLimitError as e:
                if retry_count < self.max_retries:
                    wait_time = (2 ** retry_count) * 2  # Exponential backoff
                    logger.warning(f"Rate limit hit, waiting {wait_time}s (retry {retry_count + 1}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                    return await self.generate_embeddings_batch_with_retry(texts, retry_count + 1)
                else:
                    logger.error(f"Rate limit exceeded after {self.max_retries} retries")
                    return [None] * len(texts)
                    
            except APIError as e:
                if retry_count < self.max_retries:
                    wait_time = (2 ** retry_count)
                    logger.warning(f"API error, retrying in {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
                    return await self.generate_embeddings_batch_with_retry(texts, retry_count + 1)
                else:
                    logger.error(f"API error after {self.max_retries} retries: {e}")
                    return [None] * len(texts)
                    
            except Exception as e:
                logger.error(f"Unexpected error in batch embedding: {e}", exc_info=True)
                return [None] * len(texts)
    
    async def store_chunks_in_supabase(self, chunks: List[Dict]) -> Tuple[int, int]:
        """Store chunks with robust error handling and transaction safety"""
        success_count = 0
        failed_count = 0
        
        if not chunks:
            return 0, 0
        
        # Process in smaller batches to avoid overwhelming the API
        batch_size = 20
        
        for i in range(0, len(chunks), batch_size):
            batch_chunks = chunks[i:i + batch_size]
            texts = [chunk['text'] for chunk in batch_chunks]
            
            # Generate embeddings with retry
            embeddings = await self.generate_embeddings_batch_with_retry(texts)
            
            # Prepare data for insertion
            insert_data = []
            for chunk, embedding in zip(batch_chunks, embeddings):
                if embedding:
                    insert_data.append({
                        'content': chunk['text'],
                        'embedding': embedding,
                        'metadata': chunk['metadata']
                    })
                else:
                    failed_count += 1
            
            if not insert_data:
                continue
            
            # Try batch insert first
            try:
                supabase = conn_manager.get_supabase()
                result = supabase.table('documents').insert(insert_data).execute()
                success_count += len(insert_data)
                logger.debug(f"Batch inserted {len(insert_data)} chunks")
                
            except Exception as e:
                logger.warning(f"Batch insert failed, falling back to individual inserts: {e}")
                
                # Fallback: Individual inserts with retry
                for item in insert_data:
                    retry_count = 0
                    while retry_count < self.max_retries:
                        try:
                            supabase = conn_manager.get_supabase()
                            supabase.table('documents').insert(item).execute()
                            success_count += 1
                            break
                        except Exception as insert_error:
                            retry_count += 1
                            if retry_count >= self.max_retries:
                                logger.error(f"Failed to insert chunk after {self.max_retries} retries: {insert_error}")
                                failed_count += 1
                            else:
                                await asyncio.sleep(1 * retry_count)
        
        return success_count, failed_count
    
    async def process_url_with_storage(self, url: str, crawler: AsyncWebCrawler, 
                                      pbar: tqdm) -> Tuple[bool, str, int]:
        """Process URL with comprehensive error handling"""
        try:
            scrape_result = await self.scrape_url(url, crawler)
            
            if not scrape_result.success:
                pbar.set_postfix_str(f"Failed scrape: {url[-50:]}")
                return False, scrape_result.error or "Unknown error", 0
            
            success, failed = await self.store_chunks_in_supabase(scrape_result.data['chunks'])
            
            total_chunks = scrape_result.data['total_chunks']
            
            if success > 0:
                pbar.set_postfix_str(f"✓ {scrape_result.data['title'][:30]} ({total_chunks} chunks)")
                return True, None, total_chunks
            else:
                return False, "All chunks failed to store", 0
                
        except Exception as e:
            logger.error(f"Unexpected error processing {url}: {e}", exc_info=True)
            return False, str(e), 0
        finally:
            # Force garbage collection after each URL
            gc.collect()
    
    async def scrape_batch(self, urls: List[str], batch_num: int, 
                          total_batches: int) -> Tuple[int, int, List[str], int]:
        """Scrape batch with proper browser lifecycle management"""
        
        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            extra_args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--disable-extensions",
                "--disable-background-networking",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-breakpad",
                "--disable-component-extensions-with-background-pages",
                "--disable-features=TranslateUI,BlinkGenPropertyTrees",
                "--disable-ipc-flooding-protection",
                "--disable-renderer-backgrounding",
                "--enable-features=NetworkService,NetworkServiceInProcess",
                "--force-color-profile=srgb",
                "--metrics-recording-only",
                "--mute-audio"
            ]
        )
        
        success_count = 0
        failed_count = 0
        failed_urls = []
        total_chunks_created = 0
        
        # Use proper context manager to ensure cleanup
        async with AsyncWebCrawler(config=browser_config) as crawler:
            semaphore = asyncio.Semaphore(self.parallel_limit)
            
            async def process_with_semaphore(url: str, pbar: tqdm) -> Tuple[bool, str, str, int]:
                async with semaphore:
                    success, error, chunks = await self.process_url_with_storage(url, crawler, pbar)
                # Sleep OUTSIDE semaphore to not block other tasks
                await asyncio.sleep(0.5)
                return success, error, url, chunks
            
            desc = f"Batch {batch_num}/{total_batches}"
            pbar = tqdm(total=len(urls), desc=desc, unit="url", leave=False)  # leave=False to avoid memory
            
            tasks = [process_with_semaphore(url, pbar) for url in urls]
            
            for coro in asyncio.as_completed(tasks):
                try:
                    success, error, url, chunks = await coro
                    pbar.update(1)
                    
                    if success:
                        success_count += 1
                        total_chunks_created += chunks
                    else:
                        failed_count += 1
                        failed_urls.append(url)
                        if error:
                            logger.debug(f"Failed {url}: {error}")
                except Exception as e:
                    logger.error(f"Task execution error: {e}", exc_info=True)
                    failed_count += 1
            
            pbar.close()
        
        # Force cleanup after batch
        gc.collect()
        
        return success_count, failed_count, failed_urls, total_chunks_created
    
    async def scrape_all(self, batch_size: int = 100, max_urls: Optional[int] = None,
                        skip_verification: bool = False):
        """Main scraping orchestration with comprehensive error handling"""
        
        if not self.urls:
            await self.fetch_sitemap()
        
        if not self.urls:
            logger.error("No URLs to scrape")
            return
        
        if not skip_verification and not self.verified_structure:
            await self.verify_structure()
            
            if not self.verified_structure:
                logger.warning("Structure verification failed for some URLs")
                proceed = input("Continue anyway? (y/n): ")
                if proceed.lower() != 'y':
                    return
        
        urls_to_scrape = self.urls[:max_urls] if max_urls else self.urls
        
        if max_urls:
            logger.info(f"Limiting scrape to {len(urls_to_scrape)} URLs")
        
        print(f"\n{'='*70}")
        print(f"🚀 Starting PRODUCTION scrape of {len(urls_to_scrape)} URLs")
        print(f"   Parallel limit: {self.parallel_limit}")
        print(f"   Batch size: {batch_size}")
        print(f"   Chunking: {self.chunking_method} (size={self.chunker.chunk_size}, overlap={self.chunker.chunk_overlap})")
        print(f"   Max retries: {self.max_retries}")
        print(f"{'='*70}\n")
        
        batches = [urls_to_scrape[i:i + batch_size] 
                  for i in range(0, len(urls_to_scrape), batch_size)]
        
        total_success = 0
        total_failed = 0
        all_failed_urls = []
        total_chunks = 0
        
        start_time = datetime.now()
        
        for i, batch in enumerate(batches, 1):
            logger.info(f"Processing batch {i}/{len(batches)} ({len(batch)} URLs)")
            
            try:
                success, failed, failed_urls, chunks = await self.scrape_batch(
                    batch, i, len(batches)
                )
                
                total_success += success
                total_failed += failed
                all_failed_urls.extend(failed_urls)
                total_chunks += chunks
                
                elapsed = (datetime.now() - start_time).total_seconds()
                urls_per_min = (total_success + total_failed) / elapsed * 60 if elapsed > 0 else 0
                
                print(f"   ✓ Success: {success} | ✗ Failed: {failed} | 📄 Chunks: {chunks} | ⚡ {urls_per_min:.1f} URLs/min")
                
            except Exception as e:
                logger.error(f"Batch {i} failed completely: {e}", exc_info=True)
                all_failed_urls.extend(batch)
                total_failed += len(batch)
        
        elapsed_time = (datetime.now() - start_time).total_seconds()
        
        print(f"\n{'='*70}")
        print(f"📊 First pass complete!")
        print(f"   Total processed: {len(urls_to_scrape)}")
        print(f"   ✓ Success: {total_success}")
        print(f"   ✗ Failed: {total_failed}")
        print(f"   📄 Total chunks created: {total_chunks}")
        if elapsed_time > 0 and total_success > 0:
            print(f"   ⏱️  Time elapsed: {elapsed_time:.1f}s ({elapsed_time/60:.1f} min)")
            print(f"   ⚡ Average speed: {total_success / elapsed_time * 60:.1f} URLs/min")
        print(f"{'='*70}")
        
        # Retry logic
        if all_failed_urls:
            logger.info(f"Retrying {len(all_failed_urls)} failed URLs")
            
            retry_start = datetime.now()
            retry_success = 0
            retry_failed = 0
            final_failed_urls = []
            retry_chunks = 0
            
            retry_batch_size = min(50, batch_size)
            retry_batches = [all_failed_urls[i:i + retry_batch_size] 
                           for i in range(0, len(all_failed_urls), retry_batch_size)]
            
            for i, batch in enumerate(retry_batches, 1):
                logger.info(f"Retry batch {i}/{len(retry_batches)}")
                
                try:
                    success, failed, failed_urls, chunks = await self.scrape_batch(
                        batch, i, len(retry_batches)
                    )
                    
                    retry_success += success
                    retry_failed += failed
                    final_failed_urls.extend(failed_urls)
                    retry_chunks += chunks
                    
                    print(f"   ✓ Success: {success} | ✗ Failed: {failed} | 📄 Chunks: {chunks}")
                    
                except Exception as e:
                    logger.error(f"Retry batch {i} failed: {e}", exc_info=True)
                    final_failed_urls.extend(batch)
                    retry_failed += len(batch)
            
            retry_elapsed = (datetime.now() - retry_start).total_seconds()
            total_elapsed = elapsed_time + retry_elapsed
            
            print(f"\n{'='*70}")
            print(f"🏁 FINAL RESULTS")
            print(f"{'='*70}")
            print(f"   Total URLs: {len(urls_to_scrape)}")
            print(f"   ✓ Successfully scraped: {total_success + retry_success}")
            print(f"   ✗ Failed after retry: {len(final_failed_urls)}")
            print(f"   📄 Total chunks created: {total_chunks + retry_chunks}")
            
            total_successful = total_success + retry_success
            if total_successful > 0:
                print(f"   📊 Avg chunks per document: {(total_chunks + retry_chunks) / total_successful:.1f}")
                print(f"   Success rate: {(total_successful / len(urls_to_scrape) * 100):.2f}%")
                print(f"   ⏱️  Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")
                print(f"   ⚡ Average speed: {total_successful / total_elapsed * 60:.1f} URLs/min")
            else:
                print(f"   ⚠️  No URLs were successfully scraped")
            
            print(f"{'='*70}")
            
            if final_failed_urls:
                logger.warning(f"{len(final_failed_urls)} URLs failed after retry")
                print(f"\n⚠️  Failed URLs ({len(final_failed_urls)}):")
                for url in final_failed_urls[:10]:
                    print(f"   - {url}")
                if len(final_failed_urls) > 10:
                    print(f"   ... and {len(final_failed_urls) - 10} more")
                
                with open('failed_urls.txt', 'w') as f:
                    f.write('\n'.join(final_failed_urls))
                print(f"\n💾 Failed URLs saved to: failed_urls.txt")
        else:
            print(f"\n🎉 All URLs scraped successfully!")
            print(f"   📄 Total chunks created: {total_chunks}")
            if total_success > 0:
                print(f"   📊 Average chunks per document: {total_chunks / total_success:.1f}")
                print(f"   ⏱️  Total time: {elapsed_time:.1f}s ({elapsed_time/60:.1f} min)")
                print(f"   ⚡ Average speed: {total_success / elapsed_time * 60:.1f} URLs/min")


def main():
    """Main entry point with argument parsing"""
    parser = argparse.ArgumentParser(
        description='FYI Support Scraper - Production Ready',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Production Features:
  • Comprehensive error handling and retry logic
  • Memory leak prevention with proper cleanup
  • Rate limiting and connection management
  • Detailed logging to scraper.log
  • Batch processing with fallback mechanisms
  • Exponential backoff for API errors

Examples:
  # Quick test
  python fyi_scraper_production.py --max-urls 10 --skip-verification
  
  # Production run
  python fyi_scraper_production.py --parallel 5 --max-retries 3
  
  # Full scrape with logging
  python fyi_scraper_production.py --batch-size 100
        """
    )
    
    parser.add_argument('--sitemap', default='https://support.fyi.app/hc/sitemap.xml',
                       help='Sitemap URL')
    parser.add_argument('--max-urls', type=int, default=None,
                       help='Max URLs to scrape')
    parser.add_argument('--batch-size', type=int, default=100,
                       help='URLs per batch (default: 100)')
    parser.add_argument('--parallel', type=int, default=5,
                       help='Parallel limit (default: 5)')
    parser.add_argument('--skip-verification', action='store_true',
                       help='Skip structure verification')
    parser.add_argument('--chunk-size', type=int, default=1000,
                       help='Chunk size (default: 1000)')
    parser.add_argument('--chunk-overlap', type=int, default=200,
                       help='Chunk overlap (default: 200)')
    parser.add_argument('--chunking-method', choices=['header', 'size', 'hybrid'],
                       default='hybrid', help='Chunking method (default: hybrid)')
    parser.add_argument('--max-retries', type=int, default=3,
                       help='Max retries for failed operations (default: 3)')
    
    args = parser.parse_args()
    
    print(f"\n{'='*70}")
    print(f"FYI Support Scraper - PRODUCTION Configuration")
    print(f"{'='*70}")
    print(f"Sitemap: {args.sitemap}")
    print(f"Max URLs: {args.max_urls or 'All'}")
    print(f"Batch size: {args.batch_size}")
    print(f"Parallel limit: {args.parallel}")
    print(f"Max retries: {args.max_retries}")
    print(f"Skip verification: {args.skip_verification}")
    print(f"")
    print(f"Chunking:")
    print(f"  Method: {args.chunking_method}")
    print(f"  Size: {args.chunk_size} chars")
    print(f"  Overlap: {args.chunk_overlap} chars")
    print(f"")
    print(f"Logging: scraper.log")
    print(f"{'='*70}\n")
    
    scraper = FYISupportScraper(
        args.sitemap, 
        parallel_limit=args.parallel,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        chunking_method=args.chunking_method,
        max_retries=args.max_retries
    )
    
    try:
        asyncio.run(scraper.scrape_all(
            batch_size=args.batch_size,
            max_urls=args.max_urls,
            skip_verification=args.skip_verification
        ))
    except KeyboardInterrupt:
        logger.info("Scraping interrupted by user")
        print("\n⚠️  Scraping interrupted. Progress has been saved.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        print(f"\n❌ Fatal error occurred. Check scraper.log for details.")
        raise


if __name__ == "__main__":
    main()