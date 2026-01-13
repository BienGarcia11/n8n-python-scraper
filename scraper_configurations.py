"""
Example configurations for versatile_scraper.py
Demonstrates how to customize the scraper for different website types
"""

from versatile_scraper import VersatileScraper, WEBSITE_PRESETS
import asyncio


# Example 1: Using preset configurations
async def example_preset_blog():
    """Scrape a blog post using preset configuration"""
    url = "https://example.com/blog/my-post"
    config = WEBSITE_PRESETS['blog']
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("blog_post.json")
    
    return data


# Example 2: Using preset for news articles
async def example_preset_news():
    """Scrape a news article using preset configuration"""
    url = "https://news.example.com/article"
    config = WEBSITE_PRESETS['news']
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("news_article.json")
    
    return data


# Example 3: Using preset for documentation
async def example_preset_docs():
    """Scrape documentation using preset configuration"""
    url = "https://docs.example.com/guide"
    config = WEBSITE_PRESETS['documentation']
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("documentation.json")
    
    return data


# Example 4: Using preset for ecommerce
async def example_preset_ecommerce():
    """Scrape product page using preset configuration"""
    url = "https://shop.example.com/product/123"
    config = WEBSITE_PRESETS['ecommerce']
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("product.json")
    
    return data


# Example 5: Custom configuration for specific website
async def example_custom_config():
    """Create custom configuration for a specific website"""
    url = "https://example.com/specific-page"
    
    # Define custom configuration
    config = {
        'name': 'custom-example',
        'title_selectors': ['h1.title', '.page-title', '[data-test-id="main-title"]'],
        'content_selectors': ['#main-content', '.article-body', '[data-test-id="content"]'],
        'paragraph_selectors': ['p'],
        'heading_selectors': ['h1', 'h2', 'h3', 'h4'],
        'list_selectors': ['ul', 'ol'],
        'link_selectors': ['a'],
        'code_selectors': ['pre', 'code'],
        'image_selectors': ['img', '.product-image'],
        'remove_selectors': [
            'script', 'style', 
            '.advertisement', 
            '.sidebar',
            '.comments-section',
            '[class*="ad"]',
            '.popup'
        ],
        'wait_timeout': 30000,
        'wait_strategy': 'domcontentloaded'
    }
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("custom_scrape.json")
    
    return data


# Example 6: Minimal configuration (uses defaults)
async def example_default_config():
    """Use default configuration for simple scraping"""
    url = "https://example.com/simple-page"
    
    # No config provided - uses defaults
    scraper = VersatileScraper(url)
    data = await scraper.scrape()
    scraper.save_to_json("default_scrape.json")
    
    return data


# Example 7: Advanced custom configuration
async def example_advanced_config():
    """Advanced configuration with all options"""
    url = "https://example.com/complex-page"
    
    config = {
        'name': 'advanced-custom',
        # Title selectors (tried in order)
        'title_selectors': [
            'h1.article-title',
            '.post-header h1',
            '[itemprop="headline"]',
            'title'
        ],
        # Content selectors (tried in order)
        'content_selectors': [
            'article.main-content',
            '.post-body',
            '[itemprop="articleBody"]',
            'main',
            '#content'
        ],
        # Element selectors
        'paragraph_selectors': ['p', '.text-block', '[class*="paragraph"]'],
        'heading_selectors': ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
        'list_selectors': ['ul', 'ol'],
        'link_selectors': ['a'],
        'code_selectors': ['pre', 'code', '.code-block', '[class*="code"]'],
        'image_selectors': ['img', 'figure img', '[class*="image"]'],
        # Elements to remove
        'remove_selectors': [
            'script', 'style', 'noscript',
            'nav', 'header', 'footer', 'aside',
            '.advertisement', '.ad', '[class*="ad"]',
            '.sidebar', '[class*="sidebar"]',
            '.comments', '[class*="comment"]',
            '.newsletter', '[class*="subscribe"]',
            '.popup', '.modal', '[class*="modal"]',
            '.cookie-banner', '[class*="cookie"]',
            '.social-share', '[class*="share"]',
            '.breadcrumb', '[class*="breadcrumbs"]',
            '.pagination', '[class*="paging"]'
        ],
        # Wait settings
        'wait_timeout': 45000,  # 45 seconds
        'wait_strategy': 'networkidle'  # or 'load', 'domcontentloaded', 'commit'
    }
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("advanced_scrape.json")
    
    return data


