# stratos/agents/orchestrator.py
"""
LangGraph orchestration for the StratOS pipeline.
Now with real-time progress tracking via WebSocket.
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
from stratos.db.repositories import RunRepository, RunLogRepository
from stratos.logging_config import get_run_logger, audit_logger
from stratos.retry import get_circuit_breaker, CircuitBreakerOpenError
from stratos.api.websocket import push_progress, cleanup_queue
from sqlalchemy import update


# Global circuit breakers for each agent
agent_circuit_breakers = {
    "scout": get_circuit_breaker("scout_agent"),
    "analyst": get_circuit_breaker("analyst_agent"),
    "strategist": get_circuit_breaker("strategist_agent"),
    "writer": get_circuit_breaker("writer_agent"),
}


class GraphState(TypedDict):
    run_id: str
    snapshots: list
    signals: list
    strategist_results: list
    delivery_success: bool
    error: str
    last_completed_node: str
    checkpoint: dict


async def _send_progress(run_id: str, step: str, status: str, message: str):
    """Send progress with logging."""
    logger = get_run_logger("orchestrator", run_id)
    logger.info(f"📤 PROGRESS: step={step}, status={status}, message={message}")
    try:
        await push_progress(run_id, {"step": step, "status": status, "message": message})
    except Exception as e:
        logger.error(f"Failed to send progress: {e}")


# ============================================================
# NODES
# ============================================================
async def scout_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger = get_run_logger("orchestrator", run_id)
    logger.info("=== SCOUT AGENT ===")
    
    await _send_progress(run_id, "scout", "started", "Scraping competitor blogs...")
    
    state["last_completed_node"] = "scout"
    state["checkpoint"] = {"snapshots": []}
    
    cb = agent_circuit_breakers["scout"]
    try:
        results = await cb.call(run_scout, run_id)
        state["checkpoint"]["snapshots"] = results
        count = len(results)
        await _send_progress(run_id, "scout", "completed", f"✅ Found {count} new snapshots")
        return {"snapshots": results, "last_completed_node": "scout", "checkpoint": state["checkpoint"]}
    except CircuitBreakerOpenError as e:
        logger.error(f"❌ Scout circuit breaker open: {e}")
        await _send_progress(run_id, "scout", "failed", f"❌ Scout failed: {e}")
        return {"error": str(e), "snapshots": []}
    except Exception as e:
        logger.error(f"❌ Scout node failed: {e}", exc_info=True)
        await _send_progress(run_id, "scout", "failed", f"❌ Scout failed: {e}")
        return {"error": str(e), "snapshots": []}


async def analyst_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger = get_run_logger("orchestrator", run_id)
    logger.info("=== ANALYST AGENT ===")
    
    snapshots = state.get("snapshots", [])
    if not snapshots:
        logger.info("No new snapshots to analyze.")
        await _send_progress(run_id, "analyst", "completed", "⏭️ No snapshots to analyze")
        return {"signals": [], "last_completed_node": "analyst"}
    
    await _send_progress(run_id, "analyst", "started", "Analyzing signals with LLM...")
    
    state["last_completed_node"] = "analyst"
    state["checkpoint"] = {"signals": []}
    
    cb = agent_circuit_breakers["analyst"]
    try:
        results = await cb.call(run_analyst, snapshots, run_id)
        state["checkpoint"]["signals"] = results
        count = len(results)
        await _send_progress(run_id, "analyst", "completed", f"✅ Generated {count} signals")
        return {"signals": results, "last_completed_node": "analyst", "checkpoint": state["checkpoint"]}
    except CircuitBreakerOpenError as e:
        logger.error(f"❌ Analyst circuit breaker open: {e}")
        await _send_progress(run_id, "analyst", "failed", f"❌ Analyst failed: {e}")
        return {"error": str(e), "signals": []}
    except Exception as e:
        logger.error(f"❌ Analyst node failed: {e}", exc_info=True)
        await _send_progress(run_id, "analyst", "failed", f"❌ Analyst failed: {e}")
        return {"error": str(e), "signals": []}


async def strategist_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger = get_run_logger("orchestrator", run_id)
    logger.info("=== STRATEGIST AGENT ===")
    
    signals = state.get("signals", [])
    if not signals:
        logger.info("No signals to assess.")
        await _send_progress(run_id, "strategist", "completed", "⏭️ No signals to assess")
        return {"strategist_results": [], "last_completed_node": "strategist"}
    
    await _send_progress(run_id, "strategist", "started", "Strategic reasoning in progress...")
    
    state["last_completed_node"] = "strategist"
    state["checkpoint"] = {"strategist_results": []}
    
    cb = agent_circuit_breakers["strategist"]
    try:
        results = await cb.call(run_strategist, signals, run_id)
        state["checkpoint"]["strategist_results"] = results
        count = len(results)
        await _send_progress(run_id, "strategist", "completed", f"✅ Assessed {count} competitors")
        return {"strategist_results": results, "last_completed_node": "strategist", "checkpoint": state["checkpoint"]}
    except CircuitBreakerOpenError as e:
        logger.error(f"❌ Strategist circuit breaker open: {e}")
        await _send_progress(run_id, "strategist", "failed", f"❌ Strategist failed: {e}")
        return {"error": str(e), "strategist_results": []}
    except Exception as e:
        logger.error(f"❌ Strategist node failed: {e}", exc_info=True)
        await _send_progress(run_id, "strategist", "failed", f"❌ Strategist failed: {e}")
        return {"error": str(e), "strategist_results": []}


async def writer_node(state: GraphState) -> Dict[str, Any]:
    run_id = state["run_id"]
    logger = get_run_logger("orchestrator", run_id)
    logger.info("=== WRITER AGENT ===")
    
    results = state.get("strategist_results", [])
    
    await _send_progress(run_id, "writer", "started", "Delivering briefing to Slack...")
    
    cb = agent_circuit_breakers["writer"]
    try:
        success = await cb.call(run_writer, results, run_id)
        if success:
            await _send_progress(run_id, "writer", "completed", "✅ Delivered to Slack")
        else:
            await _send_progress(run_id, "writer", "failed", "⚠️ Slack delivery failed")
        return {"delivery_success": success, "last_completed_node": "writer"}
    except CircuitBreakerOpenError as e:
        logger.error(f"❌ Writer circuit breaker open: {e}")
        await _send_progress(run_id, "writer", "failed", f"❌ Writer failed: {e}")
        return {"error": str(e), "delivery_success": False}
    except Exception as e:
        logger.error(f"❌ Writer node failed: {e}", exc_info=True)
        await _send_progress(run_id, "writer", "failed", f"❌ Writer failed: {e}")
        return {"error": str(e), "delivery_success": False}


# ============================================================
# CONDITIONAL EDGES
# ============================================================
def should_run_strategist(state: GraphState) -> str:
    signals = state.get("signals", [])
    unique_signals = [s for s in signals if not s.get("is_duplicate", False)]
    if not unique_signals:
        run_id = state.get("run_id", "unknown")
        logger = get_run_logger("orchestrator", run_id)
        logger.info("⚠️ No unique signals found. Skipping Strategist and Writer.")
        return "skip"
    return "run"


def should_run_writer(state: GraphState) -> str:
    results = state.get("strategist_results", [])
    if not results:
        run_id = state.get("run_id", "unknown")
        logger = get_run_logger("orchestrator", run_id)
        logger.info("⚠️ No strategist results. Skipping Writer.")
        return "skip"
    return "run"


# ============================================================
# BUILD GRAPH
# ============================================================
workflow = StateGraph(GraphState)

workflow.add_node("scout", scout_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("strategist", strategist_node)
workflow.add_node("writer", writer_node)

workflow.set_entry_point("scout")
workflow.add_edge("scout", "analyst")

workflow.add_conditional_edges(
    "analyst",
    should_run_strategist,
    {"run": "strategist", "skip": END}
)

workflow.add_conditional_edges(
    "strategist",
    should_run_writer,
    {"run": "writer", "skip": END}
)

workflow.add_edge("writer", END)

pipeline = workflow.compile()


_active_runs: Dict[str, asyncio.Task] = {}


async def run_pipeline(trigger_type: str = "manual", run_id: str = None) -> str:
    if run_id is None:
        run_id = str(uuid.uuid4())
    logger = get_run_logger("orchestrator", run_id)
    
    try:
        await _send_progress(run_id, "init", "started", "🚀 Pipeline started")
        
        if trigger_type == "manual":
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                running_count = await run_repo.get_running_count()
                max_concurrent = getattr(settings, "max_concurrent_runs", 5)
                if running_count >= max_concurrent and trigger_type == "scheduled":
                    logger.warning(f"Too many concurrent runs ({running_count}), queuing run {run_id}")
                    await asyncio.sleep(5)
        
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            await run_repo.create(run_id, trigger_type)
            await session.commit()
        
        logger.info(f"🚀 Initialized Run ID: {run_id}")
        logger.info(f"📋 Trigger Type: {trigger_type}")
        
        async with get_db_session_manual() as session:
            log_repo = RunLogRepository(session)
            await log_repo.create(run_id, "orchestrator", f"Run started with trigger: {trigger_type}")
            await session.commit()
        
        initial_state: GraphState = {
            "run_id": run_id,
            "snapshots": [],
            "signals": [],
            "strategist_results": [],
            "delivery_success": False,
            "error": "",
            "last_completed_node": "",
            "checkpoint": {},
        }
        
        timeout_seconds = getattr(settings, "run_timeout_seconds", 300)
        
        try:
            task = asyncio.current_task()
            if task:
                _active_runs[run_id] = task
            
            final_state = await asyncio.wait_for(
                pipeline.ainvoke(initial_state),
                timeout=timeout_seconds
            )
            
        except asyncio.TimeoutError:
            logger.error(f"❌ Run {run_id} timed out after {timeout_seconds}s")
            await _send_progress(run_id, "done", "failed", f"⏰ Run timed out")
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                await run_repo.timeout_run(run_id)
                await session.commit()
            cleanup_queue(run_id)
            return None
        finally:
            _active_runs.pop(run_id, None)
        
        if final_state.get("error"):
            logger.error(f"❌ Pipeline had errors: {final_state['error']}")
        
        signal_count = len(final_state.get("signals", []))
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            await run_repo.complete_run(run_id, signal_count)
            await session.commit()
        
        async with get_db_session_manual() as session:
            log_repo = RunLogRepository(session)
            await log_repo.create(run_id, "orchestrator", f"Run completed. Signals: {signal_count}")
            await session.commit()
        
        logger.info(f"✅ Pipeline complete! Run ID: {run_id}")
        logger.info(f"📊 Signals produced: {signal_count}")
        
        await _send_progress(run_id, "done", "completed", f"✅ Pipeline complete! {signal_count} signals generated")
        
        asyncio.create_task(_cleanup_after_delay(run_id, 60))
        
        audit_logger.log(
            action="RUN_COMPLETED",
            resource_id=run_id,
            resource_type="run",
            details={"signal_count": signal_count, "trigger_type": trigger_type},
            success=True
        )
        
        return run_id
        
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)
        await _send_progress(run_id, "done", "failed", f"❌ Pipeline failed: {e}")
        
        try:
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                await run_repo.fail_run(run_id, str(e))
                await session.commit()
        except Exception as db_error:
            logger.error(f"⚠️ Failed to mark run as failed: {db_error}")
        
        cleanup_queue(run_id)
        
        audit_logger.log(
            action="RUN_FAILED",
            resource_id=run_id,
            resource_type="run",
            details={"error": str(e)},
            success=False,
            error_message=str(e)
        )
        
        return None


async def _cleanup_after_delay(run_id: str, delay: int) -> None:
    await asyncio.sleep(delay)
    cleanup_queue(run_id)


async def cancel_run(run_id: str) -> bool:
    logger = get_run_logger("orchestrator", "cancel")
    task = _active_runs.get(run_id)
    if not task:
        logger.warning(f"Run {run_id} not found or not running")
        return False
    
    try:
        task.cancel()
        async with get_db_session_manual() as session:
            await session.execute(
                update(Run)
                .where(Run.id == run_id)
                .values(
                    status="cancelled",
                    completed_at=datetime.datetime.utcnow(),
                    error_message="Cancelled by user"
                )
            )
            await session.commit()
        
        audit_logger.log(
            action="RUN_CANCELLED",
            resource_id=run_id,
            resource_type="run",
            details={},
            success=True
        )
        await _send_progress(run_id, "done", "failed", "⏹️ Run cancelled")
        logger.info(f"✅ Run {run_id} cancelled")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to cancel run {run_id}: {e}")
        return False


async def get_run_logs(run_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    try:
        async with get_db_session_manual() as session:
            log_repo = RunLogRepository(session)
            logs = await log_repo.get_by_run(run_id, limit)
            return [
                {
                    "timestamp": l.timestamp.isoformat(),
                    "agent": l.agent,
                    "level": l.level,
                    "message": l.message,
                }
                for l in logs
            ]
    except Exception as e:
        logger.error(f"Error getting run logs: {e}")
        return []


async def get_run_queue_status() -> Dict[str, Any]:
    async with get_db_session_manual() as session:
        run_repo = RunRepository(session)
        running = await run_repo.get_running_count()
        return {
            "running_count": running,
            "max_concurrent": getattr(settings, "max_concurrent_runs", 5),
            "active_runs": list(_active_runs.keys()),
        }


def run_pipeline_sync(trigger_type: str = "manual") -> str:
    return asyncio.run(run_pipeline(trigger_type))


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    logger = get_run_logger("orchestrator", "test")
    logger.info("=" * 50)
    logger.info("  StratOS - Pipeline Test")
    logger.info("=" * 50)
    
    run_id = asyncio.run(run_pipeline("manual"))
    if run_id:
        logger.info(f"\n✅ Success! Run ID: {run_id}")
    else:
        logger.error("\n❌ Pipeline failed.")