# stratos/agents/scout.py
"""
Scout Agent - Data acquisition layer.
Now fully async with parallel scraping using asyncio.gather.
"""
import uuid
import datetime
import asyncio
from typing import List, Dict, Any
from stratos.tools.scraper import scrape_url_async
from stratos.tools.diff import compute_content_hash
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import (
    CompetitorRepository,
    RawSnapshotRepository,
    RunRepository,
)
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("scout")


async def scout_competitor(competitor_id: str, name: str, blog_url: str, run_id: str) -> List[Dict[str, Any]]:
    """
    Scout a single competitor asynchronously.
    
    Args:
        competitor_id: UUID of the competitor
        name: Competitor name
        blog_url: URL to scrape
        run_id: Current run ID
    
    Returns:
        List of snapshot dicts (empty if no new content)
    """
    results = []
    
    try:
        logger.info(f"  🔍 Scouting {name}...", extra={"run_id": run_id, "competitor": name})
        
        # Scrape the blog (async)
        scraped = await scrape_url_async(blog_url)
        content = scraped.markdown_content
        
        # Compute hash
        content_hash = compute_content_hash(content)
        
        # Check if content already exists for this competitor
        async with get_db_session_manual() as session:
            snapshot_repo = RawSnapshotRepository(session)
            exists = await snapshot_repo.exists_for_hash(competitor_id, content_hash)
        
        if not exists:
            # Save new snapshot - capture the ID from the database
            async with get_db_session_manual() as session:
                snapshot_repo = RawSnapshotRepository(session)
                snapshot = await snapshot_repo.create(
                    competitor_id=competitor_id,
                    run_id=run_id,
                    source_url=blog_url,
                    content_hash=content_hash,
                    raw_content=content,
                )
                await session.commit()
                snapshot_id = str(snapshot.id)
            
            results.append({
                "competitor_id": competitor_id,
                "competitor_name": name,
                "snapshot_id": snapshot_id,
                "content": content,
                "blog_url": blog_url,
                "content_hash": content_hash,
            })
            
            logger.info(f"    ✅ New content found for {name} (snapshot: {snapshot_id[:8]})", 
                       extra={"run_id": run_id, "competitor": name})
        else:
            logger.info(f"    ⏭️  No changes for {name}", extra={"run_id": run_id, "competitor": name})
            
    except Exception as e:
        logger.error(f"    ❌ Error scouting {name}: {e}", extra={"run_id": run_id, "competitor": name}, exc_info=True)
    
    return results


async def run_scout(run_id: str) -> List[Dict[str, Any]]:
    """
    Iterate through competitors and scrape their blogs in parallel.
    
    Args:
        run_id: Current run ID
    
    Returns:
        List of snapshot dicts for all competitors with new content.
    """
    results = []
    
    try:
        # Get all competitors
        async with get_db_session_manual() as session:
            competitor_repo = CompetitorRepository(session)
            competitors = await competitor_repo.get_all()
        
        if not competitors:
            logger.warning("⚠️ No competitors found. Please seed competitors first.", extra={"run_id": run_id})
            return []
        
        logger.info(f"📋 Found {len(competitors)} competitors to scout", extra={"run_id": run_id})
        
        # Create tasks for all competitors
        tasks = [
            scout_competitor(
                str(comp.id),
                comp.name,
                comp.blog_url,
                run_id
            )
            for comp in competitors
        ]
        
        # Run all scouts in parallel
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Flatten results and handle errors
        for result in all_results:
            if isinstance(result, Exception):
                logger.error(f"⚠️ Scout task failed: {result}", extra={"run_id": run_id})
            else:
                results.extend(result)
        
        logger.info(f"✅ Scout complete. Found {len(results)} new snapshots.", extra={"run_id": run_id})
        
    except Exception as e:
        logger.error(f"❌ Database error in run_scout: {e}", extra={"run_id": run_id}, exc_info=True)
    
    return results


# Synchronous wrapper for backward compatibility
def run_scout_sync(run_id: str) -> List[Dict[str, Any]]:
    """Synchronous wrapper for run_scout."""
    return asyncio.run(run_scout(run_id))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    run_id = str(uuid.uuid4())
    
    # Create run record first
    async def create_run():
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            await run_repo.create(run_id, "manual")
            await session.commit()
        logger.info(f"Created run record: {run_id}")
    
    asyncio.run(create_run())
    
    logger.info(f"Starting scout test with run_id: {run_id}")
    results = asyncio.run(run_scout(run_id))
    logger.info(f"Scout complete. Found {len(results)} new snapshots.")