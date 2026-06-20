import datetime
import json
import httpx
import psycopg2
from stratos.config import settings

def build_slack_blocks(run_id: str, results: list[dict]) -> list[dict]:
    """Build a Slack Block Kit message from strategic assessments."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 StratOS Weekly Intelligence Briefing",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Date:* {datetime.date.today()}"
            }
        },
        {"type": "divider"}
    ]

    threat_emojis = {
        "HIGH": "🔴",
        "MEDIUM": "🟡",
        "LOW": "🟢",
        "NEUTRAL": "⚪"
    }

    for res in results:
        comp_name = res.get("competitor_name", "Unknown")
        threat = res.get("threat_level", "NEUTRAL")
        emoji = threat_emojis.get(threat, "⚪")
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {comp_name}* (Threat: {threat})"
            }
        })
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Hypothesis:* {res.get('hypothesis', 'N/A')}"
            }
        })
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Recommendation:* {res.get('recommendation', 'N/A')}"
            }
        })
        
        blocks.append({"type": "divider"})

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": "Powered by StratOS | Next briefing in 7 days"
            }
        ]
    })

    return blocks

def deliver_to_slack(blocks: list[dict]) -> bool:
    """POST the blocks to the configured Slack webhook."""
    if not settings.slack_webhook_url:
        print("Slack delivery skipped: slack_webhook_url not set")
        return False

    try:
        response = httpx.post(
            settings.slack_webhook_url,
            json={"blocks": blocks},
            timeout=10.0
        )
        if response.status_code == 200:
            print("Slack delivery successful")
            return True
        else:
            print(f"Slack delivery failed: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"Error delivering to Slack: {e}")
        return False

def run_writer(strategist_results: list[dict], run_id: str, db_url: str) -> bool:
    """Orchestrate block building, delivery, and run completion."""
    blocks = build_slack_blocks(run_id, strategist_results)
    success = deliver_to_slack(blocks)
    
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        cur.execute("""
            UPDATE runs 
            SET status = 'complete', completed_at = %s 
            WHERE id = %s;
        """, (datetime.datetime.utcnow(), run_id))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error updating run status: {e}")
        
    return success

if __name__ == "__main__":
    sample_results = [
        {
            "competitor_name": "OpenAI",
            "threat_level": "HIGH",
            "hypothesis": "Expanding into enterprise search to disrupt incumbent SaaS workflows.",
            "recommendation": "Accelerate our roadmap for integration with shared knowledge bases."
        },
        {
            "competitor_name": "Anthropic",
            "threat_level": "MEDIUM",
            "hypothesis": "Focusing on safety-first features for financial services.",
            "recommendation": "Monitor their compliance documentation for overlap with our target market."
        }
    ]
    
    blocks = build_slack_blocks("fake-run-id", sample_results)
    print(f"Built {len(blocks)} blocks")
    print("Slack blocks built successfully")
    # print(json.dumps(blocks, indent=2))
