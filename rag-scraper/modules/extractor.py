"""
Content extraction module using Trafilatura.
Extracts clean text from HTML, removing navbars, ads, and other clutter.
"""
import logging
from typing import Optional, Dict, Any
import trafilatura

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extracts clean content from HTML using Trafilatura."""
    
    @staticmethod
    def extract(
        html: str,
        url: str,
        include_comments: bool = False,
        include_tables: bool = False,
        no_fallback: bool = False,
    ) -> Dict[str, Any]:
        """
        Extract main content from HTML.
        
        Args:
            html: Raw HTML content
            url: Source URL (for metadata)
            include_comments: Whether to include comments
            include_tables: Whether to include table content
            no_fallback: If True, return None when extraction fails
            
        Returns:
            Dictionary containing:
            - content: Extracted text
            - title: Page title
            - author: Page author (if available)
            - date: Publication date (if available)
            - url: Source URL
        """
        try:
            # Use Trafilatura to extract content
            extracted = trafilatura.extract(
                html,
                include_comments=include_comments,
                include_tables=include_tables,
                no_fallback=no_fallback,
                output_format="json",
                url=url,
            )
            
            if not extracted:
                logger.warning(f"No content extracted from {url}")
                return {
                    "content": None,
                    "title": None,
                    "author": None,
                    "date": None,
                    "url": url,
                }
            
            # Parse the JSON output
            import json
            data = json.loads(extracted)
            
            # Clean up the content
            content = data.get("text", "")
            title = data.get("title", "")
            author = data.get("author", "")
            date = data.get("date", "")
            
            # Clean content: remove excessive whitespace
            if content:
                content = " ".join(content.split())
            
            if title:
                title = title.strip()
            
            logger.info(f"Extracted {len(content)} characters from {url}")
            
            return {
                "content": content,
                "title": title,
                "author": author,
                "date": date,
                "url": url,
            }
            
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            if no_fallback:
                return {
                    "content": None,
                    "title": None,
                    "author": None,
                    "date": None,
                    "url": url,
                }
            # Fallback: return raw text
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(html, "html.parser")
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                content = soup.get_text()
                content = " ".join(content.split())
                logger.warning(f"Used fallback extraction for {url}")
                return {
                    "content": content,
                    "title": soup.title.string if soup.title else "",
                    "author": None,
                    "date": None,
                    "url": url,
                }
            except Exception as fallback_error:
                logger.error(f"Fallback extraction also failed for {url}: {fallback_error}")
                return {
                    "content": None,
                    "title": None,
                    "author": None,
                    "date": None,
                    "url": url,
                }
    
    @staticmethod
    def validate_content(content: str, min_length: int = 100) -> bool:
        """
        Validate extracted content meets minimum requirements.
        
        Args:
            content: Extracted text content
            min_length: Minimum character length
            
        Returns:
            True if content is valid, False otherwise
        """
        if not content or not isinstance(content, str):
            return False
        
        if len(content) < min_length:
            logger.warning(f"Content too short: {len(content)} < {min_length}")
            return False
        
        # Check for meaningful content (not just special characters)
        if len(content.strip()) == 0:
            return False
        
        return True
