"""
Auto-join channel management utilities.
Manages which voice channels the bot should automatically join.
"""
import json
from pathlib import Path
from typing import Dict, Set
from base_cog import logger

AUTO_JOIN_FILE = "auto_join_channels.json"


def load_auto_join_channels(file_path: str = AUTO_JOIN_FILE) -> Dict[str, Set[str]]:
    """
    Load auto-join channel configuration.

    Returns:
        Dict mapping guild_id to set of channel_ids that should auto-join
        Format: {guild_id: {channel_id1, channel_id2, ...}}
    """
    path = Path(file_path)

    if not path.exists():
        logger.info(f"Auto-join file not found, creating new: {file_path}")
        return {}

    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Convert lists back to sets
            return {guild_id: set(channels) for guild_id, channels in data.items()}
    except Exception as e:
        logger.error(f"Failed to load auto-join channels: {e}")
        return {}


def save_auto_join_channels(channels: Dict[str, Set[str]], file_path: str = AUTO_JOIN_FILE):
    """
    Save auto-join channel configuration.

    Args:
        channels: Dict mapping guild_id to set of channel_ids
        file_path: Path to save file
    """
    try:
        # Convert sets to lists for JSON serialization
        data = {guild_id: list(channel_set) for guild_id, channel_set in channels.items()}

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        logger.debug(f"Saved auto-join channels to {file_path}")
    except Exception as e:
        logger.error(f"Failed to save auto-join channels: {e}")


def add_auto_join_channel(guild_id: int, channel_id: int, file_path: str = AUTO_JOIN_FILE) -> bool:
    """
    Enable auto-join for a specific channel.

    Args:
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        file_path: Path to auto-join file

    Returns:
        True if added, False if already enabled
    """
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    channels = load_auto_join_channels(file_path)

    if guild_id_str not in channels:
        channels[guild_id_str] = set()

    if channel_id_str in channels[guild_id_str]:
        return False  # Already enabled

    channels[guild_id_str].add(channel_id_str)
    save_auto_join_channels(channels, file_path)

    logger.info(f"Enabled auto-join for channel {channel_id} in guild {guild_id}")
    return True


def remove_auto_join_channel(guild_id: int, channel_id: int, file_path: str = AUTO_JOIN_FILE) -> bool:
    """
    Disable auto-join for a specific channel.

    Args:
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        file_path: Path to auto-join file

    Returns:
        True if removed, False if wasn't enabled
    """
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    channels = load_auto_join_channels(file_path)

    if guild_id_str not in channels or channel_id_str not in channels[guild_id_str]:
        return False  # Wasn't enabled

    channels[guild_id_str].remove(channel_id_str)

    # Clean up empty guild entries
    if not channels[guild_id_str]:
        del channels[guild_id_str]

    save_auto_join_channels(channels, file_path)

    logger.info(f"Disabled auto-join for channel {channel_id} in guild {guild_id}")
    return True


def is_auto_join_channel(guild_id: int, channel_id: int, file_path: str = AUTO_JOIN_FILE) -> bool:
    """
    Check if a channel has auto-join enabled.

    Args:
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        file_path: Path to auto-join file

    Returns:
        True if auto-join is enabled for this channel
    """
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    channels = load_auto_join_channels(file_path)

    return guild_id_str in channels and channel_id_str in channels[guild_id_str]


def get_guild_auto_join_channels(guild_id: int, file_path: str = AUTO_JOIN_FILE) -> Set[str]:
    """
    Get all auto-join channels for a specific guild.

    Args:
        guild_id: Discord guild ID
        file_path: Path to auto-join file

    Returns:
        Set of channel IDs (as strings) with auto-join enabled
    """
    guild_id_str = str(guild_id)
    channels = load_auto_join_channels(file_path)

    return channels.get(guild_id_str, set())
