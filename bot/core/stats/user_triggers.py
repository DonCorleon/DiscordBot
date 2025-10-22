"""
User statistics tracking for trigger word usage.
Tracks how many times users say trigger words, with guild and channel specificity.
Guilds are completely isolated - stats are tracked per guild.
"""
import json
from dataclasses import dataclass, field, asdict
from typing import Dict
from datetime import datetime
from pathlib import Path
from bot.base_cog import logger

USER_STATS_FILE = "data/stats/user_stats.json"


@dataclass
class UserTriggerStats:
    """Statistics for a user's trigger word usage within a single guild."""
    week: int = 0
    month: int = 0
    total: int = 0
    # Track per channel: {channel_id: count}
    channel_stats: Dict[str, int] = field(default_factory=dict)
    # Track trigger words used: {trigger_word: count}
    trigger_words: Dict[str, int] = field(default_factory=dict)
    last_triggered: str = None  # ISO format timestamp


@dataclass
class UserStats:
    """
    All statistics for a single user within a guild.

    Structure:
    {
        "user_id": "123456789",
        "username": "John#1234",
        "trigger_stats": UserTriggerStats
    }
    """
    user_id: str
    username: str
    trigger_stats: UserTriggerStats = field(default_factory=UserTriggerStats)


@dataclass
class GuildUserStats:
    """Container for all user statistics within a single guild."""
    users: Dict[str, UserStats] = field(default_factory=dict)  # {user_id: UserStats}


@dataclass
class UserStatsData:
    """Container for all guild statistics. Guilds are completely isolated."""
    guilds: Dict[str, GuildUserStats] = field(default_factory=dict)  # {guild_id: GuildUserStats}


def load_user_stats(file_path: str = USER_STATS_FILE) -> UserStatsData:
    """Load user stats from JSON file."""
    logger.info(f"Loading user stats from '{file_path}'...")

    try:
        if not Path(file_path).exists():
            logger.info(f"User stats file not found, creating new one: {file_path}")
            return UserStatsData()

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        guilds = {}
        total_users = 0

        for guild_id, guild_data in data.get("guilds", {}).items():
            try:
                users = {}
                for user_id, user_data in guild_data.get("users", {}).items():
                    try:
                        # Convert trigger_stats dict to UserTriggerStats object
                        if "trigger_stats" in user_data and isinstance(user_data["trigger_stats"], dict):
                            user_data["trigger_stats"] = UserTriggerStats(**user_data["trigger_stats"])

                        users[user_id] = UserStats(**user_data)
                        total_users += 1
                    except Exception as e:
                        logger.error(f"Failed to load stats for user {user_id} in guild {guild_id}: {e}")

                guilds[guild_id] = GuildUserStats(users=users)
            except Exception as e:
                logger.error(f"Failed to load stats for guild {guild_id}: {e}")

        logger.info(f"Successfully loaded stats for {total_users} user(s) across {len(guilds)} guild(s)")
        return UserStatsData(guilds=guilds)

    except Exception as e:
        logger.error(f"Error loading user stats: {e}", exc_info=True)
        raise


def save_user_stats(file_path: str, user_stats: UserStatsData):
    """Save user stats to JSON file."""
    logger.debug(f"Saving user stats to '{file_path}'...")

    try:
        # Create backup if file exists
        # Create parent directories if needed
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        if Path(file_path).exists():
            import shutil
            shutil.copy2(file_path, f"{file_path}.backup")

        data = {"guilds": {k: asdict(v) for k, v in user_stats.guilds.items()}}

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        total_users = sum(len(guild.users) for guild in user_stats.guilds.values())
        logger.debug(f"Saved stats for {total_users} user(s) across {len(user_stats.guilds)} guild(s)")

    except Exception as e:
        logger.error(f"Error saving user stats: {e}", exc_info=True)
        raise


