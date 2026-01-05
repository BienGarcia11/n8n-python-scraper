"""Main scraper orchestrator."""
import asyncio
import logging
from typing import Dict, Any, Optional
from playwright.async_api import Page, BrowserContext
from tenacity import retry, stop_after_attempt, wait_exponential

from database import DatabaseManager
from scraper.browser import browser_manager
from scraper.interactions import ContentInteraction
from scraper.extractor import ContentExtractor
from embeddings.generator import EmbeddingGenerator

logger = logging.getLogger(__name__)


class URLScraper:
    """Main scraper class for processing URLs."""
    
    def __init__(self, db_manager: DatabaseManager, embedding_generator: EmbeddingGenerator):
        """Initialize scraper with database and embedding generators."""
        self.db = db_manager
        self.embedding_gen = embedding_generator
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def scrape_url(self, url_id: int, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single URL with retry logic."""
        context = None
        page = None
        
        try:
            logger.info(f"Starting to scrape URL {url_id}: {url}")
            
            # Mark as processing
            await self.db.update_url_status(url_id, 'processing')
            
            # Create browser context and page
            context = await browser_manager.create_context()
            page = await browser_manager.create_page(context)
            
            # Navigate to URL
            await page.goto(url, wait_until='networkidle', timeout=Config.TIMEOUT_SECONDS * 1000)
            
            # Perform interactions to reveal hidden content
            await ContentInteraction.interact_with_page(page)
            
            # Extract content
            extracted_data = await ContentExtractor.extract_page_content(page)
            
            # Validate content
            if not ContentExtractor.validate_content(extracted_data['content']):
                logger.warning(f"Content validation failed for URL {url_id}")
                await self.db.update_url_status(url_id, 'failed', 'Content validation failed')
                return None
            
            # Generate embedding
            embedding = await self.embedding_gen.generate_embedding(extracted_data['content'])
            
            # Prepare document data
            document_data = {
                'content': extracted_data['content'],
                'metadata': extracted_data['metadata'],
                'embedding': embedding
            }
            
            # Insert document
            doc_id = await self.db.insert_document(
                content=document_data['content'],
                metadata=document_data['metadata'],
                embedding=document_data['embedding']
            )
            
            if doc_id:
                # Mark as completed
                await self.db.update_url_status(url_id, 'completed')
                logger.info(f"Successfully scraped URL {url_id} -> Document {doc_id}")
                
                return {
                    'url_id': url_id,
                    'url': url,
                    'document_id': doc_id,
                    'word_count': extracted_data['word_count'],
                    'char_count': extracted_data['char_count']
                }
            else:
                raise Exception("Failed to insert document into database")
            
        except Exception as e:
            error_msg = f"Scraping failed: {str(e)}"
            logger.error(f"Error scraping URL {url_id}: {error_msg}")
            await self.db.update_url_status(url_id, 'failed', error_msg)
            return None
            
        finally:
            # Cleanup
            if page:
                try:
                    await page.close()
                except:
                    pass
            if context:
                try:
                    await browser_manager.close_context(context)
                except:
                    pass
    
    async def scrape_batch(self, url_batch: list) -> Dict[str, int]:
        """Scrape a batch of URLs."""
        results = {
            'total': len(url_batch),
            'success': 0,
            'failed': 0
        }
        
        logger.info(f"Processing batch of {len(url_batch)} URLs")
        
        # Process URLs concurrently
        tasks = []
        for url_info in url_batch:
            task = self.scrape_url(url_info['id'], url_info['url'])
            tasks.append(task)
        
        # Wait for all tasks to complete
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count results
        for result in batch_results:
            if isinstance(result, Exception):
                results['failed'] += 1
                logger.error(f"Batch task failed with exception: {result}")
            elif result:
                results['success'] += 1
            else:
                results['failed'] += 1
        
        logger.info(f"Batch completed: {results['success']} success, {results['failed']} failed")
        return results
    
    async def run(self):
        """Main scraping loop."""
        logger.info("Starting scraper")
        
        total_processed = 0
        total_success = 0
        total_failed = 0
        
        try:
            while True:
                # Get pending URLs
                urls = await self.db.get_pending_urls(limit=Config.BATCH_SIZE)
                
                if not urls:
                    logger.info("No more pending URLs to process")
                    break
                
                # Process batch
                batch_results = await self.scrape_batch(urls)
                
                total_processed += batch_results['total']
                total_success += batch_results['success']
                total_failed += batch_results['failed']
                
                # Log progress
                logger.info(
                    f"Progress: {total_processed} total, "
                    f"{total_success} success, {total_failed} failed"
                )
                
                # Small delay between batches
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            raise
        
        finally:
            logger.info(
                f"Scraping completed: {total_processed} total, "
                f"{total_success} success, {total_failed} failed"
            )
