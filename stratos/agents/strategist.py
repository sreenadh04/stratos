# stratos/agents/strategist.py
import uuid
import datetime
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from stratos.config import settings
from stratos.llm.factory import LLMFactory
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import SignalRepository, CompetitorRepository
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("strategist")

STRATEGIST_PROMPT = """
You are a senior product strategist and competitive intelligence expert.

You have received the following intelligence signals about a competitor:

Competitor: {competitor_name}
Signals:
{signals_text}

Our Product Context: {product_context}

Analyze these signals and provide a strategic assessment.

Respond ONLY with a valid JSON object in this exact format:
{{
  "hypothesis": "What strategic direction is this competitor moving toward? Be specific.",
  "threat_level": "HIGH or MEDIUM or LOW or NEUTRAL",
  "implication": "What does this mean for our product specifically?",
  "recommendation": "One concrete action we should take in response.",
  "timeframe": "immediate or this_quarter or watch"
}}

Rules:
- Be specific and actionable, not generic
- Reference actual signals in your hypothesis
- HIGH threat: direct competition with our core features
- MEDIUM threat: adjacent moves that could affect us
- LOW/NEUTRAL: worth monitoring but not urgent
"""


async def run_strategist(signals: list[dict], run_id: str) -> list[dict]:
    """Generate strategic assessments using the configured LLM provider."""
    results = []
    
    # Get LLM provider (from config)
    llm = LLMFactory.get_provider()
    logger.info(f"🧠 Using LLM provider: {llm.get_provider_name()}", extra={"run_id": run_id})
    
    try:
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            competitor_repo = CompetitorRepository(session)
            
            # Get competitor names
            competitor_names = await competitor_repo.get_name_mapping()
            
            # Group signals by competitor_id
            competitor_groups = {}
            for s in signals:
                comp_id = str(s['competitor_id'])
                if comp_id not in competitor_groups:
                    competitor_groups[comp_id] = []
                competitor_groups[comp_id].append(s)
                
            for comp_id, group in competitor_groups.items():
                try:
                    # Skip if all signals in the group are duplicates
                    if all(s.get('is_duplicate', False) for s in group):
                        continue
                    
                    competitor_name = competitor_names.get(str(comp_id), "Unknown")
                    logger.info(f"Assessing {competitor_name}...", extra={"run_id": run_id, "competitor": competitor_name})
                    
                    # Build signals text
                    signals_text = ""
                    for i, s in enumerate(group):
                        signals_text += f"{i+1}. Summary: {s['summary']}\n   Evidence: {s['evidence']}\n\n"
                    
                    # Build prompt
                    prompt = STRATEGIST_PROMPT.format(
                        competitor_name=competitor_name,
                        signals_text=signals_text,
                        product_context=settings.product_context
                    )
                    
                    # Call LLM (provider-agnostic)
                    response_text = await llm.generate(
                        prompt=prompt,
                        response_format="json",
                        temperature=0.4,
                        max_tokens=600
                    )
                    
                    # Parse JSON
                    assessment = json.loads(response_text.strip())
                    
                    hypothesis = assessment.get("hypothesis", "")
                    recommendation = assessment.get("recommendation", "")
                    threat_level = assessment.get("threat_level", "NEUTRAL")
                    
                    # Update all signals for this competitor in this run
                    await signal_repo.update_strategy(
                        competitor_id=comp_id,
                        run_id=run_id,
                        hypothesis=hypothesis,
                        recommendation=recommendation
                    )
                    
                    await session.commit()
                    
                    logger.info(f"  ✅ {competitor_name} -> threat={threat_level}", 
                               extra={"run_id": run_id, "competitor": competitor_name})
                    
                    results.append({
                        "competitor_id": comp_id,
                        "competitor_name": competitor_name,
                        "threat_level": threat_level,
                        "hypothesis": hypothesis,
                        "recommendation": recommendation
                    })
                    
                except json.JSONDecodeError as e:
                    logger.error(f"  ❌ JSON parse error for {comp_id}: {e}", 
                                extra={"run_id": run_id, "competitor": competitor_names.get(str(comp_id), "Unknown")})
                    continue
                except Exception as e:
                    logger.error(f"  ❌ Error assessing {comp_id}: {e}", 
                                extra={"run_id": run_id, "competitor": competitor_names.get(str(comp_id), "Unknown")}, 
                                exc_info=True)
                    continue
                    
    except Exception as e:
        logger.error(f"Database error in run_strategist: {e}", extra={"run_id": run_id}, exc_info=True)
            
    return results


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test():
        db_url = os.getenv("DATABASE_URL")
        
        try:
            async with get_db_session_manual() as session:
                from stratos.db.repositories import RunRepository
                run_repo = RunRepository(session)
                
                # Get most recent run
                runs = await run_repo.get_latest(1)
                if not runs:
                    logger.info("No runs found.")
                    return
                    
                run_id = str(runs[0].id)
                
                # Get signals for this run (non-duplicates)
                signal_repo = SignalRepository(session)
                signals = await signal_repo.get_by_run_with_competitor(run_id)
                
                logger.info(f"Found {len(signals)} unique signals for run {run_id}")
                results = await run_strategist(signals, run_id)
                logger.info(f"Strategist complete. Assessed {len(results)} competitors")
                
        except Exception as e:
            logger.error(f"Test failed: {e}")
    
    asyncio.run(test())