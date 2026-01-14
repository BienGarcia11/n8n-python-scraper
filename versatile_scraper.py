"""
Versatile Web Scraper using Playwright and BeautifulSoup
Extracts clean, unedited data from various websites with flexible configuration
"""

import asyncio
import json
import re
import html
from datetime import datetime
from typing import Dict, List, Optional, Union
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# Import structured logging
from logger_config import setup_logger

# Setup logger
logger = setup_logger(__name__)


class VersatileScraper:
    """Flexible web scraper that can be adapted for different websites"""
    
    def __init__(self, url: str, config: Optional[Dict] = None):
        """
        Initialize scraper with optional configuration
        
        Args:
            url: Target website URL
            config: Dictionary with custom selectors and settings
        """
        self.url = url
        self.raw_html = None
        self.soup = None
        
        # Default configuration - can be overridden
        default_config = {
            'name': 'default',
            'title_selectors': ['h1', 'title', '.article-title', '[itemprop="headline"]',
                            '[data-test-id="article-title"]'],
            'content_selectors': ['article', 'main', '.content', '#content', '[role="main"]',
                            '[data-test-id="article-content"]', '.article-content'],
            'paragraph_selectors': ['p'],
            'heading_selectors': ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
            'list_selectors': ['ul', 'ol'],
            'link_selectors': ['a'],
            'code_selectors': ['pre', 'code', '.code-block', '[class*="code"]'],
            'image_selectors': ['img', '[class*="image"]', '[role="img"]'],
            'remove_selectors': ['script', 'style', 'nav', 'footer', 'header', 'aside', 
                            '.advertisement', '.sidebar', '.comments', '.cookie-banner',
                            '.popup', '.modal', '[class*="nav"]', '[class*="footer"]'],
            'wait_timeout': 30000,
            'wait_strategy': 'domcontentloaded'
        }
        
        # Merge provided config with defaults (provided config takes precedence)
        self.config = {**default_config, **(config or {})}
        
        self.data = {
            'url': url,
            'scraper_config': self.config['name'],
            'scraped_at': datetime.now().isoformat(),
            'metadata': {},
            'content': {}
        }
    
    async def fetch_page(self):
        """Fetch webpage using Playwright"""
        logger.info("Fetching: " + self.url, extra={"url": self.url})
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']
            )
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            
            try:
                # Navigate to page with different wait strategies
                wait_until = self.config.get('wait_strategy', 'domcontentloaded')
                await page.goto(self.url, wait_until=wait_until,
                          timeout=self.config['wait_timeout'])
                
                # Wait for content to load
                await page.wait_for_timeout(2000)
                
                # Get page content
                self.raw_html = await page.content()
                
                # Clean up - remove scripts and styles
                self.raw_html = re.sub(r'<script[^>]*>.*?</script>', '', self.raw_html, flags=re.DOTALL)
                self.raw_html = re.sub(r'<style[^>]*>.*?</style>', '', self.raw_html, flags=re.DOTALL)
                
                logger.info("Page fetched successfully", extra={"url": self.url, "html_length": len(self.raw_html)})
                
            except Exception as e:
                logger.error("Error fetching page: " + str(e), extra={"url": self.url})
                raise
            finally:
                await browser.close()
    
    def parse_html(self):
        """Parse HTML using BeautifulSoup"""
        self.soup = BeautifulSoup(self.raw_html, 'html.parser')
        logger.debug("HTML parsed successfully")
    
    def extract_metadata(self) -> Dict:
        """Extract metadata from page"""
        metadata = {}
        
        # Try different title selectors
        for selector in self.config['title_selectors']:
            title = self.soup.select_one(selector)
            if title:
                metadata['title'] = self.clean_text(title.get_text())
                break
        
        # Extract meta description
        meta_desc = self.soup.find('meta', attrs={'name': 'description'})
        if meta_desc:
            metadata['description'] = meta_desc.get('content', '')
        
        # Extract meta keywords
        meta_keywords = self.soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords:
            metadata['keywords'] = meta_keywords.get('content', '')
        
        # Extract author if available
        author_selectors = ['[rel="author"]', '.author', '[itemprop="author"]',
                          '.byline', '[class*="author"]', '[data-test-id="article-author"]']
        for selector in author_selectors:
            author = self.soup.select_one(selector)
            if author:
                metadata['author'] = self.clean_text(author.get_text())
                break
        
        # Extract publication date if available
        date_selectors = ['time[datetime]', '[datetime]', '.date', '.published',
                        '[itemprop="datePublished"]', '[itemprop="dateModified"]',
                        '[class*="date"]', '[data-test-id="article-date"]']
        for selector in date_selectors:
            date_element = self.soup.select_one(selector)
            if date_element:
                metadata['publication_date'] = (date_element.get('datetime') or 
                                                  date_element.get('content') or
                                                  date_element.get('datetime') or
                                                  self.clean_text(date_element.get_text()))
                break
        
        # Extract canonical URL
        canonical = self.soup.find('link', attrs={'rel': 'canonical'})
        if canonical:
            metadata['canonical_url'] = canonical.get('href', '')
        
        return metadata
    
    def extract_content(self) -> Dict:
        """Extract structured content from page"""
        content = {}
        
        # Find main content area
        main_content = None
        for selector in self.config['content_selectors']:
            element = self.soup.select_one(selector)
            if element:
                main_content = element
                break
        
        # If no main content found, use body
        if not main_content:
            main_content = self.soup.find('body')
        
        if main_content:
            # Remove unwanted elements
            for selector in self.config['remove_selectors']:
                for element in main_content.select(selector):
                    element.decompose()
            
            # Extract headings
            headings = []
            for h in main_content.find_all(self.config['heading_selectors']):
                text = self.clean_text(h.get_text())
                if text and len(text) > 0:
                    headings.append({
                        'level': h.name,
                        'text': text,
                        'id': h.get('id', '')
                    })
            content['headings'] = headings
            
            # Extract paragraphs
            paragraphs = []
            for p in main_content.find_all(self.config['paragraph_selectors']):
                text = self.clean_text(p.get_text())
                if text and len(text) > 20:  # Filter very short paragraphs
                    paragraphs.append(text)
            content['paragraphs'] = paragraphs
            
            # Extract lists
            lists = []
            for lst in main_content.find_all(self.config['list_selectors']):
                items = []
                for li in lst.find_all('li', recursive=False):
                    text = self.clean_text(li.get_text())
                    if text:
                        items.append(text)
                if items:
                    lists.append({
                        'type': lst.name,
                        'items': items,
                        'id': lst.get('id', '')
                    })
            content['lists'] = lists
            
            # Extract links
            links = []
            for a in main_content.find_all(self.config['link_selectors'], href=True):
                text = self.clean_text(a.get_text())
                href = a['href']
                if text and href:
                    links.append({
                        'text': text,
                        'url': href
                    })
            content['links'] = links
            
            # Extract code blocks if any
            code_blocks = []
            for code in main_content.find_all(self.config['code_selectors']):
                text = self.clean_text(code.get_text())
                if text:
                    code_blocks.append(text)
            content['code_blocks'] = code_blocks
            
            # Extract images
            images = []
            for img in main_content.find_all(self.config['image_selectors']):
                alt_text = img.get('alt', '')
                src = img.get('src', '')
                if src:
                    images.append({
                        'alt': self.clean_text(alt_text),
                        'src': src
                    })
            content['images'] = images
        
        return content
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove HTML entities
        text = html.unescape(text)
        
        # Strip leading/trailing whitespace
        text = text.strip()
        
        return text
    
    def extract_full_text(self) -> str:
        """Extract the full text content in a clean format by combining structured content"""
        # Build full text from structured content that was already extracted and cleaned
        parts = []
        
        # Add metadata title if available
        if self.data.get('metadata', {}).get('title'):
            parts.append(self.data['metadata']['title'])
            parts.append('')  # Empty line
        
        # Add headings and their associated content
        headings = self.data.get('content', {}).get('headings', [])
        paragraphs = self.data.get('content', {}).get('paragraphs', [])
        lists = self.data.get('content', {}).get('lists', [])
        
        # Track which headings we've used
        heading_index = 0
        
        # Add paragraphs (these are the main content)
        for para in paragraphs:
            # Skip very short paragraphs that are likely labels
            if len(para) < 10:
                continue
            
            # Check if this paragraph starts a new section (followed by a heading later)
            if para and not para[-1] in '.!?':
                para = para + '.'
            
            parts.append(para)
        
        # Add lists
        for lst in lists:
            if lst['type'] == 'ul':
                # Unordered list
                for item in lst['items']:
                    if len(item) > 5:  # Skip very short items
                        parts.append("• " + item)
            else:
                # Ordered list
                for i, item in enumerate(lst['items'], 1):
                    if len(item) > 5:  # Skip very short items
                        parts.append(str(i) + ". " + item)
            
            parts.append('')  # Empty line after lists
        
        # Join and clean up
        text = '\n'.join(parts)
        text = self.clean_text(text)
        
        # Clean up multiple empty lines
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        return text
    
    def clean_full_text_postprocessing(self, text: str) -> str:
        """Post-process full text to remove unwanted sections that may have been missed"""
        lines = text.split('\n')
        clean_lines = []
        skip_until_empty = False
        skip_keywords = [
            'cookie settings', 'we use cookies', 'functional cookies',
            'performance cookies', 'targeting cookies', 'strictly necessary cookies',
            'manage consent preferences', 'cookie list', 'allow all',
            'confirm my choices', 'back button', 'search icon', 'filter icon',
            'was this page helpful?', 'yes', 'no', 'still have questions?',
            'contact xero support', 'start a discussion', 'product ideas',
            'skip to main content'
        ]
        
        for line in lines:
            line = line.strip()
            if not line:
                if skip_until_empty:
                    skip_until_empty = False
                clean_lines.append('')
                continue
            
            lower_line = line.lower()
            
            # Check if this line contains any skip keywords
            if any(keyword in lower_line for keyword in skip_keywords):
                skip_until_empty = True
                continue
            
            if skip_until_empty:
                continue
            
            # Filter out very short lines that are likely navigation
            if len(line) < 3 and not line.isupper():
                continue
            
            clean_lines.append(line)
        
        # Join and clean up multiple empty lines
        result = '\n'.join(clean_lines)
        result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
        result = result.strip()
        
        return result
    
    async def scrape(self) -> Dict:
        """Main scraping method"""
        logger.info("Starting scrape for: " + self.url, extra={"url": self.url, "config": self.config['name']})
        
        # Fetch page
        await self.fetch_page()
        
        # Parse HTML
        self.parse_html()
        
        # Extract data
        self.data['metadata'] = self.extract_metadata()
        self.data['content'] = self.extract_content()
        self.data['full_text'] = self.extract_full_text()
        
        logger.info("Data extracted successfully", extra={"url": self.url, "title": self.data.get('metadata', {}).get('title', 'N/A')})
        return self.data
    
    def save_to_json(self, filename: str):
        """Save scraped data to JSON file"""
        logger.info("Saving scraped data to " + filename, extra={"filename": filename, "url": self.url})
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        logger.info("Data saved successfully", extra={"filename": filename})


