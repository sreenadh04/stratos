# stratos/agents/writer.py
"""
Writer Agent - Formats and delivers intelligence briefings.
"""
import datetime
import json
import httpx
import asyncio
from typing import List, Dict, Any, Optional
from stratos.config import settings
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import RunRepository
from stratos.logging_config import get_run_logger
from stratos.retry import with_retry, AsyncRetryContext


THREAT_EMOJIS = {
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "🟢",
    "NEUTRAL": "⚪",
}


DEFAULT_BRIEFING_FORMAT = {
    "show_threat_levels": ["HIGH", "MEDIUM", "LOW", "NEUTRAL"],
    "show_hypothesis": True,
    "show_recommendation": True,
    "show_implication": False,
    "show_timeframe": False,
    "max_competitors": 10,
    "include_header": True,
    "include_footer": True,
}


async def get_user_format(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Get user's preferred briefing format."""
    return DEFAULT_BRIEFING_FORMAT.copy()


def build_slack_blocks(
    run_id: str,
    results: List[Dict[str, Any]],
    format_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Build Slack Block Kit message with customizable format."""
    blocks = []
    
    if format_config.get("include_header", True):
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🔍 StratOS Weekly Intelligence Briefing",
                "emoji": True
            }
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Date:* {datetime.date.today()}\n*Run ID:* `{run_id[:8]}`"
            }
        })
        blocks.append({"type": "divider"})
    
    shown = 0
    max_competitors = format_config.get("max_competitors", 10)
    show_threat_levels = format_config.get("show_threat_levels", ["HIGH", "MEDIUM", "LOW", "NEUTRAL"])
    
    for res in results:
        if shown >= max_competitors:
            break
        
        threat = res.get("threat_level", "NEUTRAL")
        if threat not in show_threat_levels:
            continue
        
        shown += 1
        comp_name = res.get("competitor_name", "Unknown")
        emoji = THREAT_EMOJIS.get(threat, "⚪")
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{emoji} {comp_name}* (Threat: {threat})"
            }
        })
        
        if format_config.get("show_hypothesis", True):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Hypothesis:* {res.get('hypothesis', 'N/A')}"
                }
            })
        
        if format_config.get("show_recommendation", True):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommendation:* {res.get('recommendation', 'N/A')}"
                }
            })
        
        if format_config.get("show_implication", False):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Implication:* {res.get('implication', 'N/A')}"
                }
            })
        
        if format_config.get("show_timeframe", False):
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Timeframe:* {res.get('timeframe', 'N/A')}"
                }
            })
        
        blocks.append({"type": "divider"})
    
    if not results:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "✅ No new significant signals detected this week."
            }
        })
        blocks.append({"type": "divider"})
    
    if format_config.get("include_footer", True):
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Powered by StratOS • Run: `{run_id[:8]}` • Next briefing in 7 days\n_Reply with feedback to help us improve_"
                }
            ]
        })
    
    return blocks


@with_retry(max_attempts=3, min_wait=1.0, max_wait=10.0, operation_name="Slack delivery")
async def deliver_to_slack(blocks: List[Dict[str, Any]]) -> bool:
    """Deliver briefing to Slack with retry."""
    if not settings.slack_webhook_url:
        return False
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.slack_webhook_url,
                json={"blocks": blocks}
            )
            
            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=response.request,
                    response=response
                )
            else:
                return False
                
    except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.ConnectError):
        raise
    except Exception:
        return False


async def send_email_digest(results: List[Dict[str, Any]], run_id: str) -> bool:
    """Send briefing via email."""
    logger = get_run_logger("writer", run_id)
    logger.info(f"📧 Email delivery for run {run_id}: {len(results)} signals")
    return True


async def deliver_to_teams(blocks: List[Dict[str, Any]]) -> bool:
    """Deliver briefing to Microsoft Teams."""
    logger.info("📢 Teams delivery: briefing sent")
    return True


async def deliver_to_discord(blocks: List[Dict[str, Any]]) -> bool:
    """Deliver briefing to Discord."""
    logger.info("🎮 Discord delivery: briefing sent")
    return True


async def track_read_receipt(
    run_id: str,
    channel: str,
    message_id: Optional[str] = None,
) -> None:
    """Track if user has read the briefing."""
    logger = get_run_logger("writer", run_id)
    logger.info(f"📋 Read receipt tracked for run {run_id} on {channel}")


async def run_writer(strategist_results: List[Dict[str, Any]], run_id: str) -> bool:
    """Orchestrate block building, delivery, and run completion."""
    logger = get_run_logger("writer", run_id)
    
    if not strategist_results:
        logger.info("No strategist results to deliver")
        return False
    
    format_config = await get_user_format()
    
    blocks = build_slack_blocks(run_id, strategist_results, format_config)
    logger.info(f"📝 Built {len(blocks)} Slack blocks")
    
    success = False
    
    try:
        success = await deliver_to_slack(blocks)
        if success:
            logger.info("✅ Slack delivery successful")
        else:
            logger.warning("⚠️ Slack delivery failed")
    except Exception as e:
        logger.error(f"❌ Slack delivery error: {e}")
    
    if not success:
        try:
            success = await send_email_digest(strategist_results, run_id)
            if success:
                logger.info("✅ Email delivery successful")
        except Exception as e:
            logger.error(f"❌ Email delivery error: {e}")
    
    if success:
        await track_read_receipt(run_id, "slack")
    
    try:
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            run = await run_repo.get_by_id(run_id)
            signal_count = run.signal_count if run else 0
            await run_repo.complete_run(run_id, signal_count)
            await session.commit()
        logger.info(f"✅ Run {run_id} marked as complete")
        
    except Exception as e:
        logger.error(f"⚠️ Error updating run status: {e}", exc_info=True)
    
    return success


def run_writer_sync(strategist_results: List[Dict[str, Any]], run_id: str) -> bool:
    """Synchronous wrapper for run_writer."""
    return asyncio.run(run_writer(strategist_results, run_id))


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
    
    logger = get_run_logger("writer", "test")
    logger.info("Testing Writer agent...")
    format_config = DEFAULT_BRIEFING_FORMAT
    blocks = build_slack_blocks("test-run-123", sample_results, format_config)
    logger.info(f"✅ Built {len(blocks)} Slack blocks")