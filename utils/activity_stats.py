"""
Activity statistics tracking for message engagement.
Tracks messages, reactions, replies with point-based system.
Points are intentionally randomized/calculated to keep exact message counts ambiguous.
"""
import json
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, Tuple
from datetime import datetime
from pathlib import Path
from base_cog import logger

ACTIVITY_STATS_FILE = "activity_stats.json"


@dataclass
class ActivityStats:
    """Activity statistics for a user within a guild."""
    # Point-based system (ambiguous - not 1:1 with messages)
    activity_score: float = 0.0
    daily_score: float = 0.0
    weekly_score: float = 0.0
    monthly_score: float = 0.0

    # Internal tracking (not displayed to users)
    _message_count: int = 0
    _reaction_given: int = 0
    _reaction_received: int = 0
    _replies_given: int = 0
    _replies_received: int = 0

    # Voice time tracking (in minutes) - 3 types available
    _voice_total_minutes: int = 0          # Total time in any voice channel
    _voice_total_minutes_week: int = 0
    _voice_total_minutes_month: int = 0

    _voice_unmuted_minutes: int = 0        # Time unmuted in voice
    _voice_unmuted_minutes_week: int = 0
    _voice_unmuted_minutes_month: int = 0

    _voice_speaking_minutes: int = 0       # Time actively speaking (detected by Discord)
    _voice_speaking_minutes_week: int = 0
    _voice_speaking_minutes_month: int = 0

    # Per-channel activity scores
    channel_scores: Dict[str, float] = field(default_factory=dict)

    # Track message IDs for deletion handling: {message_id: points_awarded}
    message_points: Dict[str, float] = field(default_factory=dict)

    # Track current voice state: {channel_id: (join_timestamp_iso, was_muted, was_speaking)}
    voice_sessions: Dict[str, tuple] = field(default_factory=dict)

    last_active: str = None  # ISO format timestamp


@dataclass
class UserActivityData:
    """All activity data for a single user in a guild."""
    user_id: str
    username: str
    is_bot: bool = False
    activity_stats: ActivityStats = field(default_factory=ActivityStats)


@dataclass
class GuildActivityData:
    """Container for all user activity in a guild."""
    users: Dict[str, UserActivityData] = field(default_factory=dict)  # {user_id: UserActivityData}


@dataclass
class ActivityStatsData:
    """Container for all guild activity. Guilds are isolated."""
    guilds: Dict[str, GuildActivityData] = field(default_factory=dict)  # {guild_id: GuildActivityData}


def load_activity_stats(file_path: str = ACTIVITY_STATS_FILE) -> ActivityStatsData:
    """Load activity stats from JSON file."""
    logger.info(f"Loading activity stats from '{file_path}'...")

    try:
        if not Path(file_path).exists():
            logger.info(f"Activity stats file not found, creating new one: {file_path}")
            return ActivityStatsData()

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        guilds = {}
        total_users = 0

        for guild_id, guild_data in data.get("guilds", {}).items():
            try:
                users = {}
                for user_id, user_data in guild_data.get("users", {}).items():
                    try:
                        # Convert activity_stats dict to ActivityStats object
                        if "activity_stats" in user_data and isinstance(user_data["activity_stats"], dict):
                            user_data["activity_stats"] = ActivityStats(**user_data["activity_stats"])

                        users[user_id] = UserActivityData(**user_data)
                        total_users += 1
                    except Exception as e:
                        logger.error(f"Failed to load activity for user {user_id} in guild {guild_id}: {e}")

                guilds[guild_id] = GuildActivityData(users=users)
            except Exception as e:
                logger.error(f"Failed to load activity for guild {guild_id}: {e}")

        logger.info(f"Successfully loaded activity for {total_users} user(s) across {len(guilds)} guild(s)")
        return ActivityStatsData(guilds=guilds)

    except Exception as e:
        logger.error(f"Error loading activity stats: {e}", exc_info=True)
        raise


