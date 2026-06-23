# stratos/agents/analyst.py
import uuid
import datetime
import json
import re
from stratos.config import settings
from stratos.memory.embeddings import embed_text
from stratos.memory.vector_store import QdrantStore
from stratos.llm.factory import LLMFactory
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import SignalRepository
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("analyst")

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


async def run_analyst(snapshots: list[dict], run_id: str) -> list[dict]:
    """Analyze snapshots using the configured LLM provider."""
    results = []
    store = QdrantStore()
    
    # Get LLM provider (from config)
    llm = LLMFactory.get_provider()
    logger.info(f"🔍 Using LLM provider: {llm.get_provider_name()}", extra={"run_id": run_id})
    
    try:
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            
            for snapshot in snapshots:
                try:
                    competitor_name = snapshot.get('competitor_name', 'Unknown')
                    logger.info(f"Analyzing {competitor_name}...", extra={"run_id": run_id, "competitor": competitor_name})
                    
                    # Build prompt
                    content_preview = snapshot['content'][:3000]
                    prompt = ANALYST_PROMPT.format(
                        competitor_name=competitor_name,
                        content=content_preview,
                        product_context=settings.product_context
                    )
                    
                    # Call LLM (provider-agnostic)
                    response_text = await llm.generate(
                        prompt=prompt,
                        response_format="json",
                        temperature=0.3,
                        max_tokens=500
                    )
                    
                    # Parse JSON
                    try:
                        analysis = json.loads(response_text.strip())
                    except json.JSONDecodeError:
                        match = re.search(r'\{.*\}', response_text, re.DOTALL)
                        if match:
                            analysis = json.loads(match.group(0))
                        else:
                            raise ValueError("No JSON found in response")
                    
                    summary = analysis.get("summary", "")
                    impact_level = analysis.get("impact_level", "LOW")
                    evidence = analysis.get("evidence", "")
                    confidence = analysis.get("confidence", 0.0)
                    
                    # Check for duplicates using vector search
                    is_duplicate = False
                    embedding = embed_text(summary)
                    
                    if embedding:
                        similar = store.search_similar(embedding, snapshot['competitor_id'])
                        for hit in similar:
                            if hit['score'] > 0.98:
                                is_duplicate = True
                                logger.info(f"  ⚠️ Duplicate signal skipped (score: {hit['score']:.3f})", 
                                           extra={"run_id": run_id, "competitor": competitor_name})
                                break
                        
                        if not is_duplicate:
                            store.upsert_signal(
                                signal_id=str(uuid.uuid4()),
                                vector=embedding,
                                payload={
                                    "competitor_id": snapshot['competitor_id'],
                                    "summary": summary,
                                    "impact_level": impact_level
                                }
                            )
                    
                    # Save to DB using repository
                    raw_snapshot_id = snapshot.get('snapshot_id', None)
                    
                    signal = await signal_repo.create(
                        run_id=run_id,
                        competitor_id=snapshot['competitor_id'],
                        raw_snapshot_id=raw_snapshot_id,
                        impact_level=impact_level,
                        summary=summary,
                        evidence=evidence,
                        confidence=confidence,
                        is_duplicate=is_duplicate
                    )
                    
                    await session.commit()
                    
                    results.append({
                        "signal_id": str(signal.id),
                        "competitor_id": snapshot['competitor_id'],
                        "competitor_name": competitor_name,
                        "summary": summary,
                        "evidence": evidence,
                        "impact_level": impact_level,
                        "is_duplicate": is_duplicate
                    })
                    
                    logger.info(f"  ✅ Impact: {impact_level} | {summary[:80]}...", 
                               extra={"run_id": run_id, "competitor": competitor_name})
                    
                except Exception as e:
                    logger.error(f"  ❌ Error analyzing snapshot: {e}", 
                                extra={"run_id": run_id, "competitor": snapshot.get('competitor_name', 'Unknown')}, 
                                exc_info=True)
                    await session.rollback()
                    continue
                    
    except Exception as e:
        logger.error(f"Database error in run_analyst: {e}", extra={"run_id": run_id}, exc_info=True)
            
    return results


if __name__ == "__main__":
    import asyncio
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
                    logger.info("No runs found. Run scout test first.")
                    return
                    
                run_id = str(runs[0].id)
                
                # Get snapshots for this run
                snapshot_repo = RawSnapshotRepository(session)
                snapshots = await snapshot_repo.get_by_run_with_content(run_id)
                
                logger.info(f"Found {len(snapshots)} snapshots for run {run_id}")
                results = await run_analyst(snapshots, run_id)
                logger.info(f"Analyst complete. Scored {len(results)} signals")
                
        except Exception as e:
            logger.error(f"Test failed: {e}")
    
    asyncio.run(test())