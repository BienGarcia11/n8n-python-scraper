"""
Main RAG scraper worker with HTTP API endpoints.
Orchestrates entire scraping, chunking, and embedding pipeline.
"""
import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional
from supabase import acreate_client

from config import Config
from modules.scraper import PlaywrightScraper
from modules.extractor import ContentExtractor
from modules.chunker import TextChunker
from modules.embedder import EmbeddingGenerator
from api import app_instance, set_worker_instance

# Configure logging
logging.basicConfig(
    level=Config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)


class RAGScraperWorker:
    """Main worker for RAG scraping pipeline."""
    
    def __init__(self):
        """Initialize all components."""
        logger.info("Initializing RAG Scraper Worker...")
        
        # Validate configuration
        Config.validate()
        
        # Initialize Supabase client
        self.supabase = None
        self.supabase_url = Config.SUPABASE_URL
        self.supabase_key = Config.SUPABASE_KEY
        
        # Initialize components
        self.scraper: Optional[PlaywrightScraper] = None
        self.extractor = ContentExtractor()
        self.chunker = TextChunker(
            model=Config.EMBEDDING_MODEL,
            chunk_size_tokens=Config.CHUNK_SIZE_TOKENS,
            chunk_overlap_tokens=Config.CHUNK_OVERLAP_TOKENS,
        )
        self.embedder: Optional[EmbeddingGenerator] = None
        
        # Concurrency control
        self.semaphore = asyncio.Semaphore(Config.MAX_CONCURRENT_URLS)
        self.running = True
        self.start_time = datetime.utcnow().isoformat()
        
        # Statistics
        self.stats = {
            'urls_processed': 0,
            'urls_succeeded': 0,
            'urls_failed': 0,
            'chunks_created': 0,
            'embeddings_generated': 0,
        }
        
        # Bulk task tracking
        self.bulk_task = {
            'task_id': None,
            'status': 'idle',
            'total_urls': 0,
            'processed_urls': 0,
            'failed_urls': 0,
            'percentage': 0.0,
        }
        
        logger.info("RAG Scraper Worker initialized")
    
    async def initialize(self):
        """Initialize async components."""
        logger.info("Initializing async components...")
        
        # Initialize Supabase async client
        self.supabase = await acreate_client(
            self.supabase_url,
            self.supabase_key,
        )
        logger.info("Supabase client initialized")
        
        # Initialize Playwright scraper
        self.scraper = PlaywrightScraper(
            headless=Config.PLAYWRIGHT_HEADLESS,
            timeout=Config.PLAYWRIGHT_TIMEOUT,
            user_agents=Config.USER_AGENTS,
        )
        await self.scraper.start()
        logger.info("Playwright scraper started")
        
        # Initialize embedding generator
        self.embedder = EmbeddingGenerator(
            api_key=Config.OPENAI_API_KEY,
            model=Config.EMBEDDING_MODEL,
            batch_size=100,
            max_retries=Config.RETRY_ATTEMPTS,
        )
        logger.info("Embedding generator initialized")
        
        # Register worker with API
        set_worker_instance(self)
        logger.info("Worker registered with API")
    
    async def cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up resources...")
        
        if self.scraper:
            await self.scraper.stop()
        
        if self.embedder:
            await self.embedder.close()
        
        logger.info("Cleanup complete")
    
    async def fetch_pending_urls(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Fetch pending URLs from Supabase.
        
        Args:
            limit: Maximum number of URLs to fetch
            
        Returns:
            List of URL queue entries
        """
        try:
            response = self.supabase.table('url_queue').select('*').eq('status', 'pending').limit(limit).execute()
            
            if not response.data:
                logger.debug("No pending URLs found")
                return []
            
            logger.info(f"Fetched {len(response.data)} pending URLs")
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching pending URLs: {e}")
            return []
    
    async def update_url_status(
        self,
        url_id: int,
        status: str,
        error_message: Optional[str] = None,
        attempts: int = 0,
    ):
        """
        Update URL status in database.
        
        Args:
            url_id: URL queue entry ID
            status: New status ('processing', 'completed', 'failed')
            error_message: Error message if failed
            attempts: Number of attempts
        """
        try:
            update_data = {
                'status': status,
                'attempts': attempts,
                'updated_at': datetime.utcnow().isoformat(),
            }
            
            if error_message:
                update_data['error_message'] = error_message
            
            if status == 'completed':
                update_data['processed_at'] = datetime.utcnow().isoformat()
            
            self.supabase.table('url_queue').update(update_data).eq('id', url_id).execute()
            
            logger.debug(f"Updated URL {url_id} to status: {status}")
            
        except Exception as e:
            logger.error(f"Error updating URL {url_id}: {e}")
    
    async def store_documents(
        self,
        documents: List[Dict[str, Any]],
    ) -> bool:
        """
        Store documents with embeddings in Supabase.
        
        Args:
            documents: List of document dictionaries
            
        Returns:
            True if successful, False otherwise
        """
        if not documents:
            logger.warning("No documents to store")
            return False
        
        try:
            # Batch insert documents
            response = self.supabase.table('documents').insert(documents).execute()
            
            logger.info(f"Stored {len(documents)} documents in Supabase")
            return True
            
        except Exception as e:
            logger.error(f"Error storing documents: {e}")
            return False
    
    async def process_url(self, url_entry: Dict[str, Any]):
        """
        Process a single URL through the complete pipeline.
        
        Args:
            url_entry: URL queue entry dictionary
        """
        url_id = url_entry['id']
        url = url_entry['url']
        
        logger.info(f"Processing URL {url_id}: {url}")
        
        async with self.semaphore:  # Limit concurrent processing
            try:
                # Update status to processing
                await self.update_url_status(url_id, 'processing')
                
                # Step 1: Scrape URL
                logger.info(f"Scraping {url}")
                scrape_result = await self.scraper.scrape_with_retry(
                    url,
                    max_attempts=Config.RETRY_ATTEMPTS,
                )
                
                if not scrape_result:
                    raise Exception("Scraping failed")
                
                # Step 2: Extract content
                logger.info(f"Extracting content from {url}")
                extract_result = self.extractor.extract(
                    scrape_result['html'],
                    scrape_result['url'],
                )
                
                if not extract_result['content']:
                    raise Exception("Content extraction failed or returned empty content")
                
                # Validate content
                if not self.extractor.validate_content(extract_result['content']):
                    raise Exception("Content validation failed")
                
                # Step 3: Chunk text
                logger.info(f"Chunking content from {url}")
                chunks = self.chunker.chunk_text(
                    extract_result['content'],
                    title=extract_result['title'],
                )
                
                if not chunks:
                    raise Exception("No chunks created")
                
                # Step 4: Generate embeddings
                logger.info(f"Generating embeddings for {len(chunks)} chunks")
                chunk_texts = [chunk[0] for chunk in chunks]
                embeddings = await self.embedder.embed_chunks(chunk_texts)
                
                if not embeddings:
                    raise Exception("Embedding generation failed")
                
                if len(embeddings) != len(chunks):
                    raise Exception(
                        f"Embedding count mismatch: "
                        f"{len(embeddings)} != {len(chunks)}"
                    )
                
                # Step 5: Prepare documents for storage
                documents = []
                for i, (chunk_text, chunk_index, total_chunks) in enumerate(chunks):
                    doc = {
                        'url': scrape_result['url'],
                        'title': extract_result['title'],
                        'content': chunk_text,
                        'chunk_index': chunk_index,
                        'total_chunks': total_chunks,
                        'embedding': embeddings[i],
                    }
                    documents.append(doc)
                
                # Step 6: Store documents
                logger.info(f"Storing {len(documents)} documents")
                success = await self.store_documents(documents)
                
                if not success:
                    raise Exception("Failed to store documents")
                
                # Update statistics
                self.stats['urls_succeeded'] += 1
                self.stats['chunks_created'] += len(chunks)
                self.stats['embeddings_generated'] += len(embeddings)
                
                # Update status to completed
                await self.update_url_status(
                    url_id,
                    'completed',
                    attempts=url_entry.get('attempts', 0) + 1,
                )
                
                logger.info(f"Successfully processed URL {url_id}: {url}")
                
            except Exception as e:
                logger.error(f"Failed to process URL {url_id}: {e}")
                
                # Update statistics
                self.stats['urls_failed'] += 1
                
                # Update status to failed
                await self.update_url_status(
                    url_id,
                    'failed',
                    error_message=str(e),
                    attempts=url_entry.get('attempts', 0) + 1,
                )
            
            finally:
                self.stats['urls_processed'] += 1
    
    async def process_batch(self):
        """Process a batch of pending URLs."""
        # Fetch pending URLs
        urls = await self.fetch_pending_urls(limit=Config.MAX_CONCURRENT_URLS)
        
        if not urls:
            return
        
        # Process URLs concurrently with semaphore control
        tasks = [self.process_url(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    def print_statistics(self):
        """Print current statistics."""
        logger.info("=" * 50)
        logger.info("STATISTICS")
        logger.info("=" * 50)
        logger.info(f"URLs Processed: {self.stats['urls_processed']}")
        logger.info(f"URLs Succeeded: {self.stats['urls_succeeded']}")
        logger.info(f"URLs Failed: {self.stats['urls_failed']}")
        logger.info(f"Chunks Created: {self.stats['chunks_created']}")
        logger.info(f"Embeddings Generated: {self.stats['embeddings_generated']}")
        logger.info("=" * 50)
    
    async def run(self):
        """Main worker loop."""
        logger.info("Starting RAG Scraper Worker...")
        
        # Initialize components
        await self.initialize()
        
        # Setup signal handlers for graceful shutdown
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, shutting down...")
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            # Main loop
            while self.running:
                logger.info("Polling for pending URLs...")
                
                # Process batch of URLs
                await self.process_batch()
                
                # Print statistics
                self.print_statistics()
                
                # Wait before next poll
                logger.info(f"Sleeping for {Config.POLL_INTERVAL} seconds...")
                await asyncio.sleep(Config.POLL_INTERVAL)
            
        except asyncio.CancelledError:
            logger.info("Worker cancelled")
        except Exception as e:
            logger.error(f"Error in worker loop: {e}")
        finally:
            # Cleanup
            logger.info("Shutting down worker...")
            await self.cleanup()
            logger.info("Worker stopped")


async def main():
    """Main entry point."""
    worker = RAGScraperWorker()
    await worker.run()


if __name__ == "__main__":
    # Start FastAPI server if running directly (for Railway)
    import uvicorn
    logger.info("Starting HTTP API server on port 8000...")
    uvicorn.run(
        "main:app_instance",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
