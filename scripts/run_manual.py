# scripts/run_manual.py
"""
Manually trigger the StratOS pipeline from the command line.
Includes cost tracking (#40).
"""
import os
import sys
import asyncio
from dotenv import load_dotenv

# Add parent directory to sys.path so stratos module is found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stratos.agents.orchestrator import run_pipeline
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import RunRepository
from stratos.logging_config import get_logger

logger = get_logger("run_manual")


async def main():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("❌ Error: DATABASE_URL not found in .env")
        sys.exit(1)

    print("=" * 50)
    print("  StratOS - Strategic Intelligence Agent")
    print("=" * 50)
    print("Starting intelligence run...")

    try:
        start_time = asyncio.get_event_loop().time()
        run_id = await run_pipeline("manual")
        end_time = asyncio.get_event_loop().time()
        
        if run_id:
            duration = end_time - start_time
            
            # #40: Get cost information
            async with get_db_session_manual() as session:
                run_repo = RunRepository(session)
                run = await run_repo.get_by_id(run_id)
                
                cost_info = ""
                if run and run.estimated_cost:
                    cost_info = f"\n   💰 Estimated Cost: ${run.estimated_cost:.4f}"
                
                print("\n" + "=" * 50)
                print(f"✅ Pipeline complete! Run ID: {run_id}")
                print(f"   ⏱️ Duration: {duration:.2f} seconds")
                print(f"   📊 Signals: {run.signal_count if run else 0}")
                print(cost_info)
                print("Check your Slack for the briefing.")
                print("=" * 50)
        else:
            print("\n❌ Pipeline failed to initialize.")
    except Exception as e:
        print(f"\n❌ An error occurred during the run: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())