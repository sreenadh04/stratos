# stratos/agents/orchestrator.py
"""
LangGraph orchestration for the StratOS pipeline.
Now fully async with proper database session management.
"""
import uuid
import datetime
import asyncio
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from stratos.config import settings
from stratos.agents.scout import run_scout
from stratos.agents.analyst import run_analyst
from stratos.agents.strategist import run_strategist
from stratos.agents.writer import run_writer
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import RunRepository
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("orchestrator")


class GraphState(TypedDict):
    """State shared between all agents in the pipeline."""
    run_id: str
    snapshots: list
    signals: list
    strategist_results: list
    delivery_success: bool
    error: str


async def scout_node(state: GraphState) -> Dict[str, Any]:
    """Scout agent node - acquires data from competitors."""
    logger.info("=== SCOUT AGENT ===", extra={"run_id": state["run_id"]})
    try:
        results = await run_scout(state["run_id"])
        return {"snapshots": results}
    except Exception as e:
        logger.error(f"Scout node failed: {e}", extra={"run_id": state["run_id"]}, exc_info=True)
        return {"error": str(e), "snapshots": []}


async def analyst_node(state: GraphState) -> Dict[str, Any]:
    """Analyst agent node - scores and deduplicates signals."""
    logger.info("=== ANALYST AGENT ===", extra={"run_id": state["run_id"]})
    snapshots = state.get("snapshots", [])
    if not snapshots:
        logger.info("No new snapshots to analyze.", extra={"run_id": state["run_id"]})
        return {"signals": []}
    
    try:
        results = await run_analyst(snapshots, state["run_id"])
        return {"signals": results}
    except Exception as e:
        logger.error(f"Analyst node failed: {e}", extra={"run_id": state["run_id"]}, exc_info=True)
        return {"error": str(e), "signals": []}


async def strategist_node(state: GraphState) -> Dict[str, Any]:
    """Strategist agent node - strategic reasoning."""
    logger.info("=== STRATEGIST AGENT ===", extra={"run_id": state["run_id"]})
    signals = state.get("signals", [])
    if not signals:
        logger.info("No signals to assess.", extra={"run_id": state["run_id"]})
        return {"strategist_results": []}
    
    try:
        results = await run_strategist(signals, state["run_id"])
        return {"strategist_results": results}
    except Exception as e:
        logger.error(f"Strategist node failed: {e}", extra={"run_id": state["run_id"]}, exc_info=True)
        return {"error": str(e), "strategist_results": []}


async def writer_node(state: GraphState) -> Dict[str, Any]:
    """Writer agent node - formats and delivers the briefing."""
    logger.info("=== WRITER AGENT ===", extra={"run_id": state["run_id"]})
    results = state.get("strategist_results", [])
    try:
        success = await run_writer(results, state["run_id"])
        return {"delivery_success": success}
    except Exception as e:
        logger.error(f"Writer node failed: {e}", extra={"run_id": state["run_id"]}, exc_info=True)
        return {"error": str(e), "delivery_success": False}


def should_run_strategist(state: GraphState) -> str:
    """Conditional edge: only run strategist if there are unique signals."""
    signals = state.get("signals", [])
    unique_signals = [s for s in signals if not s.get("is_duplicate", False)]
    
    if not unique_signals:
        logger.info("⚠️ No unique signals found. Skipping Strategist and Writer.", extra={"run_id": state["run_id"]})
        return "skip"
    return "run"


def should_run_writer(state: GraphState) -> str:
    """Conditional edge: only run writer if strategist produced results."""
    results = state.get("strategist_results", [])
    if not results:
        logger.info("⚠️ No strategist results. Skipping Writer.", extra={"run_id": state["run_id"]})
        return "skip"
    return "run"


# Build the async graph
workflow = StateGraph(GraphState)

workflow.add_node("scout", scout_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("strategist", strategist_node)
workflow.add_node("writer", writer_node)

workflow.set_entry_point("scout")

# Sequential edges with conditional branching
workflow.add_edge("scout", "analyst")

workflow.add_conditional_edges(
    "analyst",
    should_run_strategist,
    {
        "run": "strategist",
        "skip": END
    }
)

workflow.add_conditional_edges(
    "strategist",
    should_run_writer,
    {
        "run": "writer",
        "skip": END
    }
)

workflow.add_edge("writer", END)

# Compile the pipeline
pipeline = workflow.compile()


async def run_pipeline(trigger_type: str = "manual") -> str:
    """
    Initialize a run and execute the graph pipeline asynchronously.
    
    Args:
        trigger_type: 'manual' or 'scheduled'
    
    Returns:
        run_id: The ID of the executed run, or None if failed.
    """
    run_id = str(uuid.uuid4())
    
    try:
        # Use repository to create run - ensure commit happens
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            await run_repo.create(run_id, trigger_type)
            await session.commit()
            logger.info(f"✅ Run record created and committed: {run_id}")
        
        logger.info(f"🚀 Initialized Run ID: {run_id}")
        logger.info(f"📋 Trigger Type: {trigger_type}")
        
        # Initial state
        initial_state: GraphState = {
            "run_id": run_id,
            "snapshots": [],
            "signals": [],
            "strategist_results": [],
            "delivery_success": False,
            "error": ""
        }
        
        # Run the pipeline
        final_state = await pipeline.ainvoke(initial_state)
        
        # Update run with signal count
        signal_count = len(final_state.get("signals", []))
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            await run_repo.complete_run(run_id, signal_count)
            await session.commit()
        
        logger.info(f"✅ Pipeline complete! Run ID: {run_id}")
        logger.info(f"📊 Signals produced: {signal_count}")
        
        return run_id
        
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        
        # Mark run as failed
        try:
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                await run_repo.fail_run(run_id, str(e))
                await session.commit()
        except Exception as db_error:
            logger.error(f"⚠️ Failed to mark run as failed: {db_error}")
        
        return None


# Sync wrapper for backward compatibility
def run_pipeline_sync(trigger_type: str = "manual") -> str:
    """
    Synchronous wrapper for run_pipeline.
    Use this for scripts and non-async contexts.
    """
    return asyncio.run(run_pipeline(trigger_type))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    logger.info("=" * 50)
    logger.info("  StratOS - Pipeline Test")
    logger.info("=" * 50)
    
    # Run the pipeline
    run_id = asyncio.run(run_pipeline("manual"))
    
    if run_id:
        logger.info(f"\n✅ Success! Run ID: {run_id}")
    else:
        logger.error("\n❌ Pipeline failed.")