def save_activity_stats(file_path: str, activity_stats: ActivityStatsData):
    """Save activity stats to JSON file."""
    logger.debug(f"Saving activity stats to '{file_path}'...")

    try:
        # Create backup if file exists
        if Path(file_path).exists():
            import shutil
            shutil.copy2(file_path, f"{file_path}.backup")

        data = {"guilds": {k: asdict(v) for k, v in activity_stats.guilds.items()}}

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        total_users = sum(len(guild.users) for guild in activity_stats.guilds.values())
        logger.debug(f"Saved activity for {total_users} user(s) across {len(activity_stats.guilds)} guild(s)")

    except Exception as e:
        logger.error(f"Error saving activity stats: {e}", exc_info=True)
        raise


def calculate_message_points(has_link: bool = False, has_attachment: bool = False) -> float:
    """
    Calculate points for a message.
    Base points are randomized to keep exact message counts ambiguous.

    Returns:
        Float points (randomized base + bonuses)
    """
    # Base message points (randomized)
    points = random.uniform(0.8, 1.2)

    # Bonus for links
    if has_link:
        points += 2.0

    # Bonus for attachments/images
    if has_attachment:
        points += 2.0

    return points


def add_message_activity(
    activity_stats: ActivityStatsData,
    user_id: str,
    username: str,
    guild_id: str,
    channel_id: str,
    message_id: str,
    is_bot: bool = False,
    has_link: bool = False,
    has_attachment: bool = False
) -> ActivityStatsData:
    """
    Add activity for a message.

    Args:
        activity_stats: ActivityStatsData object
        user_id: Discord user ID
        username: Discord username
        guild_id: Discord guild ID
        channel_id: Discord channel ID
        message_id: Discord message ID
        is_bot: Whether user is a bot
        has_link: Whether message contains a link
        has_attachment: Whether message has an attachment

    Returns:
        Updated ActivityStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)
    message_id_str = str(message_id)

    # Get or create guild stats
    if guild_id_str not in activity_stats.guilds:
        activity_stats.guilds[guild_id_str] = GuildActivityData()

    guild_stats = activity_stats.guilds[guild_id_str]

    # Get or create user stats
    if user_id_str not in guild_stats.users:
        guild_stats.users[user_id_str] = UserActivityData(
            user_id=user_id_str,
            username=username,
            is_bot=is_bot
        )

    user_stat = guild_stats.users[user_id_str]
    user_stat.username = username  # Update username

    # Calculate points
    points = calculate_message_points(has_link, has_attachment)

    # Add points
    user_stat.activity_stats.activity_score += points
    user_stat.activity_stats.daily_score += points
    user_stat.activity_stats.weekly_score += points
    user_stat.activity_stats.monthly_score += points
    user_stat.activity_stats._message_count += 1

    # Track per-channel
    user_stat.activity_stats.channel_scores[channel_id_str] = \
        user_stat.activity_stats.channel_scores.get(channel_id_str, 0.0) + points

    # Store message points for deletion handling
    user_stat.activity_stats.message_points[message_id_str] = points

    # Update timestamp
    user_stat.activity_stats.last_active = datetime.utcnow().isoformat()

    return activity_stats


def add_reaction_activity(
    activity_stats: ActivityStatsData,
    reactor_id: str,
    reactor_name: str,
    author_id: str,
    author_name: str,
    guild_id: str,
    reactor_is_bot: bool = False,
    author_is_bot: bool = False
) -> ActivityStatsData:
    """
    Add activity for a reaction (both reactor and author get points).

    Args:
        activity_stats: ActivityStatsData object
        reactor_id: User ID who added the reaction
        reactor_name: Username who added the reaction
        author_id: User ID who authored the message
        author_name: Username who authored the message
        guild_id: Discord guild ID
        reactor_is_bot: Whether reactor is a bot
        author_is_bot: Whether author is a bot

    Returns:
        Updated ActivityStatsData object
    """
    guild_id_str = str(guild_id)

    # Don't count self-reactions
    if str(reactor_id) == str(author_id):
        return activity_stats

    # Get or create guild stats
    if guild_id_str not in activity_stats.guilds:
        activity_stats.guilds[guild_id_str] = GuildActivityData()

    guild_stats = activity_stats.guilds[guild_id_str]

    # Award point to reactor
    reactor_id_str = str(reactor_id)
    if reactor_id_str not in guild_stats.users:
        guild_stats.users[reactor_id_str] = UserActivityData(
            user_id=reactor_id_str,
            username=reactor_name,
            is_bot=reactor_is_bot
        )

    reactor_stat = guild_stats.users[reactor_id_str]
    reactor_stat.activity_stats.activity_score += 1.0
    reactor_stat.activity_stats.daily_score += 1.0
    reactor_stat.activity_stats.weekly_score += 1.0
    reactor_stat.activity_stats.monthly_score += 1.0
    reactor_stat.activity_stats._reaction_given += 1
    reactor_stat.activity_stats.last_active = datetime.utcnow().isoformat()

    # Award point to message author
    author_id_str = str(author_id)
    if author_id_str not in guild_stats.users:
        guild_stats.users[author_id_str] = UserActivityData(
            user_id=author_id_str,
            username=author_name,
            is_bot=author_is_bot
        )

    author_stat = guild_stats.users[author_id_str]
    author_stat.activity_stats.activity_score += 1.0
    author_stat.activity_stats.daily_score += 1.0
    author_stat.activity_stats.weekly_score += 1.0
    author_stat.activity_stats.monthly_score += 1.0
    author_stat.activity_stats._reaction_received += 1

    return activity_stats


def add_reply_activity(
    activity_stats: ActivityStatsData,
    replier_id: str,
    replier_name: str,
    original_author_id: str,
    original_author_name: str,
    guild_id: str,
    replier_is_bot: bool = False,
    author_is_bot: bool = False
) -> ActivityStatsData:
    """
    Add activity for a reply (both replier and original author get points).

    Args:
        activity_stats: ActivityStatsData object
        replier_id: User ID who replied
        replier_name: Username who replied
        original_author_id: User ID of original message author
        original_author_name: Username of original message author
        guild_id: Discord guild ID
        replier_is_bot: Whether replier is a bot
        author_is_bot: Whether original author is a bot

    Returns:
        Updated ActivityStatsData object
    """
    guild_id_str = str(guild_id)

    # Get or create guild stats
    if guild_id_str not in activity_stats.guilds:
        activity_stats.guilds[guild_id_str] = GuildActivityData()

    guild_stats = activity_stats.guilds[guild_id_str]

    # Award point to replier
    replier_id_str = str(replier_id)
    if replier_id_str not in guild_stats.users:
        guild_stats.users[replier_id_str] = UserActivityData(
            user_id=replier_id_str,
            username=replier_name,
            is_bot=replier_is_bot
        )

    replier_stat = guild_stats.users[replier_id_str]
    replier_stat.activity_stats.activity_score += 1.0
    replier_stat.activity_stats.daily_score += 1.0
    replier_stat.activity_stats.weekly_score += 1.0
    replier_stat.activity_stats.monthly_score += 1.0
    replier_stat.activity_stats._replies_given += 1
    replier_stat.activity_stats.last_active = datetime.utcnow().isoformat()

    # Award point to original author (if different user)
    if str(replier_id) != str(original_author_id):
        author_id_str = str(original_author_id)
        if author_id_str not in guild_stats.users:
            guild_stats.users[author_id_str] = UserActivityData(
                user_id=author_id_str,
                username=original_author_name,
                is_bot=author_is_bot
            )

        author_stat = guild_stats.users[author_id_str]
        author_stat.activity_stats.activity_score += 1.0
        author_stat.activity_stats.daily_score += 1.0
        author_stat.activity_stats.weekly_score += 1.0
        author_stat.activity_stats.monthly_score += 1.0
        author_stat.activity_stats._replies_received += 1

    return activity_stats


def remove_message_activity(
    activity_stats: ActivityStatsData,
    user_id: str,
    guild_id: str,
    message_id: str
) -> ActivityStatsData:
    """
    Remove activity points for a deleted message.

    Args:
        activity_stats: ActivityStatsData object
        user_id: Discord user ID
        guild_id: Discord guild ID
        message_id: Discord message ID

    Returns:
        Updated ActivityStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    message_id_str = str(message_id)

    if guild_id_str not in activity_stats.guilds:
        return activity_stats

    guild_stats = activity_stats.guilds[guild_id_str]

    if user_id_str not in guild_stats.users:
        return activity_stats

    user_stat = guild_stats.users[user_id_str]

    # Check if we have points recorded for this message
    if message_id_str in user_stat.activity_stats.message_points:
        points = user_stat.activity_stats.message_points[message_id_str]

        # Subtract points
        user_stat.activity_stats.activity_score = max(0, user_stat.activity_stats.activity_score - points)
        user_stat.activity_stats.daily_score = max(0, user_stat.activity_stats.daily_score - points)
        user_stat.activity_stats.weekly_score = max(0, user_stat.activity_stats.weekly_score - points)
        user_stat.activity_stats.monthly_score = max(0, user_stat.activity_stats.monthly_score - points)
        user_stat.activity_stats._message_count = max(0, user_stat.activity_stats._message_count - 1)

        # Remove message from tracking
        del user_stat.activity_stats.message_points[message_id_str]

        logger.debug(f"Removed {points:.2f} points from user {user_id} for deleted message {message_id}")

    return activity_stats


