# stratos/agents/writer.py
"""
Writer Agent - Formats and delivers intelligence briefings.
Now fully async with proper database session management.
"""
import datetime
import json
import httpx
import asyncio
from typing import List, Dict, Any
from stratos.config import settings
from stratos.db.session import get_db_session_manual
from stratos.db.repositories import RunRepository
from stratos.logging_config import get_logger

# Create logger
logger = get_logger("writer")


def build_slack_blocks(run_id: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                "text": f"*Date:* {datetime.date.today()}\n*Run ID:* `{run_id[:8]}`"
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

    if not results:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "✅ No new significant signals detected this week."
            }
        })
        blocks.append({"type": "divider"})
    else:
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
                "text": f"Powered by StratOS • Run: `{run_id[:8]}` • Next briefing in 7 days"
            }
        ]
    })

    return blocks


async def deliver_to_slack(blocks: List[Dict[str, Any]]) -> bool:
    """POST the blocks to the configured Slack webhook with retry logic."""
    if not settings.slack_webhook_url:
        logger.warning("⚠️ Slack delivery skipped: slack_webhook_url not set")
        return False

    # Use retry context for Slack delivery
    from stratos.retry import AsyncRetryContext
    
    try:
        async with AsyncRetryContext(
            max_attempts=3,
            min_wait=1.0,
            max_wait=10.0,
            operation_name="Slack delivery"
        ) as retry_ctx:
            async for _ in retry_ctx:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.post(
                            settings.slack_webhook_url,
                            json={"blocks": blocks}
                        )
                        
                        if response.status_code == 200:
                            logger.info("✅ Slack delivery successful")
                            retry_ctx.success(True)
                            return True
                        elif response.status_code == 429:
                            # Rate limited - retry with longer wait
                            logger.warning("Slack rate limit hit, will retry")
                            raise httpx.HTTPStatusError(
                                "Rate limited",
                                request=response.request,
                                response=response
                            )
                        else:
                            logger.error(f"❌ Slack delivery failed: {response.status_code} {response.text}")
                            # Don't retry on client errors (4xx except 429)
                            if 400 <= response.status_code < 500 and response.status_code != 429:
                                retry_ctx.success(False)
                                return False
                            raise httpx.HTTPStatusError(
                                f"Status {response.status_code}",
                                request=response.request,
                                response=response
                            )
                            
                except httpx.TimeoutException:
                    logger.warning("Slack delivery timeout, will retry")
                    retry_ctx.fail(httpx.TimeoutException("Timeout"))
                except httpx.HTTPStatusError as e:
                    if 500 <= e.response.status_code < 600:
                        # Server error - retry
                        logger.warning(f"Slack server error {e.response.status_code}, will retry")
                        retry_ctx.fail(e)
                    else:
                        # Client error - don't retry
                        logger.error(f"Slack client error: {e}")
                        retry_ctx.success(False)
                        return False
                except Exception as e:
                    logger.warning(f"Slack delivery error: {e}, will retry")
                    retry_ctx.fail(e)
                    
    except Exception as e:
        logger.error(f"❌ All Slack retry attempts failed: {e}", exc_info=True)
        return False
    
    return False


async def run_writer(strategist_results: List[Dict[str, Any]], run_id: str) -> bool:
    """
    Orchestrate block building, delivery, and run completion.
    
    Args:
        strategist_results: Results from the Strategist agent
        run_id: Current run ID
    
    Returns:
        bool: True if delivery succeeded, False otherwise
    """
    # Build Slack blocks
    blocks = build_slack_blocks(run_id, strategist_results)
    
    # Deliver to Slack
    success = await deliver_to_slack(blocks)
    
    # Update run status regardless of delivery success (as documented)
    try:
        async with get_db_session_manual() as session:
            run_repo = RunRepository(session)
            # Get current signal count from the run
            run = await run_repo.get_by_id(run_id)
            signal_count = run.signal_count if run else 0
            await run_repo.complete_run(run_id, signal_count)
            await session.commit()
        logger.info(f"✅ Run {run_id} marked as complete", extra={"run_id": run_id})
        
    except Exception as e:
        logger.error(f"⚠️ Error updating run status: {e}", extra={"run_id": run_id}, exc_info=True)
    
    return success


# Synchronous wrapper for backward compatibility
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
    
    logger.info("Testing Writer agent...")
    blocks = build_slack_blocks("test-run-123", sample_results)
    logger.info(f"✅ Built {len(blocks)} Slack blocks")
    
    # Test async delivery (will skip if no webhook)
    success = asyncio.run(deliver_to_slack(blocks))
    logger.info(f"✅ Delivery test completed: {'Success' if success else 'Failed (webhook not configured)'}")