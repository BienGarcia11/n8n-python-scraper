"""Content extraction from web pages."""
import logging
import re
from typing import Dict, Any, Optional
from playwright.async_api import Page
from bs4 import BeautifulSoup
from config import Config

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extracts and cleans content from web pages."""
    
    @staticmethod
    async def extract_page_content(page: Page) -> Dict[str, Any]:
        """Extract all relevant content from a page."""
        try:
            # Get page title
            title = await page.title()
            
            # Get URL
            url = page.url
            
            # Get HTML content
            html_content = await page.content()
            
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Extract metadata
            metadata = ContentExtractor._extract_metadata(soup, url, title)
            
            # Extract main content
            main_content = ContentExtractor._extract_main_content(soup)
            
            # Clean content
            cleaned_content = ContentExtractor._clean_content(main_content)
            
            result = {
                'url': url,
                'title': title,
                'content': cleaned_content,
                'metadata': metadata,
                'word_count': len(cleaned_content.split()),
                'char_count': len(cleaned_content)
            }
            
            logger.info(f"Extracted content from {url} ({result['word_count']} words)")
            return result
            
        except Exception as e:
            logger.error(f"Error extracting page content: {e}")
            raise
    
    @staticmethod
    def _extract_metadata(soup: BeautifulSoup, url: str, title: str) -> Dict[str, Any]:
        """Extract page metadata."""
        metadata = {
            'url': url,
            'title': title,
        }
        
        # Meta description
        description = soup.find('meta', attrs={'name': 'description'})
        if description:
            metadata['description'] = description.get('content', '')
        
        # Meta keywords
        keywords = soup.find('meta', attrs={'name': 'keywords'})
        if keywords:
            metadata['keywords'] = keywords.get('content', '')
        
        # Open Graph tags
        og_tags = ['og:title', 'og:description', 'og:image', 'og:type']
        for tag in og_tags:
            og_element = soup.find('meta', property=tag)
            if og_element:
                metadata[tag.replace('og:', 'og_')] = og_element.get('content', '')
        
        # Article metadata
        if soup.find('article'):
            metadata['content_type'] = 'article'
            
            # Try to extract author
            author = soup.find('meta', attrs={'name': 'author'})
            if author:
                metadata['author'] = author.get('content', '')
            
            # Try to extract publish date
            date = soup.find('meta', attrs={'name': 'article:published_time'})
            if date:
                metadata['published_date'] = date.get('content', '')
        else:
            metadata['content_type'] = 'webpage'
        
        return metadata
    
    @staticmethod
    def _extract_main_content(soup: BeautifulSoup) -> str:
        """Extract the main content from the page."""
        # Remove unwanted elements
        for element in soup.find_all(['script', 'style', 'noscript', 'iframe', 'nav', 'footer', 'header']):
            element.decompose()
        
        # Try to find main content area
        main_content = None
        
        # Priority 1: <main> tag
        main = soup.find('main')
        if main:
            main_content = main
        
        # Priority 2: <article> tag
        elif soup.find('article'):
            main_content = soup.find('article')
        
        # Priority 3: Common content container classes
        else:
            content_classes = [
                'content', 'article', 'post', 'entry',
                'main-content', 'post-content', 'article-content'
            ]
            for class_name in content_classes:
                element = soup.find(class_=re.compile(class_name, re.I))
                if element:
                    main_content = element
                    break
        
        # Fallback: Use body if no specific content found
        if not main_content:
            main_content = soup.find('body') or soup
        
        # Extract text
        text = main_content.get_text(separator=' ', strip=True)
        
        return text
    
    @staticmethod
    def _clean_content(text: str) -> str:
        """Clean and normalize extracted text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Remove special characters but keep basic punctuation
        text = re.sub(r'[^\w\s.,!?;:()-]', ' ', text)
        
        # Remove multiple punctuation
        text = re.sub(r'[.,!?;:]{2,}', '.', text)
        
        # Remove consecutive spaces
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @staticmethod
    def validate_content(content: str) -> bool:
        """Validate that content is meaningful."""
        # Minimum content requirements
        if len(content) < 100:
            logger.warning("Content too short (< 100 characters)")
            return False
        
        # Check for error pages
        error_indicators = [
            '404 not found', 'page not found', 'error 404',
            'access denied', 'forbidden', 'unauthorized',
            'this page cannot be found'
        ]
        
        content_lower = content.lower()
        if any(indicator in content_lower for indicator in error_indicators):
            logger.warning("Content appears to be an error page")
            return False
        
        # Check for meaningful content (minimum word count)
        words = content.split()
        if len(words) < 20:
            logger.warning("Content has too few words (< 20)")
            return False
        
        return True
    
    @staticmethod
    async def take_screenshot(page: Page, filename: str):
        """Take a screenshot of the current page."""
        try:
            await page.screenshot(path=filename, full_page=True)
            logger.debug(f"Screenshot saved to {filename}")
        except Exception as e:
            logger.error(f"Error taking screenshot: {e}")
