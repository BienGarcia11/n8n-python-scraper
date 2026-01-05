"""Main entry point for the RAG scraper."""
import asyncio
import logging
import sys
from config import Config
from database import DatabaseManager
from scraper.browser import browser_manager
from scraper.main import URLScraper
from embeddings.generator import EmbeddingGenerator


def setup_logging():
    """Configure logging for the application."""
    log_level = getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('scraper.log')
        ]
    )


async def main():
    """Main entry point."""
    # Setup logging
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("RAG System Scraper Starting")
    logger.info("=" * 60)
    
    # Validate configuration
    try:
        Config.validate()
        logger.info("Configuration validated successfully")
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Initialize components
    db_manager = None
    embedding_gen = None
    
    try:
        # Initialize database manager
        db_manager = DatabaseManager()
        
        # Get initial statistics
        stats = db_manager.get_statistics()
        logger.info(f"Database statistics: {stats}")
        
        # Initialize embedding generator
        embedding_gen = EmbeddingGenerator()
        
        # Initialize browser manager
        await browser_manager.initialize()
        
        # Create and run scraper
        scraper = URLScraper(db_manager, embedding_gen)
        await scraper.run()
        
        # Log final statistics
        final_stats = db_manager.get_statistics()
        logger.info(f"Final database statistics: {final_stats}")
        logger.info("=" * 60)
        logger.info("Scraping completed successfully")
        logger.info("=" * 60)
        
    except KeyboardInterrupt:
        logger.info("Scraper interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup
        logger.info("Cleaning up resources...")
        await browser_manager.close()
        logger.info("Cleanup completed")


if __name__ == "__main__":
    asyncio.run(main())