def get_activity_tier(score: float) -> Tuple[str, str, str]:
    """
    Get activity tier based on score (ambiguous display).

    Returns:
        Tuple of (tier_name, tier_emoji, tier_description)
    """
    if score >= 1000:
        return ("💎 Diamond", "💎", "Legendary Activity")
    elif score >= 500:
        return ("🥇 Gold", "🥇", "Very Active")
    elif score >= 250:
        return ("🥈 Silver", "🥈", "Active")
    elif score >= 100:
        return ("🥉 Bronze", "🥉", "Moderate")
    elif score >= 25:
        return ("📝 Contributor", "📝", "Getting Started")
    else:
        return ("👋 Newcomer", "👋", "Just Joined")


def get_activity_leaderboard(
    activity_stats: ActivityStatsData,
    guild_id: str,
    period: str = "total",
    include_bots: bool = False,
    limit: int = 10
) -> list:
    """
    Get activity leaderboard for a guild.

    Args:
        activity_stats: ActivityStatsData object
        guild_id: Guild ID (required - guilds are isolated)
        period: "daily", "weekly", "monthly", or "total"
        include_bots: Whether to include bots in leaderboard
        limit: Maximum number of users to return

    Returns:
        List of tuples: [(user_id, username, score, is_bot), ...]
    """
    if period not in ["daily", "weekly", "monthly", "total"]:
        raise ValueError(f"Period must be 'daily', 'weekly', 'monthly', or 'total', got '{period}'")

    guild_id_str = str(guild_id)

    # Check if guild exists in stats
    if guild_id_str not in activity_stats.guilds:
        return []

    guild_stats = activity_stats.guilds[guild_id_str]
    leaderboard = []

    for user_id, user_stat in guild_stats.users.items():
        # Filter bots if requested
        if not include_bots and user_stat.is_bot:
            continue
        if include_bots and not user_stat.is_bot:
            continue

        # Get score for period
        if period == "daily":
            score = user_stat.activity_stats.daily_score
        elif period == "weekly":
            score = user_stat.activity_stats.weekly_score
        elif period == "monthly":
            score = user_stat.activity_stats.monthly_score
        else:  # total
            score = user_stat.activity_stats.activity_score

        if score > 0:
            leaderboard.append((user_id, user_stat.username, score, user_stat.is_bot))

    # Sort by score descending
    leaderboard.sort(key=lambda x: x[2], reverse=True)

    return leaderboard[:limit]


