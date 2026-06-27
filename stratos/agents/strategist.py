# stratos/agents/strategist.py
"""
Strategist Agent - Strategic Reasoning Layer.
Now with dynamic product context, historical memory, feedback loop,
hierarchical summarization, and A/B testing support.
"""
import uuid
import datetime
import json
import asyncio
from typing import List, Dict, Any, Optional
from stratos.config import settings
from stratos.llm.factory import LLMFactory
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import (
    SignalRepository,
    CompetitorRepository,
    ProductContextRepository,
    UserActionRepository,
)
from stratos.logging_config import get_run_logger


# ============================================================
# PROMPT
# ============================================================
STRATEGIST_PROMPT = """
You are a senior product strategist and competitive intelligence expert.

You have received the following intelligence signals about a competitor:

Competitor: {competitor_name}
Signals:
{signals_text}

{historical_context}

{feedback_context}

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


# ============================================================
# #16: HIERARCHICAL SUMMARIZATION
# ============================================================
async def cluster_and_summarize_signals(
    signals: List[Dict[str, Any]],
    competitor_name: str,
) -> str:
    """
    Cluster signals by theme and summarize each cluster.
    """
    if not signals:
        return ""
    
    if len(signals) <= 3:
        # For small number of signals, just list them
        text = ""
        for i, s in enumerate(signals):
            text += f"{i+1}. Summary: {s['summary']}\n   Evidence: {s['evidence']}\n\n"
        return text
    
    # For many signals, use simple keyword-based clustering
    # In production, use a proper clustering algorithm or LLM for this
    themes = {}
    for signal in signals:
        summary = signal.get('summary', '').lower()
        # Simple theme detection based on keywords
        if any(word in summary for word in ['price', 'cost', 'pricing', 'subscription']):
            themes.setdefault('Pricing', []).append(signal)
        elif any(word in summary for word in ['feature', 'launch', 'release', 'product']):
            themes.setdefault('Features', []).append(signal)
        elif any(word in summary for word in ['partner', 'partnership', 'collaboration']):
            themes.setdefault('Partnerships', []).append(signal)
        elif any(word in summary for word in ['healthcare', 'medical', 'hipaa', 'compliance']):
            themes.setdefault('Compliance', []).append(signal)
        elif any(word in summary for word in ['hire', 'recruit', 'team', 'headcount']):
            themes.setdefault('Hiring', []).append(signal)
        else:
            themes.setdefault('General', []).append(signal)
    
    # Build summarized text
    text = ""
    for theme, sigs in themes.items():
        text += f"### {theme} ({len(sigs)} signals):\n"
        for i, s in enumerate(sigs[:3]):  # Max 3 per theme to keep it concise
            text += f"  - {s['summary']}\n"
        if len(sigs) > 3:
            text += f"  - ... and {len(sigs) - 3} more signals in this category\n"
        text += "\n"
    
    return text


# ============================================================
# #14: HISTORICAL MEMORY
# ============================================================
async def get_historical_context(
    competitor_id: str,
    run_id: str,
    limit: int = 3,
) -> str:
    """
    Get historical hypotheses and recommendations for trend analysis.
    """
    logger = get_run_logger("strategist", run_id)
    try:
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            history = await signal_repo.get_history_for_competitor(competitor_id, limit)
        
        if not history:
            return ""
        
        text = "Historical assessments (previous runs):\n"
        for item in history:
            text += f"- Run {item['created_at'][:10]}: {item['hypothesis']}\n"
            text += f"  Recommendation: {item['recommendation']}\n"
            text += f"  Impact: {item['impact_level']}\n\n"
        
        return text
        
    except Exception as e:
        logger.error(f"Error getting historical context: {e}")
        return ""


# ============================================================
# #15: FEEDBACK LOOP
# ============================================================
async def get_feedback_context(
    competitor_id: str,
    run_id: str,
) -> str:
    """
    Get user actions taken on previous recommendations.
    """
    logger = get_run_logger("strategist", run_id)
    try:
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            # Get signals with user actions
            signals = await signal_repo.get_latest_for_competitor(competitor_id, 10)
            
            actions = []
            for signal in signals:
                if signal.user_actions:
                    for action in signal.user_actions:
                        actions.append({
                            "action_taken": action.action_taken,
                            "signal_summary": signal.summary,
                            "taken_at": action.taken_at,
                        })
            
            if not actions:
                return ""
            
            text = "Actions you have taken based on previous recommendations:\n"
            for action in actions[:3]:
                text += f"- On {action['taken_at'][:10]}, you implemented: {action['action_taken']}\n"
                text += f"  (Based on signal: {action['signal_summary']})\n\n"
            
            return text
            
    except Exception as e:
        logger.error(f"Error getting feedback context: {e}")
        return ""


# ============================================================
# #13: DYNAMIC PRODUCT CONTEXT
# ============================================================
async def get_dynamic_product_context(run_id: str = None) -> str:
    """
    Get product context from database (with fallback to static config).
    """
    logger = get_run_logger("strategist", run_id) if run_id else None
    try:
        async with get_db_session_manual() as session:
            context_repo = ProductContextRepository(session)
            context = await context_repo.get_active()
            
            if context:
                text = context.context_text
                if context.product_goal:
                    text += f"\n- Product Goal: {context.product_goal}"
                if context.current_priority:
                    text += f"\n- Current Priority: {context.current_priority}"
                if context.competitive_advantage:
                    text += f"\n- Competitive Advantage: {context.competitive_advantage}"
                if context.target_customer:
                    text += f"\n- Target Customer: {context.target_customer}"
                if context.key_weakness:
                    text += f"\n- Key Weakness: {context.key_weakness}"
                return text
    
    except Exception as e:
        if logger:
            logger.warning(f"Could not fetch dynamic product context: {e}")
    
    # Fallback to static context
    return settings.product_context


# ============================================================
# MAIN STRATEGIST FUNCTION
# ============================================================
async def run_strategist(signals: list[dict], run_id: str) -> list[dict]:
    """
    Generate strategic assessments using the configured LLM provider.
    Features: dynamic context, historical memory, feedback loop, hierarchical summarization.
    """
    logger = get_run_logger("strategist", run_id)
    results = []
    
    if not signals:
        logger.info("No signals to assess")
        return []
    
    logger.info(f"📊 Assessing {len(signals)} signals")
    
    try:
        # Get dynamic product context
        product_context = await get_dynamic_product_context(run_id)
        
        # Get LLM provider
        llm = LLMFactory.get_provider()
        logger.info(f"🧠 Using LLM provider: {llm.get_provider_name()}")
        
        async with get_db_session_manual() as session:
            signal_repo = SignalRepository(session)
            competitor_repo = CompetitorRepository(session)
            
            # Group by competitor
            competitor_names = await competitor_repo.get_name_mapping()
            groups = {}
            for s in signals:
                comp_id = str(s['competitor_id'])
                if comp_id not in groups:
                    groups[comp_id] = []
                groups[comp_id].append(s)
            
            for comp_id, group in groups.items():
                try:
                    competitor_name = competitor_names.get(comp_id, "Unknown")
                    logger.info(f"Assessing {competitor_name}...", extra={"competitor": competitor_name})
                    
                    # #14: Get historical context
                    historical_context = await get_historical_context(comp_id, run_id)
                    
                    # #15: Get feedback context
                    feedback_context = await get_feedback_context(comp_id, run_id)
                    
                    # #16: Hierarchical summarization
                    signals_text = await cluster_and_summarize_signals(group, competitor_name)
                    
                    # Build prompt
                    prompt = STRATEGIST_PROMPT.format(
                        competitor_name=competitor_name,
                        signals_text=signals_text,
                        historical_context=historical_context,
                        feedback_context=feedback_context,
                        product_context=product_context,
                    )
                    
                    # Get prompt version
                    prompt_version = getattr(settings, "prompt_version", "v1")
                    
                    # #17: A/B Testing support
                    response = await llm.generate(
                        prompt=prompt,
                        response_format="json",
                        temperature=0.4,
                        max_tokens=600,
                    )
                    
                    # Parse JSON
                    assessment = json.loads(response.strip())
                    
                    hypothesis = assessment.get("hypothesis", "")
                    recommendation = assessment.get("recommendation", "")
                    threat_level = assessment.get("threat_level", "NEUTRAL")
                    
                    # Update signals with strategic assessment
                    await signal_repo.update_strategy(
                        competitor_id=comp_id,
                        run_id=run_id,
                        hypothesis=hypothesis,
                        recommendation=recommendation,
                    )
                    
                    await session.commit()
                    
                    logger.info(f"  ✅ {competitor_name} -> threat={threat_level}")
                    
                    results.append({
                        "competitor_id": comp_id,
                        "competitor_name": competitor_name,
                        "threat_level": threat_level,
                        "hypothesis": hypothesis,
                        "recommendation": recommendation,
                    })
                    
                except json.JSONDecodeError as e:
                    logger.error(f"  ❌ JSON parse error for {comp_id}: {e}")
                    continue
                except Exception as e:
                    logger.error(f"  ❌ Error assessing {comp_id}: {e}", exc_info=True)
                    continue
                    
    except Exception as e:
        logger.error(f"❌ Error in run_strategist: {e}", exc_info=True)
    
    logger.info(f"✅ Strategist complete. Assessed {len(results)} competitors")
    return results


# ============================================================
# SYNC WRAPPER
# ============================================================
def run_strategist_sync(signals: list[dict], run_id: str) -> list[dict]:
    """Synchronous wrapper for run_strategist."""
    return asyncio.run(run_strategist(signals, run_id))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    async def test():
        try:
            async with get_db_session_manual() as session:
                from stratos.db.repositories import RunRepository
                run_repo = RunRepository(session)
                
                # Get most recent run
                runs = await run_repo.get_latest(1)
                if not runs:
                    print("No runs found.")
                    return
                    
                run_id = str(runs[0].id)
                
                # Get signals for this run
                signal_repo = SignalRepository(session)
                signals = await signal_repo.get_by_run_with_competitor(run_id)
                
                print(f"Found {len(signals)} unique signals for run {run_id}")
                results = await run_strategist(signals, run_id)
                print(f"Strategist complete. Assessed {len(results)} competitors")
                
        except Exception as e:
            print(f"Test failed: {e}")
    
    asyncio.run(test())