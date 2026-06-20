import datetime
import os
import uuid
import psycopg2
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from stratos.config import settings
from stratos.agents.orchestrator import run_pipeline

load_dotenv()

app = FastAPI(title="StratOS API", version="1.0.0")

class SignalEvaluation(BaseModel):
    accurate: bool
    note: str

@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.datetime.now().isoformat()}

@app.post("/runs")
def trigger_run(background_tasks: BackgroundTasks):
    run_id = str(uuid.uuid4())
    # Note: run_pipeline itself handles DB insertion and execution.
    # We pass it to background tasks.
    background_tasks.add_task(run_pipeline, settings.database_url)
    return {"message": "Run started", "run_id": "Initialization in progress..."}

@app.get("/runs")
def get_runs():
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, status, signal_count, started_at, completed_at 
            FROM runs 
            ORDER BY started_at DESC 
            LIMIT 10;
        """)
        rows = cur.fetchall()
        runs = [
            {
                "id": r[0],
                "status": r[1],
                "signal_count": r[2],
                "started_at": r[3].isoformat() if r[3] else None,
                "completed_at": r[4].isoformat() if r[4] else None
            }
            for r in rows
        ]
        cur.close()
        conn.close()
        return runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/runs/{run_id}/signals")
def get_run_signals(run_id: str):
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("""
            SELECT s.id, c.name, s.impact_level, s.summary, s.is_duplicate 
            FROM signals s
            JOIN competitors c ON s.competitor_id = c.id
            WHERE s.run_id = %s;
        """, (run_id,))
        rows = cur.fetchall()
        signals = [
            {
                "id": r[0],
                "competitor": r[1],
                "impact_level": r[2],
                "summary": r[3],
                "is_duplicate": r[4]
            }
            for r in rows
        ]
        cur.close()
        conn.close()
        return signals
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/signals/{signal_id}/evaluate")
def evaluate_signal(signal_id: str, eval_data: SignalEvaluation):
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        cur.execute("""
            UPDATE signals 
            SET evaluated_accurate = %s, evaluator_note = %s 
            WHERE id = %s;
        """, (eval_data.accurate, eval_data.note, signal_id))
        conn.commit()
        cur.close()
        conn.close()
        return {"message": "Evaluation saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def get_dashboard():
    try:
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        
        # Get last run
        cur.execute("SELECT id, status, started_at FROM runs ORDER BY started_at DESC LIMIT 1;")
        last_run = cur.fetchone()
        
        # Get signal counts
        cur.execute("SELECT COUNT(*) FROM signals;")
        total_signals = cur.fetchone()[0]
        
        # Get monitored competitors
        cur.execute("SELECT name, website_url FROM competitors;")
        competitors = cur.fetchall()
        
        cur.close()
        conn.close()
        
        comp_html = "".join([f"<li><a href='{c[1]}'>{c[0]}</a></li>" for c in competitors])
        
        run_info = f"Last run: {last_run[2].strftime('%Y-%m-%d %H:%M:%S')} ({last_run[1]})" if last_run else "No runs yet."
        
        html_content = f"""
        <html>
            <head>
                <title>StratOS Dashboard</title>
                <style>
                    body {{ font-family: sans-serif; margin: 40px; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 800px; margin: auto; }}
                    .card {{ border: 1px solid #ddd; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                    .btn {{ background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }}
                    .btn:hover {{ background: #0056b3; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>StratOS - Competitive Intelligence Agent</h1>
                    <div class="card">
                        <h3>System Status</h3>
                        <p>{run_info}</p>
                        <p><strong>Total Signals Found:</strong> {total_signals}</p>
                        <form action="/runs" method="post">
                            <button type="submit" class="btn">Trigger New Run</button>
                        </form>
                    </div>
                    <div class="card">
                        <h3>Monitored Competitors</h3>
                        <ul>{comp_html}</ul>
                    </div>
                </div>
            </body>
        </html>
        """
        return html_content
    except Exception as e:
        return f"<html><body><h1>Error loading dashboard</h1><p>{str(e)}</p></body></html>"
