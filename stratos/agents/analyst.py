# stratos/agents/analyst.py
"""
Analyst Agent - LLM Scoring and Deduplication.
Now with batch processing, confidence filtering, and semantic caching.
"""
import uuid
import datetime
import json
import re
import asyncio
from typing import List, Dict, Any, Optional
from stratos.config import settings
from stratos.memory.embeddings import embed_text
from stratos.memory.vector_store import QdrantStore
from stratos.llm.factory import LLMFactory
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import SignalRepository
from stratos.logging_config import get_run_logger
from stratos.retry import with_retry, with_timeout, gather_with_partial_recovery


# ============================================================
# #11: EMBEDDING MODEL CONFIG
# ============================================================
EMBEDDING_MODEL = getattr(settings, "embedding_model", "text-embedding-001")
EMBEDDING_DIM = 768  # Gemini text-embedding-001


# ============================================================
# PROMPT
# ============================================================
ANALYST_PROMPT = """
You are a competitive intelligence analyst. Analyze the following content from a competitor's blog/website and extract the most important strategic signal.

Competitor: {competitor_name}
Content: {content}
Our Product Context: {product_context}

Respond ONLY with a valid JSON object in this exact format:
{{
  "summary": "one sentence summary of the key strategic signal",
  "impact_level": "HIGH or MEDIUM or LOW",
  "evidence": "specific quote or detail from the content that supports this",
  "confidence": 0.0 to 1.0
}}

Rules:
- HIGH: major product launch, pricing change, new market entry
- MEDIUM: feature update, partnership, hiring surge
- LOW: blog post, minor update, general content
- Be specific, not generic. Reference actual content.
"""


# ============================================================
# #10: SEMANTIC CACHE
# ============================================================
# Simple in-memory cache for semantic deduplication
# In production, this should use Redis or a similar distributed cache
_semantic_cache: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour


def get_cache_key(content: str) -> str:
    """Generate a cache key from content."""
    # Simple approach: use the first 100 chars + length as key
    # In production, use a proper hash
    return f"{content[:100]}_{len(content)}"


async def get_cached_analysis(content: str) -> Optional[Dict[str, Any]]:
    """Get cached analysis if available and not expired."""
    key = get_cache_key(content)
    if key in _semantic_cache:
        entry = _semantic_cache[key]
        if datetime.datetime.utcnow().timestamp() - entry["timestamp"] < CACHE_TTL_SECONDS:
            return entry["analysis"]
    return None


async def cache_analysis(content: str, analysis: Dict[str, Any]) -> None:
    """Cache the analysis result."""
    key = get_cache_key(content)
    _semantic_cache[key] = {
        "analysis": analysis,
        "timestamp": datetime.datetime.utcnow().timestamp(),
    }


# ============================================================
# #12: BATCH LLM PROCESSING
# ============================================================
async def process_snapshots_batch(
    snapshots: List[Dict[str, Any]],
    run_id: str,
) -> List[Dict[str, Any]]:
    """
    Process multiple snapshots in parallel using batch LLM calls.
    """
    logger = get_run_logger("analyst", run_id)
    
    # Get LLM provider
    llm = LLMFactory.get_provider()
    logger.info(f"🔍 Using LLM provider: {llm.get_provider_name()}")
    
    # Prepare prompts
    prompts = []
    for snapshot in snapshots:
        content_preview = snapshot['content'][:3000]
        prompt = ANALYST_PROMPT.format(
            competitor_name=snapshot['competitor_name'],
            content=content_preview,
            product_context=settings.product_context
        )
        prompts.append(prompt)
    
    # #12: Batch call to LLM
    responses = await LLMFactory.batch_generate(
        prompts=prompts,
        response_format="json",
        temperature=0.3,
        max_tokens=500,
    )
    
    # Process responses
    results = []
    for i, response in enumerate(responses):
        snapshot = snapshots[i]
        competitor_name = snapshot.get('competitor_name', 'Unknown')
        
        if response is None:
            logger.error(f"❌ Failed to get response for {competitor_name}")
            # Fallback: create a default analysis
            analysis = {
                "summary": "Analysis unavailable",
                "impact_level": "LOW",
                "evidence": "LLM call failed",
                "confidence": 0.5
            }
        else:
            # Parse JSON
            try:
                analysis = json.loads(response.strip())
            except json.JSONDecodeError:
                match = re.search(r'\{.*\}', response, re.DOTALL)
                if match:
                    try:
                        analysis = json.loads(match.group(0))
                    except json.JSONDecodeError:
                        analysis = {
                            "summary": "Analysis unavailable",
                            "impact_level": "LOW",
                            "evidence": "Parse error",
                            "confidence": 0.5
                        }
                else:
                    analysis = {
                        "summary": "Analysis unavailable",
                        "impact_level": "LOW",
                        "evidence": "Parse error",
                        "confidence": 0.5
                    }
        
        results.append({
            "snapshot": snapshot,
            "analysis": analysis,
            "competitor_name": competitor_name,
        })
    
    return results


# ============================================================
# #8: BATCH QDRANT SEARCH
# ============================================================
async def check_duplicates_batch(
    summaries: List[str],
    competitor_id: str,
) -> List[bool]:
    """
    Check duplicates for multiple summaries in one batch call.
    """
    if not summaries:
        return []
    
    store = QdrantStore()
    results = []
    
    # Generate all embeddings
    embeddings = []
    for summary in summaries:
        embedding = embed_text(summary)
        if embedding:
            embeddings.append(embedding)
        else:
            embeddings.append([])
    
    # Batch search
    for i, embedding in enumerate(embeddings):
        if embedding:
            similar = store.search_similar(embedding, competitor_id)
            is_dup = any(hit['score'] > 0.98 for hit in similar)
            results.append(is_dup)
        else:
            results.append(False)
    
    return results