def get_user_activity_rank(
    activity_stats: ActivityStatsData,
    guild_id: str,
    user_id: str,
    period: str = "total"
) -> tuple:
    """
    Get a user's rank in the activity leaderboard.

    Args:
        activity_stats: ActivityStatsData object
        guild_id: Guild ID
        user_id: User ID to get rank for
        period: "daily", "weekly", "monthly", or "total"

    Returns:
        Tuple of (rank, score, total_users) or (None, 0, 0) if not found
    """
    if period not in ["daily", "weekly", "monthly", "total"]:
        raise ValueError(f"Period must be 'daily', 'weekly', 'monthly', or 'total', got '{period}'")

    guild_id_str = str(guild_id)
    user_id_str = str(user_id)

    if guild_id_str not in activity_stats.guilds:
        return (None, 0, 0)

    guild_stats = activity_stats.guilds[guild_id_str]

    # Get user's score
    if user_id_str not in guild_stats.users:
        return (None, 0, len(guild_stats.users))

    user_stat = guild_stats.users[user_id_str]

    if period == "daily":
        user_score = user_stat.activity_stats.daily_score
    elif period == "weekly":
        user_score = user_stat.activity_stats.weekly_score
    elif period == "monthly":
        user_score = user_stat.activity_stats.monthly_score
    else:  # total
        user_score = user_stat.activity_stats.activity_score

    # Count how many users have more activity (same bot status)
    rank = 1
    for other_user_stat in guild_stats.users.values():
        # Compare only within same bot status
        if other_user_stat.is_bot != user_stat.is_bot:
            continue

        if period == "daily":
            other_score = other_user_stat.activity_stats.daily_score
        elif period == "weekly":
            other_score = other_user_stat.activity_stats.weekly_score
        elif period == "monthly":
            other_score = other_user_stat.activity_stats.monthly_score
        else:  # total
            other_score = other_user_stat.activity_stats.activity_score

        if other_score > user_score:
            rank += 1

    # Count total users with same bot status
    total_users = sum(1 for u in guild_stats.users.values() if u.is_bot == user_stat.is_bot)

    return (rank, user_score, total_users)


