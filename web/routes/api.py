"""
REST API endpoints for the Discord bot dashboard.
Provides health checks and statistics access.
"""

import logging
from fastapi import APIRouter
from web.websocket_manager import manager

logger = logging.getLogger("discordbot.web.api")

router = APIRouter(prefix="/api/v1", tags=["API"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint.
    Returns server status and connection information.
    """
    return {
        "status": "healthy",
        "service": "discord-bot-dashboard",
        "websocket_connections": manager.get_connection_count(),
        "data_available": bool(manager.data_cache)
    }


@router.get("/stats")
async def get_stats():
    """
    Get current bot statistics.
    Returns cached data from admin_data/ directory.
    """
    if not manager.data_cache:
        return {
            "error": "No data available yet",
            "message": "Bot may still be starting up or data collection is disabled"
        }

    return {
        "success": True,
        "data": manager.data_cache
    }


@router.get("/connections")
async def get_connections():
    """
    Get current WebSocket connection count.
    Useful for monitoring dashboard usage.
    """
    return {
        "active_connections": manager.get_connection_count(),
        "data_cache_keys": list(manager.data_cache.keys()) if manager.data_cache else []
    }
