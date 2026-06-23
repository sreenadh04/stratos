# stratos/api/main.py
"""
StratOS API - FastAPI application.
"""
import datetime
import uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from stratos.config import settings
from stratos.agents.orchestrator import run_pipeline
from stratos.db.session import get_db_session
from stratos.db.repositories import (
    RunRepository,
    SignalRepository,
    CompetitorRepository,
)
from stratos.scheduler.job import Scheduler
from stratos.eval.metrics import SignalEvaluator
from stratos.logging_config import get_logger
from stratos.api.auth import validate_api_key

# Create logger
logger = get_logger("api")

load_dotenv()

app = FastAPI(title="StratOS API", version="1.0.0")

# Initialize scheduler
scheduler = None
if settings.scheduler_enabled:
    scheduler = Scheduler()
    scheduler.start()
    logger.info("🚀 Scheduler started")


# Pydantic schemas
class SignalEvaluation(BaseModel):
    accurate: bool
    note: str = Field(max_length=500)


class RunResponse(BaseModel):
    id: str
    status: str
    signal_count: int
    started_at: str
    completed_at: str | None


class SignalResponse(BaseModel):
    id: str
    competitor: str
    impact_level: str | None
    summary: str | None
    is_duplicate: bool


# Health check - PUBLIC
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}


# Trigger a new run - PROTECTED
@app.post("/runs")
async def trigger_run(
    background_tasks: BackgroundTasks,
    api_key: str = Depends(validate_api_key)
):
    """Trigger a new intelligence pipeline run."""
    run_id = str(uuid.uuid4())
    background_tasks.add_task(run_pipeline, "manual")
    return {
        "message": "Run started",
        "run_id": run_id,
        "status": "running"
    }


