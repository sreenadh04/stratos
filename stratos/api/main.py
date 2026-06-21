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

        cur.execute("SELECT id, status, started_at FROM runs ORDER BY started_at DESC LIMIT 1;")
        last_run = cur.fetchone()

        cur.execute("SELECT COUNT(*) FROM signals WHERE is_duplicate = false;")
        total_signals = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM signals WHERE is_duplicate = false AND impact_level = 'HIGH';")
        high_signals = cur.fetchone()[0]

        cur.execute("SELECT id, name, website_url FROM competitors ORDER BY name;")
        competitors = cur.fetchall()

        competitor_cards = ""
        for comp_id, name, url in competitors:
            cur.execute("""
                SELECT impact_level FROM signals
                WHERE competitor_id = %s AND is_duplicate = false
                ORDER BY created_at DESC LIMIT 1;
            """, (comp_id,))
            latest = cur.fetchone()
            level = latest[0] if latest else "LOW"
            level_class = level.lower() if level in ("HIGH", "MEDIUM", "LOW") else "low"
            dot_class = "high" if level == "HIGH" else ""
            domain = url.replace("https://", "").replace("http://", "").rstrip("/")
            competitor_cards += f'''
            <div class="competitor {"threat-high" if level == "HIGH" else ""}">
                <div class="pulse-indicator {dot_class}"></div>
                <div class="competitor-info">
                    <div class="competitor-name">{name}</div>
                    <div class="competitor-meta">{domain}</div>
                </div>
                <div class="threat-badge {level_class}">{level}</div>
            </div>
            '''

        cur.execute("""
            SELECT s.id, c.name, s.impact_level, s.summary, s.recommendation, s.created_at
            FROM signals s
            JOIN competitors c ON s.competitor_id = c.id
            WHERE s.is_duplicate = false
            ORDER BY s.created_at DESC
            LIMIT 8;
        """)
        signal_rows = cur.fetchall()

        signal_html = ""
        if signal_rows:
            for sid, comp_name, impact, summary, recommendation, created_at in signal_rows:
                impact_class = (impact or "low").lower()
                time_str = created_at.strftime("%H:%M") if created_at else ""
                rec_html = ""
                if recommendation:
                    rec_html = f'''
                    <div class="signal-rec">
                        <span class="signal-rec-label">Action</span>
                        <span>{recommendation}</span>
                    </div>
                    '''
                signal_html += f'''
                <div class="signal {impact_class}">
                    <div class="signal-rail"></div>
                    <div class="signal-body">
                        <div class="signal-top">
                            <span class="signal-company">{comp_name}</span>
                            <span class="signal-time">{time_str}</span>
                        </div>
                        <div class="signal-summary">{summary or ""}</div>
                        {rec_html}
                    </div>
                </div>
                '''
        else:
            signal_html = '<div class="signal low"><div class="signal-rail"></div><div class="signal-body"><div class="signal-summary">No signals yet. Trigger a run to start monitoring.</div></div></div>'

        cur.close()
        conn.close()

        last_scan = last_run[2].strftime("%Y-%m-%d %H:%M") if last_run else "Never"
        run_id_short = str(last_run[0])[:8] if last_run else "none"

        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StratOS — Intelligence Console</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');
  :root {{
    --bg: #0E0F12; --bg-raised: #16181D; --bg-raised-2: #1C1F26; --border: #2A2D35;
    --text-primary: #EDEAE3; --text-secondary: #8B8D94; --text-tertiary: #5A5C63;
    --amber: #E8A33D; --amber-dim: #4A3A1F; --teal: #3D8B82; --teal-dim: #1C3530;
    --red: #C9533F; --red-dim: #3D2420;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text-primary); font-family: 'Inter', sans-serif; line-height: 1.5; }}
  .wrap {{ max-width: 920px; margin: 0 auto; padding: 56px 24px 80px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 48px; padding-bottom: 24px; border-bottom: 1px solid var(--border); flex-wrap: wrap; gap: 16px; }}
  .brand {{ display: flex; align-items: center; gap: 12px; }}
  .brand-mark {{ width: 32px; height: 32px; border: 1.5px solid var(--amber); border-radius: 4px; display: flex; align-items: center; justify-content: center; }}
  .brand-mark-dot {{ width: 8px; height: 8px; background: var(--amber); border-radius: 50%; animation: pulse-ring 2.4s ease-out infinite; }}
  @keyframes pulse-ring {{ 0% {{ box-shadow: 0 0 0 0 rgba(232,163,61,0.5); }} 70% {{ box-shadow: 0 0 0 10px rgba(232,163,61,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(232,163,61,0); }} }}
  .brand-text h1 {{ font-size: 18px; font-weight: 700; letter-spacing: -0.01em; }}
  .brand-text p {{ font-size: 12px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.02em; margin-top: 2px; }}
  .status-pill {{ display: flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--teal); background: var(--teal-dim); border: 1px solid rgba(61,139,130,0.3); padding: 6px 12px; border-radius: 100px; }}
  .status-dot {{ width: 6px; height: 6px; background: var(--teal); border-radius: 50%; }}
  .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 48px; }}
  .stat {{ background: var(--bg-raised); padding: 20px 24px; }}
  .stat-label {{ font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.06em; font-family: 'JetBrains Mono', monospace; margin-bottom: 8px; }}
  .stat-value {{ font-size: 28px; font-weight: 600; letter-spacing: -0.02em; }}
  .stat-value.amber {{ color: var(--amber); }}
  .stat-sub {{ font-size: 12px; color: var(--text-secondary); margin-top: 4px; }}
  .section-head {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; }}
  .section-title {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-secondary); }}
  .section-meta {{ font-size: 12px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; }}
  .competitors {{ display: flex; flex-direction: column; gap: 12px; margin-bottom: 48px; }}
  .competitor {{ background: var(--bg-raised); border: 1px solid var(--border); border-radius: 8px; padding: 18px 20px; display: flex; align-items: center; gap: 16px; }}
  .pulse-indicator {{ width: 10px; height: 10px; border-radius: 50%; background: var(--teal); flex-shrink: 0; position: relative; }}
  .pulse-indicator.high {{ background: var(--red); }}
  .competitor-info {{ flex: 1; min-width: 0; }}
  .competitor-name {{ font-size: 14px; font-weight: 600; }}
  .competitor-meta {{ font-size: 12px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; margin-top: 2px; }}
  .threat-badge {{ font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; padding: 4px 10px; border-radius: 4px; flex-shrink: 0; }}
  .threat-badge.high {{ background: var(--red-dim); color: #E8897A; }}
  .threat-badge.medium {{ background: var(--amber-dim); color: var(--amber); }}
  .threat-badge.low {{ background: var(--teal-dim); color: #6FB8AE; }}
  .signal-feed {{ display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 48px; }}
  .signal {{ background: var(--bg-raised); padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; gap: 16px; }}
  .signal:last-child {{ border-bottom: none; }}
  .signal-rail {{ width: 3px; flex-shrink: 0; border-radius: 2px; background: var(--red); }}
  .signal.medium .signal-rail {{ background: var(--amber); }}
  .signal.low .signal-rail {{ background: var(--teal); }}
  .signal-body {{ flex: 1; min-width: 0; }}
  .signal-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
  .signal-company {{ font-size: 13px; font-weight: 600; }}
  .signal-time {{ font-size: 11px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; margin-left: auto; }}
  .signal-summary {{ font-size: 13px; color: var(--text-secondary); line-height: 1.6; }}
  .signal-rec {{ font-size: 12px; color: var(--amber); margin-top: 8px; display: flex; gap: 6px; }}
  .signal-rec-label {{ font-family: 'JetBrains Mono', monospace; color: var(--text-tertiary); text-transform: uppercase; font-size: 10px; letter-spacing: 0.04em; padding-top: 1px; flex-shrink: 0; }}
  .trigger-bar {{ display: flex; align-items: center; justify-content: space-between; background: var(--bg-raised-2); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin-bottom: 48px; flex-wrap: wrap; gap: 12px; }}
  .trigger-text {{ font-size: 13px; color: var(--text-secondary); }}
  .trigger-text .mono {{ color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; }}
  .btn-trigger {{ font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; background: var(--amber); color: #1A1206; border: none; padding: 9px 18px; border-radius: 6px; cursor: pointer; letter-spacing: 0.02em; }}
  .footer {{ display: flex; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border); font-size: 12px; color: var(--text-tertiary); font-family: 'JetBrains Mono', monospace; flex-wrap: wrap; gap: 8px; }}
  .footer a {{ color: var(--text-secondary); text-decoration: none; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="brand">
      <div class="brand-mark"><div class="brand-mark-dot"></div></div>
      <div class="brand-text"><h1>StratOS</h1><p>INTELLIGENCE CONSOLE</p></div>
    </div>
    <div class="status-pill"><div class="status-dot"></div>MONITORING ACTIVE</div>
  </div>
  <div class="stats">
    <div class="stat"><div class="stat-label">Competitors tracked</div><div class="stat-value">{len(competitors)}</div></div>
    <div class="stat"><div class="stat-label">Signals found</div><div class="stat-value amber">{total_signals}</div><div class="stat-sub">{high_signals} high impact</div></div>
    <div class="stat"><div class="stat-label">Last scan</div><div class="stat-value" style="font-size:18px;">{last_scan}</div></div>
  </div>
  <div class="section-head"><div class="section-title">Tracked competitors</div><div class="section-meta">{len(competitors)} active</div></div>
  <div class="competitors">{competitor_cards}</div>
  <div class="section-head"><div class="section-title">Latest signals</div><div class="section-meta">Run #{run_id_short}</div></div>
  <div class="signal-feed">{signal_html}</div>
  <div class="trigger-bar">
    <div class="trigger-text">Run the pipeline manually — <span class="mono">POST /runs</span></div>
    <form action="/runs" method="post" style="margin:0;"><button type="submit" class="btn-trigger">RUN NOW</button></form>
  </div>
  <div class="footer">
    <span>StratOS v1.0 — autonomous intelligence pipeline</span>
    <a href="/docs">API docs →</a>
  </div>
</div>
</body>
</html>
"""
        return html_content
    except Exception as e:
        return f"<html><body style='background:#0E0F12;color:#EDEAE3;font-family:sans-serif;padding:40px;'><h1>Error loading dashboard</h1><p>{str(e)}</p></body></html>"
