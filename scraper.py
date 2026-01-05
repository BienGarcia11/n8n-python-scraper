import asyncio
import os
import time
from typing import Optional, Dict, Any
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import openai
from supabase import create_client, Client


class WebScraper:
    def __init__(self, supabase_url: str, supabase_key: str, openai_key: str):
        """Initialize the web scraper with Supabase and OpenAI credentials."""
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.openai_client = openai.AsyncOpenAI(api_key=openai_key)
        self.is_running = False
        
    async def expand_all_content(self, page: Page) -> None:
        """
        Expand all hidden content including dropdowns, accordions, tabs, etc.
        Reference A - Exact implementation from proven architecture.
        """
        expand_actions = 0
        expandable_selectors = [
            'button:has-text("Show more")',
            'button:has-text("Read more")',
            'button:has-text("Expand")',
            'button:has-text("See more")',
            'button:has-text("Continue reading")',
            'button:has-text("Full article")',
            'a:has-text("Show more")',
            '[class*="accordion"] button',
            '[aria-expanded="false"]',
            'summary',
            'button[aria-label*="more"]',
            'button[aria-label*="expand"]',
            '[class*="expand"] button',
            '[class*="show-more"] button',
            '[class*="read-more"] button',
        ]
        
        for pass_num in range(3):
            expanded_this_pass = 0
            for selector in expandable_selectors:
                try:
                    elements = await page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            await element.click(timeout=1000)
                            expanded_this_pass += 1
                            await asyncio.sleep(0.3)
                except Exception:
                    continue
                    
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await asyncio.sleep(0.5)
            except Exception:
                pass
                
            if expanded_this_pass == 0:
                break
                
        await asyncio.sleep(1)

    async def handle_cookies(self, page: Page) -> None:
        """
        Handle cookie consent dialogs.
        Reference C - Run this after page.goto
        """
        try:
            await asyncio.sleep(2)
            cookie_selectors = [
                'button:has-text("Accept")',
                'button:has-text("Accept all")',
                'button:has-text("Accept Cookies")',
                'button:has-text("Accept all cookies")',
                '[data-testid*="accept"]',
                '[id*="accept"] button',
                '[class*="accept"] button',
            ]
            for selector in cookie_selectors:
                cookie_button = await page.query_selector(selector, timeout=2000)
                if cookie_button:
                    await cookie_button.click()
                    break
        except Exception:
            pass

    async def extract_content_4step(self, page: Page) -> Optional[str]:
        """
        Extract content using 4-step strategy.
        Reference D - Adapted structure
        """
        # Step 1: Look for <main> or <article>
        try:
            main_element = await page.query_selector('main, article')
            if main_element:
                content = await main_element.text_content()
                if content and len(content.strip()) > 100:
                    return content.strip()
        except Exception:
            pass
            
        # Step 2: Look for help-center selectors
        try:
            help_selectors = [
                'div[class*="article"]',
                'div[class*="docs"]',
                'div[class*="documentation"]',
                '[class*="content"]',
            ]
            for selector in help_selectors:
                element = await page.query_selector(selector)
                if element:
                    content = await element.text_content()
                    if content and len(content.strip()) > 100:
                        return content.strip()
        except Exception:
            pass
            
        # Step 3: Body fallback (remove nav/header/footer via JS)
        try:
            content = await page.evaluate('''() => {
                const clone = document.body.cloneNode(true);
                const selectorsToRemove = ['nav', 'header', 'footer', '[role="navigation"]', '.nav', '.header', '.footer'];
                selectorsToRemove.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                return clone.innerText || clone.textContent;
            }''')
            if content and len(content.strip()) > 100:
                return content.strip()
        except Exception:
            pass
            
        # Step 4: Last resort
        try:
            content = await page.text_content('body')
            if content and len(content.strip()) > 100:
                return content.strip()
        except Exception:
            pass
            
        return None

    async def generate_embedding(self, text: str) -> list:
        """
        Generate embedding for text using OpenAI text-embedding-3-small.
        Token limit: 8191 tokens for text-embedding-3-small
        """
        # Truncate text to avoid exceeding token limit
        # Approximate 4 chars per token, so ~32764 chars max
        max_chars = 32000
        if len(text) > max_chars:
            text = text[:max_chars]
            
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            # Rate limiting: small delay after OpenAI API call
            await asyncio.sleep(0.1)
            return response.data[0].embedding
        except Exception as e:
            print(f"Error generating embedding: {e}")
            raise

    async def scrape_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape a single URL: expand, extract, embed.
        """
        browser = None
        try:
            playwright = await async_playwright().start()
            
            # Reference B - Browser launch args for Railway
            browser = await playwright.chromium.launch(
                args=[
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--no-zygote",
                    "--single-process"
                ]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            
            page = await context.new_page()
            
            # Navigate to URL
            await page.goto(url, timeout=30000, wait_until='networkidle')
            
            # Reference C - Handle cookies
            await self.handle_cookies(page)
            
            # Reference A - Expand all content
            await self.expand_all_content(page)
            
            # Reference D - Extract content
            content = await self.extract_content_4step(page)
            
            if not content:
                return None
                
            # Get page title
            title = await page.title() or "Untitled"
            
            # Reference: Generate embedding for RAG
            embedding = await self.generate_embedding(content)
            
            await browser.close()
            await playwright.stop()
            
            return {
                'content': content,
                'metadata': {'source': url, 'title': title},
                'embedding': embedding
            }
            
        except Exception as e:
            print(f"Error scraping {url}: {e}")
            if browser:
                await browser.close()
            return None

    async def process_urls(self, urls: list, max_concurrent: int = 2) -> Dict[str, Any]:
        """
        Process multiple URLs concurrently with semaphore limit.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        results = {'success': [], 'failed': []}
        
        async def process_with_semaphore(url: str):
            async with semaphore:
                try:
                    # Scrape the URL
                    data = await self.scrape_url(url)
                    if data:
                        # Insert into documents table
                        self.supabase.table('documents').insert({
                            'content': data['content'],
                            'metadata': data['metadata'],
                            'embedding': data['embedding']
                        }).execute()
                        results['success'].append(url)
                    else:
                        results['failed'].append(url)
                except Exception as e:
                    print(f"Failed to process {url}: {e}")
                    results['failed'].append(url)
        
        tasks = [process_with_semaphore(url) for url in urls]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        return results

    def get_pending_urls(self, limit: int = 100) -> list:
        """
        Get pending URLs from url_queue table.
        """
        response = self.supabase.table('url_queue').select('url').eq('status', 'pending').limit(limit).execute()
        return [row['url'] for row in response.data]

    def update_url_status(self, url: str, status: str) -> None:
        """
        Update URL status in url_queue table.
        """
        self.supabase.table('url_queue').update({
            'status': status,
            'updated_at': 'now()'
        }).eq('url', url).execute()

    def validate_data(self) -> Dict[str, Any]:
        """
        Validate scraped data for phantom completions, missing embeddings, and stuck URLs.
        """
        issues = {'phantom_completions': [], 'missing_embeddings': [], 'stuck_urls': []}
        
        # Phantom completions: URLs marked 'completed' but missing from documents
        completed_urls = self.supabase.table('url_queue').select('url').eq('status', 'completed').execute()
        for row in completed_urls.data:
            url = row['url']
            # Check if this URL exists in documents metadata
            doc = self.supabase.table('documents').select('id').filter('metadata->>source', 'eq', url).limit(1).execute()
            if not doc.data:
                issues['phantom_completions'].append(url)
        
        # Missing embeddings: Documents where content exists but embedding is NULL
        missing_emb = self.supabase.table('documents').select('id').is_('embedding', 'null').execute()
        issues['missing_embeddings'] = [row['id'] for row in missing_emb.data]
        
        # Stuck URLs: URLs stuck in 'processing' status for > 1 hour
        from datetime import datetime, timedelta
        one_hour_ago = datetime.utcnow() - timedelta(hours=1)
        stuck = self.supabase.table('url_queue').select('url').eq('status', 'processing').lt('updated_at', one_hour_ago.isoformat()).execute()
        issues['stuck_urls'] = [row['url'] for row in stuck.data]
        
        return issues

    async def fix_validation_issues(self, issues: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically fix validation errors.
        """
        results = {'fixed': 0, 'failed': 0}
        
        # Fix phantom completions: Re-scrape and insert
        for url in issues.get('phantom_completions', []):
            try:
                data = await self.scrape_url(url)
                if data:
                    self.supabase.table('documents').insert({
                        'content': data['content'],
                        'metadata': data['metadata'],
                        'embedding': data['embedding']
                    }).execute()
                    results['fixed'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                print(f"Failed to fix phantom completion for {url}: {e}")
                results['failed'] += 1
        
        # Fix missing embeddings: Retrieve content, generate embedding, update
        for doc_id in issues.get('missing_embeddings', []):
            try:
                doc = self.supabase.table('documents').select('id, content').eq('id', doc_id).single().execute()
                if doc.data:
                    content = doc.data['content']
                    embedding = await self.generate_embedding(content)
                    self.supabase.table('documents').update({'embedding': embedding}).eq('id', doc_id).execute()
                    results['fixed'] += 1
                else:
                    results['failed'] += 1
            except Exception as e:
                print(f"Failed to fix missing embedding for doc {doc_id}: {e}")
                results['failed'] += 1
        
        # Reset stuck URLs to pending
        for url in issues.get('stuck_urls', []):
            try:
                self.supabase.table('url_queue').update({'status': 'pending', 'updated_at': 'now()'}).eq('url', url).execute()
                results['fixed'] += 1
            except Exception as e:
                print(f"Failed to reset stuck URL {url}: {e}")
                results['failed'] += 1
        
        return results
