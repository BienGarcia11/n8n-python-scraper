"""
Specialized scraper for FYI.app support documentation.
Targets the article container class for clean content extraction.
"""
from .base_scraper import BaseScraper


class FYISupportScraper(BaseScraper):
    """
    Scraper specifically designed for FYI.app support knowledge base.
    
    Extracts only the main article content by targeting the specific class:
    'lt-article-container__column lt-article-container__article'
    """
    
    def __init__(
        self,
        sitemap_url: str = "https://support.fyi.app/hc/sitemap.xml",
        output_file: str = "scraped_data.csv",
        max_concurrency: int = 3,
        batch_size: int = 15,
        bypass_cache: bool = True,
        use_magic: bool = True
    ):
        """
        Initialize FYI.app support scraper.
        
        Args:
            sitemap_url: URL of the sitemap (defaults to FYI.app support sitemap)
            output_file: Path to output CSV file
            max_concurrency: Maximum concurrent requests
            batch_size: Number of URLs to process per batch
            bypass_cache: Whether to bypass cache
            use_magic: Whether to use crawl4ai's magic mode
        """
        super().__init__(
            sitemap_url=sitemap_url,
            output_file=output_file,
            max_concurrency=max_concurrency,
            batch_size=batch_size,
            bypass_cache=bypass_cache,
            use_magic=use_magic
        )
        
        # CSS selector for the main article container
        self.article_selector = ".lt-article-container__column.lt-article-container__article"
    
    def should_scrape_url(self, url: str) -> bool:
        """
        Filter URLs to scrape.
        
        Skip URLs that are not article pages (e.g., search, account, etc.).
        
        Args:
            url: URL to check
            
        Returns:
            True if URL should be scraped, False otherwise
        """
        # Skip search results and other non-article pages
        skip_patterns = [
            '/search?',
            '/account/',
            '/subscriptions/',
            '/requests/',
            '/community/',
        ]
        
        for pattern in skip_patterns:
            if pattern in url:
                self.logger.debug(f"Skipping non-article URL: {url}")
                return False
        
        # Only scrape URLs that look like articles
        # FYI.app support articles typically have /hc/en-us/articles/ pattern
        if '/articles/' in url or '/hc/en-us/' in url:
            return True
        
        # For FYI.app, we're being conservative and only scraping article URLs
        if '/hc/' not in url:
            self.logger.debug(f"Skipping non-help-center URL: {url}")
            return False
        
        return True
    
    def get_crawler_params(self) -> dict:
        """
        Get crawl4ai parameters customized for FYI.app.
        
        Uses CSS selector to target only the article content.
        
        Returns:
            Dictionary of crawler parameters
        """
        base_params = super().get_crawler_params()
        
        # Override with FYI.app specific settings
        # Use css_selector to target only the article container
        fyi_params = {
            **base_params,
            'css_selector': self.article_selector,
            # Don't need exclude_tags since we're targeting specific container
            'exclude_tags': [],
            'remove_overlay_elements': True,
        }
        
        return fyi_params
    
    def extract_content(self, result) -> dict:
        """
        Extract content from crawl result.
        
        Since we're using CSS selector, the markdown should already be clean.
        Extract additional metadata if available.
        
        Args:
            result: crawl4ai result object
            
        Returns:
            Dictionary with extracted data (url, title, content, status)
        """
        if not result.success:
            return {
                "url": result.url,
                "title": "Error",
                "content": "",
                "status": "Fail"
            }
        
        # Extract title from metadata or HTML
        title = result.metadata.get("title", "No Title")
        
        # The content should already be clean since we used CSS selector
        content = result.markdown if result.markdown else ""
        
        return {
            "url": result.url,
            "title": title,
            "content": content,
            "status": "Success"
        }
