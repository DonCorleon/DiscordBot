"""
Transcripts API endpoints for viewing voice transcriptions.
"""

import logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger("discordbot.web.transcripts")

router = APIRouter(prefix="/api/v1/transcripts", tags=["Transcripts"])


@router.get("/list")
async def list_transcripts(
    guild_id: Optional[str] = Query(None, description="Filter by guild ID"),
    channel_id: Optional[str] = Query(None, description="Filter by channel ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    search: Optional[str] = Query(None, description="Search in transcript text"),
    limit: int = Query(100, description="Maximum number of transcripts to return")
):
    """
    Get list of transcripts with optional filtering.

    Returns transcripts sorted by timestamp (newest first).
    """
    try:
        import json

        # Read transcriptions from admin data
        transcripts_file = Path("data/admin/transcriptions.json")

        if not transcripts_file.exists():
            return {
                "transcriptions": [],
                "count": 0,
                "message": "No transcriptions available yet"
            }

        with open(transcripts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            transcriptions = data.get("transcriptions", [])

        # Apply filters
        filtered = transcriptions

        if guild_id is not None:
            # Convert string to int for comparison with stored int IDs
            guild_id_int = int(guild_id)
            filtered = [t for t in filtered if t.get("guild_id") == guild_id_int]

        if channel_id is not None:
            # Convert string to int for comparison with stored int IDs
            channel_id_int = int(channel_id)
            filtered = [t for t in filtered if t.get("channel_id") == channel_id_int]

        if user_id is not None:
            filtered = [t for t in filtered if t.get("user_id") == user_id]

        if search:
            search_lower = search.lower()
            filtered = [
                t for t in filtered
                if search_lower in t.get("text", "").lower() or
                   search_lower in t.get("user", "").lower()
            ]

        # Sort by timestamp (newest first) and limit
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        filtered = filtered[:limit]

        # Convert IDs to strings for JavaScript compatibility
        for t in filtered:
            if "guild_id" in t:
                t["guild_id"] = str(t["guild_id"])
            if "channel_id" in t:
                t["channel_id"] = str(t["channel_id"])

        return {
            "transcriptions": filtered,
            "count": len(filtered),
            "total": len(transcriptions)
        }

    except Exception as e:
        logger.error(f"Error listing transcripts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds")
async def list_guilds():
    """
    Get list of guilds that have transcriptions.
    """
    try:
        import json

        transcripts_file = Path("data/admin/transcriptions.json")

        if not transcripts_file.exists():
            return {"guilds": []}

        with open(transcripts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            transcriptions = data.get("transcriptions", [])

        # Get unique guilds
        guilds_dict = {}
        for t in transcriptions:
            guild_id = t.get("guild_id")
            if guild_id and guild_id not in guilds_dict:
                guilds_dict[guild_id] = {
                    "guild_id": str(guild_id),  # Convert to string for JavaScript
                    "guild_name": t.get("guild", "Unknown")
                }

        return {"guilds": list(guilds_dict.values())}

    except Exception as e:
        logger.error(f"Error listing guilds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/channels")
async def list_channels(
    guild_id: str = Query(..., description="Guild ID to get channels for")
):
    """
    Get list of channels that have transcriptions for a specific guild.
    """
    try:
        import json

        transcripts_file = Path("data/admin/transcriptions.json")

        if not transcripts_file.exists():
            return {"channels": []}

        with open(transcripts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            transcriptions = data.get("transcriptions", [])

        # Convert string guild_id to int for comparison
        guild_id_int = int(guild_id)

        # Get unique channels for this guild
        channels_dict = {}
        for t in transcriptions:
            if t.get("guild_id") == guild_id_int:
                channel_id = t.get("channel_id")
                if channel_id and channel_id not in channels_dict:
                    channels_dict[channel_id] = {
                        "channel_id": str(channel_id),  # Convert to string for JavaScript
                        "channel_name": t.get("channel", "Unknown")
                    }

        return {"channels": list(channels_dict.values())}

    except Exception as e:
        logger.error(f"Error listing channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/all-channels")
async def list_all_channels():
    """
    Get list of all channels that have transcriptions across all guilds.
    Returns channels in "Guild:Channel" format.
    """
    try:
        import json

        transcripts_file = Path("data/admin/transcriptions.json")

        if not transcripts_file.exists():
            return {"channels": []}

        with open(transcripts_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            transcriptions = data.get("transcriptions", [])

        # Get unique channels across all guilds
        channels_dict = {}
        for t in transcriptions:
            channel_id = t.get("channel_id")
            if channel_id and channel_id not in channels_dict:
                channels_dict[channel_id] = {
                    "channel_id": str(channel_id),  # Convert to string for JavaScript
                    "channel_name": t.get("channel", "Unknown"),
                    "guild_id": str(t.get("guild_id")),  # Include guild_id
                    "guild_name": t.get("guild", "Unknown")
                }

        return {"channels": list(channels_dict.values())}

    except Exception as e:
        logger.error(f"Error listing all channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