def reset_activity_stats(activity_stats: ActivityStatsData, period: str, guild_id: str = None) -> int:
    """
    Reset activity statistics for a given period.

    Args:
        activity_stats: ActivityStatsData object
        period: "daily", "weekly", or "monthly"
        guild_id: Optional guild ID to reset specific guild only

    Returns:
        Number of users whose stats were reset
    """
    if period not in ["daily", "weekly", "monthly"]:
        raise ValueError(f"Period must be 'daily', 'weekly', or 'monthly', got '{period}'")

    count = 0

    # Determine which guilds to reset
    guilds_to_reset = {}
    if guild_id:
        guild_id_str = str(guild_id)
        if guild_id_str in activity_stats.guilds:
            guilds_to_reset[guild_id_str] = activity_stats.guilds[guild_id_str]
    else:
        guilds_to_reset = activity_stats.guilds

    # Reset stats for users in selected guilds
    for gid, guild_stats in guilds_to_reset.items():
        for user_stat in guild_stats.users.values():
            if period == "daily":
                user_stat.activity_stats.daily_score = 0.0
            elif period == "weekly":
                user_stat.activity_stats.weekly_score = 0.0
            elif period == "monthly":
                user_stat.activity_stats.monthly_score = 0.0
            count += 1

    logger.info(f"Reset {period} activity stats for {count} user(s)" + (f" in guild {guild_id}" if guild_id else " across all guilds"))
    return count


