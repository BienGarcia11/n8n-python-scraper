# Modular Scraper System

## Overview

This project now uses a modular scraper architecture that allows for site-specific scrapers to be easily created and managed. Each scraper can be customized to target specific content and extract clean, high-quality data for your RAG system.

## Architecture

```
scrapers/
├── __init__.py              # Package initialization
├── base_scraper.py          # Base class with common functionality
└── fyi_support_scraper.py   # FYI.app specialized scraper
```

## BaseScraper Class

The `BaseScraper` class provides all common functionality:

- **Sitemap parsing**: Recursively fetches URLs from sitemaps and sub-sitemaps
- **Batch processing**: Processes URLs in configurable batches
- **Concurrency control**: Limits concurrent requests to avoid overwhelming servers
- **CSV export**: Saves scraped data to CSV format
- **Error handling**: Robust error handling and logging

### Key Methods to Override

When creating a new site-specific scraper, override these methods:

1. **`should_scrape_url(url)`** - Filter which URLs to scrape
2. **`get_crawler_params()`** - Customize crawl4ai parameters
3. **`extract_content(result)`** - Custom content extraction logic

## FYISupportScraper

The FYI.app support scraper is specifically designed for FYI.app's help center at `https://support.fyi.app/hc/`.

### Key Features

1. **Targeted Content Extraction**
   - Uses CSS selector: `.lt-article-container__column.lt-article-container__article`
   - Extracts only the main article content
   - Skips navigation, footers, sidebars, and other junk content

2. **Smart URL Filtering**
   - Only scrapes article pages (`/articles/` or `/hc/en-us/` patterns)
   - Skips search results, account pages, community pages
   - Ensures clean, relevant data for RAG system

3. **Clean Data Output**
   - Produces CSV with columns: `url`, `title`, `content`, `status`
   - Content is already cleaned and formatted as markdown
   - Perfect for embedding generation and RAG retrieval

## Usage

### Running the Scraper

**Option 1: Run directly**
```bash
python manager.py
```

**Option 2: Use API**
```bash
# Start the API server
python main.py

# Then trigger scraping
curl -X POST http://localhost:8000/start
```

**Option 3: Test configuration**
```bash
python test_scraper.py
```

### Creating a New Site-Specific Scraper

1. Create a new file in `scrapers/` directory (e.g., `my_scraper.py`)
2. Inherit from `BaseScraper`
3. Override the methods you need
4. Update `scrapers/__init__.py` to export your new scraper

Example:
```python
from .base_scraper import BaseScraper

class MySiteScraper(BaseScraper):
    def __init__(self, sitemap_url="https://mysite.com/sitemap.xml"):
        super().__init__(
            sitemap_url=sitemap_url,
            output_file="my_site_data.csv"
        )
    
    def should_scrape_url(self, url):
        # Add your URL filtering logic
        return True
    
    def get_crawler_params(self):
        # Customize crawler parameters
        base_params = super().get_crawler_params()
        return {
            **base_params,
            'css_selector': '.my-article-container',
        }
```

## Configuration

### Default Parameters (can be overridden)

- `max_concurrency`: 3 (concurrent requests)
- `batch_size`: 15 (URLs per batch)
- `bypass_cache`: True
- `use_magic`: True (crawl4ai magic mode)

### Changing Parameters

```python
from scrapers import FYISupportScraper

# Create scraper with custom parameters
scraper = FYISupportScraper(
    max_concurrency=5,
    batch_size=20
)
```

## Output Format

The scraper produces a CSV file with the following columns:

| Column | Description |
|--------|-------------|
| `url` | The article URL |
| `title` | Article title |
| `content` | Clean article content in markdown format |
| `status` | "Success", "Fail", or "Skipped" |

## Benefits

1. **Cleaner Data**: Site-specific targeting produces higher quality content
2. **Better Embeddings**: Clean content improves RAG retrieval accuracy
3. **Maintainable**: Easy to add new scrapers or modify existing ones
4. **Flexible**: Configurable parameters for different use cases
5. **Modular**: Reusable base class for multiple sites

## Migration from worker.py

The old `worker.py` file is kept as a backup. The new modular system replaces it with:

- Better organization and maintainability
- Site-specific customization capabilities
- Cleaner, more maintainable code structure

The output format remains the same, so the existing `embedder.py` and `uploader.py` work seamlessly with the new scrapers.

## Troubleshooting

### Scraper skips all URLs
Check the `should_scrape_url()` method to ensure your URLs match the filtering logic.

### Content includes unwanted elements
Review the `get_crawler_params()` method and adjust the CSS selector or exclude_tags.

### Need to extract additional metadata
Override the `extract_content()` method to add custom extraction logic.