# Example 8: Scraping multiple URLs with same config
async def example_multiple_urls():
    """Scrape multiple URLs using the same configuration"""
    urls = [
        "https://example.com/page1",
        "https://example.com/page2",
        "https://example.com/page3"
    ]
    
    # Use blog preset for all
    config = WEBSITE_PRESETS['blog']
    
    for i, url in enumerate(urls):
        print(f"\n{'='*60}")
        print(f"Scraping URL {i+1}/{len(urls)}: {url}")
        print(f"{'='*60}\n")
        
        scraper = VersatileScraper(url, config)
        data = await scraper.scrape()
        
        # Save with unique filename
        filename = f"blog_post_{i+1}.json"
        scraper.save_to_json(filename)
    
    return len(urls)


# Example 9: Extracting specific content only
async def example_selective_extraction():
    """Configure to extract only specific elements"""
    url = "https://example.com/article"
    
    config = {
        'name': 'selective',
        'content_selectors': ['#main-content'],
        'remove_selectors': ['script', 'style', '.sidebar', '.comments'],
        # We can modify the scraper instance to only extract what we want
    }
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    
    # After scraping, you can manually filter the data
    # For example, only keep headings and paragraphs
    filtered_content = {
        'headings': data['content']['headings'],
        'paragraphs': data['content']['paragraphs'],
        'title': data['metadata']['title']
    }
    
    # Save filtered data
    import json
    with open("filtered_content.json", 'w') as f:
        json.dump(filtered_content, f, indent=2)
    
    return data


# Example 10: Dynamic configuration based on URL
async def example_dynamic_config(url):
    """Select configuration dynamically based on URL"""
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Select preset based on domain
    if 'blog' in domain:
        config = WEBSITE_PRESETS['blog']
    elif 'news' in domain or 'bbc.com' in domain:
        config = WEBSITE_PRESETS['news']
    elif 'docs' in domain or 'documentation' in domain:
        config = WEBSITE_PRESETS['documentation']
    elif 'shop' in domain or 'store' in domain:
        config = WEBSITE_PRESETS['ecommerce']
    else:
        config = None  # Use default
    
    scraper = VersatileScraper(url, config)
    data = await scraper.scrape()
    scraper.save_to_json("dynamic_scrape.json")
    
    return data


# Example 11: Error handling
async def example_with_error_handling(url):
    """Scrape with proper error handling"""
    config = WEBSITE_PRESETS['blog']
    
    try:
        scraper = VersatileScraper(url, config)
        data = await scraper.scrape()
        
        # Validate that we got some content
        if not data.get('full_text'):
            raise ValueError("No content extracted")
        
        scraper.save_to_json("safe_scrape.json")
        print("✓ Scraping successful")
        return data
        
    except Exception as e:
        print(f"✗ Error scraping {url}: {e}")
        # Log the error or handle it appropriately
        return None


# Main function to run examples
async def main():
    """Run example demonstrations"""
    
    print("="*60)
    print("VERSATILE SCRAPER - CONFIGURATION EXAMPLES")
    print("="*60)
    
    print("\nAvailable examples:")
    print("1. example_preset_blog() - Scrape blog post with preset")
    print("2. example_preset_news() - Scrape news article with preset")
    print("3. example_preset_docs() - Scrape documentation with preset")
    print("4. example_preset_ecommerce() - Scrape product page with preset")
    print("5. example_custom_config() - Use custom configuration")
    print("6. example_default_config() - Use default configuration")
    print("7. example_advanced_config() - Advanced custom configuration")
    print("8. example_multiple_urls() - Scrape multiple URLs")
    print("9. example_selective_extraction() - Extract specific content")
    print("10. example_dynamic_config(url) - Dynamic config based on URL")
    print("11. example_with_error_handling(url) - With error handling")
    
    print("\n" + "="*60)
    print("To run an example, call the function:")
    print("  asyncio.run(example_preset_blog())")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())