def start_voice_session(
    activity_stats: ActivityStatsData,
    user_id: str,
    username: str,
    guild_id: str,
    channel_id: str,
    is_muted: bool = False,
    is_deafened: bool = False,
    is_bot: bool = False
) -> ActivityStatsData:
    """
    Start tracking a voice session when user joins voice channel.

    Args:
        activity_stats: ActivityStatsData object
        user_id: Discord user ID
        username: Discord username
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        is_muted: Whether user is muted
        is_deafened: Whether user is deafened
        is_bot: Whether user is a bot

    Returns:
        Updated ActivityStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    # Get or create guild stats
    if guild_id_str not in activity_stats.guilds:
        activity_stats.guilds[guild_id_str] = GuildActivityData()

    guild_stats = activity_stats.guilds[guild_id_str]

    # Get or create user stats
    if user_id_str not in guild_stats.users:
        guild_stats.users[user_id_str] = UserActivityData(
            user_id=user_id_str,
            username=username,
            is_bot=is_bot
        )

    user_stat = guild_stats.users[user_id_str]
    user_stat.username = username  # Update username

    # Store voice session start time and state
    # Format: (join_timestamp_iso, is_muted, is_deafened, speaking_detected)
    join_time = datetime.utcnow().isoformat()
    user_stat.activity_stats.voice_sessions[channel_id_str] = (join_time, is_muted, is_deafened, False)

    logger.debug(f"[Voice] Started session for {username} in channel {channel_id} (muted={is_muted})")

    return activity_stats


def end_voice_session(
    activity_stats: ActivityStatsData,
    user_id: str,
    guild_id: str,
    channel_id: str
) -> ActivityStatsData:
    """
    End tracking a voice session when user leaves voice channel.
    Calculates and adds the time spent.

    Args:
        activity_stats: ActivityStatsData object
        user_id: Discord user ID
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID

    Returns:
        Updated ActivityStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    if guild_id_str not in activity_stats.guilds:
        return activity_stats

    guild_stats = activity_stats.guilds[guild_id_str]

    if user_id_str not in guild_stats.users:
        return activity_stats

    user_stat = guild_stats.users[user_id_str]

    # Check if we have an active session
    if channel_id_str not in user_stat.activity_stats.voice_sessions:
        return activity_stats

    # Get session data
    join_time_iso, was_muted, was_deafened, speaking_detected = user_stat.activity_stats.voice_sessions[channel_id_str]
    join_time = datetime.fromisoformat(join_time_iso)
    leave_time = datetime.utcnow()

    # Calculate minutes spent
    time_delta = leave_time - join_time
    minutes_spent = int(time_delta.total_seconds() / 60)

    if minutes_spent > 0:
        # Add to total voice time
        user_stat.activity_stats._voice_total_minutes += minutes_spent
        user_stat.activity_stats._voice_total_minutes_week += minutes_spent
        user_stat.activity_stats._voice_total_minutes_month += minutes_spent

        # Add to unmuted time if user was not muted/deafened
        if not was_muted and not was_deafened:
            user_stat.activity_stats._voice_unmuted_minutes += minutes_spent
            user_stat.activity_stats._voice_unmuted_minutes_week += minutes_spent
            user_stat.activity_stats._voice_unmuted_minutes_month += minutes_spent

        # Add to speaking time if speaking was detected
        if speaking_detected:
            user_stat.activity_stats._voice_speaking_minutes += minutes_spent
            user_stat.activity_stats._voice_speaking_minutes_week += minutes_spent
            user_stat.activity_stats._voice_speaking_minutes_month += minutes_spent

        logger.debug(f"[Voice] Ended session for user {user_id}: {minutes_spent} minutes (muted={was_muted}, speaking={speaking_detected})")

    # Remove session from tracking
    del user_stat.activity_stats.voice_sessions[channel_id_str]

    return activity_stats


def update_voice_state(
    activity_stats: ActivityStatsData,
    user_id: str,
    guild_id: str,
    channel_id: str,
    is_muted: bool = False,
    is_deafened: bool = False,
    is_speaking: bool = False
) -> ActivityStatsData:
    """
    Update voice state (mute/unmute/speaking) for an active session.

    Args:
        activity_stats: ActivityStatsData object
        user_id: Discord user ID
        guild_id: Discord guild ID
        channel_id: Discord voice channel ID
        is_muted: Whether user is currently muted
        is_deafened: Whether user is currently deafened
        is_speaking: Whether user is currently speaking

    Returns:
        Updated ActivityStatsData object
    """
    user_id_str = str(user_id)
    guild_id_str = str(guild_id)
    channel_id_str = str(channel_id)

    if guild_id_str not in activity_stats.guilds:
        return activity_stats

    guild_stats = activity_stats.guilds[guild_id_str]

    if user_id_str not in guild_stats.users:
        return activity_stats

    user_stat = guild_stats.users[user_id_str]

    # Check if we have an active session
    if channel_id_str not in user_stat.activity_stats.voice_sessions:
        return activity_stats

    # Update session state
    join_time_iso, old_muted, old_deafened, old_speaking = user_stat.activity_stats.voice_sessions[channel_id_str]

    # Mark speaking detected if user is speaking (sticky flag)
    speaking_detected = old_speaking or is_speaking

    user_stat.activity_stats.voice_sessions[channel_id_str] = (join_time_iso, is_muted, is_deafened, speaking_detected)

    logger.debug(f"[Voice] Updated state for user {user_id} in channel {channel_id}: muted={is_muted}, speaking={speaking_detected}")

    return activity_stats


