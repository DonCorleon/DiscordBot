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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from web.websocket_manager import manager
from web.routes import api, websocket, logs, transcripts, sounds

# Configure logger
logger = logging.getLogger("discordbot.web.app")

# Create FastAPI app
app = FastAPI(
    title="Discord Bot Admin Dashboard",
    description="Real-time monitoring and administration for Discord bot",
    version="0.1.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Templates
templates = Jinja2Templates(directory="web/templates")

# Include routers
app.include_router(api.router)
app.include_router(websocket.router)
app.include_router(logs.router)
app.include_router(transcripts.router)
app.include_router(sounds.router)

# Background task reference
data_pusher_task: Optional[asyncio.Task] = None


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """
    Main dashboard page with real-time updates.
    """
    return templates.TemplateResponse("dashboard.html", {"request": request, "active_page": "dashboard"})


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """
    Logs viewer page with filtering and search.
    """
    return templates.TemplateResponse("logs.html", {"request": request, "active_page": "logs"})


@app.get("/transcripts", response_class=HTMLResponse)
async def transcripts_page(request: Request):
    """
    Voice transcriptions viewer page with real-time updates.
    """
    return templates.TemplateResponse("transcripts.html", {"request": request, "active_page": "transcripts"})


@app.get("/sounds", response_class=HTMLResponse)
async def sounds_page(request: Request):
    """
    Sound management page for uploading, editing, and deleting soundboard files.
    """
    return templates.TemplateResponse("sounds.html", {"request": request, "active_page": "sounds"})


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
