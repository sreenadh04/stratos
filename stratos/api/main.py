# stratos/api/main.py
"""
StratOS API - FastAPI application.
Now with pagination, versioning, E2E health checks, alerting, and dependency health.
"""
import datetime
import uuid
import asyncio
from typing import Optional, List
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, Query, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.openapi.utils import get_openapi
from stratos.api.websocket import websocket_endpoint
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from stratos.config import settings
from stratos.agents.orchestrator import run_pipeline, cancel_run, get_run_logs, get_run_queue_status
from stratos.db.session import get_db_session
from stratos.db.repositories import (
    RunRepository,
    SignalRepository,
    CompetitorRepository,
    AuditLogRepository,
)
from stratos.scheduler.job import Scheduler
from stratos.eval.metrics import SignalEvaluator
from stratos.logging_config import get_logger, audit_logger
from stratos.api.auth import (
    validate_api_key,
    optional_api_key,
    setup_cors,
    create_api_key,
    revoke_api_key,
    _api_keys,
    log_api_action,
)
from stratos.api.dashboard import render_dashboard
from stratos.retry import with_timeout

load_dotenv()

# Create logger
logger = get_logger("api")

app = FastAPI(
    title="StratOS API",
    version="1.0.0",
    description="Autonomous Competitive Intelligence Agent API",
    contact={
        "name": "StratOS Team",
        "email": "support@stratos.com",
    },
)

# Setup CORS (#35)
setup_cors(app)

# Initialize scheduler
scheduler = None
if settings.scheduler_enabled:
    scheduler = Scheduler()
    scheduler.start()
    logger.info("🚀 Scheduler started")


# ============================================================
# #33: CUSTOM OPENAPI
# ============================================================
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="StratOS API",
        version="1.0.0",
        description="Autonomous Competitive Intelligence Agent API",
        routes=app.routes,
        tags=[
            {"name": "Runs", "description": "Pipeline execution and status"},
            {"name": "Signals", "description": "Intelligence signals and evaluation"},
            {"name": "Metrics", "description": "Performance and accuracy metrics"},
            {"name": "Health", "description": "System health and monitoring"},
            {"name": "API Keys", "description": "API key management"},
        ],
    )
    
    # Add security scheme
    openapi_schema["components"]["securitySchemes"] = {
        "APIKeyHeader": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi


# ============================================================
# #30: PAGINATION SCHEMA
# ============================================================
class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    limit: int
    offset: int
    next_offset: Optional[int]


# ============================================================
# #38: ALERTING
# ============================================================
async def send_alert(message: str, severity: str = "warning"):
    """
    Send alert via configured channels.
    Supports Slack webhook and email.
    """
    try:
        # Slack alert
        if settings.alerting_enabled and settings.alert_webhook_url:
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(
                    settings.alert_webhook_url,
                    json={"text": f"[{severity.upper()}] {message}"}
                )
        
        # Log alert
        logger.warning(f"⚠️ ALERT [{severity}]: {message}")
        
    except Exception as e:
        logger.error(f"Failed to send alert: {e}")


# ============================================================
# #39: DEPENDENCY HEALTH CHECKS
# ============================================================
async def check_groq_health() -> bool:
    """Check if Groq API is healthy."""
    try:
        from stratos.llm.factory import LLMFactory
        provider = LLMFactory.get_provider("groq")
        # Simple test generation
        await with_timeout(
            provider.generate,
            5.0,
            prompt="Respond with 'OK'",
            max_tokens=10
        )
        return True
    except Exception as e:
        logger.warning(f"Groq health check failed: {e}")
        return False


async def check_qdrant_health() -> bool:
    """Check if Qdrant is healthy."""
    try:
        from stratos.memory.vector_store import QdrantStore
        store = QdrantStore()
        await with_timeout(store.client.get_collections, 5.0)
        return True
    except Exception as e:
        logger.warning(f"Qdrant health check failed: {e}")
        return False


async def check_postgres_health() -> bool:
    """Check if PostgreSQL is healthy."""
    try:
        async with get_db_session_manual() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.warning(f"PostgreSQL health check failed: {e}")
        return False


# ============================================================
# HEALTH ENDPOINTS
# ============================================================
@app.get("/health", tags=["Health"])
async def health_check():
    """Basic liveness check."""
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}


