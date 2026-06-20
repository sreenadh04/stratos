import os
import psycopg2
from dotenv import load_dotenv

def init_db():
    load_dotenv()
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        print("Error: DATABASE_URL not found in .env")
        return

    try:
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()

        # Create Competitor table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id UUID PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                website_url VARCHAR(500) NOT NULL,
                blog_url VARCHAR(500) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Table 'competitors' created successfully.")

        # Create Run table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id UUID PRIMARY KEY,
                status VARCHAR(50) DEFAULT 'pending',
                trigger_type VARCHAR(50) DEFAULT 'scheduled',
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                signal_count INTEGER DEFAULT 0,
                error_message TEXT,
                langsmith_run_id VARCHAR(255)
            );
        """)
        print("Table 'runs' created successfully.")

        # Create RawSnapshot table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS raw_snapshots (
                id UUID PRIMARY KEY,
                competitor_id UUID NOT NULL REFERENCES competitors(id),
                run_id UUID NOT NULL REFERENCES runs(id),
                source_url VARCHAR(500) NOT NULL,
                content_hash VARCHAR(64) NOT NULL,
                raw_content TEXT NOT NULL,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Table 'raw_snapshots' created successfully.")

        # Create Signal table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id UUID PRIMARY KEY,
                run_id UUID NOT NULL REFERENCES runs(id),
                competitor_id UUID NOT NULL REFERENCES competitors(id),
                raw_snapshot_id UUID REFERENCES raw_snapshots(id),
                impact_level VARCHAR(10),
                summary TEXT,
                evidence TEXT,
                hypothesis TEXT,
                recommendation TEXT,
                confidence FLOAT,
                is_duplicate BOOLEAN DEFAULT FALSE,
                evaluated_accurate BOOLEAN,
                evaluator_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        print("Table 'signals' created successfully.")

        conn.commit()
        cur.close()
        conn.close()
        print("Database initialization complete.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    init_db()