# Preset configurations for common website types
WEBSITE_PRESETS = {
    'blog': {
        'name': 'blog',
        'title_selectors': ['h1', '[class*="post-title"]', '[itemprop="headline"]'],
        'content_selectors': ['article', '[class*="post-content"]', '[itemprop="articleBody"]'],
        'remove_selectors': ['script', 'style', 'nav', 'footer', 'aside', '[class*="sidebar"]',
                          '[class*="comments"]', '.related-posts'],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    },
    
    'news': {
        'name': 'news',
        'title_selectors': ['h1', '[class*="article-title"]', '[data-test-id="headline"]'],
        'content_selectors': ['article', '[class*="article-body"]', '[class*="story-content"]'],
        'remove_selectors': ['script', 'style', 'nav', 'footer', 'aside', '[class*="ad"]',
                          '[class*="sidebar"]', '[class*="newsletter"]'],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    },
    
    'documentation': {
        'name': 'documentation',
        'title_selectors': ['h1', '[class*="docs-title"]', '[role="heading"]'],
        'content_selectors': ['main', '[class*="docs-content"]', '[class*="markdown-body"]'],
        'remove_selectors': ['script', 'style', 'nav', 'footer', 'aside', '[class*="toc"]',
                          '[class*="navigation"]', '.breadcrumb'],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    },
    
    'ecommerce': {
        'name': 'ecommerce',
        'title_selectors': ['h1', '[class*="product-title"]', '[itemprop="name"]'],
        'content_selectors': ['[class*="product-description"]', '[itemprop="description"]',
                            '[class*="details"]'],
        'remove_selectors': ['script', 'style', 'nav', 'footer', 'aside', '[class*="cart"]',
                          '[class*="related-products"]', '[class*="reviews"]'],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    },
    
    'xero': {
        'name': 'xero',
        'title_selectors': ['h1', 'article h1', '.article-title', '[data-test-id="article-title"]'],
        'content_selectors': ['article', '[data-test-id="article-content"]', '.article-content'],
        'remove_selectors': ['script', 'style', 'nav', 'footer', 'aside', 'header',
                          '[class*="cookie"]', '[class*="consent"]', '[id*="cookie"]',
                          '.cookie-banner', '.cookie-settings', '[id*="ot-pc"]',
                          '[class*="nav"]', '[class*="header"]', '[class*="footer"]',
                          '.breadcrumb', '[class*="breadcrumb"]',
                          '.search', '[class*="search"]', '[id*="search"]',
                          '.skip-link', '[class*="skip"]',
                          '.back-button', '[class*="back"]',
                          '[data-test-id="was-this-page-helpful"]',
                          '[data-test-id="still-have-questions"]',
                          '[class*="social-share"]', '[class*="share"]'],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    }
}


