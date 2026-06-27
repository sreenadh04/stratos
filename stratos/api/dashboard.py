# stratos/api/dashboard.py
"""
Dashboard HTML rendering for StratOS.
"""
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from stratos.db.repositories import RunRepository, SignalRepository, CompetitorRepository
from stratos.logging_config import get_logger
from stratos.config import settings

logger = get_logger("dashboard")


async def render_dashboard(db: AsyncSession) -> HTMLResponse:
    """Render the live HTML dashboard."""
    try:
        # Roll back any pending transaction to start fresh
        try:
            await db.rollback()
        except Exception:
            pass

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
    <meta name="api-key" content="{settings.api_key}">
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
        
        /* ===== PROGRESS BAR STYLES ===== */
        .progress-container {{
            display: none;
            width: 100%;
            margin-top: 16px;
            padding: 16px 20px;
            background: var(--bg-card);
            border-radius: var(--radius);
            border: 1px solid var(--border-color);
        }}
        .progress-container.visible {{
            display: block;
            animation: fadeSlideDown 0.4s ease-out;
        }}
        @keyframes fadeSlideDown {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .progress-bar-container {{
            width: 100%;
            height: 6px;
            background: var(--bg-secondary);
            border-radius: 3px;
            overflow: hidden;
        }}
        .progress-bar {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent-amber), var(--accent-teal));
            border-radius: 3px;
            transition: width 0.5s ease;
            width: 0%;
        }}
        .progress-steps {{
            display: flex;
            justify-content: space-between;
            margin-top: 14px;
            gap: 8px;
        }}
        .step {{
            flex: 1;
            text-align: center;
            font-size: 11px;
            padding: 6px 4px;
            border-radius: 4px;
            background: var(--bg-secondary);
            color: var(--text-muted);
            transition: all 0.4s ease;
            border: 1px solid transparent;
            font-weight: 500;
        }}
        .step.active {{
            background: var(--accent-amber-dim);
            color: var(--accent-amber);
            border-color: rgba(232,163,61,0.3);
            box-shadow: 0 0 20px rgba(232,163,61,0.1);
        }}
        .step.completed {{
            background: var(--accent-teal-dim);
            color: var(--accent-teal);
            border-color: rgba(61,139,130,0.3);
        }}
        .step.failed {{
            background: var(--accent-red-dim);
            color: var(--accent-red);
            border-color: rgba(201,83,63,0.3);
        }}
        #progress-message {{
            font-size: 13px;
            min-height: 24px;
            margin-top: 12px;
            text-align: center;
            color: var(--text-secondary);
        }}
        /* ===== END PROGRESS BAR STYLES ===== */
        
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
            .progress-steps {{ flex-wrap: wrap; }}
            .step {{ flex: 0 0 calc(50% - 4px); }}
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
    
    <!-- ===== PROGRESS CONTAINER ===== -->
    <div id="progress-container" class="progress-container">
        <div class="progress-bar-container">
            <div id="progress-bar" class="progress-bar"></div>
        </div>
        <div class="progress-steps">
            <div class="step" data-step="init">🚀 Start</div>
            <div class="step" data-step="scout">🔍 Scout</div>
            <div class="step" data-step="analyst">🧠 Analyst</div>
            <div class="step" data-step="strategist">🎯 Strategist</div>
            <div class="step" data-step="writer">📨 Writer</div>
            <div class="step" data-step="done">✅ Done</div>
        </div>
        <div id="progress-message">⏳ Connecting...</div>
    </div>
    <!-- ===== END PROGRESS CONTAINER ===== -->
    
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
    
    // ============================================================
    // WEBSOCKET PROGRESS TRACKING
    // ============================================================
    let ws = null;

    function triggerRun() {{
        const btn = document.getElementById('run-btn');
        const text = document.getElementById('trigger-text');
        btn.disabled = true;
        btn.textContent = 'Running...';
        btn.style.opacity = '0.6';
        text.innerHTML = '🚀 Pipeline started — connecting to live updates...';
        
        const container = document.getElementById('progress-container');
        container.className = 'progress-container visible';
        resetProgress();
        
        const apiKey = document.querySelector('meta[name="api-key"]').getAttribute('content');
        
        fetch('/runs', {{
            method: 'POST',
            headers: {{
                'X-API-Key': apiKey
            }}
        }})
        .then(res => {{
            if (!res.ok) {{
                throw new Error(`HTTP ${{res.status}}`);
            }}
            return res.json();
        }})
        .then(data => {{
            const runId = data.run_id;
            console.log('📡 Run started with ID:', runId);
            text.innerHTML = `📡 Run started: <span class="mono">${{runId.slice(0, 8)}}</span>`;
            connectWebSocket(runId);
        }})
        .catch(err => {{
            btn.disabled = false;
            btn.textContent = 'Run Now';
            btn.style.opacity = '1';
            text.innerHTML = '❌ Something went wrong — try again';
            container.className = 'progress-container';
        }});
    }}

    function connectWebSocket(runId) {{
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${{protocol}}//${{window.location.host}}/ws/${{runId}}`;
        console.log('🔌 Connecting WebSocket to:', wsUrl);
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {{
            console.log('✅ WebSocket connected');
            document.getElementById('progress-message').textContent = '⏳ Waiting for pipeline to start...';
        }};
        
        ws.onmessage = function(event) {{
            console.log('📨 WebSocket message received:', event.data);
            try {{
                const data = JSON.parse(event.data);
                console.log('📊 Parsed data:', data);
                if (data.type === 'heartbeat') {{
                    console.log('💓 Heartbeat received');
                    return;
                }}
                updateProgress(data);
            }} catch (e) {{
                console.error('❌ Error parsing WebSocket message:', e);
            }}
        }};
        
        ws.onclose = function() {{
            console.log('❌ WebSocket closed');
        }};
        
        ws.onerror = function(error) {{
            console.error('❌ WebSocket error:', error);
            document.getElementById('progress-message').textContent = '⚠️ Connection lost, but pipeline is still running.';
        }};
    }}

    function resetProgress() {{
        document.getElementById('progress-bar').style.width = '0%';
        document.querySelectorAll('.step').forEach(el => {{
            el.className = 'step';
        }});
        document.getElementById('progress-message').textContent = '';
    }}

    function updateProgress(data) {{
        console.log('🔄 updateProgress called with:', data);
        const step = data.step;
        const status = data.status;
        const message = data.message || '';
        
        const steps = ['init', 'scout', 'analyst', 'strategist', 'writer', 'done'];
        const currentIndex = steps.indexOf(step);
        if (currentIndex !== -1) {{
            const progress = Math.min((currentIndex / (steps.length - 1)) * 100, 100);
            document.getElementById('progress-bar').style.width = progress + '%';
        }}
        
        const stepEl = document.querySelector(`.step[data-step="${{step}}"]`);
        if (stepEl) {{
            if (status === 'started') {{
                stepEl.className = 'step active';
            }} else if (status === 'completed') {{
                stepEl.className = 'step completed';
            }} else if (status === 'failed') {{
                stepEl.className = 'step failed';
            }}
        }}
        
        const msgEl = document.getElementById('progress-message');
        if (message) {{
            msgEl.textContent = message;
        }}
        
        if (step === 'done') {{
            document.getElementById('progress-bar').style.width = '100%';
            setTimeout(() => {{
                const btn = document.getElementById('run-btn');
                btn.disabled = false;
                btn.textContent = 'Run Now';
                btn.style.opacity = '1';
                const text = document.getElementById('trigger-text');
                if (status === 'completed') {{
                    text.innerHTML = '✅ Run complete — reloading dashboard';
                }} else {{
                    text.innerHTML = '❌ Run failed — check logs';
                }}
                setTimeout(() => location.reload(), 2000);
            }}, 1000);
            if (ws) ws.close();
        }}
    }}
</script>
</body>
</html>
'''
        return HTMLResponse(content=html_content, status_code=200)
        
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        return HTMLResponse(
            content=f"<html><body style='background:#0E0F12;color:#EDEAE3;font-family:sans-serif;padding:40px;'><h1>Error loading dashboard</h1><pre style='color:#E8897A;font-size:13px;'>{error_detail}</pre></body></html>",
            status_code=500
        )