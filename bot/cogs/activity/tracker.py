"""
Activity tracker cog for monitoring user engagement.
Tracks messages, reactions, replies, and calculates activity scores.
"""
import re
import asyncio
import discord
from discord.ext import commands, tasks
from dataclasses import dataclass
from bot.base_cog import BaseCog, logger
from bot.core.config_base import ConfigBase, config_field
from bot.core.stats.activity import (
    load_activity_stats, save_activity_stats, add_message_activity,
    add_reaction_activity, add_reply_activity, remove_message_activity,
    process_voice_minute_tick, ACTIVITY_STATS_FILE
)


# -------- Configuration Schema --------

@dataclass
class ActivityConfig(ConfigBase):
    """Activity tracking and statistics configuration schema."""

    # Voice Tracking Settings
    voice_tracking_enabled: bool = config_field(
        default=True,
        description="Enable tracking of voice channel activity and time",
        category="Stats",
        guild_override=True
    )

    voice_points_per_minute: float = config_field(
        default=0.0,
        description="Points awarded per minute in voice (0.0 = disabled)",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    voice_time_display_mode: str = config_field(
        default="ranges",
        description="How to display voice time in stats",
        category="Stats",
        guild_override=True,
        choices=["ranges", "descriptions", "points_only"]
    )

    voice_tracking_type: str = config_field(
        default="total",
        description="What voice time to track",
        category="Stats",
        guild_override=True,
        choices=["total", "unmuted", "speaking"]
    )

    # Voice Time Level Thresholds (for range display)
    voice_time_level_1: int = config_field(
        default=1,
        description="Voice time threshold in hours for level 1 (< 1 hour)",
        category="Stats",
        guild_override=True,
        min_value=0,
        max_value=1000
    )

    voice_time_level_2: int = config_field(
        default=5,
        description="Voice time threshold in hours for level 2 (1-5 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_3: int = config_field(
        default=10,
        description="Voice time threshold in hours for level 3 (5-10 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_4: int = config_field(
        default=25,
        description="Voice time threshold in hours for level 4 (10-25 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_5: int = config_field(
        default=50,
        description="Voice time threshold in hours for level 5 (25-50 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_6: int = config_field(
        default=100,
        description="Voice time threshold in hours for level 6 (50-100 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_7: int = config_field(
        default=250,
        description="Voice time threshold in hours for level 7 (100-250 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    voice_time_level_8: int = config_field(
        default=500,
        description="Voice time threshold in hours for level 8 (250-500 hours)",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=1000
    )

    # Weekly Recap Settings
    enable_weekly_recap: bool = config_field(
        default=False,
        description="Enable automatic weekly activity recap posts",
        category="Stats",
        guild_override=True
    )

    weekly_recap_channel_id: int = config_field(
        default=0,
        description="Channel ID to post weekly recaps (0 = disabled)",
        category="Stats",
        guild_override=True,
        min_value=0
    )

    weekly_recap_day: int = config_field(
        default=0,
        description="Day of week for recap (0=Monday, 6=Sunday)",
        category="Stats",
        guild_override=True,
        min_value=0,
        max_value=6
    )

    weekly_recap_hour: int = config_field(
        default=9,
        description="Hour to post recap (24-hour format)",
        category="Stats",
        guild_override=True,
        min_value=0,
        max_value=23
    )

    # Activity Points Settings
    activity_base_message_points_min: float = config_field(
        default=0.8,
        description="Minimum points awarded for a message",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    activity_base_message_points_max: float = config_field(
        default=1.2,
        description="Maximum points awarded for a message",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    activity_link_bonus_points: float = config_field(
        default=2.0,
        description="Bonus points for messages containing links",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    activity_attachment_bonus_points: float = config_field(
        default=2.0,
        description="Bonus points for messages with attachments",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    activity_reaction_points: float = config_field(
        default=1.0,
        description="Points awarded for adding reactions",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    activity_reply_points: float = config_field(
        default=1.0,
        description="Points awarded for replying to messages",
        category="Stats",
        guild_override=True,
        min_value=0.0,
        max_value=10.0
    )

    # Leaderboard Settings
    leaderboard_default_limit: int = config_field(
        default=10,
        description="Default number of entries shown in leaderboard",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=50
    )

    user_stats_channel_breakdown_limit: int = config_field(
        default=5,
        description="Number of channels shown in user stats breakdown",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=20
    )

    user_stats_triggers_limit: int = config_field(
        default=5,
        description="Number of top triggers shown in user stats",
        category="Stats",
        guild_override=True,
        min_value=1,
        max_value=20
    )

    leaderboard_bar_chart_length: int = config_field(
        default=15,
        description="Character length of bar charts in leaderboard",
        category="Stats",
        guild_override=True,
        min_value=5,
        max_value=50
    )


class ActivityTracker(BaseCog):
    """Track user activity across messages, reactions, and replies."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

        # Register config schema
        from bot.core.config_system import CogConfigSchema
        schema = CogConfigSchema.from_dataclass("Activity", ActivityConfig)
        bot.config_manager.register_schema("Activity", schema)
        logger.info("Registered Activity config schema")

        # Track processed reactions to prevent duplicates: {(message_id, user_id, emoji): True}
        self.processed_reactions = {}
        # Cache activity stats in memory to avoid repeated file loads
        self._cached_stats = None
        self._stats_dirty = False  # Track if cache needs to be saved

        # Start voice time background task (use ConfigManager)
        cfg = bot.config_manager.for_guild("Activity")
        if cfg.voice_tracking_enabled:
            self.voice_time_task.start()
            logger.info("[ActivityTracker] Voice time tracking task started")

    def _get_stats(self):
        """Get cached stats or load from disk if not cached."""
        if self._cached_stats is None:
            self._cached_stats = load_activity_stats(ACTIVITY_STATS_FILE)
        return self._cached_stats

    def _save_stats(self, force=False):
        """Save cached stats to disk if dirty or forced."""
        if self._cached_stats and (self._stats_dirty or force):
            save_activity_stats(ACTIVITY_STATS_FILE, self._cached_stats)
            self._stats_dirty = False
            logger.debug("[ActivityTracker] Saved activity stats to disk")

    def _mark_dirty(self):
        """Mark stats as needing to be saved."""
        self._stats_dirty = True

    def _has_link(self, content: str) -> bool:
        """Check if message contains a URL."""
        url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
        return bool(re.search(url_pattern, content))

    def _has_attachment(self, message: discord.Message) -> bool:
        """Check if message has attachments (images, files, etc.)."""
        return len(message.attachments) > 0 or len(message.embeds) > 0

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track message activity."""
        # Ignore DMs
        if not message.guild:
            return

        # Don't track bot commands
        if message.content.startswith('~'):
            return

        try:
            activity_stats = self._get_stats()

            # Check for links and attachments
            has_link = self._has_link(message.content)
            has_attachment = self._has_attachment(message)

            # Add message activity
            activity_stats = add_message_activity(
                activity_stats,
                user_id=message.author.id,
                username=str(message.author),
                guild_id=message.guild.id,
                channel_id=message.channel.id,
                message_id=message.id,
                is_bot=message.author.bot,
                has_link=has_link,
                has_attachment=has_attachment
            )

            # Check if this is a reply
            if message.reference and message.reference.message_id:
                try:
                    # Fetch the original message
                    original_message = await message.channel.fetch_message(message.reference.message_id)

                    # Add reply activity
                    activity_stats = add_reply_activity(
                        activity_stats,
                        replier_id=message.author.id,
                        replier_name=str(message.author),
                        original_author_id=original_message.author.id,
                        original_author_name=str(original_message.author),
                        guild_id=message.guild.id,
                        replier_is_bot=message.author.bot,
                        author_is_bot=original_message.author.bot
                    )

                    logger.debug(f"[Activity] Reply tracked: {message.author} -> {original_message.author}")
                except:
                    pass  # Original message might be deleted

            self._mark_dirty()
            self._save_stats()

            logger.debug(
                f"[Activity] Message tracked: {message.author} in #{message.channel.name} "
                f"(link={has_link}, attachment={has_attachment})"
            )

        except Exception as e:
            logger.error(f"Failed to track message activity: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Track message edits (only if new link/attachment added)."""
        # Ignore DMs
        if not after.guild:
            return

        # Ignore bot commands
        if after.content.startswith('~'):
            return

        try:
            # Check if link or attachment was added
            had_link_before = self._has_link(before.content)
            has_link_after = self._has_link(after.content)
            had_attachment_before = self._has_attachment(before)
            has_attachment_after = self._has_attachment(after)

            new_link = has_link_after and not had_link_before
            new_attachment = has_attachment_after and not had_attachment_before

            # Only award points if something new was added
            if new_link or new_attachment:
                activity_stats = self._get_stats()

                # Calculate bonus points for what was added
                bonus_points = 0.0
                if new_link:
                    bonus_points += 2.0
                if new_attachment:
                    bonus_points += 2.0

                # Get user stats
                guild_id_str = str(after.guild.id)
                user_id_str = str(after.author.id)

                if guild_id_str in activity_stats.guilds:
                    guild_stats = activity_stats.guilds[guild_id_str]
                    if user_id_str in guild_stats.users:
                        user_stat = guild_stats.users[user_id_str]

                        # Add bonus points
                        user_stat.activity_stats.activity_score += bonus_points
                        user_stat.activity_stats.daily_score += bonus_points
                        user_stat.activity_stats.weekly_score += bonus_points
                        user_stat.activity_stats.monthly_score += bonus_points

                        # Update message points tracking
                        message_id_str = str(after.id)
                        if message_id_str in user_stat.activity_stats.message_points:
                            user_stat.activity_stats.message_points[message_id_str] += bonus_points

                        self._mark_dirty()
                        self._save_stats()

                        logger.debug(
                            f"[Activity] Edit bonus: {after.author} added "
                            f"{'link' if new_link else ''}{' and ' if new_link and new_attachment else ''}"
                            f"{'attachment' if new_attachment else ''} (+{bonus_points} points)"
                        )

        except Exception as e:
            logger.error(f"Failed to track message edit: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Remove points when message is deleted."""
        # Ignore DMs
        if not message.guild:
            return

        try:
            activity_stats = self._get_stats()

            # Remove message activity
            activity_stats = remove_message_activity(
                activity_stats,
                user_id=message.author.id,
                guild_id=message.guild.id,
                message_id=message.id
            )

            self._mark_dirty()
            self._save_stats()

            logger.debug(f"[Activity] Message deleted: removed points for {message.author}")

        except Exception as e:
            logger.error(f"Failed to handle message deletion: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Track reaction activity."""
        # Ignore DMs
        if not reaction.message.guild:
            return

        # Ignore bot reactions to their own messages
        if user.bot:
            return

        try:
            # Create unique key for this reaction
            reaction_key = (reaction.message.id, user.id, str(reaction.emoji))

            # Check if we've already processed this exact reaction
            if reaction_key in self.processed_reactions:
                return  # Duplicate - ignore

            # Mark as processed
            self.processed_reactions[reaction_key] = True

            activity_stats = self._get_stats()

            # Add reaction activity
            activity_stats = add_reaction_activity(
                activity_stats,
                reactor_id=user.id,
                reactor_name=str(user),
                author_id=reaction.message.author.id,
                author_name=str(reaction.message.author),
                guild_id=reaction.message.guild.id,
                reactor_is_bot=user.bot,
                author_is_bot=reaction.message.author.bot
            )

            self._mark_dirty()
            self._save_stats()

            logger.debug(
                f"[Activity] Reaction tracked: {user} -> {reaction.message.author} "
                f"(emoji: {reaction.emoji})"
            )

        except Exception as e:
            logger.error(f"Failed to track reaction: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction: discord.Reaction, user: discord.User):
        """Remove reaction from processed list when removed."""
        # Create unique key for this reaction
        reaction_key = (reaction.message.id, user.id, str(reaction.emoji))

        # Remove from processed reactions
        if reaction_key in self.processed_reactions:
            del self.processed_reactions[reaction_key]
            logger.debug(f"[Activity] Reaction removed from tracking: {user} on message {reaction.message.id}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Track voice channel join/leave and state changes."""
        from bot.core.stats.activity import (
            start_voice_session, end_voice_session, update_voice_state
        )

        # Skip if voice tracking is disabled (use ConfigManager)
        cfg = self.bot.config_manager.for_guild("Activity")
        if not cfg.voice_tracking_enabled:
            return

        try:
            activity_stats = self._get_stats()

            # User joined a voice channel
            if before.channel is None and after.channel is not None:
                activity_stats = start_voice_session(
                    activity_stats,
                    user_id=member.id,
                    username=str(member),
                    guild_id=member.guild.id,
                    channel_id=after.channel.id,
                    is_muted=after.self_mute or after.mute,
                    is_deafened=after.self_deaf or after.deaf,
                    is_bot=member.bot
                )
                self._mark_dirty()
                self._save_stats()
                logger.debug(f"[Activity] {member} joined voice channel {after.channel.name}")

            # User left a voice channel
            elif before.channel is not None and after.channel is None:
                activity_stats = end_voice_session(
                    activity_stats,
                    user_id=member.id,
                    guild_id=member.guild.id,
                    channel_id=before.channel.id
                )
                self._mark_dirty()
                self._save_stats()
                logger.debug(f"[Activity] {member} left voice channel {before.channel.name}")

            # User switched voice channels
            elif before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
                # End session in old channel
                activity_stats = end_voice_session(
                    activity_stats,
                    user_id=member.id,
                    guild_id=member.guild.id,
                    channel_id=before.channel.id
                )
                # Start session in new channel
                activity_stats = start_voice_session(
                    activity_stats,
                    user_id=member.id,
                    username=str(member),
                    guild_id=member.guild.id,
                    channel_id=after.channel.id,
                    is_muted=after.self_mute or after.mute,
                    is_deafened=after.self_deaf or after.deaf,
                    is_bot=member.bot
                )
                self._mark_dirty()
                self._save_stats()
                logger.debug(f"[Activity] {member} switched from {before.channel.name} to {after.channel.name}")

            # User changed state (mute/unmute/deaf) in same channel
            elif before.channel is not None and after.channel is not None and before.channel.id == after.channel.id:
                # Check if mute or deaf status changed
                if (before.self_mute != after.self_mute or before.mute != after.mute or
                    before.self_deaf != after.self_deaf or before.deaf != after.deaf):

                    activity_stats = update_voice_state(
                        activity_stats,
                        user_id=member.id,
                        guild_id=member.guild.id,
                        channel_id=after.channel.id,
                        is_muted=after.self_mute or after.mute,
                        is_deafened=after.self_deaf or after.deaf,
                        is_speaking=False  # We'll detect speaking separately
                    )
                    self._mark_dirty()
                    self._save_stats()
                    logger.debug(f"[Activity] {member} changed voice state (muted={after.self_mute or after.mute})")

        except Exception as e:
            logger.error(f"Failed to track voice state: {e}", exc_info=True)

    @tasks.loop(minutes=1)
    async def voice_time_task(self):
        """Background task that runs every minute to update voice time for all active sessions."""
        try:
            # Get config for activity tracking
            cfg = self.bot.config_manager.for_guild("Activity")

            # Check if anyone is in voice channels first
            has_active_sessions = False
            for guild in self.bot.guilds:
                for voice_channel in guild.voice_channels:
                    # Check if any non-bot members are in the channel
                    if any(not member.bot for member in voice_channel.members):
                        has_active_sessions = True
                        break
                if has_active_sessions:
                    break

            # Skip processing if no one is in voice
            if not has_active_sessions:
                logger.debug("[ActivityTracker] No active voice sessions, skipping tick")
                return

            # Get cached stats (loads only once)
            activity_stats = self._get_stats()
            changes_made = False

            # Process voice time for each guild
            for guild in self.bot.guilds:
                guild_id_str = str(guild.id)

                # Check if this guild has any active sessions
                if guild_id_str in activity_stats.guilds:
                    guild_stats = activity_stats.guilds[guild_id_str]
                    has_sessions = any(
                        user_stat.activity_stats.voice_sessions
                        for user_stat in guild_stats.users.values()
                    )

                    if has_sessions:
                        activity_stats = process_voice_minute_tick(
                            activity_stats,
                            guild_id=guild_id_str,
                            points_per_minute=cfg.voice_points_per_minute
                        )
                        changes_made = True

            # Only save if changes were actually made
            if changes_made:
                self._mark_dirty()
                self._save_stats()
                logger.debug("[ActivityTracker] Voice time tick processed and saved")
            else:
                logger.debug("[ActivityTracker] No voice sessions to process")

        except Exception as e:
            logger.error(f"Failed to process voice time tick: {e}", exc_info=True)

    @voice_time_task.before_loop
    async def before_voice_time_task(self):
        """Wait for bot to be ready before starting the voice time task."""
        await self.bot.wait_until_ready()
        logger.info("[ActivityTracker] Bot ready, starting voice time task")

    def cog_unload(self):
        """Cancel background tasks when cog is unloaded."""
        # Save any pending changes before unloading
        self._save_stats(force=True)

        if self.voice_time_task.is_running():
            self.voice_time_task.cancel()
            logger.info("[ActivityTracker] Voice time tracking task cancelled")


async def setup(bot):
    """Load the ActivityTracker cog."""
    try:
        await bot.add_cog(ActivityTracker(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}", exc_info=True)
