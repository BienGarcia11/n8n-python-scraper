"""
Bulk URL Scraper for RAG System
=============================
Scrapes all pending URLs from database and imports directly to Supabase
Bypasses n8n workflow for better reliability and performance

Usage:
    python bulk_scrape_import.py
    python bulk_scrape_import.py --limit 100
    python bulk_scrape_import.py --batch-size 3 --concurrency 2
"""

import asyncio
import argparse
import os
import sys
from typing import List, Dict, Any
from datetime import datetime
import traceback

import httpx
from playwright.async_api import async_playwright
import html2text
import trafilatura
from supabase import create_client, Client

# ============== CONFIGURATION ==============

# Supabase Configuration
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ykohyrwipxpwztptfopi.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Anon key (service_role for writes)

# Scraping Configuration
DEFAULT_BATCH_SIZE = 3          # URLs per batch
DEFAULT_CONCURRENCY = 2         # Concurrent pages
DEFAULT_LIMIT = None            # No limit by default
BROWSER_RESTART_INTERVAL = 30   # Restart browser every 30 URLs

# OpenAI Configuration (for embeddings)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ============== SUPABASE CLIENT ==============

def get_supabase_client() -> Client:
    """Initialize Supabase client"""
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY environment variable is required")
    
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return client


def get_pending_urls(client: Client, limit: int = None) -> List[Dict]:
    """Fetch pending URLs from url_queue table"""
    query = client.table("url_queue").select("*").eq("status", "pending")
    
    if limit:
        query = query.limit(limit)
    
    result = query.order("id", desc=True).execute()
    return result.data if result.data else []


def update_url_status(client: Client, url: str, status: str, content: str = None, title: str = None):
    """Update URL status in database"""
    update_data = {"status": status}
    
    if content is not None:
        update_data["content"] = content
    
    if title is not None:
        update_data["title"] = title
    
    client.table("url_queue").update(update_data).eq("url", url).execute()


def insert_document(client: Client, url: str, content: str, title: str):
    """Insert scraped content into documents table"""
    from openai import OpenAI
    import tiktoken
    
    if not OPENAI_API_KEY:
        print("⚠️  Warning: OPENAI_API_KEY not set - skipping embeddings")
        return
    
    try:
        # Generate embeddings using OpenAI
        client_oai = OpenAI(api_key=OPENAI_API_KEY)
        response = client_oai.embeddings.create(
            model="text-embedding-3-small",
            input=content[:8191]  # Limit to 8191 tokens
        )
        embedding = response.data[0].embedding
        
        # Insert document with embedding
        client.table("documents").insert({
            "content": content,
            "embedding": embedding,
            "metadata": {
                "source": url,
                "source_type": "web_scrape",
                "title": title,
                "scraped_at": datetime.utcnow().isoformat()
            }
        }).execute()
        
        print(f"  ✓ Document inserted with embedding")
        
    except Exception as e:
        print(f"  ⚠️  Failed to generate embeddings: {e}")
        # Insert without embedding as fallback
        try:
            client.table("documents").insert({
                "content": content,
                "metadata": {
                    "source": url,
                    "source_type": "web_scrape",
                    "title": title,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "no_embedding": True
                }
            }).execute()
            print(f"  ✓ Document inserted without embedding")
        except Exception as e2:
            print(f"  ❌ Failed to insert document: {e2}")


# ============== SCRAPING FUNCTIONS ==============

def extract_content(html_content: str) -> str:
    """Extract main content using trafilatura, fallback to html2text"""
    
    # Try trafilatura first
    extracted = trafilatura.extract(
        html_content,
        include_links=True,
        include_formatting=True,
        include_tables=True,
        no_fallback=False,
    )
    
    if extracted and len(extracted.strip()) > 200:
        return extracted
    
    # Fallback to html2text
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.body_width = 0
    
    fallback_content = h.handle(html_content)
    
    # Basic cleanup
    lines = fallback_content.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not any([
            stripped.startswith('Skip to'),
            stripped.startswith('Cookie'),
            stripped.startswith('Accept all'),
            'privacy policy' in stripped.lower(),
            'terms of service' in stripped.lower(),
            len(stripped) < 3,
        ]):
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


async def scrape_single_url(context, url, semaphore, max_retries=3):
    """Scrape a single URL with retry logic"""
    url = url.strip()
    if not url:
        return None
    
    last_error = None
    for attempt in range(max_retries):
        async with semaphore:
            page = await context.new_page()
            try:
                print(f"    Scraping: {url} (attempt {attempt + 1}/{max_retries})")
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                
                html_content = await asyncio.wait_for(page.content(), timeout=30000)
                title = await asyncio.wait_for(page.title(), timeout=5000)
                
                content = extract_content(html_content)
                
                if not content or len(content.strip()) < 50:
                    raise ValueError("Extracted content too short (< 50 chars)")
                
                original_size = len(html_content)
                extracted_size = len(content)
                print(f"      ✓ Success: {original_size:,} → {extracted_size:,} chars")
                
                return {
                    "url": url,
                    "title": title,
                    "content": content,
                    "status": "success",
                    "attempts": attempt + 1
                }
                
            except asyncio.TimeoutError as e:
                last_error = f"Timeout: {str(e)}"
                print(f"      ⏱️  Timeout on attempt {attempt + 1}")
                await asyncio.sleep(2 ** attempt)
                
            except ValueError as e:
                last_error = f"Validation: {str(e)}"
                print(f"      ❌ Validation failed: {e}")
                await asyncio.sleep(1)
                
            except Exception as e:
                last_error = str(e)
                print(f"      ❌ Error: {e}")
                await asyncio.sleep(1)
                
            finally:
                try:
                    await page.close()
                except Exception as e:
                    print(f"      Warning: Failed to close page - {e}")
    
    print(f"    ❌ FAILED after {max_retries} attempts: {url}")
    return {
        "url": url,
        "title": None,
        "content": None,
        "status": "error",
        "error": last_error,
        "attempts": max_retries
    }


