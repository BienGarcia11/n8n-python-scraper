import os
import asyncio
import requests
import hashlib
from urllib.parse import urlparse
from typing import List, Dict, Any

from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler
from supabase import create_client
from openai import OpenAI
import tiktoken
from dotenv import load_dotenv
from tqdm import tqdm
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)


# =========================
# CONFIG
# =========================

SITEMAP_URL = "https://support.fyi.app/hc/sitemap.xml"

ARTICLE_CONTAINER_CLASS = (
    "lt-article-container__column lt-article-container__article"
)

HEADERS = {
    "User-Agent": "FYI-RAG-Scraper/1.0"
}

EMBED_MODEL = "text-embedding-3-small"
CHUNK_TOKENS = 500
CHUNK_OVERLAP = 50

# Batch & Concurrency configuration
EMBEDDING_BATCH_SIZE = 100  # OpenAI supports up to 2048
DB_INSERT_BATCH_SIZE = 100   # Optimal for Supabase
CONCURRENT_URLS = 5          # Concurrent scraping limit
MAX_RETRIES = 3              # Retry attempts


# =========================
# ENV / CLIENTS
# =========================

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"]
)

openai = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

tokenizer = tiktoken.get_encoding("cl100k_base")


# =========================
# RETRY LOGIC
# =========================

retry_strategy = retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException, Exception)),
    reraise=True
)


# =========================
# HELPERS
# =========================

@retry_strategy
def fetch_xml(url: str) -> BeautifulSoup:
    res = requests.get(url, headers=HEADERS, timeout=30)
    res.raise_for_status()
    return BeautifulSoup(res.text, "xml")


def load_sitemap_urls(sitemap_url: str) -> List[str]:
    """Recursively fetch URLs from sitemap or sitemap index."""
    soup = fetch_xml(sitemap_url)
    
    # Check if it's a sitemap index
    sitemaps = soup.find_all("sitemap")
    if sitemaps:
        child_urls = [s.find("loc").text.strip() for s in sitemaps]
        all_urls = []
        print(f"🔗 Sitemap index detected, fetching {len(child_urls)} child sitemaps...")
        for child_url in tqdm(child_urls, desc="Fetching child sitemaps"):
            all_urls.extend(load_sitemap_urls(child_url))
        return all_urls

    # Regular sitemap
    return [loc.text.strip() for loc in soup.find_all("loc")]


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str) -> List[str]:
    tokens = tokenizer.encode(text)
    chunks = []

    start = 0
    while start < len(tokens):
        end = start + CHUNK_TOKENS
        chunk = tokens[start:end]
        chunks.append(tokenizer.decode(chunk))
        start += CHUNK_TOKENS - CHUNK_OVERLAP

    return chunks


