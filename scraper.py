import asyncio
import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from playwright.async_api import async_playwright, Browser, Page
from bs4 import BeautifulSoup
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import aiohttp

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WebScraper:
    def __init__(self):
        """Initialize the web scraper with Supabase and OpenAI clients."""
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_SERVICE_KEY')
        self.openai_api_key = os.getenv('OPENAI_API_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_KEY must be set in environment variables")
        
        if not self.openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set in environment variables")
        
        # Initialize clients
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        self.openai_client = AsyncOpenAI(api_key=self.openai_api_key)
        self.browser: Optional[Browser] = None
        self.playwright = None
        
        # Configuration
        self.max_concurrent_scrapes = 5
        self.page_timeout = 30000  # 30 seconds
        self.embedding_model = "text-embedding-3-small"
        self.max_content_length = 8191  # OpenAI token limit
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)
        logger.info("Browser launched successfully")
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed successfully")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def fetch_pending_urls(self, limit: int = 100) -> list[Dict[str, Any]]:
        """Fetch pending URLs from the url_queue table."""
        try:
            response = self.supabase.table('url_queue') \
                .select('*') \
                .eq('status', 'pending') \
                .limit(limit) \
                .order('created_at', asc=True) \
                .execute()
            
            urls = response.data
            logger.info(f"Fetched {len(urls)} pending URLs")
            return urls
        except Exception as e:
            logger.error(f"Error fetching pending URLs: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def update_url_status(self, url_id: int, status: str, error_message: Optional[str] = None):
        """Update the status of a URL in the queue."""
        try:
            update_data = {
                'status': status,
                'updated_at': datetime.utcnow().isoformat()
            }
            if error_message:
                update_data['metadata'] = {'error': error_message}
            
            self.supabase.table('url_queue') \
                .update(update_data) \
                .eq('id', url_id) \
                .execute()
            
            logger.info(f"Updated URL {url_id} status to {status}")
        except Exception as e:
            logger.error(f"Error updating URL status for {url_id}: {str(e)}")
            raise
    
    async def scrape_url(self, url: str) -> Dict[str, Any]:
        """Scrape a single URL using Playwright."""
        try:
            page: Page = await self.browser.new_page()
            
            # Set timeout and wait for page to load
            await page.set_default_timeout(self.page_timeout)
            
            # Navigate to URL
            await page.goto(url, wait_until='networkidle', timeout=self.page_timeout)
            
            # Get page content
            content = await page.content()
            
            # Extract additional metadata
            title = await page.title()
            
            # Extract text content using Playwright
            body_text = await page.evaluate('() => document.body.innerText')
            
            await page.close()
            
            # Parse with BeautifulSoup for better text extraction
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                script.decompose()
            
            # Get clean text
            clean_text = soup.get_text(separator=' ', strip=True)
            
            return {
                'title': title,
                'content': clean_text,
                'raw_html': content,
                'url': url,
                'scraped_at': datetime.utcnow().isoformat(),
                'status': 'success'
            }
            
        except Exception as e:
            logger.error(f"Error scraping URL {url}: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding for text using OpenAI."""
        try:
            # Truncate text if too long
            if len(text) > self.max_content_length:
                text = text[:self.max_content_length]
            
            response = await self.openai_client.embeddings.create(
                model=self.embedding_model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def save_document(self, url_data: Dict[str, Any], scraped_data: Dict[str, Any], embedding: list[float]):
        """Save scraped document with embedding to documents table."""
        try:
            document_data = {
                'content': scraped_data['content'],
                'metadata': {
                    'url': url_data['url'],
                    'title': scraped_data['title'],
                    'url_queue_id': url_data['id'],
                    'scraped_at': scraped_data['scraped_at']
                },
                'embedding': embedding,
                'created_at': datetime.utcnow().isoformat(),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            self.supabase.table('documents') \
                .insert(document_data) \
                .execute()
            
            logger.info(f"Saved document for URL {url_data['url']}")
            
        except Exception as e:
            logger.error(f"Error saving document for URL {url_data['url']}: {str(e)}")
            raise
    
    async def process_url(self, url_data: Dict[str, Any]):
        """Process a single URL: scrape, generate embedding, and save."""
        url_id = url_data['id']
        url = url_data['url']
        
        try:
            logger.info(f"Processing URL: {url}")
            
            # Mark as processing
            await self.update_url_status(url_id, 'processing')
            
            # Scrape the URL
            scraped_data = await self.scrape_url(url)
            
            # Generate embedding
            embedding = await self.generate_embedding(scraped_data['content'])
            
            # Save to documents table
            await self.save_document(url_data, scraped_data, embedding)
            
            # Mark as completed
            await self.update_url_status(url_id, 'completed')
            
            logger.info(f"Successfully processed URL: {url}")
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Failed to process URL {url}: {error_message}")
            await self.update_url_status(url_id, 'failed', error_message)
    
    async def process_urls_concurrently(self, urls: list[Dict[str, Any]]):
        """Process multiple URLs concurrently."""
        semaphore = asyncio.Semaphore(self.max_concurrent_scrapes)
        
        async def process_with_semaphore(url_data):
            async with semaphore:
                await self.process_url(url_data)
        
        tasks = [process_with_semaphore(url_data) for url_data in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run(self, max_urls: Optional[int] = None):
        """Main method to run the scraper."""
        logger.info("Starting web scraper...")
        
        async with self:
            while True:
                # Fetch pending URLs
                urls = await self.fetch_pending_urls(limit=max_urls or 100)
                
                if not urls:
                    logger.info("No more pending URLs to process. Exiting.")
                    break
                
                # Process URLs concurrently
                await self.process_urls_concurrently(urls)
                
                # If max_urls is set, exit after processing that many
                if max_urls and len(urls) < max_urls:
                    break
        
        logger.info("Web scraper completed!")


async def main():
    """Main entry point."""
    max_urls = os.getenv('MAX_URLS_PER_RUN')
    max_urls = int(max_urls) if max_urls else None
    
    scraper = WebScraper()
    await scraper.run(max_urls=max_urls)


if __name__ == "__main__":
    asyncio.run(main())
