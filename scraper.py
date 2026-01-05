import asyncio
import os
import time
import hashlib
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import openai
from supabase import create_client, Client
import trafilatura
import html2text
import redis


class WebScraper:
    def __init__(self, supabase_url: str, supabase_key: str, openai_key: str, redis_url: Optional[str] = None):
        """Initialize web scraper with Supabase, OpenAI, and optional Redis."""
        self.supabase: Client = create_client(supabase_url, supabase_key)
        self.openai_client = openai.AsyncOpenAI(api_key=openai_key)
        self.is_running = False
        self.cancel_requested = False  # Stop signal flag
        
        # Browser management
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.request_count = 0
        self.browser_restart_interval = 30  # Restart every 30 URLs
        
        # Redis caching (optional)
        self.redis_client: Optional[redis.Redis] = None
        self.use_cache = False
        
        if redis_url:
            try:
                self.redis_client = redis.from_url(redis_url, decode_responses=True)
                # Test connection
                self.redis_client.ping()
                self.use_cache = True
                print("✅ Redis cache connected")
            except Exception as e:
                print(f"⚠️  Redis connection failed: {e} (caching disabled)")
                self.redis_client = None
        else:
            print("ℹ️  Redis not configured (caching disabled)")
    
    def _get_cache_key(self, prefix: str, data: str) -> str:
        """Generate cache key with prefix and hash."""
        hash_val = hashlib.md5(data.encode()).hexdigest()
        return f"{prefix}:{hash_val}"
    
    def _cache_get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        if not self.use_cache or not self.redis_client:
            return None
        try:
            value = self.redis_client.get(key)
            if value:
                return json.loads(value)
        except Exception:
            pass
        return None
    
    def _cache_set(self, key: str, value: Any, ttl: int = 86400):
        """Set value in Redis cache with TTL (default 24h)."""
        if not self.use_cache or not self.redis_client:
            return
        try:
            self.redis_client.setex(key, ttl, json.dumps(value))
        except Exception as e:
            print(f"⚠️  Redis cache set failed: {e}")
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[Optional[list]]:
        """
        Generate embeddings for multiple texts in one API call (Phase 1).
        Batches up to 2048 texts (OpenAI limit).
        """
        if not texts:
            return []
        
        # Truncate each text to avoid exceeding token limit
        max_chars = 32000
        truncated_texts = [t[:max_chars] if len(t) > max_chars else t for t in texts]
        
        try:
            response = await self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=truncated_texts
            )
            # Rate limiting: small delay after OpenAI API call
            await asyncio.sleep(0.1)
            return [item.embedding for item in response.data]
        except Exception as e:
            print(f"  ⚠️  Batch embedding failed: {e}")
            raise
        
    async def get_browser_context(self) -> BrowserContext:
        """Get or create browser context with automatic restart."""
        if self.request_count >= self.browser_restart_interval:
            print(f"🔄 Restarting browser (URLs processed: {self.request_count})")
            await self.restart_browser()
            self.request_count = 0
            return self.context
            
        if self.context is None:
            print("🌐 Initializing browser context...")
            await self.initialize_browser()
            print("✅ Browser context ready")
            
        return self.context
    
    async def initialize_browser(self):
        """Initialize browser with Railway-optimized arguments."""
        playwright = await async_playwright().start()
        
        # Reference B - Browser launch args for Railway
        self.browser = await playwright.chromium.launch(
            args=[
                "--disable-dev-shm-usage",
                "--disable-setuid-sandbox",
                "--no-sandbox",
                "--disable-gpu",
                "--no-zygote",
                "--single-process"
            ]
        )
        
        self.context = await self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
    
    async def restart_browser(self):
        """Restart browser to clear memory."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            print("✅ Browser closed for restart")
        except Exception as e:
            print(f"⚠️  Error closing browser: {e}")
        
        await self.initialize_browser()
        print("✅ Browser restarted")
        
    async def close_browser(self):
        """Close browser and cleanup."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        except Exception as e:
            print(f"⚠️  Error closing browser: {e}")
        
        self.context = None
        self.browser = None
        
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
                    print("  ✓ Cookie banner dismissed")
                    break
        except Exception:
            pass

    def extract_content_html(self, html_content: str) -> str:
        """
        Extract main content using trafilatura, fallback to html2text.
        Improved extraction from old system.
        """
        # Try trafilatura first - handles most sites well
        extracted = trafilatura.extract(
            html_content,
            include_links=True,
            include_formatting=True,
            include_tables=True,
            no_fallback=False,
        )
        
        # If trafilatura extracted meaningful content, use it
        if extracted and len(extracted.strip()) > 200:
            return extracted.strip()
        
        # Fallback to html2text for pages trafilatura can't parse
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines
        
        fallback_content = h.handle(html_content)
        
        # Basic cleanup for fallback
        lines = fallback_content.split('\n')
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip common junk patterns
            if stripped and not any([
                stripped.startswith('Skip to'),
                stripped.startswith('Cookie'),
                stripped.startswith('Accept all'),
                'privacy policy' in stripped.lower(),
                'terms of service' in stripped.lower(),
                len(stripped) < 3,
            ]):
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()

    async def extract_content_4step(self, page: Page) -> Optional[str]:
        """
        Extract content using 4-step strategy.
        Reference D - Adapted structure
        """
        # Step 1: Look for <main> or <article>
        try:
            main_element = await page.query_selector('main, article')
            if main_element:
                html = await main_element.inner_html()
                content = self.extract_content_html(html)
                if content and len(content.strip()) > 100:
                    print("  ✓ Extracted from main/article element")
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
                    html = await element.inner_html()
                    content = self.extract_content_html(html)
                    if content and len(content.strip()) > 100:
                        print(f"  ✓ Extracted from selector: {selector}")
                        return content.strip()
        except Exception:
            pass
            
        # Step 3: Body fallback (remove nav/header/footer via JS)
        try:
            html = await page.evaluate('''() => {
                const clone = document.body.cloneNode(true);
                const selectorsToRemove = ['nav', 'header', 'footer', '[role="navigation"]', '.nav', '.header', '.footer'];
                selectorsToRemove.forEach(selector => {
                    clone.querySelectorAll(selector).forEach(el => el.remove());
                });
                return clone.innerHTML;
            }''')
            content = self.extract_content_html(html)
            if content and len(content.strip()) > 100:
                print("  ✓ Extracted from body (filtered)")
                return content.strip()
        except Exception:
            pass
            
        # Step 4: Last resort - get all HTML and extract
        try:
            html = await page.content()
            content = self.extract_content_html(html)
            if content and len(content.strip()) > 100:
                print("  ✓ Extracted from page (full)")
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
            print(f"  ⚠️  Embedding failed: {e}")
            raise

    def insert_or_update_document(self, url: str, content: str, title: str, embedding: Optional[list]) -> str:
        """
        Insert new document or update existing one.
        Prevents duplicates by checking metadata.source.
        """
        # Check for existing document
        existing = self.supabase.table('documents').select('*').contains('metadata', {'source': url}).execute()
        
        insert_data = {
            'content': content,
            'metadata': {
                'source': url,
                'source_type': 'web_scrape',
                'title': title,
                'scraped_at': datetime.utcnow().isoformat()
            }
        }
        
        if embedding:
            insert_data['embedding'] = embedding
        
        if existing.data and len(existing.data) > 0:
            # UPDATE existing document
            doc_id = existing.data[0]['id']
            self.supabase.table('documents').update(insert_data).eq('id', doc_id).execute()
            print(f"  ✓ Updated existing document (ID: {doc_id})")
            return 'updated'
        else:
            # INSERT new document
            self.supabase.table('documents').insert(insert_data).execute()
            print(f"  ✓ Inserted new document")
            return 'inserted'

    async def scrape_url(self, url: str, max_retries: int = 3, generate_embedding: bool = True) -> Optional[Dict[str, Any]]:
        """
        Scrape a single URL: expand, extract, embed.
        With retry logic and exponential backoff.
        Checks for cancellation before processing.
        
        Args:
            url: URL to scrape
            max_retries: Number of retry attempts
            generate_embedding: If False, skip embedding generation (for phantom completion fixes)
        """
        # Check if cancellation was requested
        if self.cancel_requested:
            print(f"  ⏹️  Skipping {url[:50]}... (cancellation requested)")
            return None
            
        context = await self.get_browser_context()
        self.request_count += 1
        
        last_error = None
        
        for attempt in range(max_retries):
            # Check for cancellation at each retry
            if self.cancel_requested:
                print(f"  ⏹️  Cancelling {url[:50]}... (attempt {attempt + 1})")
                return None
                
            page = None
            try:
                print(f"  Scraping: {url[:70]}{'...' if len(url) > 70 else ''} (attempt {attempt + 1}/{max_retries})")
                
                page = await context.new_page()
                
                # Use "domcontentloaded" instead of "networkidle" (faster, more reliable)
                await page.goto(url, timeout=60000, wait_until='domcontentloaded')
                
                # Reference C - Handle cookies
                await self.handle_cookies(page)
                
                # Reference A - Expand all content
                await self.expand_all_content(page)
                
                # Reference D - Extract content
                content = await self.extract_content_4step(page)
                
                # Validate content (minimum 50 characters)
                if not content or len(content.strip()) < 50:
                    raise ValueError(f"Extracted content too short ({len(content) if content else 0} chars < 50 minimum)")
                
                # Get page title
                title = await page.title() or "Untitled"
                
                print(f"    ✓ Success: {len(content):,} chars extracted")
                
                await page.close()
                
                # Reference: Generate embedding for RAG
                embedding = await self.generate_embedding(content)
                
                return {
                    'url': url,
                    'content': content,
                    'title': title,
                    'embedding': embedding,
                    'status': 'success',
                    'attempts': attempt + 1
                }
                
            except asyncio.TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                print(f"    ⏱️  Timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except ValueError as e:
                last_error = f"Validation: {str(e)}"
                print(f"    ❌ Validation failed on attempt {attempt + 1}: {e}")
                await asyncio.sleep(1)
                
            except Exception as e:
                last_error = str(e)
                print(f"    ❌ Error on attempt {attempt + 1}: {e}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            finally:
                if page:
                    try:
                        await page.close()
                    except Exception:
                        pass
        
        print(f"    ❌ FAILED after {max_retries} attempts: {url[:70]}...")
        return {
            'url': url,
            'content': None,
            'title': None,
            'embedding': None,
            'status': 'error',
            'error': last_error,
            'attempts': max_retries
        }

    async def process_urls(self, urls: list, max_concurrent: int = 3) -> Dict[str, Any]:
        """
        Process multiple URLs concurrently with semaphore limit.
        Uses batched embeddings for efficiency (Phase 1).
        Checks for cancellation and stops immediately when requested.
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        scraped_data = []
        cancelled = False
        
        # Phase 1: Scrape all URLs concurrently (collect data first)
        async def scrape_with_semaphore(url: str):
            nonlocal cancelled
            
            # Skip if already cancelled
            if cancelled:
                return None
                
            async with semaphore:
                # Check for cancellation before processing
                if self.cancel_requested:
                    cancelled = True
                    return None
                    
                try:
                    # Scrape URL without embedding (will do in batch)
                    data = await self.scrape_url(url, max_retries=3, generate_embedding=False)
                    return data
                except Exception as e:
                    if not self.cancel_requested:
                        print(f"  ❌ Failed to scrape {url}: {e}")
                    return None
        
        # Create scraping tasks
        scrape_tasks = [scrape_with_semaphore(url) for url in urls]
        
        try:
            # Gather all scraped data
            scraped_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)
        except asyncio.CancelledError:
            print("  ⏹️  Processing cancelled by stop request")
            cancelled = True
            return {'success': [], 'failed': []}
        
        # Filter out cancellations and errors
        for result in scraped_results:
            if result is not None and not isinstance(result, Exception):
                scraped_data.append(result)
        
        # Phase 2: Batch generate embeddings (Phase1 efficiency)
        successful_data = [d for d in scraped_data if d and d.get('status') == 'success']
        failed_data = [d for d in scraped_data if d and d.get('status') != 'success']
        
        scraped_data_urls = []
        
        if successful_data:
            print(f"  🔄 Generating {len(successful_data)} embeddings in batch...")
            try:
                # Batch generate embeddings (up to 2048 at once)
                texts = [d['content'] for d in successful_data]
                embeddings = await self.generate_embeddings_batch(texts)
                
                # Assign embeddings back to data
                for i, data in enumerate(successful_data):
                    if i < len(embeddings):
                        data['embedding'] = embeddings[i]
                        # Insert or update document
                        self.insert_or_update_document(
                            data['url'],
                            data['content'],
                            data['title'],
                            data['embedding']
                        )
                        scraped_data_urls.append(data['url'])
                    
                print(f"  ✓ Batch embeddings complete: {len(scraped_data_urls)} documents saved")
            except Exception as e:
                print(f"  ⚠️  Batch embedding failed, falling back to individual: {e}")
                # Fallback to individual embeddings
                for data in successful_data:
                    try:
                        embedding = await self.generate_embedding(data['content'])
                        self.insert_or_update_document(
                            data['url'],
                            data['content'],
                            data['title'],
                            embedding
                        )
                        scraped_data_urls.append(data['url'])
                    except Exception:
                        self.update_url_status(data['url'], 'failed')
        
        # Update status for failed URLs
        for data in failed_data:
            self.update_url_status(data['url'], 'failed')
        
        return {
            'success': scraped_data_urls,
            'failed': [d['url'] for d in failed_data]
        }

    async def process_urls_batched(self, max_concurrent: int = 3, batch_size: int = 30) -> Dict[str, Any]:
        """
        Process ALL pending URLs in batches with browser restarts.
        
        Workflow:
        1. Get batch of 30 URLs
        2. Process 3 URLs concurrently
        3. After batch of 30 done, restart browser (memory cleanup)
        4. Get next batch of 30 URLs
        5. Repeat until all pending URLs processed
        """
        print(f"🚀 Starting batched processing (batch_size={batch_size}, concurrent={max_concurrent})")
        
        total_results = {'success': [], 'failed': []}
        batch_num = 0
        
        while True:
            # Check for cancellation
            if self.cancel_requested:
                print("  ⏹️  Batched processing cancelled")
                break
            
            # Get next batch of URLs
            batch_urls = self.get_pending_urls(limit=None, batch_size=batch_size, batch_num=batch_num)
            
            if not batch_urls:
                print(f"✅ No more URLs to process")
                break
            
            print(f"\n📦 Batch {batch_num + 1}: Processing {len(batch_urls)} URLs")
            
            # Mark all URLs in batch as 'processing'
            for url in batch_urls:
                self.update_url_status(url, 'processing')
            
            # Process this batch
            batch_results = await self.process_urls(batch_urls, max_concurrent=max_concurrent)
            
            # Update status based on results
            for url in batch_results['success']:
                self.update_url_status(url, 'completed')
                total_results['success'].append(url)
            
            for url in batch_results['failed']:
                self.update_url_status(url, 'failed')
                total_results['failed'].append(url)
            
            print(f"  Batch {batch_num + 1} complete: {len(batch_results['success'])} success, {len(batch_results['failed'])} failed")
            
            # Reset request count for next batch (browser will restart at start of next batch)
            self.request_count = 0
            
            # Move to next batch
            batch_num += 1
        
        print(f"\n✅ All batches complete: {len(total_results['success'])} success, {len(total_results['failed'])} failed")
        
        return total_results

    def get_pending_urls(self, limit: Optional[int] = None, batch_size: int = 30, batch_num: int = 0) -> list:
        """
        Get pending URLs in batches.
        
        Args:
            limit: Maximum total URLs to get (None = all)
            batch_size: How many URLs to return in this batch (default 30)
            batch_num: Which batch number (0-indexed, for pagination)
        
        Returns:
            List of URLs for this batch (max batch_size)
        """
        query = self.supabase.table('url_queue').select('url').eq('status', 'pending')
        
        # Apply limit if specified
        if limit is not None:
            query = query.limit(limit)
        else:
            # For batched processing, paginate by batch_size
            offset = batch_num * batch_size
            query = query.range(offset, offset + batch_size - 1)
        
        response = query.execute()
        return [row['url'] for row in response.data]
    
    def get_total_pending_count(self) -> int:
        """Get total count of pending URLs."""
        response = self.supabase.table('url_queue').select('id', count='exact').eq('status', 'pending').execute()
        return response.count if hasattr(response, 'count') else 0

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
        Uses pagination to fetch ALL URLs - no limits.
        """
        issues = {'phantom_completions': [], 'missing_embeddings': [], 'stuck_urls': []}
        
        print("🔍 Starting complete validation (checking ALL URLs)...")
        
        # 1. Phantom Completions: URLs marked 'completed' but missing from documents
        print("  Checking for phantom completions (ALL completed URLs)...")
        try:
            # Get ALL completed URLs with pagination
            completed_urls = self._fetch_all_rows('url_queue', 'url', 'status', 'completed')
            
            if completed_urls:
                all_urls = set(row['url'] for row in completed_urls)
                print(f"    Loaded {len(all_urls)} completed URLs")
                
                # Get ALL document sources with pagination
                docs_data = self._fetch_all_rows('documents', 'metadata')
                doc_sources = set()
                for doc in docs_data:
                    metadata = doc.get('metadata', {})
                    source = metadata.get('source')
                    if source:
                        doc_sources.add(source)
                
                print(f"    Loaded {len(doc_sources)} document sources")
                
                # Find phantom completions
                for url in all_urls:
                    if url not in doc_sources:
                        issues['phantom_completions'].append(url)
                
                print(f"  ✓ Found {len(issues['phantom_completions'])} phantom completions out of {len(all_urls)} checked")
            else:
                print(f"  ✓ No completed URLs to check")
                
        except Exception as e:
            print(f"  ⚠️  Error checking phantom completions: {e}")
            # Fallback to slower method
            self._validate_phantom_completions_fallback(issues)
        
        # 2. Missing Embeddings: Documents where embedding is NULL
        print("  Checking for missing embeddings (ALL documents)...")
        try:
            # Get ALL documents without embeddings with pagination
            missing_emb = self._fetch_all_rows('documents', 'id', filter_column='embedding', filter_value='null')
            if missing_emb:
                issues['missing_embeddings'] = [row['id'] for row in missing_emb]
                print(f"  ✓ Found {len(issues['missing_embeddings'])} documents without embeddings")
            else:
                print(f"  ✓ No documents without embeddings")
                
        except Exception as e:
            print(f"  ⚠️  Error checking missing embeddings: {e}")
            # Fallback to slower method
            self._validate_missing_embeddings_fallback(issues)
        
        # 3. Stuck URLs: URLs in 'processing' status for > 1 hour
        print("  Checking for stuck URLs (ALL processing URLs)...")
        try:
            # Get ALL processing URLs with pagination
            processing_urls = self._fetch_all_rows('url_queue', 'url, updated_at', 'status', 'processing')
            
            if processing_urls:
                # Filter by time (1 hour ago)
                issues['stuck_urls'] = [
                    row['url'] for row in processing_urls 
                    if row.get('updated_at') and self._is_older_than_one_hour(row['updated_at'])
                ]
                print(f"  ✓ Found {len(issues['stuck_urls'])} stuck URLs out of {len(processing_urls)} processing")
            else:
                print(f"  ✓ No processing URLs to check")
                
        except Exception as e:
            print(f"  ⚠️  Error checking stuck URLs: {e}")
            # Fallback to slower method
            self._validate_stuck_urls_fallback(issues)
        
        print(f"✅ Validation complete: {len(issues['phantom_completions'])} phantom, {len(issues['missing_embeddings'])} missing emb, {len(issues['stuck_urls'])} stuck")
        
        return issues
    
    def _is_older_than_one_hour(self, timestamp_str: str) -> bool:
        """Helper to check if timestamp is older than 1 hour."""
        from datetime import timedelta
        try:
            # Parse timestamp from PostgreSQL format
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                return (datetime.utcnow() - timestamp).total_seconds() > 3600
        except Exception:
            pass
        return False
    
    def _fetch_all_rows(self, table: str, columns: str, filter_column: Optional[str] = None, filter_value: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Fetch ALL rows from a table using pagination to bypass Supabase's 1000-row limit.
        """
        all_rows = []
        offset = 0
        batch_size = 1000  # Maximum rows per request
        
        while True:
            query = self.supabase.table(table).select(columns)
            
            # Apply filter if specified
            if filter_column and filter_value:
                if filter_value == 'null':
                    query = query.is_(filter_column, 'null')
                else:
                    query = query.eq(filter_column, filter_value)
            
            # Apply pagination
            query = query.range(offset, offset + batch_size - 1)
            
            # Execute query
            response = query.execute()
            
            # If no rows returned, we're done
            if not response.data or len(response.data) == 0:
                break
            
            # Add rows to result
            all_rows.extend(response.data)
            
            # Check if we got less than batch_size (last page)
            if len(response.data) < batch_size:
                break
            
            # Move to next page
            offset += batch_size
            print(f"    Fetched {len(all_rows)} rows so far...")
        
        return all_rows
    
    def _validate_phantom_completions_fallback(self, issues: Dict[str, Any]):
        """Fallback method for phantom completions using Supabase client - checks ALL with pagination."""
        print("  Using fallback method for phantom completions (ALL URLs)...")
        
        # Get ALL completed URLs with pagination
        completed_urls = self._fetch_all_rows('url_queue', 'url', 'status', 'completed')
        
        # Get ALL document sources with pagination
        all_document_sources = set()
        docs = self._fetch_all_rows('documents', 'metadata')
        for doc in docs:
            metadata = doc.get('metadata', {})
            source = metadata.get('source')
            if source:
                all_document_sources.add(source)
        
        # Find phantom completions
        for row in completed_urls:
            url = row['url']
            if url not in all_document_sources:
                issues['phantom_completions'].append(url)
        
        print(f"  ✓ Fallback found {len(issues['phantom_completions'])} phantom completions")
    
    def _validate_missing_embeddings_fallback(self, issues: Dict[str, Any]):
        """Fallback method for missing embeddings using Supabase client - checks ALL with pagination."""
        print("  Using fallback method for missing embeddings (ALL documents)...")
        
        # Get ALL documents without embeddings with pagination
        missing_emb = self._fetch_all_rows('documents', 'id', filter_column='embedding', filter_value='null')
        issues['missing_embeddings'] = [row['id'] for row in missing_emb]
        print(f"  ✓ Fallback found {len(issues['missing_embeddings'])} documents without embeddings")
    
    def _validate_stuck_urls_fallback(self, issues: Dict[str, Any]):
        """Fallback method for stuck URLs using Supabase client - checks ALL with pagination."""
        print("  Using fallback method for stuck URLs (ALL URLs)...")
        
        # Get ALL processing URLs with pagination
        stuck = self._fetch_all_rows('url_queue', 'url, updated_at', 'status', 'processing')
        
        # Filter by time in Python
        for row in stuck:
            url = row['url']
            if row.get('updated_at') and self._is_older_than_one_hour(row['updated_at']):
                issues['stuck_urls'].append(url)
        
        print(f"  ✓ Fallback found {len(issues['stuck_urls'])} stuck URLs")

    async def fix_validation_issues(self, issues: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automatically fix validation errors using batched processing.
        """
        results = {'fixed': 0, 'failed': 0}
        
        # Fix phantom completions: Re-scrape and insert (in batches of 30)
        phantom_urls = issues.get('phantom_completions', [])
        print(f"\n🔧 Fixing {len(phantom_urls)} phantom completions (batched)...")
        
        for batch_num in range(0, len(phantom_urls), 30):
            # Check for cancellation
            if self.cancel_requested:
                print("  ⏹️  Phantom completion fix cancelled")
                break
            
            batch = phantom_urls[batch_num:batch_num + 30]
            print(f"\n  Batch {batch_num // 30 + 1}: Processing {len(batch)} phantom URLs")
            
            # Process batch with 3 concurrent
            batch_results = await self.process_urls(batch, max_concurrent=3)
            
            # Update results
            for url in batch_results['success']:
                # Already inserted by process_urls, just count
                results['fixed'] += 1
            
            for url in batch_results['failed']:
                results['failed'] += 1
            
            print(f"  Batch {batch_num // 30 + 1} complete: {len(batch_results['success'])} fixed, {len(batch_results['failed'])} failed")
            
            # Reset request count for browser restart
            self.request_count = 0
        
        # Fix missing embeddings: Retrieve content, generate embedding, update (batched)
        missing_emb_ids = issues.get('missing_embeddings', [])
        print(f"\n🔧 Fixing {len(missing_emb_ids)} missing embeddings (batched)...")
        
        for batch_num in range(0, len(missing_emb_ids), 30):
            # Check for cancellation
            if self.cancel_requested:
                print("  ⏹️  Missing embedding fix cancelled")
                break
            
            batch = missing_emb_ids[batch_num:batch_num + 30]
            print(f"\n  Batch {batch_num // 30 + 1}: Processing {len(batch)} document IDs")
            
            # Process batch concurrently
            batch_fixed = 0
            batch_failed = 0
            
            async def fix_one_embedding(doc_id):
                try:
                    doc = self.supabase.table('documents').select('id, content').eq('id', doc_id).single().execute()
                    if doc.data:
                        content = doc.data['content']
                        embedding = await self.generate_embedding(content)
                        self.supabase.table('documents').update({'embedding': embedding}).eq('id', doc_id).execute()
                        return True
                    return False
                except Exception as e:
                    print(f"  ❌ Failed to fix missing embedding for doc {doc_id}: {e}")
                    return False
            
            # Process 3 at a time
            tasks = [fix_one_embedding(doc_id) for doc_id in batch]
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results_list:
                if isinstance(result, Exception):
                    batch_failed += 1
                elif result:
                    batch_fixed += 1
                else:
                    batch_failed += 1
            
            results['fixed'] += batch_fixed
            results['failed'] += batch_failed
            
            print(f"  Batch {batch_num // 30 + 1} complete: {batch_fixed} fixed, {batch_failed} failed")
        
        # Reset stuck URLs to pending (batched)
        stuck_urls = issues.get('stuck_urls', [])
        print(f"\n🔧 Resetting {len(stuck_urls)} stuck URLs (batched)...")
        
        for batch_num in range(0, len(stuck_urls), 30):
            # Check for cancellation
            if self.cancel_requested:
                print("  ⏹️  Stuck URL reset cancelled")
                break
            
            batch = stuck_urls[batch_num:batch_num + 30]
            print(f"\n  Batch {batch_num // 30 + 1}: Resetting {len(batch)} URLs")
            
            batch_fixed = 0
            batch_failed = 0
            
            for url in batch:
                try:
                    self.supabase.table('url_queue').update({'status': 'pending', 'updated_at': 'now()'}).eq('url', url).execute()
                    batch_fixed += 1
                except Exception as e:
                    print(f"  ❌ Failed to reset stuck URL {url}: {e}")
                    batch_failed += 1
            
            results['fixed'] += batch_fixed
            results['failed'] += batch_failed
            
            print(f"  Batch {batch_num // 30 + 1} complete: {batch_fixed} fixed, {batch_failed} failed")
        
        print(f"\n✅ All validation fixes complete: {results['fixed']} fixed, {results['failed']} failed")
        
        return results
    
    async def cleanup(self):
        """Cleanup browser resources."""
        await self.close_browser()