def process_voice_minute_tick(
    activity_stats: ActivityStatsData,
    guild_id: str,
    points_per_minute: float = 0.0
) -> ActivityStatsData:
    """
    Process one minute tick for all active voice sessions.
    Called by background task every minute.

    Args:
        activity_stats: ActivityStatsData object
        guild_id: Discord guild ID
        points_per_minute: Points to award per minute (from config)

    Returns:
        Updated ActivityStatsData object
    """
    guild_id_str = str(guild_id)

    if guild_id_str not in activity_stats.guilds:
        return activity_stats

    guild_stats = activity_stats.guilds[guild_id_str]

    # Process each user with active voice sessions
    for user_id, user_stat in guild_stats.users.items():
        if not user_stat.activity_stats.voice_sessions:
            continue

        # User has active voice session(s)
        for channel_id, (join_time_iso, is_muted, is_deafened, speaking_detected) in user_stat.activity_stats.voice_sessions.items():
            # Add 1 minute to total voice time
            user_stat.activity_stats._voice_total_minutes += 1
            user_stat.activity_stats._voice_total_minutes_week += 1
            user_stat.activity_stats._voice_total_minutes_month += 1

            # Add to unmuted time if not muted/deafened
            if not is_muted and not is_deafened:
                user_stat.activity_stats._voice_unmuted_minutes += 1
                user_stat.activity_stats._voice_unmuted_minutes_week += 1
                user_stat.activity_stats._voice_unmuted_minutes_month += 1

            # Add to speaking time if speaking detected
            if speaking_detected:
                user_stat.activity_stats._voice_speaking_minutes += 1
                user_stat.activity_stats._voice_speaking_minutes_week += 1
                user_stat.activity_stats._voice_speaking_minutes_month += 1

            # Award activity points if configured
            if points_per_minute > 0:
                user_stat.activity_stats.activity_score += points_per_minute
                user_stat.activity_stats.daily_score += points_per_minute
                user_stat.activity_stats.weekly_score += points_per_minute
                user_stat.activity_stats.monthly_score += points_per_minute

    return activity_stats


def format_voice_time_ranges(minutes: int) -> str:
    """
    Format voice time in ambiguous ranges.

    Args:
        minutes: Total minutes

    Returns:
        String representation of time range
    """
    hours = minutes / 60

    if hours < 1:
        return "< 1 hour"
    elif hours < 5:
        return "1-5 hours"
    elif hours < 10:
        return "5-10 hours"
    elif hours < 25:
        return "10-25 hours"
    elif hours < 50:
        return "25-50 hours"
    elif hours < 100:
        return "50-100 hours"
    elif hours < 250:
        return "100-250 hours"
    elif hours < 500:
        return "250-500 hours"
    else:
        return "500+ hours"


def format_voice_time_description(minutes: int) -> Tuple[str, str]:
    """
    Format voice time as vague descriptions.

    Args:
        minutes: Total minutes

    Returns:
        Tuple of (tier_name, tier_description)
    """
    hours = minutes / 60

    if hours < 1:
        return ("👂 Lurker", "Rarely in voice")
    elif hours < 10:
        return ("🎧 Listener", "Occasionally present")
    elif hours < 50:
        return ("💬 Regular", "Frequently in voice")
    elif hours < 100:
        return ("🎤 Active Member", "Very active in voice")
    elif hours < 250:
        return ("⭐ Voice Champion", "Always around")
    else:
        return ("🏆 Voice Legend", "Lives in voice chat")


def get_voice_time_display(
    minutes: int,
    display_mode: str = "ranges",
    tracking_type: str = "total"
) -> str:
    """
    Get formatted voice time for display.

    Args:
        minutes: Total minutes
        display_mode: "ranges", "descriptions", or "points_only"
        tracking_type: "total", "unmuted", or "speaking"

    Returns:
        Formatted string for display
    """
    type_labels = {
        "total": "Voice Time",
        "unmuted": "Active Voice Time",
        "speaking": "Speaking Time"
    }

    type_label = type_labels.get(tracking_type, "Voice Time")

    if display_mode == "ranges":
        time_range = format_voice_time_ranges(minutes)
        return f"**{type_label}:** {time_range}"

    elif display_mode == "descriptions":
        tier_name, tier_desc = format_voice_time_description(minutes)
        return f"**{type_label}:** {tier_name} - {tier_desc}"

    elif display_mode == "points_only":
        # Don't show voice time, only points (which are shown elsewhere)
        return ""

    else:
        # Fallback to ranges
        time_range = format_voice_time_ranges(minutes)
        return f"**{type_label}:** {time_range}"
