"""
Playwright scraper module with anti-bot detection.
Manages browser contexts and pages for web scraping.
"""
import logging
import random
import os
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, TimeoutError
import asyncio

logger = logging.getLogger(__name__)


class PlaywrightScraper:
    """Async Playwright scraper with context management and anti-bot detection."""
    
    def __init__(
        self,
        headless: bool = True,
        timeout: int = 30000,
        user_agents: Optional[list] = None,
    ):
        """
        Initialize Playwright scraper.
        
        Args:
            headless: Run browser in headless mode
            timeout: Default timeout in milliseconds
            user_agents: List of user agent strings for rotation
        """
        self.headless = headless
        self.timeout = timeout
        self.user_agents = user_agents or [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        ]
        self.playwright = None
        self.browser: Optional[Browser] = None
        
        # Get browsers path from environment or use default
        self.browsers_path = os.getenv('PLAYWRIGHT_BROWSERS_PATH', '/home/worker/.cache/ms-playwright')
        logger.info(f"Playwright browsers path: {self.browsers_path}")
        
        logger.info(
            f"Initialized Playwright scraper: headless={headless}, "
            f"timeout={timeout}ms"
        )
    
    async def start(self):
        """Start Playwright and launch browser."""
        logger.info("Starting Playwright...")
        self.playwright = await async_playwright().start()
        
        # Launch Chromium browser (no custom path - let Playwright find it)
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
            ],
        )
        
        logger.info("Playwright browser started successfully")
    
    async def stop(self):
        """Stop Playwright and close browser."""
        logger.info("Stopping Playwright...")
        
        if self.browser:
            await self.browser.close()
            self.browser = None
        
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None
        
        logger.info("Playwright stopped successfully")
    
    def _get_random_user_agent(self) -> str:
        """Get a random user agent from the list."""
        return random.choice(self.user_agents)
    
    async def _create_context(self) -> BrowserContext:
        """
        Create a new browser context with anti-bot measures.
        
        Returns:
            BrowserContext with randomized settings
        """
        if not self.browser:
            raise RuntimeError("Browser not started. Call start() first.")
        
        context = await self.browser.new_context(
            user_agent=self._get_random_user_agent(),
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation'],
            geolocation={'latitude': 40.7128, 'longitude': -74.0060},
            color_scheme='light',
            reduced_motion='no-motion',
        )
        
        # Set additional headers
        await context.set_extra_http_headers({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'DNT': '1',
            'Connection': 'keep-alive',
        })
        
        return context
    
    async def _random_delay(self, min_seconds: float = 1.0, max_seconds: float = 3.0):
        """Sleep for a random duration to mimic human behavior."""
        delay = random.uniform(min_seconds, max_seconds)
        await asyncio.sleep(delay)
    
    async def scrape(
        self,
        url: str,
        wait_for_selector: Optional[str] = None,
        wait_for_timeout: int = 5000,
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape a URL and return HTML content.
        
        Args:
            url: URL to scrape
            wait_for_selector: CSS selector to wait for before scraping
            wait_for_timeout: Timeout in milliseconds for wait_for_selector
            
        Returns:
            Dictionary containing:
            - html: Page HTML content
            - url: Final URL (after redirects)
            - status: HTTP status code (if available)
        """
        context = None
        page = None
        
        try:
            # Create isolated context for this URL
            context = await self._create_context()
            page = await context.new_page()
            
            logger.info(f"Navigating to {url}")
            
            # Navigate to URL
            response = await page.goto(
                url,
                wait_until='networkidle',
                timeout=self.timeout,
            )
            
            # Wait for page to stabilize
            await self._random_delay(1.0, 2.0)
            
            # Wait for specific selector if provided
            if wait_for_selector:
                logger.info(f"Waiting for selector: {wait_for_selector}")
                try:
                    await page.wait_for_selector(
                        wait_for_selector,
                        timeout=wait_for_timeout,
                    )
                except TimeoutError:
                    logger.warning(
                        f"Selector {wait_for_selector} not found within timeout, "
                        "continuing anyway"
                    )
            
            # Get final URL (after redirects)
            final_url = page.url
            
            # Get HTML content
            html = await page.content()
            
            # Get status code if available
            status = response.status if response else None
            
            logger.info(
                f"Successfully scraped {url} "
                f"(final_url={final_url}, status={status}, "
                f"content_length={len(html)})"
            )
            
            return {
                'html': html,
                'url': final_url,
                'status': status,
            }
            
        except TimeoutError as e:
            logger.error(f"Timeout while scraping {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return None
        finally:
            # Always close page and context to prevent memory leaks
            if page:
                await page.close()
            if context:
                await context.close()
    
    async def scrape_with_retry(
        self,
        url: str,
        max_attempts: int = 3,
        wait_for_selector: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Scrape URL with retry logic and exponential backoff.
        
        Args:
            url: URL to scrape
            max_attempts: Maximum number of attempts
            wait_for_selector: CSS selector to wait for
            
        Returns:
            Scrape result dictionary or None if all attempts fail
        """
        delays = [2, 5, 10]  # Exponential backoff in seconds
        
        for attempt in range(1, max_attempts + 1):
            logger.info(f"Attempt {attempt}/{max_attempts} for {url}")
            
            result = await self.scrape(
                url,
                wait_for_selector=wait_for_selector,
            )
            
            if result:
                return result
            
            # Don't wait after last attempt
            if attempt < max_attempts:
                delay = delays[min(attempt - 1, len(delays) - 1)]
                logger.info(f"Waiting {delay}s before retry...")
                await asyncio.sleep(delay)
        
        logger.error(f"Failed to scrape {url} after {max_attempts} attempts")
        return None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.stop()
