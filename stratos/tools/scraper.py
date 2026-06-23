# stratos/tools/scraper.py
"""
Web scraping utilities using Firecrawl.
Now with async support and retry logic for reliability.
"""
import datetime
import asyncio
from dataclasses import dataclass
from typing import Optional
from firecrawl import FirecrawlApp
from stratos.config import settings
from stratos.retry import with_retry, retry_async
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("scraper")


@dataclass
class ScrapedContent:
    """Container for scraped content."""
    url: str
    markdown_content: str
    title: str
    scraped_at: datetime.datetime


def scrape_url_sync(url: str) -> ScrapedContent:
    """
    Synchronous version of scrape_url.
    Falls back to sync if async is not available.
    """
    try:
        app = FirecrawlApp(api_key=settings.firecrawl_api_key)
        result = app.scrape_url(url, formats=["markdown"])
        
        # Extract markdown and metadata
        try:
            markdown = result.markdown
            title = result.metadata.title if result.metadata and result.metadata.title else url
        except AttributeError:
            markdown = result.get("markdown", "")
            metadata = result.get("metadata", {})
            title = metadata.get("title", url) if metadata else url
        
        if not markdown or len(markdown) < 100:
            raise ValueError("Content too short or empty")
        
        return ScrapedContent(
            url=url,
            markdown_content=markdown,
            title=title,
            scraped_at=datetime.datetime.utcnow()
        )
        
    except ValueError as ve:
        raise ve
    except Exception as e:
        raise RuntimeError(f"Failed to scrape {url}: {str(e)}")


@with_retry(max_attempts=3, min_wait=1.0, max_wait=10.0, operation_name="scrape_url_async")
async def scrape_url_async(url: str) -> ScrapedContent:
    """
    Asynchronous version of scrape_url with retry logic.
    Retries up to 3 times with exponential backoff on failure.
    """
    try:
        # Firecrawl's async support - run in thread pool
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: scrape_url_sync(url)
        )
        return result
        
    except Exception as e:
        logger.warning(f"Scrape failed for {url}: {e}")
        raise RuntimeError(f"Failed to scrape {url} asynchronously: {str(e)}")


async def scrape_multiple(urls: list[str]) -> list[ScrapedContent]:
    """
    Scrape multiple URLs in parallel with individual retry logic.
    
    Args:
        urls: List of URLs to scrape
    
    Returns:
        List of ScrapedContent objects (errors are raised individually)
    """
    tasks = [scrape_url_async(url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    scraped_results = []
    for url, result in zip(urls, results):
        if isinstance(result, Exception):
            logger.error(f"Failed to scrape {url}: {result}")
        else:
            scraped_results.append(result)
    
    return scraped_results


if __name__ == "__main__":
    test_url = "https://openai.com/blog"
    
    # Test async version with retry
    print("Testing async scraper with retry...")
    try:
        content = asyncio.run(scrape_url_async(test_url))
        print(f"✅ Title: {content.title}")
        print(f"✅ Content length: {len(content.markdown_content)} chars")
    except Exception as e:
        print(f"❌ Async test failed: {e}")
    
    # Test parallel scraping with retry
    print("\nTesting parallel scraping with retry...")
    urls = [
        "https://openai.com/blog",
        "https://www.anthropic.com/news",
        "https://cohere.com/blog",
    ]
    try:
        results = asyncio.run(scrape_multiple(urls))
        print(f"✅ Scraped {len(results)} URLs successfully")
        for r in results:
            print(f"   - {r.title[:50]}...")
    except Exception as e:
        print(f"❌ Parallel test failed: {e}")