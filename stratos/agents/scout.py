# stratos/agents/scout.py
"""
Scout Agent - Data acquisition layer.
Now fully async with parallel scraping, retry logic, timeouts, and multi-source support.
"""
import uuid
import datetime
import asyncio
from typing import List, Dict, Any, Optional
from stratos.tools.scraper import scrape_url_async
from stratos.tools.diff import compute_content_hash
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import (
    CompetitorRepository,
    RawSnapshotRepository,
    RunRepository,
)
from stratos.logging_config import get_run_logger
from stratos.retry import with_retry, with_timeout, gather_with_partial_recovery


# ============================================================
# SOURCE TYPES
# ============================================================
SOURCE_TYPES = {
    "blog": {"supported": True, "priority": 1},
    "github": {"supported": True, "priority": 2},
    "linkedin": {"supported": True, "priority": 3},
    "twitter": {"supported": True, "priority": 4},
}


# ============================================================
# SCOUT COMPETITOR WITH RETRY AND TIMEOUT
# ============================================================
@with_retry(max_attempts=3, min_wait=1.0, max_wait=10.0, operation_name="scout_competitor")
async def scout_competitor_with_retry(
    competitor_id: str,
    name: str,
    blog_url: str,
    source_type: str,
    run_id: str,
) -> List[Dict[str, Any]]:
    """
    Scout a single competitor with retry logic.
    """
    logger = get_run_logger("scout", run_id)
    results = []
    
    try:
        logger.info(f"  🔍 Scouting {name} ({source_type})...", extra={"competitor": name})
        
        # #3: Timeout for each competitor (increased to 30 seconds for Firecrawl)
        snapshots = await with_timeout(
            _scout_competitor_internal,
            30.0,
            competitor_id,
            name,
            blog_url,
            source_type,
            run_id,
        )
        
        if snapshots:
            results.extend(snapshots)
            logger.info(f"    ✅ Found {len(snapshots)} new snapshots for {name}")
        else:
            logger.info(f"    ⏭️  No new content for {name}")
            
    except asyncio.TimeoutError:
        logger.error(f"    ⏰ Timeout scouting {name}")
    except Exception as e:
        logger.error(f"    ❌ Error scouting {name}: {e}")
    
    return results


async def _scout_competitor_internal(
    competitor_id: str,
    name: str,
    blog_url: str,
    source_type: str,
    run_id: str,
) -> List[Dict[str, Any]]:
    """
    Internal implementation – uses Firecrawl directly (no RSS/DOM parsing).
    """
    results = []
    
    try:
        # Use Firecrawl to scrape the main blog page
        content = await scrape_url_async(blog_url)
        content_hash = compute_content_hash(content.markdown_content)
        
        async with get_db_session_manual() as session:
            snapshot_repo = RawSnapshotRepository(session)
            exists = await snapshot_repo.exists_for_hash(competitor_id, content_hash)
            
            if not exists:
                snapshot = await snapshot_repo.create(
                    competitor_id=competitor_id,
                    run_id=run_id,
                    source_url=blog_url,
                    content_hash=content_hash,
                    raw_content=content.markdown_content,
                    source_type=source_type,
                )
                await session.commit()
                
                results.append({
                    "competitor_id": competitor_id,
                    "competitor_name": name,
                    "snapshot_id": str(snapshot.id),
                    "content": content.markdown_content,
                    "blog_url": blog_url,
                    "content_hash": content_hash,
                    "source_type": source_type,
                    "title": content.title,
                })
                
    except Exception as e:
        logger = get_run_logger("scout", run_id)
        logger.error(f"Error scraping {name}: {e}")
    
    return results


# ============================================================
# MAIN SCOUT WITH PARALLEL SCRAPING
# ============================================================
async def run_scout(run_id: str) -> List[Dict[str, Any]]:
    """
    Iterate through competitors and scrape their blogs in parallel.
    Supports multiple source types.
    """
    logger = get_run_logger("scout", run_id)
    results = []
    
    try:
        # Get all competitors
        async with get_db_session_manual() as session:
            competitor_repo = CompetitorRepository(session)
            competitors = await competitor_repo.get_all()
        
        if not competitors:
            logger.warning("⚠️ No competitors found. Please seed competitors first.")
            return []
        
        logger.info(f"📋 Found {len(competitors)} competitors to scout")
        
        # #1: Create tasks for all competitors
        tasks = [
            lambda comp=comp: scout_competitor_with_retry(
                str(comp.id),
                comp.name,
                comp.blog_url,
                getattr(comp, 'source_type', 'blog'),
                run_id
            )
            for comp in competitors
        ]
        
        # #5: Run with partial failure recovery
        all_results = await gather_with_partial_recovery(
            tasks,
            continue_on_failure=True,
            max_retries=2,
        )
        
        # Flatten results and handle errors
        for result in all_results:
            if isinstance(result, Exception):
                logger.error(f"⚠️ Scout task failed: {result}")
            elif result:
                results.extend(result)
        
        # #6: Update competitor health status
        async with get_db_session_manual() as session:
            competitor_repo = CompetitorRepository(session)
            for comp in competitors:
                comp_id = str(comp.id)
                has_results = any(
                    r.get('competitor_id') == comp_id for r in results
                )
                await competitor_repo.update_health_status(comp_id, has_results)
            await session.commit()
        
        logger.info(f"✅ Scout complete. Found {len(results)} new snapshots.")
        
    except Exception as e:
        logger.error(f"❌ Database error in run_scout: {e}", exc_info=True)
    
    return results


# ============================================================
# SYNC WRAPPER (for backward compatibility)
# ============================================================
def run_scout_sync(run_id: str) -> List[Dict[str, Any]]:
    """Synchronous wrapper for run_scout."""
    return asyncio.run(run_scout(run_id))


# ============================================================
# BACKWARD COMPATIBILITY ALIAS
# ============================================================
scout_competitor = scout_competitor_with_retry


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