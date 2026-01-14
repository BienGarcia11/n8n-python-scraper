"""
Test script to verify structured logging is working correctly
"""

from logger_config import setup_logger

def test_logging():
    """Test different log levels and structured output"""
    logger = setup_logger(__name__)
    
    logger.info("Application started", extra={"test": "logging", "status": "starting"})
    logger.debug("Debug message", extra={"level": "debug"})
    logger.warning("Warning message", extra={"level": "warning"})
    logger.error("Error message", extra={"level": "error"})
    
    # Test with structured data
    data = {
        "url": "https://example.com",
        "status": "processing",
        "chunks": 10,
        "embedding_dimension": 1536
    }
    logger.info("Processing data", extra=data)
    
    logger.info("Test completed successfully", extra={"status": "done"})

if __name__ == "__main__":
    test_logging()
