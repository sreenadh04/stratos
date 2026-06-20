import os
import sys
from dotenv import load_dotenv

# Add parent directory to sys.path so stratos module is found
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stratos.agents.orchestrator import run_pipeline

def main():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        sys.exit(1)

    print("=" * 50)
    print("  StratOS - Strategic Intelligence Agent")
    print("=" * 50)
    print("Starting intelligence run...")

    try:
        run_id = run_pipeline(db_url)
        if run_id:
            print("\n" + "=" * 50)
            print(f"✅ Pipeline complete! Run ID: {run_id}")
            print("Check your Slack for the briefing.")
            print("=" * 50)
        else:
            print("\n❌ Pipeline failed to initialize.")
    except Exception as e:
        print(f"\n❌ An error occurred during the run: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
