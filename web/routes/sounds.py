"""
Sound Management API endpoints for soundboard files.
"""

import logging
import json
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

logger = logging.getLogger("discordbot.web.sounds")

router = APIRouter(prefix="/api/v1/sounds", tags=["Sounds"])

# Paths
SOUNDBOARD_DIR = Path("data/soundboard")
SOUNDBOARD_CONFIG = Path("data/config/soundboard.json")

# Allowed file extensions
ALLOWED_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac"}


class SoundMetadata(BaseModel):
    """Sound metadata update model."""
    title: Optional[str] = None
    description: Optional[str] = None
    triggers: Optional[List[str]] = None
    volume_adjust: Optional[float] = None
    guild_id: Optional[str] = None
    is_disabled: Optional[bool] = None
    cooldown: Optional[int] = None


def _load_soundboard_config():
    """Load and parse soundboard.json"""
    if not SOUNDBOARD_CONFIG.exists():
        return {"sounds": {}}

    with open(SOUNDBOARD_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_soundboard_config(config_data):
    """Save soundboard.json"""
    with open(SOUNDBOARD_CONFIG, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2)


@router.get("/list")
async def list_sounds(
    search: Optional[str] = Query(None, description="Filter by title or filename"),
    guild_id: Optional[str] = Query(None, description="Filter by guild ID")
):
    """
    Get list of all soundboard sounds with metadata.

    Returns sounds with: id, title, triggers, play stats, volume, guild info
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        sounds = []
        for sound_id, sound_data in sounds_dict.items():
            # Apply guild filter
            if guild_id and sound_data.get("guild_id") != guild_id:
                continue

            # Apply search filter
            if search:
                search_lower = search.lower()
                title = sound_data.get("title", "").lower()
                filename = Path(sound_data.get("soundfile", "")).name.lower()
                if search_lower not in title and search_lower not in filename:
                    continue

            # Extract file path and check if file exists
            soundfile_path = Path(sound_data.get("soundfile", ""))
            file_exists = soundfile_path.exists()
            file_size = soundfile_path.stat().st_size if file_exists else 0

            # Get play stats
            play_stats = sound_data.get("play_stats", {})

            sounds.append({
                "id": sound_id,
                "title": sound_data.get("title", sound_id),
                "description": sound_data.get("description", ""),
                "triggers": sound_data.get("triggers", []),
                "filename": soundfile_path.name,
                "soundfile": str(soundfile_path),
                "file_exists": file_exists,
                "size": file_size,
                "size_formatted": _format_size(file_size),
                "play_count": play_stats.get("total", 0),
                "volume_adjust": sound_data.get("audio_metadata", {}).get("volume_adjust", 1.0),
                "guild_id": sound_data.get("guild_id", "default_guild"),
                "guild_name": _get_guild_name(sound_data.get("guild_id", "default_guild")),
                "is_disabled": sound_data.get("is_disabled", False),
                "is_private": sound_data.get("is_private", False),
                "cooldown": sound_data.get("settings", {}).get("cooldown", 0),
                "added_by": sound_data.get("added_by", "Unknown"),
                "added_date": sound_data.get("added_date", ""),
                "last_played": play_stats.get("last_played", "")
            })

        # Sort by title
        sounds.sort(key=lambda x: x["title"].lower())

        return {
            "sounds": sounds,
            "count": len(sounds),
            "total_size": sum(s["size"] for s in sounds),
            "total_size_formatted": _format_size(sum(s["size"] for s in sounds))
        }

    except Exception as e:
        logger.error(f"Error listing sounds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds")
async def list_guilds():
    """
    Get list of guilds that have sounds.
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        # Get unique guilds
        guilds_dict = {}
        for sound_data in sounds_dict.values():
            guild_id = sound_data.get("guild_id", "default_guild")
            if guild_id not in guilds_dict:
                guilds_dict[guild_id] = {
                    "guild_id": guild_id,
                    "guild_name": _get_guild_name(guild_id),
                    "sound_count": 0
                }
            guilds_dict[guild_id]["sound_count"] += 1

        return {"guilds": list(guilds_dict.values())}

    except Exception as e:
        logger.error(f"Error listing guilds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sound_id}")
async def get_sound(sound_id: str):
    """
    Get detailed information for a specific sound.
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        if sound_id not in sounds_dict:
            raise HTTPException(status_code=404, detail=f"Sound '{sound_id}' not found")

        sound_data = sounds_dict[sound_id]
        soundfile_path = Path(sound_data.get("soundfile", ""))
        file_exists = soundfile_path.exists()
        file_size = soundfile_path.stat().st_size if file_exists else 0

        play_stats = sound_data.get("play_stats", {})

        return {
            "id": sound_id,
            "title": sound_data.get("title", sound_id),
            "description": sound_data.get("description", ""),
            "triggers": sound_data.get("triggers", []),
            "filename": soundfile_path.name,
            "soundfile": str(soundfile_path),
            "file_exists": file_exists,
            "size": file_size,
            "size_formatted": _format_size(file_size),
            "play_count": play_stats.get("total", 0),
            "volume_adjust": sound_data.get("audio_metadata", {}).get("volume_adjust", 1.0),
            "guild_id": sound_data.get("guild_id", "default_guild"),
            "guild_name": _get_guild_name(sound_data.get("guild_id", "default_guild")),
            "is_disabled": sound_data.get("is_disabled", False),
            "is_private": sound_data.get("is_private", False),
            "cooldown": sound_data.get("settings", {}).get("cooldown", 0),
            "added_by": sound_data.get("added_by", "Unknown"),
            "added_date": sound_data.get("added_date", ""),
            "last_played": play_stats.get("last_played", ""),
            "guild_play_counts": play_stats.get("guild_play_count", {})
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sound: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_sound(
    file: UploadFile = File(...),
    title: str = Query(...),
    guild_id: str = Query("default_guild"),
    description: str = Query(""),
    triggers: str = Query("")  # Comma-separated
):
    """
    Upload a new sound file to the soundboard.

    Validates file extension and creates new sound entry in config.
    """
    try:
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Ensure soundboard directory exists
        SOUNDBOARD_DIR.mkdir(parents=True, exist_ok=True)

        # Save file
        target_path = SOUNDBOARD_DIR / file.filename
        if target_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"File '{file.filename}' already exists"
            )

        content = await file.read()
        with open(target_path, 'wb') as f:
            f.write(content)

        # Parse triggers
        trigger_list = [t.strip() for t in triggers.split(",") if t.strip()]

        # Create sound ID (sanitized title or filename)
        sound_id = title.lower().replace(" ", "_").replace("-", "_")
        if guild_id != "default_guild":
            sound_id = f"{guild_id}_{sound_id}"

        # Load config and add new sound
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        # Check if ID already exists
        if sound_id in sounds_dict:
            # Append number to make unique
            counter = 1
            while f"{sound_id}_{counter}" in sounds_dict:
                counter += 1
            sound_id = f"{sound_id}_{counter}"

        sounds_dict[sound_id] = {
            "title": title,
            "triggers": trigger_list,
            "soundfile": str(target_path),
            "description": description,
            "added_by": "Web Admin",
            "added_by_id": "0",
            "added_date": "2025-01-01T00:00:00",
            "guild_id": guild_id,
            "last_edited_by": None,
            "last_edited_date": None,
            "is_private": False,
            "is_disabled": False,
            "approved": True,
            "play_stats": {
                "week": 0,
                "month": 0,
                "total": 0,
                "guild_play_count": {},
                "trigger_word_stats": {},
                "last_played": None,
                "played_by": []
            },
            "audio_metadata": {
                "duration": None,
                "volume_adjust": 1.0
            },
            "settings": {
                "cooldown": 0,
                "autoplay": False
            }
        }

        config_data["sounds"] = sounds_dict
        _save_soundboard_config(config_data)

        logger.info(f"Uploaded sound: {sound_id} ({file.filename})")

        return {
            "success": True,
            "sound_id": sound_id,
            "filename": file.filename,
            "size": len(content),
            "message": f"Successfully uploaded {title}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading sound: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{sound_id}")
async def delete_sound(sound_id: str):
    """
    Delete a sound from the soundboard.

    Removes both the file and its config entry.
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        if sound_id not in sounds_dict:
            raise HTTPException(status_code=404, detail=f"Sound '{sound_id}' not found")

        sound_data = sounds_dict[sound_id]
        soundfile_path = Path(sound_data.get("soundfile", ""))

        # Delete file if it exists
        if soundfile_path.exists():
            soundfile_path.unlink()
            logger.info(f"Deleted sound file: {soundfile_path}")

        # Remove from config
        del sounds_dict[sound_id]
        config_data["sounds"] = sounds_dict
        _save_soundboard_config(config_data)

        return {
            "success": True,
            "sound_id": sound_id,
            "message": f"Successfully deleted {sound_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sound: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{sound_id}")
async def update_sound_metadata(sound_id: str, metadata: SoundMetadata):
    """
    Update sound metadata.
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        if sound_id not in sounds_dict:
            raise HTTPException(status_code=404, detail=f"Sound '{sound_id}' not found")

        sound_data = sounds_dict[sound_id]

        # Update metadata fields
        if metadata.title is not None:
            sound_data["title"] = metadata.title

        if metadata.description is not None:
            sound_data["description"] = metadata.description

        if metadata.triggers is not None:
            sound_data["triggers"] = metadata.triggers

        if metadata.volume_adjust is not None:
            if not 0.0 <= metadata.volume_adjust <= 2.0:
                raise HTTPException(status_code=400, detail="Volume must be between 0.0 and 2.0")
            if "audio_metadata" not in sound_data:
                sound_data["audio_metadata"] = {}
            sound_data["audio_metadata"]["volume_adjust"] = metadata.volume_adjust

        if metadata.guild_id is not None:
            sound_data["guild_id"] = metadata.guild_id

        if metadata.is_disabled is not None:
            sound_data["is_disabled"] = metadata.is_disabled

        if metadata.cooldown is not None:
            if "settings" not in sound_data:
                sound_data["settings"] = {}
            sound_data["settings"]["cooldown"] = metadata.cooldown

        # Update last edited info
        sound_data["last_edited_by"] = "Web Admin"
        from datetime import datetime
        sound_data["last_edited_date"] = datetime.now().isoformat()

        # Save config
        sounds_dict[sound_id] = sound_data
        config_data["sounds"] = sounds_dict
        _save_soundboard_config(config_data)

        logger.info(f"Updated metadata for {sound_id}")

        return {
            "success": True,
            "sound_id": sound_id,
            "message": f"Successfully updated {sound_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating sound metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/play/{sound_id}")
async def play_sound(sound_id: str):
    """
    Stream a sound file for preview in browser.

    Returns the audio file with appropriate Content-Type header.
    """
    try:
        config_data = _load_soundboard_config()
        sounds_dict = config_data.get("sounds", {})

        if sound_id not in sounds_dict:
            raise HTTPException(status_code=404, detail=f"Sound '{sound_id}' not found")

        sound_data = sounds_dict[sound_id]
        soundfile_path = Path(sound_data.get("soundfile", ""))

        if not soundfile_path.exists():
            raise HTTPException(status_code=404, detail=f"Sound file not found: {soundfile_path.name}")

        # Determine media type
        ext = soundfile_path.suffix.lower()
        media_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac"
        }
        media_type = media_types.get(ext, "application/octet-stream")

        return FileResponse(
            path=soundfile_path,
            media_type=media_type,
            filename=soundfile_path.name
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving sound file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def _get_guild_name(guild_id: str) -> str:
    """Get guild name from ID (placeholder - could fetch from bot)."""
    guild_names = {
        "default_guild": "Global",
        "1410579846379081801": "Soundboards",
        "1386497411278573652": "The Ranch"
    }
    return guild_names.get(guild_id, guild_id)
