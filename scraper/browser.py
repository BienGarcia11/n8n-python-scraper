"""Browser management for Playwright."""
import asyncio
import logging
import random
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from config import Config

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages Playwright browser instances for scraping."""
    
    def __init__(self):
        """Initialize browser manager."""
        self.playwright = None
        self.browser: Optional[Browser] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Playwright and browser."""
        if self._initialized:
            return
        
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=Config.HEADLESS,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu'
                ]
            )
            self._initialized = True
            logger.info("Browser manager initialized")
        except Exception as e:
            logger.error(f"Error initializing browser: {e}")
            raise
    
    async def create_context(self) -> BrowserContext:
        """Create a new browser context with random user agent."""
        if not self._initialized:
            await self.initialize()
        
        user_agent = random.choice(Config.USER_AGENTS)
        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='America/New_York',
            permissions=['geolocation']
        )
        
        logger.debug(f"Created browser context with UA: {user_agent[:50]}...")
        return context
    
    async def create_page(self, context: BrowserContext) -> Page:
        """Create a new page in the given context."""
        page = await context.new_page()
        
        # Set default timeout
        page.set_default_timeout(Config.TIMEOUT_SECONDS * 1000)
        
        # Block unnecessary resources for speed
        await page.route("**/*.{png,jpg,jpeg,gif,svg,ico,webp,woff,woff2,ttf}", lambda route: route.abort())
        await page.route("**/*.{css}", lambda route: route.abort())
        
        return page
    
    async def close_context(self, context: BrowserContext):
        """Close a browser context."""
        try:
            await context.close()
            logger.debug("Closed browser context")
        except Exception as e:
            logger.error(f"Error closing context: {e}")
    
    async def close(self):
        """Close browser and cleanup."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        self._initialized = False
        logger.info("Browser manager closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global browser manager instance
browser_manager = BrowserManager()
