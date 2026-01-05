"""Dynamic content interaction handlers."""
import asyncio
import logging
from typing import List
from playwright.async_api import Page
from config import Config

logger = logging.getLogger(__name__)


class ContentInteraction:
    """Handles interaction with dynamic content on web pages."""
    
    @staticmethod
    async def scroll_full_page(page: Page):
        """Scroll through entire page to trigger lazy loading."""
        try:
            logger.debug("Starting full page scroll")
            
            # Get initial page height
            previous_height = 0
            current_height = await page.evaluate("document.body.scrollHeight")
            
            # Scroll in increments
            scroll_increment = 500
            position = 0
            
            while position < current_height:
                await page.evaluate(f"window.scrollTo(0, {position})")
                await asyncio.sleep(Config.SCROLL_WAIT_MS / 1000)
                position += scroll_increment
                
                # Check if page height changed (new content loaded)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height > current_height:
                    current_height = new_height
                    logger.debug(f"Page height increased to {current_height}")
            
            # Final scroll to bottom
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(2)
            
            logger.debug("Full page scroll completed")
            
        except Exception as e:
            logger.error(f"Error during page scrolling: {e}")
    
    @staticmethod
    async def click_all_expandable_elements(page: Page):
        """Click all expandable elements to reveal hidden content."""
        try:
            logger.debug("Clicking expandable elements")
            
            # Selectors for various expandable elements
            selectors = [
                'details[open="false"] summary',
                'details:not([open]) summary',
                '[aria-expanded="false"]',
                'button[class*="expand"], button[class*="show"], button[class*="more"]',
                'a[class*="expand"], a[class*="show"], a[class*="more"]',
                '.dropdown-toggle',
                '.accordion-toggle',
                '.read-more',
                '.show-more',
                '.view-more'
            ]
            
            clicked_count = 0
            for selector in selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        try:
                            await element.click()
                            clicked_count += 1
                            await asyncio.sleep(Config.INTERACTION_WAIT_MS / 1000)
                        except Exception as e:
                            logger.debug(f"Could not click element with selector {selector}: {e}")
                except Exception as e:
                    logger.debug(f"Error with selector {selector}: {e}")
            
            logger.debug(f"Clicked {clicked_count} expandable elements")
            
        except Exception as e:
            logger.error(f"Error clicking expandable elements: {e}")
    
    @staticmethod
    async def hover_over_elements(page: Page):
        """Hover over elements that might trigger content display."""
        try:
            logger.debug("Hovering over interactive elements")
            
            selectors = [
                '[data-hover-trigger]',
                '.dropdown',
                '.menu-item',
                '[data-toggle="dropdown"]'
            ]
            
            hovered_count = 0
            for selector in selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements[:5]:  # Limit to avoid excessive hovering
                        try:
                            await element.hover()
                            hovered_count += 1
                            await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.debug(f"Could not hover over element: {e}")
                except Exception as e:
                    logger.debug(f"Error hovering with selector {selector}: {e}")
            
            logger.debug(f"Hovered over {hovered_count} elements")
            
        except Exception as e:
            logger.error(f"Error hovering over elements: {e}")
    
    @staticmethod
    async def wait_for_dynamic_content(page: Page, timeout: int = 10000):
        """Wait for dynamic content to load."""
        try:
            logger.debug("Waiting for dynamic content")
            
            # Wait for common loading indicators to disappear
            loading_selectors = [
                '.loading',
                '.spinner',
                '[data-loading="true"]',
                '.skeleton-loader'
            ]
            
            for selector in loading_selectors:
                try:
                    await page.wait_for_selector(selector, state='detached', timeout=timeout)
                except:
                    pass  # Selector not found or timeout
            
            # Wait for network idle
            try:
                await page.wait_for_load_state('networkidle', timeout=timeout)
            except:
                logger.debug("Network idle timeout, continuing")
            
            logger.debug("Dynamic content wait completed")
            
        except Exception as e:
            logger.error(f"Error waiting for dynamic content: {e}")
    
    @staticmethod
    async def interact_with_page(page: Page):
        """Perform all necessary interactions to reveal hidden content."""
        try:
            # Step 1: Click expandable elements
            await ContentInteraction.click_all_expandable_elements(page)
            
            # Step 2: Hover over interactive elements
            await ContentInteraction.hover_over_elements(page)
            
            # Step 3: Scroll to trigger lazy loading
            await ContentInteraction.scroll_full_page(page)
            
            # Step 4: Wait for content to load
            await ContentInteraction.wait_for_dynamic_content(page)
            
            # Step 5: Check for newly appeared expandable elements
            await ContentInteraction.click_all_expandable_elements(page)
            
            # Step 6: Final scroll to catch any remaining lazy-loaded content
            await ContentInteraction.scroll_full_page(page)
            
            logger.info("All page interactions completed")
            
        except Exception as e:
            logger.error(f"Error during page interactions: {e}")
            raise
