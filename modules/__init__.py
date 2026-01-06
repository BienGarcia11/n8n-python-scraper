"""
RAG Scraper Modules Package.

This package contains all the core modules for the RAG scraper worker:
- scraper: Playwright browser management with anti-bot detection
- extractor: Trafilatura-based content extraction
- chunker: Token-aware text chunking with overlap
- embedder: OpenAI embedding generation
"""

from .scraper import PlaywrightScraper
from .extractor import ContentExtractor
from .chunker import TextChunker
from .embedder import EmbeddingGenerator

__all__ = [
    "PlaywrightScraper",
    "ContentExtractor",
    "TextChunker",
    "EmbeddingGenerator",
]

__version__ = "1.0.0"