@retry_strategy
def embed_texts_batch(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for multiple texts in one API call."""
    if not texts:
        return []
    response = openai.embeddings.create(
        model=EMBED_MODEL,
        input=texts
    )
    return [item.embedding for item in response.data]


def already_ingested(url: str, hash_value: str) -> bool:
    result = (
        supabase.table("documents")
        .select("id")
        .eq("metadata->>url", url)
        .eq("metadata->>hash", hash_value)
        .limit(1)
        .execute()
    )
    return len(result.data) > 0


@retry_strategy
def insert_chunks_batch(chunks_data: List[Dict[str, Any]]):
    """Insert multiple chunks into Supabase in one operation."""
    if not chunks_data:
        return
    supabase.table("documents").insert(chunks_data).execute()


# =========================
# VALIDATION
# =========================

async def validate_structure(sample_urls: List[str]):
    print("🔍 Validating article structure...\n")

    async with AsyncWebCrawler() as crawler:
        for url in sample_urls:
            result = await crawler.arun(url)
            soup = BeautifulSoup(result.html, "lxml")

            article = soup.find("div", class_=ARTICLE_CONTAINER_CLASS)

            if not article:
                raise RuntimeError(
                    f"❌ Structure mismatch detected at: {url}"
                )

            print(f"✅ Structure OK: {url}")

    print("\n✔ All sampled URLs share the same structure\n")


# =========================
# SCRAPING + INGESTION
# =========================

async def process_url(url: str, crawler: AsyncWebCrawler, semaphore: asyncio.Semaphore, stats: Dict[str, int]):
    async with semaphore:
        try:
            result = await crawler.arun(url)
            soup = BeautifulSoup(result.html, "lxml")

            article = soup.find("div", class_=ARTICLE_CONTAINER_CLASS)
            if not article:
                # print(f"⚠ No article container for {url}, skipping")
                stats["skipped"] += 1
                return

            title_tag = soup.find("h1")
            title = title_tag.get_text(strip=True) if title_tag else ""

            content = article.get_text("\n", strip=True)
            hash_value = content_hash(content)

            if already_ingested(url, hash_value):
                stats["skipped"] += 1
                return

            chunks = chunk_text(content)
            
            # Batch embedding
            embeddings = embed_texts_batch(chunks)
            
            base_metadata = {
                "url": url,
                "title": title,
                "source": "fyi_support",
                "sitemap": SITEMAP_URL,
                "hash": hash_value
            }

            # Prepare batch insert
            chunks_to_insert = []
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                chunks_to_insert.append({
                    "content": chunk,
                    "embedding": embedding,
                    "metadata": {
                        **base_metadata,
                        "chunk_index": i
                    }
                })
            
            # Batch insert
            insert_chunks_batch(chunks_to_insert)
            
            stats["processed"] += 1
            stats["chunks"] += len(chunks)
            
        except Exception as e:
            print(f"❌ Error processing {url}: {e}")
            stats["errors"] += 1


async def scrape_and_ingest(urls: List[str]):
    semaphore = asyncio.Semaphore(CONCURRENT_URLS)
    stats = {"processed": 0, "skipped": 0, "errors": 0, "chunks": 0}
    
    print(f"🚀 Starting concurrent scraping of {len(urls)} URLs...")
    print(f"   Concurrency: {CONCURRENT_URLS} URLs at a time\n")
    
    async with AsyncWebCrawler() as crawler:
        tasks = [process_url(url, crawler, semaphore, stats) for url in urls]
        for f in tqdm(asyncio.as_completed(tasks), total=len(urls), desc="Scraping URLs"):
            await f

    print("\n📊 SCRAPING SUMMARY:")
    print(f"   Total URLs: {len(urls)}")
    print(f"   ✅ Processed: {stats['processed']}")
    print(f"   ⏩ Skipped: {stats['skipped']}")
    print(f"   ❌ Errors: {stats['errors']}")
    print(f"   📝 Total chunks inserted: {stats['chunks']}")
    if stats['processed'] > 0:
        print(f"   ⚡ Average chunks per URL: {stats['chunks'] / stats['processed']:.1f}")


# =========================
# SCRAPER FACTORY (future-proof)
# =========================

def get_scraper(sitemap_url: str):
    domain = urlparse(sitemap_url).netloc

    if domain == "support.fyi.app":
        return run_fyi_support_scraper

    raise ValueError(f"No scraper registered for {domain}")


# =========================
# MAIN SCRAPER
# =========================

async def run_fyi_support_scraper():
    all_urls = load_sitemap_urls(SITEMAP_URL)
    urls = [
        url for url in all_urls
        if "/articles/" in url
    ]

    print(f"📍 Found {len(urls)} ARTICLE URLs in sitemap\n")

    if not urls:
        print("Empty sitemap, exiting.")
        return

    await validate_structure(urls[:3]) # Reduced sample size for speed
    await scrape_and_ingest(urls)

    print("\n🎉 FYI support ingestion complete")


# =========================
# ENTRY POINT
# =========================

if __name__ == "__main__":
    scraper = get_scraper(SITEMAP_URL)
    asyncio.run(scraper())
