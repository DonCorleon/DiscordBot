"""
WebSocket endpoint for real-time dashboard updates.
Handles WebSocket connections and message passing.
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from web.websocket_manager import manager

logger = logging.getLogger("discordbot.web.websocket")

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Protocol:
        - On connect: Sends "init" message with current cached data
        - While connected: Receives "update" messages every 2 seconds
        - Can receive event messages: "command", "message", etc.

    Message format:
        {
            "type": "init|update|command|message|log",
            "data": {...},
            "timestamp": "ISO8601"
        }
    """
    await manager.connect(websocket)

    try:
        # Send initial data
        await manager.send_personal({
            "type": "init",
            "data": manager.data_cache
        }, websocket)

        # Keep connection alive and handle incoming messages
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()

            # Handle client requests here
            # For now, we just log them
            logger.debug(f"Received from client: {data}")

            # You could implement commands like:
            # - "ping" -> respond with "pong"
            # - "refresh" -> send latest data
            # - etc.

    except WebSocketDisconnect:
        logger.info("Client disconnected normally")
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)
