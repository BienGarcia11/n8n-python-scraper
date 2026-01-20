"""
Modular scraper system for knowledge base extraction.
"""

from .base_scraper import BaseScraper
from .fyi_support_scraper import FYISupportScraper

__all__ = ['BaseScraper', 'FYISupportScraper']
