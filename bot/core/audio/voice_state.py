"""
Persistent voice channel state management.
Tracks which voice channels the bot was in when it shut down,
and automatically rejoins them on startup if users are present.
"""
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from bot.base_cog import logger

VOICE_STATE_FILE = "data/config/voice_state.json"


def save_voice_state(guild_id: int, channel_id: int, session_id: str = None, file_path: str = VOICE_STATE_FILE):
    """
    Save the bot's current voice channel state.

    Args:
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        session_id: Optional transcript session ID (for resume on restart)
        file_path: Path to state file
    """
    try:
        # Load existing state
        state = load_voice_state(file_path)

        # Update state
        guild_id_str = str(guild_id)
        state[guild_id_str] = {
            "channel_id": str(channel_id),
            "last_joined": datetime.now().isoformat(),
            "session_id": session_id  # Store session ID for resume
        }

        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        # Save state
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)

        logger.debug(f"Saved voice state: guild={guild_id}, channel={channel_id}")

    except Exception as e:
        logger.error(f"Failed to save voice state: {e}")


def remove_voice_state(guild_id: int, file_path: str = VOICE_STATE_FILE):
    """
    Remove voice state for a guild (bot left the channel).

    Args:
        guild_id: Discord guild ID
        file_path: Path to state file
    """
    try:
        state = load_voice_state(file_path)
        guild_id_str = str(guild_id)

        if guild_id_str in state:
            del state[guild_id_str]

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2)

            logger.debug(f"Removed voice state for guild {guild_id}")

    except Exception as e:
        logger.error(f"Failed to remove voice state: {e}")


def load_voice_state(file_path: str = VOICE_STATE_FILE) -> Dict[str, Dict[str, str]]:
    """
    Load voice channel state from file.

    Returns:
        Dict mapping guild_id to channel state
        Format: {guild_id: {"channel_id": str, "last_joined": str}}
    """
    path = Path(file_path)

    if not path.exists():
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load voice state: {e}")
        return {}


def get_voice_state(guild_id: int, file_path: str = VOICE_STATE_FILE) -> Optional[Dict[str, str]]:
    """
    Get the saved voice state for a guild.

    Args:
        guild_id: Discord guild ID
        file_path: Path to state file

    Returns:
        Dict with {"channel_id": str, "last_joined": str, "session_id": str} if found, None otherwise
    """
    state = load_voice_state(file_path)
    guild_id_str = str(guild_id)

    if guild_id_str in state:
        return state[guild_id_str]

    return None


def clear_voice_state(file_path: str = VOICE_STATE_FILE):
    """
    Clear all voice state (useful for testing or cleanup).

    Args:
        file_path: Path to state file
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)

        logger.info("Cleared all voice state")

    except Exception as e:
        logger.error(f"Failed to clear voice state: {e}")