async def main():
    """Main function to run versatile scraper"""
    # Example: Scrape a news article
    url = "https://central.xero.com/0/article/Suspend-archive-or-delete-a-tax-return-in-Tax-manager"
    
    # Use a preset configuration or create custom
    config = WEBSITE_PRESETS['xero']  # Or use custom config dict
    
    # Alternative: Create custom configuration
    # config = {
    #     'name': 'custom',
    #     'content_selectors': ['#main-content', '.article'],
    #     'remove_selectors': ['script', 'style', '.ads']
    # }
    
    # Create scraper instance
    scraper = VersatileScraper(url, config)
    
    # Scrape page
    data = await scraper.scrape()
    
    # Save to JSON file
    output_file = "scraped_data.json"
    scraper.save_to_json(output_file)
    
    # Log summary
    summary = {
        "title": data.get('metadata', {}).get('title', 'N/A'),
        "url": data['url'],
        "configuration": data.get('scraper_config', 'N/A'),
        "headings_count": len(data.get('content', {}).get('headings', [])),
        "paragraphs_count": len(data.get('content', {}).get('paragraphs', [])),
        "lists_count": len(data.get('content', {}).get('lists', [])),
        "links_count": len(data.get('content', {}).get('links', [])),
        "images_count": len(data.get('content', {}).get('images', [])),
        "full_text_length": len(data.get('full_text', ''))
    }
    logger.info("SCRAPING SUMMARY", extra=summary)
    
    # Automatically generate embeddings after scraping
    logger.info("Generating embeddings...")
    try:
        from embedding_generator import EmbeddingGenerator
        generator = EmbeddingGenerator()
        # Use scraped_data.json with optimized parameters
        generator.process(input_file=output_file, chunk_size=800, overlap=100)
        logger.info("Embeddings generated successfully")
    except Exception as e:
        logger.warning("Could not generate embeddings: " + str(e), extra={"error": str(e)})
        logger.warning("Make sure OPENAI_API_KEY is set in .env file")


if __name__ == "__main__":
    asyncio.run(main())