async def scrape_batch(urls: List[str], max_concurrent: int) -> List[Dict]:
    """Scrape a batch of URLs"""
    global request_count
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            channel="chrome",
            args=[
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
                '--no-sandbox',
                '--disable-gpu',
                '--no-zygote',
                '--single-process'
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        tasks = [scrape_single_url(context, url, semaphore) for url in urls]
        results = await asyncio.gather(*tasks)
        
        await browser.close()
    
    request_count += len(urls)
    return [r for r in results if r is not None]


# ============== MAIN PROCESSING ==============

request_count = 0


async def process_batch(client: Client, urls: List[str], batch_num: int, concurrency: int):
    """Process a single batch of URLs"""
    print(f"\n{'='*60}")
    print(f"BATCH {batch_num}: Processing {len(urls)} URLs")
    print(f"{'='*60}")
    
    # Mark as processing
    for url in urls:
        try:
            update_url_status(client, url, "processing")
        except Exception as e:
            print(f"  ⚠️  Failed to mark {url} as processing: {e}")
    
    # Scrape
    results = await scrape_batch(urls, concurrency)
    
    # Process results
    successful = 0
    failed = 0
    
    for result in results:
        url = result["url"]
        
        if result["status"] == "success":
            try:
                # Insert into documents
                insert_document(client, url, result["content"], result["title"])
                
                # Mark as completed
                update_url_status(client, url, "completed", result["content"], result["title"])
                successful += 1
                
            except Exception as e:
                print(f"  ❌ Failed to process {url}: {e}")
                traceback.print_exc()
                failed += 1
        else:
            try:
                # Mark as failed
                update_url_status(client, url, "failed")
                failed += 1
            except Exception as e:
                print(f"  ⚠️  Failed to mark {url} as failed: {e}")
    
    return successful, failed


async def main_async(args):
    """Main async function"""
    # Validate environment
    if not SUPABASE_KEY:
        print("❌ Error: SUPABASE_KEY environment variable is required")
        print("\nSet it with:")
        print("  export SUPABASE_KEY='your-key'")
        print("  # OR on Windows:")
        print("  set SUPABASE_KEY=your-key")
        sys.exit(1)
    
    # Connect to database
    print("🔌 Connecting to Supabase...")
    client = get_supabase_client()
    
    # Fetch pending URLs
    print(f"\n📋 Fetching pending URLs...")
    all_urls = get_pending_urls(client, limit=args.limit)
    total_urls = len(all_urls)
    
    if total_urls == 0:
        print("✅ No pending URLs found!")
        return
    
    print(f"✓ Found {total_urls} pending URLs")
    
    # Process in batches
    batch_size = args.batch_size
    batches = [all_urls[i:i + batch_size] for i in range(0, total_urls, batch_size)]
    total_batches = len(batches)
    
    print(f"\n⚙️  Configuration:")
    print(f"   Total URLs: {total_urls}")
    print(f"   Batch size: {batch_size}")
    print(f"   Total batches: {total_batches}")
    print(f"   Concurrency: {args.concurrency}")
    print(f"   OpenAI embeddings: {'Enabled' if OPENAI_API_KEY else 'Disabled'}")
    
    # Process each batch
    total_successful = 0
    total_failed = 0
    
    for batch_num, batch in enumerate(batches, 1):
        urls = [item["url"] for item in batch]
        
        successful, failed = await process_batch(
            client,
            urls,
            batch_num,
            args.concurrency
        )
        
        total_successful += successful
        total_failed += failed
        
        print(f"\n📊 Batch {batch_num}/{total_batches} Summary:")
        print(f"   ✓ Success: {successful}")
        print(f"   ❌ Failed: {failed}")
        print(f"   Progress: {total_successful}/{total_urls} URLs processed")
        
        # Browser restart every BROWSER_RESTART_INTERVAL URLs
        if batch_num * batch_size >= BROWSER_RESTART_INTERVAL:
            print(f"\n🔄 Browser restart interval reached ({BROWSER_RESTART_INTERVAL} URLs)")
            # New browser will be created in next batch
    
    # Final summary
    print(f"\n{'='*60}")
    print("🎉 FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"Total URLs processed: {total_urls}")
    print(f"✅ Successful: {total_successful}")
    print(f"❌ Failed: {total_failed}")
    print(f"Success rate: {total_successful/total_urls*100:.1f}%")
    print(f"\n✅ Bulk import complete!")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Bulk scrape URLs and import to RAG system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bulk_scrape_import.py                 # Process all pending URLs
  python bulk_scrape_import.py --limit 100     # Process first 100 URLs
  python bulk_scrape_import.py --batch-size 3   # Smaller batches (more memory safe)
  python bulk_scrape_import.py --concurrency 2   # Reduce concurrent pages
        """
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of URLs to process (default: all pending)"
    )
    
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"URLs per batch (default: {DEFAULT_BATCH_SIZE})"
    )
    
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DEFAULT_CONCURRENCY,
        help=f"Concurrent pages per batch (default: {DEFAULT_CONCURRENCY})"
    )
    
    args = parser.parse_args()
    
    # Run async main
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
