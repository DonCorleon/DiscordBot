"""
Transcripts API endpoints for viewing voice transcriptions.
"""

import logging
import json
from pathlib import Path
from typing import Optional, List
from datetime import datetime
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


@router.get("/history/guilds")
async def list_historical_guilds():
    """
    Get list of guilds that have historical transcript sessions.
    """
    try:
        transcripts_dir = Path("data/transcripts/sessions")

        if not transcripts_dir.exists():
            return {"guilds": []}

        guilds_dict = {}

        # Walk through guild directories
        for guild_dir in transcripts_dir.iterdir():
            if not guild_dir.is_dir():
                continue

            guild_id = guild_dir.name

            # Read first session file to get guild name
            for channel_dir in guild_dir.iterdir():
                if not channel_dir.is_dir():
                    continue

                for session_file in channel_dir.glob("*.json"):
                    try:
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_data = json.load(f)

                        if guild_id not in guilds_dict:
                            guilds_dict[guild_id] = {
                                "guild_id": session_data.get("guild_id"),
                                "guild_name": session_data.get("guild_name", "Unknown")
                            }
                            break  # Got guild info, move to next guild

                    except Exception as e:
                        logger.warning(f"Failed to read session file {session_file}: {e}")
                        continue

                if guild_id in guilds_dict:
                    break  # Got guild info, move to next guild

        return {"guilds": list(guilds_dict.values())}

    except Exception as e:
        logger.error(f"Error listing historical guilds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/channels")
async def list_historical_channels(
    guild_id: Optional[str] = Query(None, description="Guild ID to get channels for")
):
    """
    Get list of channels that have historical transcript sessions.
    If guild_id is provided, returns channels for that guild.
    Otherwise returns all channels across all guilds.
    """
    try:
        transcripts_dir = Path("data/transcripts/sessions")

        if not transcripts_dir.exists():
            return {"channels": []}

        channels_dict = {}

        # Walk through directory structure
        for guild_dir in transcripts_dir.iterdir():
            if not guild_dir.is_dir():
                continue

            # Filter by guild if specified
            if guild_id and guild_dir.name != guild_id:
                continue

            for channel_dir in guild_dir.iterdir():
                if not channel_dir.is_dir():
                    continue

                channel_id = channel_dir.name

                # Read first session file to get channel name
                for session_file in channel_dir.glob("*.json"):
                    try:
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_data = json.load(f)

                        if channel_id not in channels_dict:
                            channels_dict[channel_id] = {
                                "channel_id": session_data.get("channel_id"),
                                "channel_name": session_data.get("channel_name", "Unknown"),
                                "guild_id": session_data.get("guild_id"),
                                "guild_name": session_data.get("guild_name", "Unknown")
                            }
                            break  # Got channel info, move to next channel

                    except Exception as e:
                        logger.warning(f"Failed to read session file {session_file}: {e}")
                        continue

        return {"channels": list(channels_dict.values())}

    except Exception as e:
        logger.error(f"Error listing historical channels: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/sessions")
async def list_historical_sessions(
    guild_id: Optional[str] = Query(None, description="Filter by guild ID"),
    channel_id: Optional[str] = Query(None, description="Filter by channel ID")
):
    """
    Get list of historical transcript sessions.

    Returns sessions sorted by start time (newest first).
    Each session includes: session_id, guild info, channel info, start/end times, duration, participant count, message count.
    """
    try:
        # Get transcripts directory from config (use default for now)
        transcripts_dir = Path("data/transcripts/sessions")

        if not transcripts_dir.exists():
            return {
                "sessions": [],
                "count": 0,
                "message": "No historical sessions available yet"
            }

        sessions = []

        # Walk through guild_id/channel_id directory structure
        for guild_dir in transcripts_dir.iterdir():
            if not guild_dir.is_dir():
                continue

            # Filter by guild if specified
            if guild_id and guild_dir.name != guild_id:
                continue

            for channel_dir in guild_dir.iterdir():
                if not channel_dir.is_dir():
                    continue

                # Filter by channel if specified
                if channel_id and channel_dir.name != channel_id:
                    continue

                # Read all session files in this channel
                for session_file in channel_dir.glob("*.json"):
                    try:
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_data = json.load(f)

                        # Extract summary info
                        stats = session_data.get("stats", {})
                        sessions.append({
                            "session_id": session_data.get("session_id"),
                            "guild_id": session_data.get("guild_id"),
                            "guild_name": session_data.get("guild_name"),
                            "channel_id": session_data.get("channel_id"),
                            "channel_name": session_data.get("channel_name"),
                            "start_time": session_data.get("start_time"),
                            "end_time": session_data.get("end_time"),
                            "duration_seconds": stats.get("duration_seconds"),
                            "total_messages": stats.get("total_messages", 0),
                            "unique_speakers": stats.get("unique_speakers", 0),
                            "file_path": str(session_file)
                        })

                    except Exception as e:
                        logger.warning(f"Failed to read session file {session_file}: {e}")
                        continue

        # Sort by start_time (newest first)
        sessions.sort(key=lambda x: x.get("start_time", ""), reverse=True)

        return {
            "sessions": sessions,
            "count": len(sessions)
        }

    except Exception as e:
        logger.error(f"Error listing historical sessions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/session/{session_id}")
async def get_historical_session(session_id: str):
    """
    Get full transcript data for a specific historical session.

    Returns complete session data including all transcript entries and participant events.
    """
    try:
        # Get transcripts directory
        transcripts_dir = Path("data/transcripts/sessions")

        if not transcripts_dir.exists():
            raise HTTPException(status_code=404, detail="No historical sessions available")

        # Search for the session file (it's in guild_id/channel_id/filename format)
        for session_file in transcripts_dir.glob(f"**/*_{session_id}.json"):
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                return {
                    "session": session_data,
                    "success": True
                }

            except Exception as e:
                logger.error(f"Failed to read session file {session_file}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to read session: {e}")

        # Session not found
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading historical session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
