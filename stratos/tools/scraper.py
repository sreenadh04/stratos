import datetime
from dataclasses import dataclass
from firecrawl import FirecrawlApp
from stratos.config import settings

@dataclass
class ScrapedContent:
    url: str
    markdown_content: str
    title: str
    scraped_at: datetime.datetime

def scrape_url(url: str) -> ScrapedContent:
    try:
        app = FirecrawlApp(api_key=settings.firecrawl_api_key)
        # Firecrawl v1.x+ SDK uses formats as a keyword argument directly
        result = app.scrape_url(url, formats=["markdown"])
        
        # In v1.x+ SDK, result.markdown and result.metadata (as an object) are expected
        try:
            markdown = result.markdown
            # result.metadata is a DocumentMetadata object
            title = result.metadata.title if result.metadata and result.metadata.title else url
        except AttributeError:
            # Fallback if it's still a dict
            markdown = result.get("markdown", "")
            metadata = result.get("metadata", {})
            title = metadata.get("title", url) if metadata else url
        
        if not markdown or len(markdown) < 100:
            raise ValueError("Content too short")
            
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

if __name__ == "__main__":
    test_url = "https://openai.com/blog"
    try:
        print(f"Scraping {test_url}...")
        content = scrape_url(test_url)
        print(f"Title: {content.title}")
        print(f"Markdown preview (first 200 chars):\n{content.markdown_content[:200]}...")
    except Exception as e:
        print(f"Test failed: {e}")
