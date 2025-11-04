"""
Background writer for soundboard play statistics.
Batches stat updates and writes to soundboard.json periodically to avoid blocking sound queue.
"""
import asyncio
from collections import deque
from datetime import datetime
from bot.base_cog import logger


class SoundboardStatsWriter:
    """
    Background worker that batches soundboard stat updates and writes to disk periodically.
    Prevents blocking the sound queue with file I/O on every sound play.
    """

    def __init__(self, bot, soundboard_cog):
        """
        Initialize the soundboard stats writer.

        Args:
            bot: Discord bot instance (for ConfigManager access)
            soundboard_cog: SoundboardCog instance (for accessing soundboard data and save function)
        """
        self.bot = bot
        self.soundboard_cog = soundboard_cog
        self.pending_updates = deque()  # Queue of (guild_id, soundfile, user_id, trigger_word)
        self._write_task = None
        self._stop_flag = False
        logger.info("SoundboardStatsWriter initialized")

    def queue_update(self, guild_id: int, soundfile: str, user_id: str, trigger_word: str = None):
        """
        Queue a soundboard stat update to be written later (non-blocking).

        Args:
            guild_id: Discord guild ID
            soundfile: Path to sound file
            user_id: Discord user ID who triggered the sound
            trigger_word: Optional trigger word that was used
        """
        self.pending_updates.append((guild_id, soundfile, user_id, trigger_word))

    def start(self):
        """Start the background write task."""
        if self._write_task is None or self._write_task.done():
            self._stop_flag = False
            self._write_task = asyncio.create_task(self._write_loop())
            logger.info("SoundboardStatsWriter background task started")

    async def _write_loop(self):
        """Background task that periodically flushes pending stats to disk."""
        try:
            while not self._stop_flag:
                # Read interval from config (hot-swappable)
                sys_cfg = self.bot.config_manager.for_guild("System")
                interval = sys_cfg.soundboard_stats_write_interval

                await asyncio.sleep(interval)

                # Process all pending updates
                if self.pending_updates:
                    await self._flush_pending_updates()

        except asyncio.CancelledError:
            logger.info("SoundboardStatsWriter background task cancelled")
            # Flush remaining updates before stopping
            if self.pending_updates:
                await self._flush_pending_updates()
            raise
        except Exception as e:
            logger.error(f"Error in SoundboardStatsWriter background task: {e}", exc_info=True)

    async def _flush_pending_updates(self):
        """Flush all pending updates to disk (runs in thread to avoid blocking event loop)."""
        try:
            # Get snapshot of pending updates
            updates_to_process = list(self.pending_updates)
            self.pending_updates.clear()

            # Process in background thread to avoid blocking event loop
            await asyncio.to_thread(self._apply_updates, updates_to_process)

            logger.debug(f"Flushed {len(updates_to_process)} soundboard stat update(s)")

        except Exception as e:
            logger.error(f"Error flushing soundboard stats: {e}", exc_info=True)

    def _apply_updates(self, updates: list):
        """
        Apply batched updates to soundboard (runs in thread).

        Args:
            updates: List of (guild_id, soundfile, user_id, trigger_word) tuples
        """
        try:
            from bot.cogs.audio.soundboard import save_soundboard, SOUNDBOARD_FILE

            # Apply all updates to in-memory soundboard
            for guild_id, soundfile, user_id, trigger_word in updates:
                self._apply_single_update(guild_id, soundfile, user_id, trigger_word)

            # Save once after all updates
            save_soundboard(SOUNDBOARD_FILE, self.soundboard_cog.soundboard)
            logger.debug(f"Applied {len(updates)} stat updates and saved soundboard")

        except Exception as e:
            logger.error(f"Error applying soundboard stat updates: {e}", exc_info=True)
            raise

    def _apply_single_update(self, guild_id: int, soundfile: str, user_id: str, trigger_word: str = None):
        """
        Apply a single stat update to in-memory soundboard (runs in thread).

        Args:
            guild_id: Discord guild ID
            soundfile: Path to sound file
            user_id: Discord user ID
            trigger_word: Optional trigger word
        """
        guild_id_str = str(guild_id)
        user_id_str = str(user_id)

        # Find sound by soundfile
        sound_entry = None
        for entry in self.soundboard_cog.soundboard.sounds.values():
            if entry.soundfile == soundfile:
                sound_entry = entry
                break

        if not sound_entry:
            logger.warning(f"Soundfile '{soundfile}' not found in soundboard during stats update")
            return

        # Update stats in memory
        stats = sound_entry.play_stats
        stats.week += 1
        stats.month += 1
        stats.total += 1
        stats.guild_play_count[guild_id_str] = stats.guild_play_count.get(guild_id_str, 0) + 1
        stats.last_played = datetime.utcnow().isoformat()
        stats.played_by = [user_id_str]

        # Track trigger word usage
        if trigger_word:
            stats.trigger_word_stats[trigger_word] = stats.trigger_word_stats.get(trigger_word, 0) + 1

    async def stop(self):
        """Stop the background task and flush remaining updates."""
        self._stop_flag = True
        if self._write_task and not self._write_task.done():
            self._write_task.cancel()
            try:
                await self._write_task
            except asyncio.CancelledError:
                pass
        logger.info("SoundboardStatsWriter stopped")


# Global singleton instance (initialized by SoundboardCog)
_soundboard_stats_writer: SoundboardStatsWriter = None


def get_soundboard_stats_writer() -> SoundboardStatsWriter:
    """Get the global SoundboardStatsWriter instance."""
    return _soundboard_stats_writer


def init_soundboard_stats_writer(bot, soundboard_cog) -> SoundboardStatsWriter:
    """
    Initialize the global SoundboardStatsWriter instance.

    Args:
        bot: Discord bot instance
        soundboard_cog: SoundboardCog instance

    Returns:
        SoundboardStatsWriter instance
    """
    global _soundboard_stats_writer
    if _soundboard_stats_writer is None:
        _soundboard_stats_writer = SoundboardStatsWriter(bot, soundboard_cog)
    return _soundboard_stats_writer
