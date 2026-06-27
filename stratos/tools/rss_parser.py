# stratos/tools/rss_parser.py
"""
RSS feed parser for change detection.
"""
import feedparser
from typing import List, Dict, Any
from stratos.logging_config import get_logger

logger = get_logger("rss_parser")


async def parse_rss(rss_url: str) -> List[Dict[str, Any]]:
    """
    Parse RSS feed and extract posts.
    
    Args:
        rss_url: URL of the RSS feed
    
    Returns:
        List of post dicts with keys: url, title, content_hash
    """
    try:
        feed = feedparser.parse(rss_url)
        
        if feed.bozo:  # bozo = True if parsing failed
            logger.warning(f"RSS parsing failed for {rss_url}: {feed.bozo_exception}")
            return []
        
        posts = []
        for entry in feed.entries[:10]:  # Limit to latest 10 posts
            post = {
                "url": entry.get("link", ""),
                "title": entry.get("title", ""),
                "content_hash": None,  # Will be computed when content is fetched
                "full_content": "",  # Will be fetched separately
                "published": entry.get("published", ""),
            }
            if post["url"]:
                posts.append(post)
        
        logger.info(f"Found {len(posts)} posts in RSS feed")
        return posts
        
    except Exception as e:
        logger.error(f"Error parsing RSS feed: {e}")
        return []
