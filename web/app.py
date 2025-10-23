"""
FastAPI application for Discord bot web dashboard.
Provides REST API and WebSocket endpoints for real-time monitoring.
"""

import asyncio
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from web.websocket_manager import manager
from web.routes import api, websocket

# Configure logger
logger = logging.getLogger("discordbot.web.app")

# Create FastAPI app
app = FastAPI(
    title="Discord Bot Admin Dashboard",
    description="Real-time monitoring and administration for Discord bot",
    version="0.1.0"
)

# Include routers
app.include_router(api.router)
app.include_router(websocket.router)

# Background task reference
data_pusher_task: Optional[asyncio.Task] = None


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Simple status page showing the web server is running.
    Frontend dashboard will be added in Phase 4.
    """
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Discord Bot Dashboard</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: #1a1a1a;
                color: #e0e0e0;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
            }
            .container {
                text-align: center;
                background: #2d2d2d;
                padding: 3rem;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }
            h1 {
                color: #5865F2;
                margin: 0 0 1rem 0;
            }
            p {
                color: #b0b0b0;
                margin: 0.5rem 0;
            }
            .status {
                display: inline-block;
                padding: 0.5rem 1rem;
                background: #43b581;
                color: white;
                border-radius: 6px;
                margin-top: 1rem;
                font-weight: bold;
            }
            a {
                color: #5865F2;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Discord Bot Dashboard</h1>
            <div class="status">✅ Web Server Running</div>
            <p style="margin-top: 2rem;">Backend is operational (Phase 1-3 complete)</p>
            <p>Frontend dashboard coming in Phase 4</p>
            <p style="margin-top: 2rem;">
                <a href="/api/v1/health">Health Check</a> |
                <a href="/api/v1/stats">Statistics</a> |
                <a href="/docs">API Docs</a>
            </p>
        </div>
    </body>
    </html>
    """


async def data_pusher():
    """
    Background task that reads admin_data/*.json files and pushes updates to WebSocket clients.
    Runs every 2 seconds for near real-time updates.
    """
    admin_data_dir = Path("data/admin")
    logger.info("Data pusher task started")

    while True:
        try:
            # Read all JSON files from admin_data/
            data = {}

            if admin_data_dir.exists():
                for json_file in admin_data_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            file_data = json.load(f)
                            data[json_file.stem] = file_data
                    except Exception as e:
                        logger.error(f"Error reading {json_file}: {e}")

            # Update cache
            manager.update_cache(data)

            # Broadcast to all connected clients
            if manager.get_connection_count() > 0:
                await manager.broadcast({
                    "type": "update",
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                })

            # Wait before next update (2 seconds for near real-time)
            await asyncio.sleep(2)

        except asyncio.CancelledError:
            logger.info("Data pusher task cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in data_pusher: {e}", exc_info=True)
            await asyncio.sleep(5)  # Wait longer on error


@app.on_event("startup")
async def startup_event():
    """Start background tasks when app starts."""
    global data_pusher_task
    logger.info("Starting web dashboard background tasks")
    data_pusher_task = asyncio.create_task(data_pusher())


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup background tasks when app shuts down."""
    global data_pusher_task
    logger.info("Shutting down web dashboard")

    if data_pusher_task and not data_pusher_task.done():
        data_pusher_task.cancel()
        try:
            await data_pusher_task
        except asyncio.CancelledError:
            pass


async def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """
    Run the web server.

    Args:
        host: Host to bind to (0.0.0.0 for all interfaces, 127.0.0.1 for local only)
        port: Port to listen on
        reload: Enable auto-reload on code changes (development only)
    """
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    # For standalone testing
    logger.info("Starting web dashboard in standalone mode")
    asyncio.run(run_server())