def increment_user_trigger_stat(
    user_stats: UserStatsData,
    user_id: str,
    username: str,
    guild_id: str,
    channel_id: str,
    trigger_word: str = None
) -> UserStatsData:
    """
    Increment trigger stats for a user within a specific guild.

    Args:
        user_stats: UserStatsData object
        user_id: Discord user ID
        username: Discord username
        guild_id: Discord guild ID
        channel_id: Discord channel ID where trigger was used
        trigger_word: Optional trigger word that was used

    Returns:
        Updated UserStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    # Get or create guild stats
    if guild_id_str not in user_stats.guilds:
        user_stats.guilds[guild_id_str] = GuildUserStats()

    guild_stats = user_stats.guilds[guild_id_str]

    # Get or create user stats within this guild
    if user_id_str not in guild_stats.users:
        guild_stats.users[user_id_str] = UserStats(
            user_id=user_id_str,
            username=username
        )

    user_stat = guild_stats.users[user_id_str]

    # Update username in case it changed
    user_stat.username = username

    # Increment counts
    user_stat.trigger_stats.week += 1
    user_stat.trigger_stats.month += 1
    user_stat.trigger_stats.total += 1

    # Track channel-specific count within this guild
    user_stat.trigger_stats.channel_stats[channel_id_str] = \
        user_stat.trigger_stats.channel_stats.get(channel_id_str, 0) + 1

    # Track trigger word if provided
    if trigger_word:
        user_stat.trigger_stats.trigger_words[trigger_word] = \
            user_stat.trigger_stats.trigger_words.get(trigger_word, 0) + 1

    # Update timestamp
    user_stat.trigger_stats.last_triggered = datetime.utcnow().isoformat()

    return user_stats


def reset_user_stats(user_stats: UserStatsData, period: str, guild_id: str = None) -> int:
    """
    Reset user statistics for a given period.

    Args:
        user_stats: UserStatsData object
        period: "week" or "month"
        guild_id: Optional guild ID to reset stats for specific guild only

    Returns:
        Number of users whose stats were reset
    """
    if period not in ["week", "month"]:
        raise ValueError(f"Period must be 'week' or 'month', got '{period}'")

    count = 0

    # Determine which guilds to reset
    guilds_to_reset = {}
    if guild_id:
        guild_id_str = str(guild_id)
        if guild_id_str in user_stats.guilds:
            guilds_to_reset[guild_id_str] = user_stats.guilds[guild_id_str]
    else:
        guilds_to_reset = user_stats.guilds

    # Reset stats for users in selected guilds
    for gid, guild_stats in guilds_to_reset.items():
        for user_stat in guild_stats.users.values():
            if period == "week":
                user_stat.trigger_stats.week = 0
            elif period == "month":
                user_stat.trigger_stats.month = 0
            count += 1

    logger.info(f"Reset {period} stats for {count} user(s)" + (f" in guild {guild_id}" if guild_id else " across all guilds"))
    return count


def get_leaderboard(
    user_stats: UserStatsData,
    guild_id: str,
    period: str = "total",
    channel_id: str = None,
    limit: int = 10
) -> list:
    """
    Get leaderboard of users by trigger count for a specific guild.

    Args:
        user_stats: UserStatsData object
        guild_id: Guild ID (required - guilds are isolated)
        period: "week", "month", or "total"
        channel_id: Optional channel filter within the guild
        limit: Maximum number of users to return

    Returns:
        List of tuples: [(user_id, username, count), ...]
    """
    if period not in ["week", "month", "total"]:
        raise ValueError(f"Period must be 'week', 'month', or 'total', got '{period}'")

    guild_id_str = str(guild_id)

    # Check if guild exists in stats
    if guild_id_str not in user_stats.guilds:
        return []

    guild_stats = user_stats.guilds[guild_id_str]
    leaderboard = []

    for user_id, user_stat in guild_stats.users.items():
        count = 0

        # Apply filtering based on channel
        if channel_id:
            # Channel-specific leaderboard within this guild
            count = user_stat.trigger_stats.channel_stats.get(str(channel_id), 0)
        else:
            # Guild-wide leaderboard
            if period == "week":
                count = user_stat.trigger_stats.week
            elif period == "month":
                count = user_stat.trigger_stats.month
            else:  # total
                count = user_stat.trigger_stats.total

        if count > 0:
            leaderboard.append((user_id, user_stat.username, count))

    # Sort by count descending
    leaderboard.sort(key=lambda x: x[2], reverse=True)

    return leaderboard[:limit]


def get_user_rank(
    user_stats: UserStatsData,
    guild_id: str,
    user_id: str,
    period: str = "total"
) -> tuple:
    """
    Get a user's rank in the guild leaderboard.

    Args:
        user_stats: UserStatsData object
        guild_id: Guild ID
        user_id: User ID to get rank for
        period: "week", "month", or "total"

    Returns:
        Tuple of (rank, total_count, user_count) or (None, 0, 0) if not found
    """
    if period not in ["week", "month", "total"]:
        raise ValueError(f"Period must be 'week', 'month', or 'total', got '{period}'")

    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in user_stats.guilds:
        return (None, 0, 0)

    guild_stats = user_stats.guilds[guild_id_str]

    # Get user's count
    if user_id_str not in guild_stats.users:
        return (None, 0, len(guild_stats.users))

    user_stat = guild_stats.users[user_id_str]

    if period == "week":
        user_count = user_stat.trigger_stats.week
    elif period == "month":
        user_count = user_stat.trigger_stats.month
    else:  # total
        user_count = user_stat.trigger_stats.total

    # Count how many users have more triggers
    rank = 1
    for other_user_stat in guild_stats.users.values():
        if period == "week":
            other_count = other_user_stat.trigger_stats.week
        elif period == "month":
            other_count = other_user_stat.trigger_stats.month
        else:  # total
            other_count = other_user_stat.trigger_stats.total

        if other_count > user_count:
            rank += 1

    total_users = len(guild_stats.users)
    return (rank, user_count, total_users)


def get_user_channel_breakdown(
    user_stats: UserStatsData,
    guild_id: str,
    user_id: str,
    limit: int = 5
) -> list:
    """
    Get a user's channel usage breakdown.

    Args:
        user_stats: UserStatsData object
        guild_id: Guild ID
        user_id: User ID
        limit: Maximum number of channels to return

    Returns:
        List of tuples: [(channel_id, count), ...] sorted by count descending
    """
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in user_stats.guilds:
        return []

    guild_stats = user_stats.guilds[guild_id_str]

    if user_id_str not in guild_stats.users:
        return []

    user_stat = guild_stats.users[user_id_str]
    channel_stats = user_stat.trigger_stats.channel_stats

    # Sort by count descending
    sorted_channels = sorted(channel_stats.items(), key=lambda x: x[1], reverse=True)

    return sorted_channels[:limit]


def get_weekly_recap_data(user_stats: UserStatsData, guild_id: str) -> dict:
    """
    Get weekly recap data for a guild.

    Args:
        user_stats: UserStatsData object
        guild_id: Guild ID

    Returns:
        Dictionary with recap data:
        {
            "top_user": (user_id, username, count),
            "most_active_channel": (channel_id, count),
            "total_triggers": int,
            "total_users": int,
            "avg_per_user": float
        }
    """
    guild_id_str = str(guild_id)

    if guild_id_str not in user_stats.guilds:
        return {
            "top_user": None,
            "most_active_channel": None,
            "total_triggers": 0,
            "total_users": 0,
            "avg_per_user": 0.0
        }

    guild_stats = user_stats.guilds[guild_id_str]

    # Find top user of the week
    top_user = None
    max_count = 0
    total_triggers = 0
    active_users = 0

    for user_id, user_stat in guild_stats.users.items():
        week_count = user_stat.trigger_stats.week
        total_triggers += week_count

        if week_count > 0:
            active_users += 1

        if week_count > max_count:
            max_count = week_count
            top_user = (user_id, user_stat.username, week_count)

    # Find most active channel
    channel_counts = {}
    for user_stat in guild_stats.users.values():
        for channel_id, count in user_stat.trigger_stats.channel_stats.items():
            channel_counts[channel_id] = channel_counts.get(channel_id, 0) + count

    most_active_channel = None
    if channel_counts:
        max_channel_id = max(channel_counts, key=channel_counts.get)
        most_active_channel = (max_channel_id, channel_counts[max_channel_id])

    # Calculate average
    avg_per_user = total_triggers / active_users if active_users > 0 else 0.0

    return {
        "top_user": top_user,
        "most_active_channel": most_active_channel,
        "total_triggers": total_triggers,
        "total_users": active_users,
        "avg_per_user": avg_per_user
    }


def render_bar_chart(value: int, max_value: int, bar_length: int = 20) -> str:
    """
    Render an ASCII bar chart.

    Args:
        value: Current value
        max_value: Maximum value (for scaling)
        bar_length: Total length of the bar in characters

    Returns:
        String representation of the bar
    """
    if max_value == 0:
        filled = 0
    else:
        filled = int((value / max_value) * bar_length)

    empty = bar_length - filled
    return "█" * filled + "░" * empty


def get_user_top_triggers(
    user_stats: UserStatsData,
    guild_id: str,
    user_id: str,
    limit: int = 5
) -> list:
    """
    Get a user's most-used trigger words.

    Args:
        user_stats: UserStatsData object
        guild_id: Guild ID
        user_id: User ID
        limit: Maximum number of trigger words to return

    Returns:
        List of tuples: [(trigger_word, count), ...] sorted by count descending
    """
    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in user_stats.guilds:
        return []

    guild_stats = user_stats.guilds[guild_id_str]

    if user_id_str not in guild_stats.users:
        return []

    user_stat = guild_stats.users[user_id_str]
    trigger_words = user_stat.trigger_stats.trigger_words

    # Sort by count descending
    sorted_triggers = sorted(trigger_words.items(), key=lambda x: x[1], reverse=True)

    return sorted_triggers[:limit]


def render_progress_bar(current: int, target: int, bar_length: int = 10) -> str:
    """
    Render a progress bar with percentage.

    Args:
        current: Current progress
        target: Target value
        bar_length: Total length of the bar in characters

    Returns:
        String like "[████░░░░░░] 40%"
    """
    if target == 0:
        percentage = 0
        filled = 0
    else:
        percentage = int((current / target) * 100)
        filled = int((current / target) * bar_length)

    empty = bar_length - filled
    bar = "█" * filled + "░" * empty

    return f"[{bar}] {percentage}%"
