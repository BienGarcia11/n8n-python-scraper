import asyncio
import os
import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page
from supabase import create_client, Client
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "10"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))
SCRAPER_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT", "30000"))

# Initialize clients
supabase: Optional[Client] = None
openai_client: Optional[AsyncOpenAI] = None


class URLScraper:
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.playwright = None
        
    async def init(self):
        """Initialize Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox']
        )
        logger.info("Playwright browser initialized")
        
    async def close(self):
        """Close browser and cleanup"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        logger.info("Browser closed")
        
    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Scrape a single URL and return content"""
        if not self.browser:
            await self.init()
            
        page: Optional[Page] = None
        try:
            page = await self.browser.new_page(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            logger.info(f"Scraping URL: {url}")
            await page.goto(url, wait_until='networkidle', timeout=SCRAPER_TIMEOUT)
            
            # Wait for content to load
            await asyncio.sleep(1)
            
            # Get page content
            content = await page.content()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(content, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(["script", "style", "noscript"]):
                script.decompose()
            
            # Extract text content
            text = soup.get_text(separator='\n', strip=True)
            
            # Extract metadata
            title = soup.find('title')
            title_text = title.get_text().strip() if title else url
            
            meta_description = soup.find('meta', attrs={'name': 'description'})
            description = meta_description.get('content', '') if meta_description else ''
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return {
                'url': url,
                'title': title_text,
                'description': description,
                'content': text[:100000],  # Limit content size
                'scraped_at': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error scraping {url}: {str(e)}")
            return None
        finally:
            if page:
                await page.close()


async def generate_embedding(text: str) -> Optional[list]:
    """Generate embedding for text using OpenAI"""
    try:
        response = await openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # OpenAI limit
            encoding_format="float"
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding: {str(e)}")
        return None


async def update_url_status(url_id: int, status: str, error_message: Optional[str] = None):
    """Update URL status in url_queue table"""
    try:
        data = {
            'status': status,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if error_message:
            data['error_message'] = error_message
            
        supabase.table('url_queue').update(data).eq('id', url_id).execute()
    except Exception as e:
        logger.error(f"Error updating URL status: {str(e)}")


async def insert_document(scraped_data: Dict[str, Any], embedding: list):
    """Insert scraped document with embedding into documents table"""
    try:
        document_data = {
            'content': scraped_data['content'],
            'metadata': {
                'url': scraped_data['url'],
                'title': scraped_data['title'],
                'description': scraped_data['description'],
                'scraped_at': scraped_data['scraped_at']
            },
            'embedding': embedding
        }
        
        supabase.table('documents').insert(document_data).execute()
        logger.info(f"Document inserted for URL: {scraped_data['url']}")
    except Exception as e:
        logger.error(f"Error inserting document: {str(e)}")
        raise


async def process_url(url_record: Dict[str, Any], scraper: URLScraper) -> bool:
    """Process a single URL with retries"""
    url_id = url_record['id']
    url = url_record['url']
    
    for attempt in range(MAX_RETRIES):
        try:
            # Mark as processing
            await update_url_status(url_id, 'processing')
            
            # Scrape URL
            scraped_data = await scraper.scrape_url(url)
            
            if not scraped_data:
                raise Exception("Failed to scrape URL - no content returned")
            
            if len(scraped_data['content']) < 50:
                raise Exception("Content too short - likely not useful")
            
            # Generate embedding
            embedding = await generate_embedding(scraped_data['content'])
            
            if not embedding:
                raise Exception("Failed to generate embedding")
            
            # Insert document
            await insert_document(scraped_data, embedding)
            
            # Mark as completed
            await update_url_status(url_id, 'completed')
            logger.info(f"Successfully processed URL: {url}")
            return True
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1}/{MAX_RETRIES} failed for {url}: {str(e)}")
            
            if attempt == MAX_RETRIES - 1:
                await update_url_status(url_id, 'failed', str(e))
                logger.error(f"Failed to process URL after {MAX_RETRIES} attempts: {url}")
                return False
            
            # Wait before retry
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    return False


async def get_pending_urls(limit: int = BATCH_SIZE) -> list:
    """Get pending URLs from url_queue"""
    try:
        result = supabase.table('url_queue').select('*').eq('status', 'pending').limit(limit).execute()
        return result.data
    except Exception as e:
        logger.error(f"Error fetching pending URLs: {str(e)}")
        return []


async def process_batch(urls: list, scraper: URLScraper):
    """Process a batch of URLs concurrently"""
    tasks = [process_url(url_record, scraper) for url_record in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = sum(1 for r in results if r is True)
    logger.info(f"Batch completed: {success_count}/{len(urls)} successful")
    
    return success_count


async def main():
    """Main scraper function"""
    global supabase, openai_client
    
    # Validate environment variables
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY environment variable not set")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY environment variable not set")
    
    # Initialize clients
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    logger.info("Scraper initialized")
    
    # Initialize scraper
    scraper = URLScraper()
    await scraper.init()
    
    try:
        total_processed = 0
        while True:
            # Get pending URLs
            pending_urls = await get_pending_urls(BATCH_SIZE)
            
            if not pending_urls:
                logger.info("No more pending URLs to process")
                break
            
            logger.info(f"Processing batch of {len(pending_urls)} URLs")
            
            # Process batch
            success_count = await process_batch(pending_urls, scraper)
            total_processed += success_count
            
            # Brief pause between batches
            await asyncio.sleep(1)
        
        logger.info(f"Scraping completed. Total processed: {total_processed}")
        
    finally:
        await scraper.close()
        logger.info("Scraper shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
