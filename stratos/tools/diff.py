import hashlib
import os
import psycopg2
from dotenv import load_dotenv

def compute_content_hash(content: str) -> str:
    """Normalize content and return SHA-256 hex digest."""
    normalized = content.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def is_new_content(competitor_id: str, content_hash: str, db_url: str) -> bool:
    """Check if content hash already exists for this competitor in raw_snapshots."""
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT id FROM raw_snapshots WHERE competitor_id = %s AND content_hash = %s LIMIT 1;",
            (competitor_id, content_hash)
        )
        
        row = cur.fetchone()
        return row is None
        
    except Exception as e:
        print(f"Error checking content hash: {e}")
        return True # Default to True on error to avoid missing data, or could raise
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    
    sample_text = "  Hello World  "
    sample_hash = compute_content_hash(sample_text)
    print(f"Sample hash: {sample_hash}")
    
    # Simple verification of normalization
    if sample_hash == compute_content_hash("hello world"):
        print("Hash function working correctly (normalization verified)")
    else:
        print("Hash function normalization failed")
