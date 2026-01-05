"""Configuration settings for the scraper."""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Configuration class for scraper settings."""
    
    # Supabase
    SUPABASE_URL = os.getenv('SUPABASE_URL')
    SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')
    
    # OpenAI
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    
    # Scraper settings
    CONCURRENCY_LIMIT = int(os.getenv('CONCURRENCY_LIMIT', 5))
    BATCH_SIZE = int(os.getenv('BATCH_SIZE', 50))
    MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))
    TIMEOUT_SECONDS = int(os.getenv('TIMEOUT_SECONDS', 30))
    SCROLL_WAIT_MS = int(os.getenv('SCROLL_WAIT_MS', 1000))
    INTERACTION_WAIT_MS = int(os.getenv('INTERACTION_WAIT_MS', 1000))
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Browser settings
    HEADLESS = True
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]
    
    @classmethod
    def validate(cls) -> bool:
        """Validate required configuration."""
        required = [
            ('SUPABASE_URL', cls.SUPABASE_URL),
            ('SUPABASE_SERVICE_KEY', cls.SUPABASE_SERVICE_KEY),
            ('OPENAI_API_KEY', cls.OPENAI_API_KEY),
        ]
        
        missing = [name for name, value in required if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        return True
