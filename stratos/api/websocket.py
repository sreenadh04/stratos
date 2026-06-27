# stratos/api/websocket.py
"""
WebSocket handling for real-time pipeline progress.
"""
import asyncio
import json
from typing import Dict, Any
from fastapi import WebSocket, WebSocketDisconnect
from stratos.logging_config import get_logger

logger = get_logger("websocket")

# Global store of active run progress queues
_run_queues: Dict[str, asyncio.Queue] = {}

# Maximum number of messages to keep in queue
MAX_QUEUE_SIZE = 100


def get_progress_queue(run_id: str) -> asyncio.Queue:
    """Get or create a progress queue for a run."""
    if run_id not in _run_queues:
        _run_queues[run_id] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    return _run_queues[run_id]


async def push_progress(run_id: str, message: Dict[str, Any]) -> None:
    """
    Push a progress message to a run's queue.
    Called from the orchestrator during pipeline execution.
    """
    logger.info(f"📤 PUSHING PROGRESS to run {run_id}: {message}")
    queue = get_progress_queue(run_id)
    try:
        await queue.put(message)
    except asyncio.QueueFull:
        logger.warning(f"Progress queue full for run {run_id}, dropping message")


def cleanup_queue(run_id: str) -> None:
    """Clean up queue after run completes."""
    if run_id in _run_queues:
        del _run_queues[run_id]


async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time progress updates.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for run {run_id}")
    
    queue = get_progress_queue(run_id)
    
    try:
        while True:
            # Wait for a progress message from the queue
            try:
                message = await asyncio.wait_for(queue.get(), timeout=30.0)
                logger.info(f"📤 SENDING to WebSocket: {message}")
                await websocket.send_text(json.dumps(message))
            except asyncio.TimeoutError:
                # Send a heartbeat to keep connection alive
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
                continue
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for run {run_id}")
    finally:
        cleanup_queue(run_id)