# Get recent runs - PROTECTED
@app.get("/runs", response_model=list[RunResponse])
async def get_runs(
    db: AsyncSession = Depends(get_db_session),
    api_key: str = Depends(validate_api_key)
):
    """Get the 10 most recent runs."""
    try:
        run_repo = RunRepository(db)
        runs = await run_repo.get_latest(10)
        return [
            {
                "id": str(run.id),
                "status": run.status,
                "signal_count": run.signal_count or 0,
                "started_at": run.started_at.isoformat() if run.started_at else "",
                "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            }
            for run in runs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get signals for a run - PROTECTED
@app.get("/runs/{run_id}/signals", response_model=list[SignalResponse])
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


# Evaluate a signal - PROTECTED
@app.post("/signals/{signal_id}/evaluate")
async def evaluate_signal(
    signal_id: str,
    eval_data: SignalEvaluation,
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
        return {"message": "Evaluation saved successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Get evaluation metrics - PROTECTED
@app.get("/metrics")
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


# Get run-specific metrics - PROTECTED
@app.get("/runs/{run_id}/metrics")
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


# Get summary stats for dashboard - PROTECTED
@app.get("/stats")
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


# Dashboard - PUBLIC (HTML only)
@app.get("/", response_class=HTMLResponse)
async def get_dashboard(db: AsyncSession = Depends(get_db_session)):
    """Live HTML dashboard showing current state."""
    try:
        run_repo = RunRepository(db)
        signal_repo = SignalRepository(db)
        competitor_repo = CompetitorRepository(db)
        
        # Safely get runs
        runs = []
        try:
            runs = await run_repo.get_latest(20)
        except Exception as e:
            logger.error(f"Could not fetch runs: {e}")
            runs = []
        
        last_run = runs[0] if runs else None
        
        # Safely get counts
        total_signals = 0
        high_signals = 0
        try:
            total_signals = await signal_repo.get_count()
            high_signals = await signal_repo.get_high_impact_count()
        except Exception as e:
            logger.error(f"Could not fetch signal counts: {e}")
        
        # Safely get competitors
        competitors = []
        try:
            competitors = await competitor_repo.get_all()
        except Exception as e:
            logger.error(f"Could not fetch competitors: {e}")
            competitors = []
        
        # Build competitor cards
        competitor_cards = ""
        for comp in competitors:
            try:
                signals = await signal_repo.get_latest_for_competitor(str(comp.id), 1)
                level = signals[0].impact_level if signals and signals[0].impact_level else "LOW"
            except:
                level = "LOW"
            
            level_class = level.lower() if level in ("HIGH", "MEDIUM", "LOW") else "low"
            dot_class = "high" if level == "HIGH" else ""
            domain = comp.website_url.replace("https://", "").replace("http://", "").rstrip("/")
            
            competitor_cards += f'''
            <div class="competitor-card" data-impact="{level}">
                <div class="competitor-header">
                    <div class="competitor-avatar">{comp.name[:2].upper()}</div>
                    <div class="competitor-info">
                        <div class="competitor-name">{comp.name}</div>
                        <div class="competitor-domain">{domain}</div>
                    </div>
                    <div class="threat-badge {level_class}">{level}</div>
                </div>
                <div class="competitor-status">
                    <div class="status-dot {dot_class}"></div>
                    <span class="status-text">{'Active' if level != 'LOW' else 'Monitoring'}</span>
                </div>
            </div>
            '''
        
        # Safely get signals for the feed
        signals = []
        if last_run:
            try:
                signals = await signal_repo.get_by_run_with_competitor(str(last_run.id))
            except Exception as e:
                logger.error(f"Could not fetch signals: {e}")
                signals = []
        latest_signals = signals[:10] if signals else []
        
        signal_html = ""
        if latest_signals:
            for s in latest_signals:
                impact_class = (s.get("impact_level") or "low").lower()
                summary = s.get("summary") or ""
                recommendation = s.get("recommendation") or ""
                competitor = s.get("competitor_name") or "Unknown"
                
                rec_html = ""
                if recommendation:
                    rec_html = f'''
                    <div class="signal-recommendation">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 2L2 7l10 5 10-5-10-5z"/>
                            <path d="M2 17l10 5 10-5"/>
                            <path d="M2 12l10 5 10-5"/>
                        </svg>
                        <span>{recommendation}</span>
                    </div>
                    '''
                
                signal_html += f'''
                <div class="signal-item {impact_class}">
                    <div class="signal-icon">{'🔴' if impact_class == 'high' else '🟡' if impact_class == 'medium' else '🟢'}</div>
                    <div class="signal-content">
                        <div class="signal-header">
                            <span class="signal-company">{competitor}</span>
                            <span class="signal-badge {impact_class}">{s.get("impact_level", "LOW")}</span>
                        </div>
                        <div class="signal-summary">{summary}</div>
                        {rec_html}
                    </div>
                </div>
                '''
        else:
            signal_html = '''
            <div class="signal-item empty">
                <div class="signal-content">
                    <div class="signal-summary">No signals yet. Trigger a run to start monitoring.</div>
                </div>
            </div>
            '''
        
        # Build run history
        run_history_html = ""
        for run in runs[:8]:
            status_class = "success" if run.status == "complete" else "warning" if run.status == "running" else "error"
            status_icon = "✅" if run.status == "complete" else "🔄" if run.status == "running" else "❌"
            time_str = run.started_at.strftime("%H:%M") if run.started_at else "N/A"
            
            run_history_html += f'''
            <div class="run-item">
                <span class="run-status {status_class}">{status_icon}</span>
                <span class="run-time">{time_str}</span>
                <span class="run-id">#{str(run.id)[:8]}</span>
                <span class="run-signals">{run.signal_count or 0} signals</span>
            </div>
            '''
        
        # Chart data
        chart_labels = [f"Run {i+1}" for i in range(min(5, len(runs)))]
        chart_signals = [r.signal_count or 0 for r in runs[:5]]
        
        threat_counts = [0, 0, 0]
        for s in signals:
            level = s.get("impact_level")
            if level == "HIGH":
                threat_counts[0] += 1
            elif level == "MEDIUM":
                threat_counts[1] += 1
            else:
                threat_counts[2] += 1

        html_content = f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StratOS — Intelligence Console</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
        :root {{
            --bg-primary: #0B0D10;
            --bg-secondary: #13161A;
            --bg-card: #1A1E24;
            --bg-card-hover: #22282F;
            --border-color: #2A3038;
            --text-primary: #F0EDE8;
            --text-secondary: #A8AAB0;
            --text-muted: #6A6E76;
            --accent-amber: #E8A33D;
            --accent-amber-dim: #4A3A1F;
            --accent-teal: #3D8B82;
            --accent-teal-dim: #1C3530;
            --accent-red: #C9533F;
            --accent-red-dim: #3D2420;
            --shadow: 0 4px 24px rgba(0,0,0,0.4);
            --radius: 12px;
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: 'Inter', sans-serif;
            line-height: 1.6;
            min-height: 100vh;
        }}
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: var(--bg-secondary); }}
        ::-webkit-scrollbar-thumb {{ background: var(--border-color); border-radius: 3px; }}
        .app {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px 32px 60px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 32px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .logo {{
            display: flex;
            align-items: center;
            gap: 14px;
        }}
        .logo-icon {{
            width: 40px;
            height: 40px;
            border: 2px solid var(--accent-amber);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
        }}
        .logo-icon::after {{
            content: '';
            width: 10px;
            height: 10px;
            background: var(--accent-amber);
            border-radius: 50%;
            animation: pulse-ring 2.4s ease-out infinite;
        }}
        @keyframes pulse-ring {{
            0% {{ box-shadow: 0 0 0 0 rgba(232,163,61,0.5); }}
            70% {{ box-shadow: 0 0 0 14px rgba(232,163,61,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(232,163,61,0); }}
        }}
        .logo-text h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -0.02em; }}
        .logo-text span {{ font-size: 12px; color: var(--text-muted); font-weight: 400; letter-spacing: 0.06em; text-transform: uppercase; display: block; }}
        .header-actions {{ display: flex; align-items: center; gap: 16px; }}
        .status-pill {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--accent-teal);
            background: var(--accent-teal-dim);
            border: 1px solid rgba(61,139,130,0.25);
            padding: 6px 14px;
            border-radius: 100px;
            font-weight: 500;
        }}
        .status-pill .dot {{
            width: 6px;
            height: 6px;
            background: var(--accent-teal);
            border-radius: 50%;
            animation: pulse-dot 1.8s ease-in-out infinite;
        }}
        @keyframes pulse-dot {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.3; }}
        }}
        .btn-primary {{
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 600;
            background: var(--accent-amber);
            color: #1A1206;
            border: none;
            padding: 10px 24px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        .btn-primary:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(232,163,61,0.3);
        }}
        .btn-primary:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 32px;
        }}
        .stat-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 20px 24px;
            transition: all 0.2s ease;
        }}
        .stat-card:hover {{
            background: var(--bg-card-hover);
            border-color: var(--text-muted);
        }}
        .stat-label {{ font-size: 12px; font-weight: 500; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; }}
        .stat-value {{ font-size: 32px; font-weight: 700; margin-top: 4px; letter-spacing: -0.02em; }}
        .stat-value.amber {{ color: var(--accent-amber); }}
        .stat-value.teal {{ color: var(--accent-teal); }}
        .stat-value.red {{ color: var(--accent-red); }}
        .stat-sub {{ font-size: 13px; color: var(--text-secondary); margin-top: 2px; }}
        .main-grid {{
            display: grid;
            grid-template-columns: 1fr 360px;
            gap: 24px;
            margin-bottom: 32px;
        }}
        @media (max-width: 1024px) {{
            .main-grid {{ grid-template-columns: 1fr; }}
        }}
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            overflow: hidden;
        }}
        .card-header {{
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-title {{ font-size: 15px; font-weight: 600; }}
        .card-badge {{ font-size: 11px; color: var(--text-muted); background: var(--bg-secondary); padding: 2px 10px; border-radius: 100px; font-weight: 500; }}
        .card-body {{ padding: 20px 24px; }}
        .competitors-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}
        @media (max-width: 600px) {{
            .competitors-grid {{ grid-template-columns: 1fr; }}
        }}
        .competitor-card {{
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 14px 16px;
            transition: all 0.2s ease;
        }}
        .competitor-card:hover {{ border-color: var(--text-muted); }}
        .competitor-header {{ display: flex; align-items: center; gap: 12px; }}
        .competitor-avatar {{
            width: 36px;
            height: 36px;
            border-radius: 8px;
            background: var(--bg-card-hover);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 600;
            color: var(--accent-amber);
            flex-shrink: 0;
        }}
        .competitor-info {{ flex: 1; min-width: 0; }}
        .competitor-name {{ font-size: 14px; font-weight: 600; }}
        .competitor-domain {{ font-size: 11px; color: var(--text-muted); }}
        .threat-badge {{ font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 4px; letter-spacing: 0.04em; flex-shrink: 0; }}
        .threat-badge.high {{ background: var(--accent-red-dim); color: #E8897A; }}
        .threat-badge.medium {{ background: var(--accent-amber-dim); color: var(--accent-amber); }}
        .threat-badge.low {{ background: var(--accent-teal-dim); color: #6FB8AE; }}
        .competitor-status {{ display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 11px; color: var(--text-muted); }}
        .status-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--accent-teal); }}
        .status-dot.high {{ background: var(--accent-red); }}
        .signal-feed {{ max-height: 480px; overflow-y: auto; }}
        .signal-item {{
            display: flex;
            gap: 14px;
            padding: 14px 16px;
            border-bottom: 1px solid var(--border-color);
            transition: background 0.15s ease;
        }}
        .signal-item:hover {{ background: var(--bg-secondary); }}
        .signal-item:last-child {{ border-bottom: none; }}
        .signal-item.empty {{ color: var(--text-muted); justify-content: center; padding: 32px 16px; }}
        .signal-icon {{ font-size: 20px; flex-shrink: 0; width: 28px; text-align: center; }}
        .signal-content {{ flex: 1; min-width: 0; }}
        .signal-header {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
        .signal-company {{ font-size: 13px; font-weight: 600; }}
        .signal-badge {{ font-size: 9px; font-weight: 700; padding: 1px 10px; border-radius: 100px; letter-spacing: 0.04em; text-transform: uppercase; }}
        .signal-badge.high {{ background: var(--accent-red-dim); color: #E8897A; }}
        .signal-badge.medium {{ background: var(--accent-amber-dim); color: var(--accent-amber); }}
        .signal-badge.low {{ background: var(--accent-teal-dim); color: #6FB8AE; }}
        .signal-summary {{ font-size: 13px; color: var(--text-secondary); margin-top: 2px; line-height: 1.5; }}
        .signal-recommendation {{ font-size: 12px; color: var(--accent-amber); margin-top: 6px; display: flex; align-items: center; gap: 6px; }}
        .signal-recommendation svg {{ flex-shrink: 0; }}
        .charts-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 32px;
        }}
        @media (max-width: 768px) {{
            .charts-grid {{ grid-template-columns: 1fr; }}
        }}
        .chart-container {{ position: relative; height: 200px; }}
        .run-history {{ max-height: 300px; overflow-y: auto; }}
        .run-item {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 8px 0;
            border-bottom: 1px solid var(--border-color);
            font-size: 13px;
        }}
        .run-item:last-child {{ border-bottom: none; }}
        .run-status {{ font-size: 16px; }}
        .run-status.success {{ color: var(--accent-teal); }}
        .run-status.warning {{ color: var(--accent-amber); }}
        .run-status.error {{ color: var(--accent-red); }}
        .run-time {{ color: var(--text-muted); font-size: 12px; width: 44px; }}
        .run-id {{ color: var(--text-secondary); font-family: monospace; font-size: 12px; }}
        .run-signals {{ margin-left: auto; color: var(--text-muted); font-size: 12px; }}
        .trigger-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius);
            padding: 16px 24px;
            margin-bottom: 32px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .trigger-text {{ font-size: 13px; color: var(--text-secondary); }}
        .trigger-text .mono {{ color: var(--text-muted); font-family: monospace; }}
        .footer {{
            display: flex;
            justify-content: space-between;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            font-size: 12px;
            color: var(--text-muted);
            flex-wrap: wrap;
            gap: 8px;
        }}
        .footer a {{ color: var(--text-secondary); text-decoration: none; transition: color 0.2s; }}
        .footer a:hover {{ color: var(--text-primary); }}
        .sidebar {{ display: flex; flex-direction: column; gap: 24px; }}
        @media (max-width: 600px) {{
            .app {{ padding: 16px; }}
            .header {{ flex-direction: column; align-items: stretch; }}
            .header-actions {{ flex-wrap: wrap; }}
            .stats-grid {{ grid-template-columns: 1fr 1fr; }}
            .stat-value {{ font-size: 24px; }}
        }}
    </style>
</head>
<body>
<div class="app">
    <header class="header">
        <div class="logo">
            <div class="logo-icon"></div>
            <div class="logo-text">
                <h1>StratOS</h1>
                <span>Intelligence Console</span>
            </div>
        </div>
        <div class="header-actions">
            <div class="status-pill">
                <span class="dot"></span>
                Monitoring Active
            </div>
            <button class="btn-primary" id="run-btn" onclick="triggerRun()">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                    <polygon points="5,3 19,12 5,21 5,3"/>
                </svg>
                Run Now
            </button>
        </div>
    </header>
    
    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-label">Competitors</div>
            <div class="stat-value teal">{len(competitors)}</div>
            <div class="stat-sub">Tracked</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Signals</div>
            <div class="stat-value amber">{total_signals}</div>
            <div class="stat-sub">{high_signals} high impact</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Last Scan</div>
            <div class="stat-value" style="font-size:22px;">{last_run.started_at.strftime('%b %d, %H:%M') if last_run else 'Never'}</div>
            <div class="stat-sub">Run #{str(last_run.id)[:8] if last_run else 'none'}</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">Status</div>
            <div class="stat-value" style="font-size:18px;color:var(--accent-teal);">● Healthy</div>
            <div class="stat-sub">{len(runs)} total runs</div>
        </div>
    </div>
    
    <div class="charts-grid">
        <div class="card">
            <div class="card-header">
                <span class="card-title">📊 Signal Trends</span>
                <span class="card-badge">Last 5 runs</span>
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="signalChart"></canvas>
                </div>
            </div>
        </div>
        <div class="card">
            <div class="card-header">
                <span class="card-title">🎯 Threat Distribution</span>
                <span class="card-badge">{sum(threat_counts)} total</span>
            </div>
            <div class="card-body">
                <div class="chart-container">
                    <canvas id="threatChart"></canvas>
                </div>
            </div>
        </div>
    </div>
    
    <div class="main-grid">
        <div>
            <div class="card" style="margin-bottom:24px;">
                <div class="card-header">
                    <span class="card-title">🏢 Competitors</span>
                    <span class="card-badge">{len(competitors)} active</span>
                </div>
                <div class="card-body">
                    <div class="competitors-grid">
                        {competitor_cards}
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">📡 Latest Signals</span>
                    <span class="card-badge">Live feed</span>
                </div>
                <div class="card-body" style="padding:0;">
                    <div class="signal-feed" id="signal-feed">
                        {signal_html}
                    </div>
                </div>
            </div>
        </div>
        <div class="sidebar">
            <div class="card">
                <div class="card-header">
                    <span class="card-title">⏱️ Run History</span>
                    <span class="card-badge">Recent</span>
                </div>
                <div class="card-body" style="padding:8px 16px;">
                    <div class="run-history">
                        {run_history_html}
                    </div>
                </div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">📈 Quick Stats</span>
                </div>
                <div class="card-body">
                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
                        <div>
                            <div style="font-size:11px;color:var(--text-muted);">Precision</div>
                            <div style="font-size:20px;font-weight:700;color:var(--accent-teal);">-</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-muted);">Duplicates</div>
                            <div style="font-size:20px;font-weight:700;color:var(--text-secondary);">0%</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-muted);">High Impact</div>
                            <div style="font-size:20px;font-weight:700;color:var(--accent-red);">{high_signals}</div>
                        </div>
                        <div>
                            <div style="font-size:11px;color:var(--text-muted);">Coverage</div>
                            <div style="font-size:20px;font-weight:700;color:var(--accent-amber);">100%</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="trigger-bar" id="trigger-bar">
        <div class="trigger-text" id="trigger-text">
            Run the pipeline manually — <span class="mono">POST /runs</span>
        </div>
        <span style="font-size:12px;color:var(--text-muted);">Last run: {last_run.started_at.strftime('%b %d, %H:%M') if last_run else 'Never'}</span>
    </div>
    
    <footer class="footer">
        <span>StratOS v1.0 — Autonomous Intelligence Pipeline</span>
        <a href="/docs" target="_blank">API Documentation →</a>
    </footer>
</div>

<script>
    document.addEventListener('DOMContentLoaded', function() {{
        const signalCtx = document.getElementById('signalChart').getContext('2d');
        new Chart(signalCtx, {{
            type: 'line',
            data: {{
                labels: {chart_labels},
                datasets: [{{
                    label: 'Signals',
                    data: {chart_signals},
                    borderColor: '#E8A33D',
                    backgroundColor: 'rgba(232,163,61,0.1)',
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#E8A33D',
                    pointRadius: 4,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{ legend: {{ display: false }} }},
                scales: {{
                    y: {{ beginAtZero: true, grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#6A6E76' }} }},
                    x: {{ grid: {{ display: false }}, ticks: {{ color: '#6A6E76', font: {{ size: 10 }} }} }}
                }}
            }}
        }});
        
        const threatCtx = document.getElementById('threatChart').getContext('2d');
        new Chart(threatCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['HIGH', 'MEDIUM', 'LOW'],
                datasets: [{{
                    data: {threat_counts},
                    backgroundColor: ['#C9533F', '#E8A33D', '#3D8B82'],
                    borderWidth: 0,
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'bottom',
                        labels: {{ color: '#A8AAB0', font: {{ size: 11 }}, padding: 12, usePointStyle: true, pointStyle: 'circle' }}
                    }}
                }},
                cutout: '70%'
            }}
        }});
    }});
    
    function triggerRun() {{
        const btn = document.getElementById('run-btn');
        const text = document.getElementById('trigger-text');
        btn.disabled = true;
        btn.textContent = 'Running...';
        btn.style.opacity = '0.6';
        text.innerHTML = '🚀 Pipeline started — scanning competitors, this takes about 30-60 seconds';
        
        fetch('/runs', {{ method: 'POST' }})
            .then(res => res.json())
            .then(data => {{
                setTimeout(() => {{
                    text.innerHTML = '✅ Run complete — reloading dashboard';
                    setTimeout(() => location.reload(), 1500);
                }}, 45000);
            }})
            .catch(err => {{
                btn.disabled = false;
                btn.textContent = 'Run Now';
                btn.style.opacity = '1';
                text.innerHTML = '❌ Something went wrong — try again';
            }});
    }}
</script>
</body>
</html>
'''
        return html_content
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return f"<html><body style='background:#0E0F12;color:#EDEAE3;font-family:sans-serif;padding:40px;'><h1>Error loading dashboard</h1><pre style='color:#E8897A;font-size:13px;'>{error_detail}</pre></body></html>"


# Shutdown handler
@app.on_event("shutdown")
def shutdown_scheduler():
    global scheduler
    if scheduler:
        scheduler.shutdown()
        logger.info("🛑 Scheduler shutdown")