# #37: E2E HEALTH
@app.get("/health/e2e", tags=["Health"])
async def e2e_health_check():
    """
    End-to-end health check.
    Triggers a synthetic test run and verifies completion.
    """
    logger.info("Running E2E health check...")
    
    try:
        # Trigger a test run
        run_id = await run_pipeline("health_check")
        
        if not run_id:
            await send_alert("E2E health check failed: Run did not start", "critical")
            return JSONResponse(
                status_code=503,
                content={"status": "unhealthy", "message": "Failed to start test run"}
            )
        
        # Wait for completion with timeout
        start_time = datetime.datetime.now()
        max_wait = 120  # 2 minutes
        
        while (datetime.datetime.now() - start_time).seconds < max_wait:
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                run = await run_repo.get_by_id(run_id)
                if run and run.status == "complete":
                    return {
                        "status": "healthy",
                        "run_id": run_id,
                        "signal_count": run.signal_count,
                        "message": "E2E health check passed"
                    }
                if run and run.status == "failed":
                    await send_alert(f"E2E health check failed: Run {run_id} failed", "critical")
                    return JSONResponse(
                        status_code=503,
                        content={"status": "unhealthy", "message": f"Test run failed: {run.error_message}"}
                    )
            await asyncio.sleep(5)
        
        await send_alert(f"E2E health check timed out: Run {run_id}", "critical")
        return JSONResponse(
            status_code=504,
            content={"status": "unhealthy", "message": "E2E health check timed out"}
        )
        
    except Exception as e:
        await send_alert(f"E2E health check exception: {e}", "critical")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "message": str(e)}
        )


# #39: DEPENDENCY HEALTH
@app.get("/health/dependencies", tags=["Health"])
async def dependency_health_check():
    """Check health of all external dependencies."""
    results = {}
    
    # Check PostgreSQL
    results["postgresql"] = await check_postgres_health()
    
    # Check Qdrant
    results["qdrant"] = await check_qdrant_health()
    
    # Check Groq
    results["groq"] = await check_groq_health()
    
    # Overall status
    all_healthy = all(results.values())
    
    if not all_healthy:
        unhealthy = [k for k, v in results.items() if not v]
        await send_alert(f"Dependency health check failed: {unhealthy}", "warning")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "results": results, "unhealthy": unhealthy}
        )
    
    return {"status": "healthy", "results": results}


# ============================================================
# RUNS ENDPOINTS
# ============================================================
# SignalEvaluation schema
class SignalEvaluation(BaseModel):
    accurate: bool
    note: str = Field(max_length=500)


@app.post("/runs", tags=["Runs"])
async def trigger_run(
    background_tasks: BackgroundTasks,
    request: Request,
    api_key: str = Depends(validate_api_key)
):
    """
    Trigger a new intelligence pipeline run.
    Runs in the background and delivers results to Slack.
    """
    # Generate run ID
    run_id = str(uuid.uuid4())
    
    # Pass the run_id to the pipeline
    background_tasks.add_task(run_pipeline, "manual", run_id)  # <-- Pass run_id here
    
    # Audit log
    await log_api_action(
        request,
        "TRIGGER_RUN",
        api_key=api_key[:8],
        resource_id=run_id,
        resource_type="run",
        details={"trigger_type": "manual"}
    )
    
    return {
        "message": "Run started",
        "run_id": run_id,
        "status": "running"
    }


