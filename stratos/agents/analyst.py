import uuid
import datetime
import json
import psycopg2
import os
import re
from groq import Groq
from stratos.config import settings
from stratos.memory.embeddings import embed_text
from stratos.memory.vector_store import QdrantStore

client = Groq(api_key=settings.groq_api_key)

ANALYST_PROMPT = """
You are a competitive intelligence analyst. Analyze the following content from a competitor's blog/website and extract the most important strategic signal.

Competitor: {competitor_name}
Content: {content}
Our Product Context: {product_context}

Respond ONLY with a valid JSON object in this exact format:
{{
  "summary": "one sentence summary of the key strategic signal",
  "impact_level": "HIGH or MEDIUM or LOW",
  "evidence": "specific quote or detail from the content that supports this",
  "confidence": 0.0 to 1.0
}}

Rules:
- HIGH: major product launch, pricing change, new market entry
- MEDIUM: feature update, partnership, hiring surge
- LOW: blog post, minor update, general content
- Be specific, not generic. Reference actual content.
"""

def run_analyst(snapshots: list[dict], run_id: str, db_url: str) -> list[dict]:
    results = []
    store = QdrantStore()
    conn = None
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        for snapshot in snapshots:
            try:
                print(f"Analyzing {snapshot['competitor_name']}...")
                
                # Build prompt
                content_preview = snapshot['content'][:3000]
                prompt = ANALYST_PROMPT.format(
                    competitor_name=snapshot['competitor_name'],
                    content=content_preview,
                    product_context=settings.product_context
                )
                
                # Call Groq
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}]
                )
                response_text = response.choices[0].message.content
                
                # Parse JSON
                raw_text = response_text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text.replace("```json", "", 1)
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                
                try:
                    # Robust parsing: try to find JSON object using regex
                    match = re.search(r'\{.*\}', raw_text, re.DOTALL)
                    if match:
                        raw_text = match.group(0)
                    analysis = json.loads(raw_text.strip())
                except Exception as parse_error:
                    print(f"  JSON parse error for {snapshot['competitor_name']}: {parse_error}")
                    analysis = {
                        "summary": "Analysis unavailable", 
                        "impact_level": "LOW", 
                        "evidence": "Parse error", 
                        "confidence": 0.5
                    }

                summary = analysis.get("summary", "")
                impact_level = analysis.get("impact_level", "LOW")
                evidence = analysis.get("evidence", "")
                confidence = analysis.get("confidence", 0.0)
                
                # Check for duplicates
                is_duplicate = False
                embedding = embed_text(summary)
                
                if embedding:
                    similar = store.search_similar(embedding, snapshot['competitor_id'])
                    for hit in similar:
                        if hit['score'] > 0.98:
                            is_duplicate = True
                            print("  Duplicate signal skipped")
                            break
                    
                    if not is_duplicate:
                        store.upsert_signal(
                            signal_id=str(uuid.uuid4()),
                            vector=embedding,
                            payload={
                                "competitor_id": snapshot['competitor_id'],
                                "summary": summary,
                                "impact_level": impact_level
                            }
                        )
                
                # Save to DB
                signal_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO signals (
                        id, run_id, competitor_id, raw_snapshot_id, 
                        impact_level, summary, evidence, confidence, 
                        is_duplicate, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    signal_id, run_id, snapshot['competitor_id'], snapshot['snapshot_id'],
                    impact_level, summary, evidence, confidence,
                    is_duplicate, datetime.datetime.utcnow()
                ))
                
                results.append({
                    "signal_id": signal_id,
                    "competitor_id": snapshot['competitor_id'],
                    "competitor_name": snapshot.get("competitor_name", "Unknown"),
                    "summary": summary,
                    "evidence": evidence,
                    "impact_level": impact_level,
                    "is_duplicate": is_duplicate
                })
                
                print(f"  Impact: {impact_level} | {summary[:80]}")
                
            except Exception as e:
                print(f"  Error analyzing snapshot for {snapshot.get('competitor_name')}: {e}")
                continue
                
        conn.commit()
        cur.close()
        
    except Exception as e:
        print(f"Database error in run_analyst: {e}")
    finally:
        if conn:
            conn.close()
            
    return results

if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        
        # Get most recent run
        cur.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1;")
        run_row = cur.fetchone()
        
        if not run_row:
            print("No runs found. Run scout test first.")
            exit(1)
            
        run_id = run_row[0]
        
        # Get snapshots for this run
        cur.execute("""
            SELECT s.id, s.competitor_id, s.raw_content, c.name 
            FROM raw_snapshots s
            JOIN competitors c ON s.competitor_id = c.id
            WHERE s.run_id = %s;
        """, (run_id,))
        
        snapshot_rows = cur.fetchall()
        snapshots = [
            {
                "snapshot_id": r[0],
                "competitor_id": r[1],
                "content": r[2],
                "competitor_name": r[3]
            }
            for r in snapshot_rows
        ]
        
        print(f"Found {len(snapshots)} snapshots for run {run_id}")
        results = run_analyst(snapshots, run_id, db_url)
        print(f"Analyst complete. Scored {len(results)} signals")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Test failed: {e}")