# ============================================================
# MAIN ANALYST FUNCTION
# ============================================================
async def run_analyst(snapshots: list[dict], run_id: str) -> list[dict]:
    """
    Analyze snapshots using the configured LLM provider.
    Features: batch processing, confidence filtering, semantic caching.
    """
    logger = get_run_logger("analyst", run_id)
    results = []
    store = QdrantStore()
    
    if not snapshots:
        logger.info("No snapshots to analyze")
        return []
    
    logger.info(f"📊 Analyzing {len(snapshots)} snapshots")
    
    try:
        # #12: Process in parallel
        processed = await process_snapshots_batch(snapshots, run_id)
        
        # #8: Batch Qdrant deduplication
        summaries = [p["analysis"].get("summary", "") for p in processed]
        competitor_id = snapshots[0].get('competitor_id', '')
        
        # Only batch dedup if all snapshots are from the same competitor
        # Otherwise, process individually
        same_competitor = all(s.get('competitor_id') == competitor_id for s in snapshots)
        
        if same_competitor and competitor_id:
            duplicate_flags = await check_duplicates_batch(summaries, competitor_id)
        else:
            duplicate_flags = [False] * len(processed)
        
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            
            for i, p in enumerate(processed):
                snapshot = p["snapshot"]
                analysis = p["analysis"]
                competitor_name = p["competitor_name"]
                
                summary = analysis.get("summary", "")
                impact_level = analysis.get("impact_level", "LOW")
                evidence = analysis.get("evidence", "")
                confidence = analysis.get("confidence", 0.0)
                
                # #9: Confidence-based filtering
                if confidence < 0.6:
                    logger.info(f"  ⏭️ Skipping low-confidence signal for {competitor_name} (confidence: {confidence:.2f})")
                    continue
                
                # #10: Check semantic cache
                cached = await get_cached_analysis(summary)
                if cached:
                    logger.info(f"  🔄 Using cached analysis for {competitor_name}")
                    summary = cached.get("summary", summary)
                    impact_level = cached.get("impact_level", impact_level)
                    evidence = cached.get("evidence", evidence)
                    confidence = cached.get("confidence", confidence)
                
                # Check if duplicate from batch
                is_duplicate = duplicate_flags[i] if i < len(duplicate_flags) else False
                
                if is_duplicate:
                    logger.info(f"  ⚠️ Duplicate signal skipped for {competitor_name}")
                    # Still save to DB but marked as duplicate
                else:
                    # Store in Qdrant
                    embedding = embed_text(summary)
                    if embedding:
                        store.upsert_signal(
                            signal_id=str(uuid.uuid4()),
                            vector=embedding,
                            payload={
                                "competitor_id": snapshot['competitor_id'],
                                "summary": summary,
                                "impact_level": impact_level
                            }
                        )
                    
                    # Cache the analysis
                    await cache_analysis(summary, analysis)
                
                # Save to DB
                raw_snapshot_id = snapshot.get('snapshot_id', None)
                signal = await signal_repo.create(
                    run_id=run_id,
                    competitor_id=snapshot['competitor_id'],
                    raw_snapshot_id=raw_snapshot_id,
                    impact_level=impact_level,
                    summary=summary,
                    evidence=evidence,
                    confidence=confidence,
                    is_duplicate=is_duplicate,
                    prompt_version=getattr(settings, "prompt_version", None),
                    llm_provider_used=getattr(settings, "llm_provider", "groq"),
                )
                
                await session.commit()
                
                results.append({
                    "signal_id": str(signal.id),
                    "competitor_id": snapshot['competitor_id'],
                    "competitor_name": competitor_name,
                    "summary": summary,
                    "evidence": evidence,
                    "impact_level": impact_level,
                    "is_duplicate": is_duplicate,
                    "confidence": confidence,
                })
                
                logger.info(f"  ✅ {competitor_name} -> {impact_level} | {summary[:60]}...")
        
        logger.info(f"✅ Analyst complete. Generated {len(results)} signals")
        return results
        
    except Exception as e:
        logger.error(f"❌ Error in run_analyst: {e}", exc_info=True)
        return results


# ============================================================
# SYNC WRAPPER (for backward compatibility)
# ============================================================
def run_analyst_sync(snapshots: list[dict], run_id: str) -> list[dict]:
    """Synchronous wrapper for run_analyst."""
    return asyncio.run(run_analyst(snapshots, run_id))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test():
        try:
            async with get_db_session_manual() as session:
                from stratos.db.repositories import RunRepository, RawSnapshotRepository
                run_repo = RunRepository(session)
                
                # Get most recent run
                runs = await run_repo.get_latest(1)
                if not runs:
                    print("No runs found. Run scout test first.")
                    return
                    
                run_id = str(runs[0].id)
                
                # Get snapshots for this run
                snapshot_repo = RawSnapshotRepository(session)
                snapshots = await snapshot_repo.get_by_run_with_content(run_id)
                
                print(f"Found {len(snapshots)} snapshots for run {run_id}")
                results = await run_analyst(snapshots, run_id)
                print(f"Analyst complete. Scored {len(results)} signals")
                
        except Exception as e:
            print(f"Test failed: {e}")
    
    asyncio.run(test())