# #30: PAGINATION
@app.get("/runs", tags=["Runs"])
async def get_runs(
    db: AsyncSession = Depends(get_db_session),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    api_key: str = Depends(validate_api_key)
):
    """Get recent runs with pagination (#30)."""
    try:
        run_repo = RunRepository(db)
        runs = await run_repo.get_latest(limit, offset)
        
        # Get total count
        from sqlalchemy import select, func
        from stratos.db.models import Run
        total_result = await db.execute(select(func.count()).select_from(Run))
        total = total_result.scalar_one()
        
        return {
            "items": [
                {
                    "id": str(run.id),
                    "status": run.status,
                    "signal_count": run.signal_count or 0,
                    "started_at": run.started_at.isoformat() if run.started_at else None,
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "trigger_type": run.trigger_type,
                    "estimated_cost": run.estimated_cost,
                }
                for run in runs
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if offset + limit < total else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# #23: RUN CANCELLATION
@app.post("/runs/{run_id}/cancel", tags=["Runs"])
async def cancel_run_endpoint(
    run_id: str,
    request: Request,
    api_key: str = Depends(validate_api_key)
):
    """Cancel a running run (#23)."""
    success = await cancel_run(run_id)
    if success:
        await log_api_action(
            request,
            "CANCEL_RUN",
            api_key=api_key[:8],
            resource_id=run_id,
            resource_type="run",
            details={"action": "cancel"}
        )
        return {"message": "Run cancelled successfully", "run_id": run_id}
    raise HTTPException(status_code=404, detail="Run not found or not running")


# #26: RUN LOGS
@app.get("/runs/{run_id}/logs", tags=["Runs"])
async def get_run_logs_endpoint(
    run_id: str,
    limit: int = Query(100, ge=1, le=1000),
    api_key: str = Depends(validate_api_key)
):
    """Get detailed logs for a run (#26)."""
    logs = await get_run_logs(run_id, limit)
    if logs is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "logs": logs}


# #24: RUN QUEUE STATUS
@app.get("/runs/queue/status", tags=["Runs"])
async def get_queue_status(
    api_key: str = Depends(validate_api_key)
):
    """Get current run queue status (#24)."""
    return await get_run_queue_status()


# ============================================================
# SIGNALS ENDPOINTS
# ============================================================
@app.get("/runs/{run_id}/signals", tags=["Signals"])
async def get_run_signals(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Get all signals produced by a specific run."""
    try:
        signal_repo = SignalRepository(db)
        signals = await signal_repo.get_by_run_with_competitor(run_id)
        return signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/signals/{signal_id}/evaluate", tags=["Signals"])
async def evaluate_signal(
    signal_id: str,
    eval_data: SignalEvaluation,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Submit human evaluation for a signal."""
    try:
        signal_repo = SignalRepository(db)
        success = await signal_repo.evaluate_signal(
            signal_id,
            eval_data.accurate,
            eval_data.note
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        await log_api_action(
            request,
            "EVALUATE_SIGNAL",
            api_key=api_key[:8],
            resource_id=signal_id,
            resource_type="signal",
            details={"accurate": eval_data.accurate}
        )
        
        return {"message": "Evaluation saved successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# METRICS ENDPOINTS
# ============================================================
@app.get("/metrics", tags=["Metrics"])
async def get_metrics(
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Get overall evaluation metrics."""
    try:
        evaluator = SignalEvaluator()
        metrics = await evaluator.compute_metrics()
        return {
            "total_signals": metrics.total_signals,
            "evaluated_count": metrics.evaluated_count,
            "precision": metrics.precision,
            "duplicate_rate": metrics.duplicate_rate,
            "high_impact_accuracy": metrics.high_impact_accuracy,
            "medium_impact_accuracy": metrics.medium_impact_accuracy,
            "low_impact_accuracy": metrics.low_impact_accuracy,
            "last_evaluated": metrics.last_evaluated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/runs/{run_id}/metrics", tags=["Metrics"])
async def get_run_metrics(
    run_id: str,
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Get evaluation metrics for a specific run."""
    try:
        evaluator = SignalEvaluator()
        metrics = await evaluator.get_run_metrics(run_id)
        if "error" in metrics:
            raise HTTPException(status_code=404, detail=metrics["error"])
        return metrics
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats", tags=["Metrics"])
async def get_stats(
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Get summary statistics for the dashboard."""
    try:
        evaluator = SignalEvaluator()
        stats = await evaluator.get_summary_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# #34: API KEY MANAGEMENT
# ============================================================
@app.post("/api-keys/create", tags=["API Keys"])
async def create_api_key_endpoint(
    user_id: str = "default",
    api_key: str = Depends(validate_api_key)
):
    """Create a new API key."""
    key = await create_api_key(user_id)
    return {
        "api_key": key,
        "message": "Store this key securely. It will not be shown again.",
        "user_id": user_id
    }


@app.post("/api-keys/revoke", tags=["API Keys"])
async def revoke_api_key_endpoint(
    key_to_revoke: str,
    api_key: str = Depends(validate_api_key)
):
    """Revoke an API key."""
    success = await revoke_api_key(key_to_revoke)
    if success:
        return {"message": "API key revoked successfully"}
    raise HTTPException(status_code=404, detail="API key not found")


@app.get("/api-keys/list", tags=["API Keys"])
async def list_api_keys_endpoint(
    api_key: str = Depends(validate_api_key)
):
    """List all active API keys."""
    active_keys = [
        {"key": k[:16] + "...", "created_at": v["created_at"], "last_used": v.get("last_used")}
        for k, v in _api_keys.items()
        if v.get("is_active", True)
    ]
    return {"keys": active_keys}


# ============================================================
# DASHBOARD
# ============================================================
@app.get("/", response_class=HTMLResponse, tags=["Health"])
async def get_dashboard(db: AsyncSession = Depends(get_db_session)):
    """Live HTML dashboard showing current state."""
    return await render_dashboard(db)


# ============================================================
# WEBSOCKET ENDPOINT
# ============================================================
@app.websocket("/ws/{run_id}")
async def websocket_progress(websocket: WebSocket, run_id: str):
    await websocket_endpoint(websocket, run_id)

# ============================================================
# SHUTDOWN HANDLER
# ============================================================
@app.on_event("shutdown")
def shutdown_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("🛑 Scheduler shutdown")