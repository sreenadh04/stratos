import uuid
import datetime
import os
import psycopg2
from typing import TypedDict
from langgraph.graph import StateGraph, END
from stratos.config import settings
from stratos.agents.scout import run_scout
from stratos.agents.analyst import run_analyst
from stratos.agents.strategist import run_strategist
from stratos.agents.writer import run_writer

class GraphState(TypedDict):
    run_id: str
    snapshots: list
    signals: list
    strategist_results: list
    delivery_success: bool
    error: str


def scout_node(state: GraphState):
    print("\n=== SCOUT AGENT ===")
    try:
        results = run_scout(state["run_id"], settings.database_url)
        return {"snapshots": results}
    except Exception as e:
        print(f"Scout node failed: {e}")
        return {"error": str(e), "snapshots": []}


def analyst_node(state: GraphState):
    print("\n=== ANALYST AGENT ===")
    snapshots = state.get("snapshots", [])
    if not snapshots:
        print("No new snapshots to analyze.")
        return {"signals": []}
    
    try:
        results = run_analyst(snapshots, state["run_id"], settings.database_url)
        return {"signals": results}
    except Exception as e:
        print(f"Analyst node failed: {e}")
        return {"error": str(e), "signals": []}


def strategist_node(state: GraphState):
    print("\n=== STRATEGIST AGENT ===")
    signals = state.get("signals", [])
    if not signals:
        print("No signals to assess.")
        return {"strategist_results": []}
    
    try:
        results = run_strategist(signals, state["run_id"], settings.database_url)
        return {"strategist_results": results}
    except Exception as e:
        print(f"Strategist node failed: {e}")
        return {"error": str(e), "strategist_results": []}


def writer_node(state: GraphState):
    print("\n=== WRITER AGENT ===")
    results = state.get("strategist_results", [])
    try:
        success = run_writer(results, state["run_id"], settings.database_url)
        return {"delivery_success": success}
    except Exception as e:
        print(f"Writer node failed: {e}")
        return {"error": str(e), "delivery_success": False}


# Build the graph
workflow = StateGraph(GraphState)

workflow.add_node("scout", scout_node)
workflow.add_node("analyst", analyst_node)
workflow.add_node("strategist", strategist_node)
workflow.add_node("writer", writer_node)

workflow.set_entry_point("scout")
workflow.add_edge("scout", "analyst")
workflow.add_edge("analyst", "strategist")
workflow.add_edge("strategist", "writer")
workflow.add_edge("writer", END)

pipeline = workflow.compile()

def run_pipeline(db_url: str) -> str:
    """Initialize a run and execute the graph pipeline."""
    run_id = str(uuid.uuid4())
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO runs (id, status, trigger_type, started_at)
            VALUES (%s, %s, %s, %s)
        """, (run_id, 'running', 'manual', datetime.datetime.utcnow()))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to initialize run in DB: {e}")
        return None

    print(f"Initialized Run ID: {run_id}")
    
    initial_state: GraphState = {
        "run_id": run_id,
        "snapshots": [],
        "signals": [],
        "strategist_results": [],
        "delivery_success": False,
        "error": ""
    }
    
    pipeline.invoke(initial_state)
    return run_id

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Error: DATABASE_URL not found in .env")
    else:
        print("Starting StratOS pipeline...")
        finished_id = run_pipeline(database_url)
        if finished_id:
            print(f"\nPipeline complete. Run ID: {finished_id}")
