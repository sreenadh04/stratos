import uuid
import datetime
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from groq import Groq
from stratos.config import settings

client = Groq(api_key=settings.groq_api_key)

STRATEGIST_PROMPT = """
You are a senior product strategist and competitive intelligence expert.

You have received the following intelligence signals about a competitor:

Competitor: {competitor_name}
Signals:
{signals_text}

Our Product Context: {product_context}

Analyze these signals and provide a strategic assessment.

Respond ONLY with a valid JSON object in this exact format:
{{
  "hypothesis": "What strategic direction is this competitor moving toward? Be specific.",
  "threat_level": "HIGH or MEDIUM or LOW or NEUTRAL",
  "implication": "What does this mean for our product specifically?",
  "recommendation": "One concrete action we should take in response.",
  "timeframe": "immediate or this_quarter or watch"
}}

Rules:
- Be specific and actionable, not generic
- Reference actual signals in your hypothesis
- HIGH threat: direct competition with our core features
- MEDIUM threat: adjacent moves that could affect us
- LOW/NEUTRAL: worth monitoring but not urgent
"""

def run_strategist(signals: list[dict], run_id: str, db_url: str) -> list[dict]:
    results = []
    conn = None
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Query all competitors into a dict
        cur.execute("SELECT id, name FROM competitors;")
        competitor_names = {str(r["id"]): r["name"] for r in cur.fetchall()}
        
        # Group signals by competitor_id
        competitor_groups = {}
        for s in signals:
            comp_id = str(s['competitor_id'])
            if comp_id not in competitor_groups:
                competitor_groups[comp_id] = []
            competitor_groups[comp_id].append(s)
            
        for comp_id, group in competitor_groups.items():
            try:
                # Skip if all signals in the group are duplicates
                if all(s.get('is_duplicate', False) for s in group):
                    continue
                
                competitor_name = competitor_names.get(str(comp_id), "Unknown")
                print(f"Assessing {competitor_name}...")
                
                # Build signals text
                signals_text = ""
                for i, s in enumerate(group):
                    signals_text += f"{i+1}. Summary: {s['summary']}\n   Evidence: {s['evidence']}\n\n"
                
                # Build prompt
                prompt = STRATEGIST_PROMPT.format(
                    competitor_name=competitor_name,
                    signals_text=signals_text,
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
                
                assessment = json.loads(raw_text.strip())
                hypothesis = assessment.get("hypothesis", "")
                recommendation = assessment.get("recommendation", "")
                threat_level = assessment.get("threat_level", "NEUTRAL")
                
                # Update all signals for this competitor in this run
                cur.execute("""
                    UPDATE signals 
                    SET hypothesis = %s, recommendation = %s
                    WHERE competitor_id = %s AND run_id = %s;
                """, (hypothesis, recommendation, comp_id, run_id))
                
                print(f"Strategist: {competitor_name} -> threat={threat_level}")
                
                results.append({
                    "competitor_id": comp_id,
                    "competitor_name": competitor_name,
                    "threat_level": threat_level,
                    "hypothesis": hypothesis,
                    "recommendation": recommendation
                })
                
            except Exception as e:
                print(f"  Error assessing {comp_id}: {e}")
                continue
                
        conn.commit()
        cur.close()
        
    except Exception as e:
        print(f"Database error in run_strategist: {e}")
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
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get most recent run
        cur.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1;")
        run_row = cur.fetchone()
        
        if not run_row:
            print("No runs found.")
            exit(1)
            
        run_id = str(run_row["id"])
        
        # Get signals for this run (non-duplicates)
        cur.execute("""
            SELECT s.competitor_id, s.summary, s.evidence, c.name, s.is_duplicate
            FROM signals s
            JOIN competitors c ON s.competitor_id = c.id
            WHERE s.run_id = %s AND s.is_duplicate = false;
        """, (run_id,))
        
        signal_rows = cur.fetchall()
        signals = [
            {
                "competitor_id": str(r["competitor_id"]),
                "summary": r["summary"],
                "evidence": r["evidence"],
                "competitor_name": r["name"],
                "is_duplicate": r["is_duplicate"]
            }
            for r in signal_rows
        ]
        
        print(f"Found {len(signals)} unique signals for run {run_id}")
        results = run_strategist(signals, run_id, db_url)
        print(f"Strategist complete. Assessed {len(results)} competitors")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Test failed: {e}")
