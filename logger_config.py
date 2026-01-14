"""
Structured Logging Configuration for Railway
Configures JSON logging with contextual information for better observability
"""

import logging
import sys
import os
from datetime import datetime
from pythonjsonlogger import jsonlogger


def setup_logger(name: str = "app", level: str = None) -> logging.Logger:
    """
    Set up a structured JSON logger for Railway
    
    Args:
        name: Logger name (typically __name__ or module name)
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
              Defaults to LOG_LEVEL env var or INFO
    
    Returns:
        Configured logger instance
    """
    # Determine log level from env var or default to INFO
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level))
    
    # Avoid duplicate handlers
    if logger.handlers:
        return logger
    
    # Create JSON formatter for Railway logs
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        extra={}
    )
    
    # Console handler (for Railway)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level))
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


# Convenience function to get a module-level logger
def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module
    
    Args:
        name: Logger name (use __name__)
    
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Add custom log levels if needed
logging.TRACE = 5  # For very detailed tracing
logging.addLevelName(logging.TRACE, "TRACE")

def trace(self, message, *args, **kwargs):
    """Add trace method to logger"""
    if self.isEnabledFor(logging.TRACE):
        self._log(logging.TRACE, message, args, **kwargs)

logging.Logger.trace = trace


# Module-level logger for direct imports
logger = setup_logger("app")
