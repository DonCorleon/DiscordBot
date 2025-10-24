"""
Sound Management API endpoints for soundboard files.
"""

import logging
import json
from pathlib import Path
from typing import Optional
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
    volume: Optional[float] = None


@router.get("/list")
async def list_sounds(
    search: Optional[str] = Query(None, description="Filter by filename")
):
    """
    Get list of all soundboard files with metadata.

    Returns sound files with: filename, size, play_count, volume
    """
    try:
        # Load soundboard config for metadata
        config_data = {}
        if SOUNDBOARD_CONFIG.exists():
            with open(SOUNDBOARD_CONFIG, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        sounds = []

        if SOUNDBOARD_DIR.exists():
            for sound_file in SOUNDBOARD_DIR.iterdir():
                if sound_file.is_file() and sound_file.suffix.lower() in ALLOWED_EXTENSIONS:
                    filename = sound_file.name

                    # Apply search filter
                    if search and search.lower() not in filename.lower():
                        continue

                    # Get metadata from config
                    file_config = config_data.get(filename, {})

                    sounds.append({
                        "filename": filename,
                        "size": sound_file.stat().st_size,
                        "size_formatted": _format_size(sound_file.stat().st_size),
                        "play_count": file_config.get("play_count", 0),
                        "volume": file_config.get("volume", 1.0),
                        "extension": sound_file.suffix.lower()
                    })

        # Sort by filename
        sounds.sort(key=lambda x: x["filename"].lower())

        return {
            "sounds": sounds,
            "count": len(sounds),
            "total_size": sum(s["size"] for s in sounds),
            "total_size_formatted": _format_size(sum(s["size"] for s in sounds))
        }

    except Exception as e:
        logger.error(f"Error listing sounds: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_sound(file: UploadFile = File(...)):
    """
    Upload a new sound file to the soundboard.

    Validates file extension and saves to soundboard directory.
    """
    try:
        # Validate file extension
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            )

        # Check if file already exists
        target_path = SOUNDBOARD_DIR / file.filename
        if target_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f"File '{file.filename}' already exists"
            )

        # Ensure soundboard directory exists
        SOUNDBOARD_DIR.mkdir(parents=True, exist_ok=True)

        # Save file
        content = await file.read()
        with open(target_path, 'wb') as f:
            f.write(content)

        logger.info(f"Uploaded sound file: {file.filename} ({len(content)} bytes)")

        # Add to config with default values
        config_data = {}
        if SOUNDBOARD_CONFIG.exists():
            with open(SOUNDBOARD_CONFIG, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        config_data[file.filename] = {
            "play_count": 0,
            "volume": 1.0
        }

        with open(SOUNDBOARD_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)

        return {
            "success": True,
            "filename": file.filename,
            "size": len(content),
            "message": f"Successfully uploaded {file.filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading sound: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{filename}")
async def delete_sound(filename: str):
    """
    Delete a sound file from the soundboard.

    Removes both the file and its config entry.
    """
    try:
        # Security: Prevent path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        target_path = SOUNDBOARD_DIR / filename

        # Check if file exists
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Delete file
        target_path.unlink()
        logger.info(f"Deleted sound file: {filename}")

        # Remove from config
        if SOUNDBOARD_CONFIG.exists():
            with open(SOUNDBOARD_CONFIG, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            if filename in config_data:
                del config_data[filename]

                with open(SOUNDBOARD_CONFIG, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2)

        return {
            "success": True,
            "filename": filename,
            "message": f"Successfully deleted {filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting sound: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{filename}")
async def update_sound_metadata(filename: str, metadata: SoundMetadata):
    """
    Update sound file metadata (volume, etc).
    """
    try:
        # Security: Prevent path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        target_path = SOUNDBOARD_DIR / filename

        # Check if file exists
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Load config
        config_data = {}
        if SOUNDBOARD_CONFIG.exists():
            with open(SOUNDBOARD_CONFIG, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        # Ensure file has config entry
        if filename not in config_data:
            config_data[filename] = {"play_count": 0, "volume": 1.0}

        # Update metadata
        if metadata.volume is not None:
            if not 0.0 <= metadata.volume <= 2.0:
                raise HTTPException(status_code=400, detail="Volume must be between 0.0 and 2.0")
            config_data[filename]["volume"] = metadata.volume

        # Save config
        with open(SOUNDBOARD_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Updated metadata for {filename}: {metadata.dict(exclude_none=True)}")

        return {
            "success": True,
            "filename": filename,
            "metadata": config_data[filename],
            "message": f"Successfully updated {filename}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating sound metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/play/{filename}")
async def play_sound(filename: str):
    """
    Stream a sound file for preview in browser.

    Returns the audio file with appropriate Content-Type header.
    """
    try:
        # Security: Prevent path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")

        target_path = SOUNDBOARD_DIR / filename

        # Check if file exists
        if not target_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found")

        # Determine media type
        ext = target_path.suffix.lower()
        media_types = {
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".ogg": "audio/ogg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac"
        }
        media_type = media_types.get(ext, "application/octet-stream")

        return FileResponse(
            path=target_path,
            media_type=media_type,
            filename=filename
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
