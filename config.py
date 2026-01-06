"""
Configuration module for the RAG scraper worker.
Loads environment variables and provides centralized configuration.
"""
import os
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

class Config:
    """Application configuration."""
    
    # Supabase Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536
    
    # Worker Configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    MAX_CONCURRENT_URLS: int = int(os.getenv("MAX_CONCURRENT_URLS", "3"))
    RETRY_ATTEMPTS: int = int(os.getenv("RETRY_ATTEMPTS", "3"))
    POLL_INTERVAL: int = int(os.getenv("POLL_INTERVAL", "5"))
    
    # Chunking Configuration
    CHUNK_SIZE_TOKENS: int = 500
    CHUNK_OVERLAP_TOKENS: int = 50
    
    # Playwright Configuration
    PLAYWRIGHT_BROWSERS_PATH: str = os.getenv("PLAYWRIGHT_BROWSERS_PATH", "/ms-playwright")
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_TIMEOUT: int = 30000  # 30 seconds
    
    # Anti-Bot Configuration
    USER_AGENTS: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    
    # Retry Configuration (exponential backoff in seconds)
    RETRY_DELAYS: List[int] = [2, 5, 10]  # For 3 retry attempts
    
    @classmethod
    def validate(cls) -> None:
        """Validate that all required configuration is present."""
        required_vars = [
            ("SUPABASE_URL", cls.SUPABASE_URL),
            ("SUPABASE_KEY", cls.SUPABASE_KEY),
            ("OPENAI_API_KEY", cls.OPENAI_API_KEY),
        ]
        
        missing = [name for name, value in required_vars if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Validate ranges
        if cls.MAX_CONCURRENT_URLS < 1:
            raise ValueError("MAX_CONCURRENT_URLS must be at least 1")
        if cls.RETRY_ATTEMPTS < 0:
            raise ValueError("RETRY_ATTEMPTS cannot be negative")
        if cls.POLL_INTERVAL < 1:
            raise ValueError("POLL_INTERVAL must be at least 1 second")
