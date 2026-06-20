import uuid
import datetime
import psycopg2
from stratos.tools.scraper import scrape_url
from stratos.tools.diff import compute_content_hash, is_new_content
from stratos.config import settings

def run_scout(run_id: str, db_url: str) -> list[dict]:
    """
    Iterate through competitors, scrape their blogs, and save new snapshots.
    """
    results = []
    conn = None
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # 1. Fetch all competitors
        cur.execute("SELECT id, name, blog_url FROM competitors;")
        competitors = cur.fetchall()
        
        for comp_id, name, blog_url in competitors:
            try:
                print(f"Scouting {name}...")
                
                # 2. Scrape blog
                scraped = scrape_url(blog_url)
                content = scraped.markdown_content
                
                # 3. Compute hash and check if new
                content_hash = compute_content_hash(content)
                if is_new_content(comp_id, content_hash, db_url):
                    # 4. Save new snapshot
                    snapshot_id = str(uuid.uuid4())
                    captured_at = datetime.datetime.utcnow()
                    
                    cur.execute("""
                        INSERT INTO raw_snapshots (id, competitor_id, run_id, source_url, content_hash, raw_content, captured_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (snapshot_id, comp_id, run_id, blog_url, content_hash, content, captured_at))
                    
                    results.append({
                        "competitor_id": comp_id,
                        "competitor_name": name,
                        "snapshot_id": snapshot_id,
                        "content": content,
                        "blog_url": blog_url
                    })
                    print(f"  New content found for {name}")
                else:
                    print(f"  No changes for {name}")
                    
            except Exception as e:
                print(f"  Error scouting {name}: {e}")
                continue
                
        conn.commit()
        cur.close()
        
    except Exception as e:
        print(f"Database error in run_scout: {e}")
    finally:
        if conn:
            conn.close()
            
    return results

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    run_id = str(uuid.uuid4())
    
    # Insert a real row into the runs table
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
        print(f"Created run record: {run_id}")
    except Exception as e:
        print(f"Failed to create run record: {e}")
        exit(1)
    
    print(f"Starting scout test with run_id: {run_id}")
    results = run_scout(run_id, db_url)
    print(f"Scout complete. Found {len(results)} new snapshots")
