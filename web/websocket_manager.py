"""
WebSocket connection manager for real-time dashboard updates.
Manages active WebSocket connections and broadcasts data to all connected clients.
"""

import logging
from typing import List, Dict, Any
from fastapi import WebSocket
from datetime import datetime

logger = logging.getLogger("discordbot.web.websocket")


class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.data_cache: Dict[str, Any] = {}
        logger.info("WebSocket connection manager initialized")

    async def connect(self, websocket: WebSocket):
        """Accept and store a new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New WebSocket connection (total: {len(self.active_connections)})")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket disconnected (remaining: {len(self.active_connections)})")

    async def broadcast(self, message: Dict[str, Any]):
        """
        Send message to all connected clients.
        Automatically removes disconnected clients.
        """
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            if conn in self.active_connections:
                self.active_connections.remove(conn)

        if disconnected:
            logger.info(f"Cleaned up {len(disconnected)} disconnected clients")

    async def send_personal(self, message: Dict[str, Any], websocket: WebSocket):
        """Send message to a specific client."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            # Remove from active connections if send failed
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    def update_cache(self, data: Dict[str, Any]):
        """Update cached data for new connections."""
        self.data_cache = data

    def get_connection_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)


# Global connection manager instance
manager = ConnectionManager()
