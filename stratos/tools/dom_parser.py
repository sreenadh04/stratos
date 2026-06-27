# stratos/tools/dom_parser.py
"""
DOM parser for extracting posts from HTML.
"""
from typing import List, Dict, Any
import httpx
from bs4 import BeautifulSoup
from stratos.logging_config import get_logger

logger = get_logger("dom_parser")


async def parse_dom_for_posts(url: str) -> List[Dict[str, Any]]:
    """
    Parse HTML and extract blog post links.
    
    Args:
        url: URL of the blog page
    
    Returns:
        List of post dicts with keys: url, title, content_hash
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find all links that look like blog posts
        posts = []
        seen_urls = set()
        
        # Common blog post link patterns
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            text = link.get_text(strip=True)
            
            # Filter for likely blog post links
            if _is_blog_post_link(href, text):
                # Resolve relative URLs
                if href.startswith("/"):
                    href = url.rstrip("/") + href
                elif href.startswith("./"):
                    href = url.rstrip("/") + href[1:]
                elif not href.startswith("http"):
                    href = url.rstrip("/") + "/" + href
                
                if href not in seen_urls:
                    seen_urls.add(href)
                    posts.append({
                        "url": href,
                        "title": text or href,
                        "content_hash": None,
                        "full_content": "",
                    })
        
        # Limit to latest posts
        return posts[:10]
        
    except Exception as e:
        logger.error(f"Error parsing DOM: {e}")
        return []


def _is_blog_post_link(href: str, text: str) -> bool:
    """
    Heuristic to determine if a link is likely a blog post.
    """
    # Exclude common non-post links
    exclude_patterns = [
        "/tag/", "/category/", "/author/", "/page/",
        "javascript:", "#", "mailto:", "tel:",
        "/search", "/about", "/contact", "/privacy",
    ]
    
    for pattern in exclude_patterns:
        if pattern in href:
            return False
    
    # Include likely post patterns
    include_patterns = [
        "/blog/", "/news/", "/post/", "/article/",
        "/p/", "/entry/", "/202", "/20"  # Year-based URLs
    ]
    
    for pattern in include_patterns:
        if pattern in href:
            return True
    
    # If text is not empty and href is not too short
    if text and len(href) > 10 and "/" in href:
        return True
    
    return False
