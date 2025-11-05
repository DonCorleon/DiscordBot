# voicespeech.py
import json
import discord
from discord import FFmpegPCMAudio
from discord.ext import commands, voice_recv
from discord.ext.voice_recv.extras import speechrecognition as dsr
import asyncio
import os
from dataclasses import dataclass
from datetime import datetime
from bot.base_cog import BaseCog, logger
from bot.core.config_base import ConfigBase, config_field
from bot.core.audio.sources import DuckedAudioSource
from bot.core.errors import UserFeedback
from bot.core.transcript_session import TranscriptSessionManager
from bot.config import config


# -------- Configuration Schema --------

@dataclass
class VoiceConfig(ConfigBase):
    """Voice channel and auto-join configuration schema."""

    auto_join_enabled: bool = config_field(
        default=True,
        description="Enable auto-join when users enter voice channels",
        category="Audio/Voice Channels/Auto-Join",
        guild_override=True
    )

    auto_disconnect_timeout: int = config_field(
        default=300,
        description="Seconds to wait before leaving empty voice channel (0 = stay forever)",
        category="Audio/Voice Channels/Auto-Disconnect",
        guild_override=True,
        min_value=0,
        max_value=3600
    )

    sound_playback_timeout: float = config_field(
        default=30.0,
        description="Maximum seconds to wait for sound playback to complete",
        category="Audio/Playback",
        guild_override=True,
        min_value=5.0,
        max_value=120.0
    )

    sound_queue_warning_size: int = config_field(
        default=50,
        description="Warn when sound queue exceeds this size",
        category="Audio/Playback",
        guild_override=True,
        min_value=10,
        max_value=500
    )

    # Transcript Session Settings
    transcript_enabled: bool = config_field(
        default=True,
        description="Enable transcript session recording",
        category="Audio/Speech Recognition",
        guild_override=True
    )

    transcript_flush_interval: int = config_field(
        default=30,
        description="Seconds between transcript file updates (lower = more writes, less data loss risk)",
        category="Audio/Speech Recognition",
        guild_override=False,
        min_value=5,
        max_value=300
    )

    transcript_dir: str = config_field(
        default="data/transcripts/sessions",
        description="Directory to store transcript session files",
        category="Data Storage",
        guild_override=False
    )

# Monkey patch for discord-ext-voice-recv bug
def _patched_remove_ssrc(self, *, user_id: int):
    """Patched version of _remove_ssrc that handles missing reader gracefully."""
    try:
        ssrc = self._ssrcs.pop(user_id, None)
        if ssrc is not None and hasattr(self, '_reader') and self._reader is not discord.utils.MISSING:
            if hasattr(self._reader, 'speaking_timer') and self._reader.speaking_timer is not None:
                self._reader.speaking_timer.drop_ssrc(ssrc)
    except Exception as e:
        logger.debug(f"Error in _remove_ssrc for user {user_id}: {e}")


# Apply the patch
try:
    from discord.ext.voice_recv import VoiceRecvClient

    VoiceRecvClient._remove_ssrc = _patched_remove_ssrc
    logger.info("Applied voice_recv _remove_ssrc patch")
except Exception as e:
    logger.warning(f"Could not apply voice_recv patch: {e}")


class VoiceSpeechCog(BaseCog):

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

        # Register config schemas
        from bot.core.config_system import CogConfigSchema
        from bot.core.audio.speech_engines.config import SpeechConfig

        voice_schema = CogConfigSchema.from_dataclass("Voice", VoiceConfig)
        bot.config_manager.register_schema("Voice", voice_schema)
        logger.info("Registered Voice config schema")

        speech_schema = CogConfigSchema.from_dataclass("Speech", SpeechConfig)
        bot.config_manager.register_schema("Speech", speech_schema)
        logger.info("Registered Speech config schema")

        self.active_sinks = {}
        self._keepalive_task = None
        self.sound_queues = {}  # {guild_id: asyncio.Queue}
        self.queue_tasks = {}  # {guild_id: Task}

        # Track current audio sources for ducking control
        self.current_sources = {}  # {guild_id: DuckedAudioSource}

        # Ducking configuration per guild
        self.ducking_config = {}  # {guild_id: {"enabled": bool, "level": float}}

        # Track speaking users per guild
        self.speaking_users = {}  # {guild_id: set(user_ids)}

        # Auto-disconnect timeout tasks
        self.disconnect_tasks = {}  # {guild_id: Task}

        # Transcript session manager (pass bot for ConfigManager access)
        self.transcript_manager = TranscriptSessionManager(bot)
        logger.info("Initialized TranscriptSessionManager")

        # Initialize user stats writer
        from bot.core.stats.user_triggers import init_stats_writer
        self.stats_writer = init_stats_writer(bot)
        logger.info("Initialized UserStatsWriter")

    async def cog_load(self):
        """Called when the cog is loaded."""
        # Start transcript flush task
        self.transcript_manager.start_flush_task()
        logger.info("Started transcript flush task")

        # Start user stats writer
        self.stats_writer.start()
        logger.info("Started UserStatsWriter background task")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        from bot.core.audio.auto_join import is_auto_join_channel

        guild_id = member.guild.id

        # Handle auto-join when someone joins an enabled channel
        voice_cfg = self.bot.config_manager.for_guild("Voice", guild_id)
        if voice_cfg.auto_join_enabled and not member.bot:
            # User joined a channel
            if before.channel is None and after.channel is not None:
                # Check if this channel has auto-join enabled
                if is_auto_join_channel(guild_id, after.channel.id):
                    # Check if bot is not already connected
                    if not member.guild.voice_client:
                        try:
                            vc = await after.channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
                            logger.info(f"[{member.guild.name}] Auto-joined {after.channel.name} (triggered by {member.name})")

                            # Start keepalive if needed
                            if not self._keepalive_task:
                                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())

                            # Auto-start listening
                            if guild_id not in self.active_sinks:
                                # Create a minimal context object for speech listener
                                class AutoJoinContext:
                                    def __init__(self, guild, voice_client):
                                        self.guild = guild
                                        self.voice_client = voice_client

                                ctx = AutoJoinContext(member.guild, vc)
                                engine = self._create_speech_listener(ctx)
                                await engine.start_listening(vc)
                                # Store both engine and sink
                                self.active_sinks[guild_id] = {
                                    'engine': engine,
                                    'sink': engine.get_sink()
                                }
                                logger.info(f"[{member.guild.name}] Auto-started listening in {after.channel.name}")

                            # Start transcript session
                            session_id = self.transcript_manager.start_session(
                                channel_id=str(after.channel.id),
                                guild_id=str(guild_id),
                                guild_name=member.guild.name,
                                channel_name=after.channel.name,
                                first_user_id=str(member.id),
                                first_username=member.display_name
                            )

                            # Save voice state for persistence (with session_id)
                            from bot.core.audio.voice_state import save_voice_state
                            save_voice_state(guild_id, after.channel.id, session_id)

                            # Cancel any pending disconnect
                            if guild_id in self.disconnect_tasks:
                                self.disconnect_tasks[guild_id].cancel()
                                del self.disconnect_tasks[guild_id]

                        except Exception as e:
                            logger.error(f"Failed to auto-join {after.channel.name}: {e}")

        # Track participant join/leave events for transcript sessions (all users, not just auto-join)
        if not member.bot and member.guild.voice_client:
            bot_channel = member.guild.voice_client.channel
            voice_channel_id = str(bot_channel.id)

            # User joined the channel where bot is
            if before.channel != bot_channel and after.channel == bot_channel:
                # Check if this user was already added in start_session (avoid duplicate)
                session = self.transcript_manager.get_active_session(voice_channel_id)
                should_add = True

                if session and session.participant_events:
                    # Check if the last event was a join for this same user (within 1 second)
                    last_event = session.participant_events[-1]
                    if (last_event.event_type == "join" and
                        last_event.user_id == str(member.id)):
                        # This is a duplicate from start_session, skip it
                        should_add = False

                if should_add:
                    self.transcript_manager.add_participant(
                        channel_id=voice_channel_id,
                        user_id=str(member.id),
                        username=member.display_name
                    )

            # User left the channel where bot is
            elif before.channel == bot_channel and after.channel != bot_channel:
                self.transcript_manager.remove_participant(
                    channel_id=voice_channel_id,
                    user_id=str(member.id)
                )

        # Handle disconnect when channel becomes empty or cancel timer when someone rejoins
        # Skip if the member is a bot (prevents bot's own disconnect from re-triggering)
        if member.guild.voice_client and not member.bot:
            bot_channel = member.guild.voice_client.channel
            members_in_channel = [m for m in bot_channel.members if not m.bot]

            # User joined the bot's channel - cancel any pending disconnect
            if after.channel == bot_channel and len(members_in_channel) > 0:
                if guild_id in self.disconnect_tasks:
                    self.disconnect_tasks[guild_id].cancel()
                    del self.disconnect_tasks[guild_id]
                    logger.info(f"[{member.guild.name}] User rejoined, cancelled disconnect timer")

            # User left the bot's channel - check if channel is now empty
            if before.channel == bot_channel and len(members_in_channel) == 0:
                # Cancel any existing disconnect task
                if guild_id in self.disconnect_tasks:
                    self.disconnect_tasks[guild_id].cancel()

                # Start timeout before disconnecting
                async def disconnect_after_timeout():
                    try:
                        guild = member.guild
                        # Get timeout from ConfigManager
                        voice_cfg = self.bot.config_manager.for_guild("Voice", guild_id)
                        timeout = voice_cfg.auto_disconnect_timeout
                        await asyncio.sleep(timeout)
                        logger.info(f"[{guild.name}] Timeout reached ({timeout}s), disconnecting from {bot_channel.name}")

                        # Cancel queue processor
                        if guild_id in self.queue_tasks:
                            self.queue_tasks[guild_id].cancel()
                            del self.queue_tasks[guild_id]
                        if guild_id in self.sound_queues:
                            del self.sound_queues[guild_id]

                        # Stop listening
                        if guild_id in self.active_sinks:
                            try:
                                sink_data = self.active_sinks[guild_id]
                                if isinstance(sink_data, dict):
                                    engine = sink_data.get('engine')
                                    if engine:
                                        await engine.stop_listening()
                                if guild.voice_client:
                                    guild.voice_client.stop_listening()
                            except Exception as e:
                                logger.error(f"[{guild.name}] Error stopping listener: {e}")
                            del self.active_sinks[guild_id]

                        # Clean up current source
                        if guild_id in self.current_sources:
                            try:
                                self.current_sources[guild_id].cleanup()
                            except:
                                pass
                            del self.current_sources[guild_id]

                        # Clear speaking users
                        if guild_id in self.speaking_users:
                            del self.speaking_users[guild_id]

                        try:
                            if guild.voice_client:
                                # Get channel ID before disconnecting
                                channel_id = str(guild.voice_client.channel.id) if guild.voice_client.channel else None

                                await guild.voice_client.disconnect()
                                # Remove voice state (disconnected due to timeout)
                                from bot.core.audio.voice_state import remove_voice_state
                                remove_voice_state(guild_id)

                                # End transcript session
                                if channel_id:
                                    self.transcript_manager.end_session(channel_id)

                                logger.info(f"[{guild.name}] Disconnected after timeout")
                            else:
                                logger.debug(f"[{guild.name}] Voice client already disconnected")
                        except Exception as e:
                            logger.error(f"[{guild.name}] Error disconnecting: {e}")

                        # Clean up task reference
                        if guild_id in self.disconnect_tasks:
                            del self.disconnect_tasks[guild_id]

                    except asyncio.CancelledError:
                        logger.debug(f"[{guild.name}] Disconnect timeout cancelled")

                self.disconnect_tasks[guild_id] = self.bot.loop.create_task(disconnect_after_timeout())
                # Get timeout for logging
                voice_cfg = self.bot.config_manager.for_guild("Voice", guild_id)
                logger.info(f"[{member.guild.name}] All users left, starting {voice_cfg.auto_disconnect_timeout}s disconnect timer")

    async def cog_unload(self):
        logger.info("Unloading VoiceSpeechCog...")

        # Stop user stats writer (flushes pending updates)
        await self.stats_writer.stop()

        # Stop transcript flush task
        self.transcript_manager.stop_flush_task()

        # Stop keepalive
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        # Cancel queue tasks
        for guild_id, task in list(self.queue_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Cancel disconnect tasks
        for guild_id, task in list(self.disconnect_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop listening
        for guild_id, sink in list(self.active_sinks.items()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                try:
                    guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"Error stopping sink for guild {guild_id}: {e}")

        # Clean up audio sources
        for guild_id in list(self.current_sources.keys()):
            try:
                self.current_sources[guild_id].cleanup()
            except:
                pass

        # End all transcript sessions and disconnect from voice
        for guild in self.bot.guilds:
            if guild.voice_client:
                try:
                    # End transcript session before disconnecting
                    channel_id = str(guild.voice_client.channel.id) if guild.voice_client.channel else None
                    if channel_id:
                        self.transcript_manager.end_session(channel_id)

                    await guild.voice_client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting from guild {guild.id}: {e}")

        self.active_sinks.clear()
        self.sound_queues.clear()
        self.queue_tasks.clear()
        self.current_sources.clear()
        self.speaking_users.clear()
        logger.info("VoiceSpeechCog cleanup complete.")

    async def _process_sound_queue(self, guild_id: int):
        """Process sound queue with ducking support."""
        queue = self.sound_queues[guild_id]

        try:
            while True:
                soundfile, sound_key, volume, vc, user_id, trigger_word, channel_id, username, from_speech = await queue.get()

                if not vc or not vc.is_connected():
                    logger.warning(f"[Guild {guild_id}] Voice client disconnected, skipping {soundfile}")
                    queue.task_done()
                    continue

                if not os.path.isfile(soundfile):
                    logger.error(f"[Guild {guild_id}] Sound file missing: {soundfile}")
                    queue.task_done()
                    continue

                event = asyncio.Event()

                def after_callback(error):
                    if error:
                        logger.error(f"[Guild {guild_id}] Playback error for '{soundfile}': {error}",
                                     exc_info=error)
                    else:
                        logger.debug(f"[Guild {guild_id}] Finished playing '{soundfile}'")

                    # Clean up source
                    if guild_id in self.current_sources:
                        try:
                            self.current_sources[guild_id].cleanup()
                        except:
                            pass
                        del self.current_sources[guild_id]

                    self.bot.loop.call_soon_threadsafe(event.set)

                # Calculate effective volume (read from config dynamically for hot-reload support)
                soundboard_cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
                effective_volume = volume * soundboard_cfg.default_volume

                # Get ducking config (use ConfigManager as default)
                ducking_config = self.ducking_config.get(
                    guild_id,
                    {"enabled": soundboard_cfg.ducking_enabled, "level": soundboard_cfg.ducking_level}
                )

                # Get audio engine config from SystemConfig
                sys_cfg = self.bot.config_manager.for_guild("System")

                # Create ducked audio source
                try:
                    source = DuckedAudioSource(
                        soundfile,
                        volume=effective_volume,
                        ducking_level=ducking_config["level"],
                        duck_transition_ms=sys_cfg.audio_duck_transition_ms,
                        sample_rate=sys_cfg.audio_sample_rate,
                        channels=sys_cfg.audio_channels,
                        chunk_size=sys_cfg.audio_chunk_size
                    )
                except Exception as e:
                    logger.error(f"[Guild {guild_id}] Failed to create audio source for '{soundfile}': {e}",
                                 exc_info=True)
                    queue.task_done()
                    continue

                # Store for ducking control
                self.current_sources[guild_id] = source

                # If users are currently speaking, start ducked
                if guild_id in self.speaking_users and self.speaking_users[guild_id] and ducking_config["enabled"]:
                    source.duck()
                    logger.debug(f"[Guild {guild_id}] Starting playback ducked (users speaking)")

                # Play through Discord
                vc.play(source, after=after_callback)
                logger.info(f"[Guild {guild_id}] ▶️ Playing '{soundfile}' (volume: {effective_volume:.2f})")

                # Add to transcript (skip TTS temp files - they're already logged as [TTS])
                if vc.channel:
                    # Check if this is a TTS temp file (starts with "tmp" and ends with .wav/.mp3)
                    is_tts_temp = os.path.basename(soundfile).startswith("tmp") and soundfile.endswith((".wav", ".mp3"))

                    if not is_tts_temp:
                        # Use trigger word if available, otherwise sound name
                        sound_content = trigger_word if trigger_word else (sound_key if sound_key else os.path.basename(soundfile))
                        # Include who triggered the sound
                        content = f"[{username}] {sound_content}"
                        # Use "TRIGGER" for speech-triggered sounds, "SOUND" for manual commands
                        message_type = "TRIGGER" if from_speech else "SOUND"
                        self.transcript_manager.add_bot_message(
                            channel_id=str(vc.channel.id),
                            bot_id=str(self.bot.user.id),
                            bot_name=self.bot.user.name,
                            message_type=message_type,
                            content=content
                        )

                # Update soundboard play stats
                soundboard_cog = self.bot.get_cog("Soundboard")
                if soundboard_cog and sound_key:
                    soundboard_cog.increment_play_stats(guild_id, soundfile, str(user_id), trigger_word)

                # Track user trigger stats (queue for background writing - non-blocking)
                if trigger_word and channel_id:
                    try:
                        from bot.core.stats.user_triggers import get_stats_writer
                        stats_writer = get_stats_writer()
                        if stats_writer:
                            stats_writer.queue_update(
                                user_id=str(user_id),
                                username=username,
                                guild_id=str(guild_id),
                                channel_id=str(channel_id),
                                trigger_word=trigger_word
                            )
                            logger.debug(f"[Guild {guild_id}] Queued trigger stat for '{trigger_word}' by {username}")
                        else:
                            logger.warning(f"[Guild {guild_id}] UserStatsWriter not initialized, skipping stat tracking")
                    except Exception as e:
                        logger.error(f"[Guild {guild_id}] Failed to queue user trigger stat: {e}", exc_info=True)

                # Get playback timeout from unified config manager
                playback_timeout = 30.0  # default
                if hasattr(self.bot, 'config_manager'):
                    playback_timeout = self.bot.config_manager.get("Voice", "sound_playback_timeout", guild_id)

                try:
                    await asyncio.wait_for(event.wait(), timeout=playback_timeout)
                except asyncio.TimeoutError:
                    logger.error(f"[Guild {guild_id}] Playback timeout for '{soundfile}'")
                    if vc.is_playing():
                        vc.stop()

                queue.task_done()

        except asyncio.CancelledError:
            logger.info(f"[Guild {guild_id}] Queue processor cancelled")
            raise
        except Exception as e:
            logger.critical(f"[Guild {guild_id}] Unexpected error: {e}", exc_info=True)

    async def queue_sound(self, guild_id: int, soundfile: str, user: discord.User, sound_key: str = None,
                          volume: float = 1.0, trigger_word: str = None, channel_id: int = None,
                          from_speech: bool = False):
        """Queue a sound for playback.

        Args:
            from_speech: True if triggered by speech recognition, False if from manual command
        """
        if guild_id not in self.sound_queues:
            self.sound_queues[guild_id] = asyncio.Queue()
            self.queue_tasks[guild_id] = asyncio.create_task(self._process_sound_queue(guild_id))

        await self.sound_queues[guild_id].put((soundfile, sound_key, volume, user.guild.voice_client, user.id, trigger_word, channel_id, user.display_name, from_speech))

        queue_size = self.sound_queues[guild_id].qsize()
        logger.debug(
            f"[Guild {guild_id}] Queued '{soundfile}' (volume: {volume:.2f}, queue size: {queue_size})")

        # Warn if queue size exceeds threshold
        warning_threshold = 50  # default
        if hasattr(self.bot, 'config_manager'):
            warning_threshold = self.bot.config_manager.get("Voice", "sound_queue_warning_size", guild_id)

        if queue_size > warning_threshold:
            logger.warning(f"[Guild {guild_id}] Sound queue size ({queue_size}) exceeds warning threshold ({warning_threshold})")

    async def _keepalive_loop(self):
        """Keepalive loop to prevent voice disconnection."""
        await self.bot.wait_until_ready()
        logger.info("Keepalive loop started")
        try:
            while True:
                for guild_id, sink in list(self.active_sinks.items()):
                    try:
                        guild = self.bot.get_guild(guild_id)
                        if not guild or not guild.voice_client:
                            continue
                        vc = guild.voice_client

                        # Only send silence if not playing
                        if vc.is_playing():
                            continue

                        # Check if voice connection is fully established (ssrc must be an integer)
                        from discord.utils import MISSING
                        if vc.ssrc is MISSING or not isinstance(vc.ssrc, int):
                            logger.debug(f"[Guild {guild_id}] Skipping keepalive - connection not ready (ssrc={vc.ssrc})")
                            continue

                        silence = b'\xf8\xff\xfe'
                        vc.send_audio_packet(silence, encode=False)
                        logger.info(f"[Guild {guild_id}] Keepalive Sent")
                    except Exception as e:
                        logger.error(f"[Guild {guild_id}] Keepalive error: {e}", exc_info=True)
                # Read from config dynamically for hot-reload support
                sys_cfg = self.bot.config_manager.for_guild("System")
                await asyncio.sleep(sys_cfg.keepalive_interval)
        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled")
            raise


    def _create_speech_listener(self, ctx):
        """Create a speech recognition listener with ducking support and error handling."""
        guild_id = ctx.guild.id
        # Get the voice channel ID from the bot's voice client (as string for transcript session)
        voice_channel_id = str(ctx.guild.voice_client.channel.id) if ctx.guild.voice_client else None

        def text_callback(member: discord.Member, text: str):
            """
            CRITICAL: Keep this callback MINIMAL and FAST.
            This runs in the speech recognition thread - any blocking delays voice packets.
            Offload ALL heavy work to async tasks via run_coroutine_threadsafe.

            Args:
                member: Discord member who spoke
                text: Transcribed text (plain string from pluggable engines, already parsed)
            """
            try:
                # ===== FAST: Parse and validate (keep in callback) =====
                transcribed_text = text.strip()
                if not transcribed_text:
                    return

                # ===== FAST: Create data dict (keep in callback) =====
                guild_name = ctx.guild.name
                channel_name = ctx.guild.voice_client.channel.name if ctx.guild.voice_client else "Unknown"

                transcription_data = {
                    "timestamp": datetime.now().isoformat(),
                    "guild_id": guild_id,
                    "guild": guild_name,
                    "channel_id": voice_channel_id,
                    "channel": channel_name,
                    "user_id": str(member.id),
                    "user": member.display_name,
                    "user_avatar_url": member.display_avatar.url if member.display_avatar else None,
                    "text": transcribed_text,
                    "triggers": []
                }

                # ===== FAST: Console log (keep in callback) =====
                logger.debug(
                    f"\033[92m[{guild_name}] [{member.id}] [{member.display_name}] : {transcribed_text}\033[0m"
                )

                # ===== OFFLOAD: Everything else to async task =====
                async def process_transcription():
                    """Process transcription asynchronously - all heavy/blocking operations here."""
                    try:
                        # Get data collector
                        from bot.core.admin.data_collector import get_data_collector
                        data_collector = get_data_collector()

                        # Update user info
                        if data_collector:
                            data_collector.update_user_info(member)

                        # Add to transcript session
                        self.transcript_manager.add_transcript(
                            channel_id=voice_channel_id,
                            user_id=str(member.id),
                            username=member.display_name,
                            text=transcribed_text,
                            confidence=1.0
                        )

                        # Check for soundboard triggers
                        soundboard_cog = self.bot.get_cog("Soundboard")
                        if not soundboard_cog:
                            # No soundboard - just log and record
                            logger.debug(f"[TRANSCRIPTION] {json.dumps(transcription_data)}")
                            if data_collector:
                                data_collector.record_transcription(transcription_data)
                            return

                        # Get triggered sound files
                        files = soundboard_cog.get_soundfiles_for_text(guild_id, member.id, transcribed_text)
                        if files:
                            # Queue all triggered sounds
                            for soundfile, sound_key, volume, trigger_word in files:
                                if os.path.isfile(soundfile):
                                    # Add trigger info
                                    transcription_data["triggers"].append({
                                        "word": trigger_word,
                                        "sound": os.path.basename(soundfile),
                                        "volume": volume
                                    })
                                    # Queue sound (speech-triggered)
                                    await self.queue_sound(guild_id, soundfile, member, sound_key, volume, trigger_word, voice_channel_id, from_speech=True)

                        # Log transcription with triggers
                        logger.debug(f"[TRANSCRIPTION] {json.dumps(transcription_data)}")

                        # Record to data collector (websocket broadcast)
                        if data_collector:
                            data_collector.record_transcription(transcription_data)

                    except Exception as e:
                        logger.error(f"Error processing transcription: {e}", exc_info=True)

                # Schedule async processing - don't wait for it
                asyncio.run_coroutine_threadsafe(process_transcription(), self.bot.loop)

            except Exception as e:
                logger.error(f"Error in text_callback: {e}", exc_info=True)

        # Ducking callback for speech engines
        def ducking_callback(guild_id: int, member: discord.Member, is_speaking: bool):
            """Handle speaking events for audio ducking."""
            if is_speaking:
                self._handle_user_speaking_start(guild_id, member.id)
            else:
                self._handle_user_speaking_stop(guild_id, member.id)

        # Get speech config to determine which engine to use
        from bot.core.audio.speech_engines import create_speech_engine
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        logger.info(f"[Guild {guild_id}] Creating speech engine: {speech_cfg.engine}")

        # Create speech engine (Vosk or Whisper based on config)
        engine = create_speech_engine(
            self.bot,
            text_callback,
            engine_type=speech_cfg.engine,
            ducking_callback=ducking_callback
        )

        return engine

    def _handle_user_speaking_start(self, guild_id: int, user_id: int):
        """Handle when a user starts speaking - duck the audio."""
        # Initialize speaking users set if needed
        if guild_id not in self.speaking_users:
            self.speaking_users[guild_id] = set()

        # Add user to speaking set
        self.speaking_users[guild_id].add(user_id)

        # Check if ducking is enabled (use ConfigManager as default)
        soundboard_cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
        ducking_cfg = self.ducking_config.get(
            guild_id,
            {"enabled": soundboard_cfg.ducking_enabled, "level": soundboard_cfg.ducking_level}
        )
        if not ducking_cfg["enabled"]:
            return

        # Duck current audio if playing
        if guild_id in self.current_sources:
            self.current_sources[guild_id].duck()
            logger.debug(f"[Guild {guild_id}] 🔉 Ducking audio (user {user_id} speaking)")

    def _handle_user_speaking_stop(self, guild_id: int, user_id: int):
        """Handle when a user stops speaking - unduck if no one else speaking."""
        if guild_id not in self.speaking_users:
            return

        # Remove user from speaking set
        self.speaking_users[guild_id].discard(user_id)

        # Check if ducking is enabled (use ConfigManager as default)
        soundboard_cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
        ducking_cfg = self.ducking_config.get(
            guild_id,
            {"enabled": soundboard_cfg.ducking_enabled, "level": soundboard_cfg.ducking_level}
        )
        if not ducking_cfg["enabled"]:
            return

        # Unduck only if no one else is speaking
        if not self.speaking_users[guild_id] and guild_id in self.current_sources:
            self.current_sources[guild_id].unduck()
            logger.debug(f"[Guild {guild_id}] 🔊 Unducking audio (no users speaking)")


    @commands.command(help="Configure audio ducking settings")
    async def ducking(self, ctx, setting: str = None, value: str = None):
        """
        Configure audio ducking when users speak.

        Usage:
            ~ducking - Show current settings
            ~ducking on/off - Enable/disable ducking for this guild
            ~ducking level <0-100> - Set ducking level for this guild
            ~ducking reset - Reset to global default config

        Examples:
            ~ducking on
            ~ducking level 30
            ~ducking off
            ~ducking reset
        """
        guild_id = ctx.guild.id

        # Get current config (use ConfigManager as default)
        soundboard_cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
        if guild_id not in self.ducking_config:
            # Initialize with ConfigManager values
            self.ducking_config[guild_id] = {
                "enabled": soundboard_cfg.ducking_enabled,
                "level": soundboard_cfg.ducking_level
            }

        ducking_cfg = self.ducking_config[guild_id]

        # Show current settings
        if setting is None:
            status = "✅ Enabled" if ducking_cfg["enabled"] else "❌ Disabled"
            level_percent = int(ducking_cfg["level"] * 100)

            # Check if using global default or guild override
            using_global = (guild_id not in self.ducking_config or
                          (ducking_cfg["enabled"] == soundboard_cfg.ducking_enabled and
                           ducking_cfg["level"] == soundboard_cfg.ducking_level))
            source = "(using global config)" if using_global else "(guild override)"

            embed = discord.Embed(
                title="🔊 Audio Ducking Settings",
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value=f"{status} {source}", inline=False)
            embed.add_field(name="Duck Level", value=f"{level_percent}%", inline=True)
            embed.add_field(
                name="ℹ️ Info",
                value="Ducking automatically reduces audio volume when users speak.\n"
                      f"Global default: {'Enabled' if soundboard_cfg.ducking_enabled else 'Disabled'} @ {int(soundboard_cfg.ducking_level * 100)}%",
                inline=False
            )
            embed.set_footer(text="Use ~ducking on/off or ~ducking level <0-100>")

            return await ctx.send(embed=embed)

        # Handle reset to global default
        if setting.lower() in ["reset", "default", "global"]:
            if guild_id in self.ducking_config:
                del self.ducking_config[guild_id]
            await UserFeedback.success(ctx,
                f"Reset to global default: {'Enabled' if soundboard_cfg.ducking_enabled else 'Disabled'} @ {int(soundboard_cfg.ducking_level * 100)}%")
            return

        # Handle on/off
        if setting.lower() in ["on", "enable", "enabled", "yes"]:
            ducking_cfg["enabled"] = True
            await UserFeedback.success(ctx, f"Audio ducking **enabled** (level: {int(ducking_cfg['level'] * 100)}%)")
            return

        if setting.lower() in ["off", "disable", "disabled", "no"]:
            ducking_cfg["enabled"] = False

            # Unduck if currently ducked
            if guild_id in self.current_sources:
                self.current_sources[guild_id].unduck()

            await UserFeedback.info(ctx, "Audio ducking **disabled**")
            return

        # Handle level setting
        if setting.lower() in ["level", "amount", "volume"]:
            if value is None:
                return await UserFeedback.error(ctx, "Please specify a level between 0-100. Example: `~ducking level 50`")

            try:
                level_percent = int(value)
                if not 0 <= level_percent <= 100:
                    return await UserFeedback.error(ctx, "Level must be between 0 and 100")

                ducking_cfg["level"] = level_percent / 100.0
                await UserFeedback.success(ctx, f"Ducking level set to **{level_percent}%**")

            except ValueError:
                await UserFeedback.error(ctx, "Invalid level. Please use a number between 0-100")
            return

        await UserFeedback.error(ctx, "Invalid setting. Use: `~ducking on/off` or `~ducking level <0-100>`")

    @commands.command(help="Join a voice channel (optional: channel name or ID)")
    async def join(self, ctx, *, channel_input: str = None):
        from bot.core.audio.auto_join import add_auto_join_channel

        # If already connected
        if ctx.voice_client:
            return await UserFeedback.info(ctx, "Already connected to a voice channel.")

        # Determine which channel to join
        target_channel = None

        if channel_input:
            # Try to find channel by ID first
            try:
                channel_id = int(channel_input)
                target_channel = ctx.guild.get_channel(channel_id)
                if target_channel and not isinstance(target_channel, discord.VoiceChannel):
                    return await UserFeedback.error(ctx, f"Channel with ID `{channel_id}` is not a voice channel.")
            except ValueError:
                # Not an ID, search by name (case-insensitive)
                channel_name_lower = channel_input.lower()
                for channel in ctx.guild.voice_channels:
                    if channel.name.lower() == channel_name_lower:
                        target_channel = channel
                        break

                # If exact match not found, try partial match
                if not target_channel:
                    for channel in ctx.guild.voice_channels:
                        if channel_name_lower in channel.name.lower():
                            target_channel = channel
                            break

            if not target_channel:
                return await UserFeedback.error(ctx, f"Could not find voice channel: `{channel_input}`")
        else:
            # No argument provided, join caller's channel
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await UserFeedback.warning(ctx, "You're not in a voice channel. Please specify a channel name or ID.")
            target_channel = ctx.author.voice.channel

        # Connect to the channel
        try:
            vc = await target_channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)

            # Start keepalive task if not already running
            if not self._keepalive_task:
                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())

            # Enable auto-join for this channel
            voice_cfg = self.bot.config_manager.for_guild("Voice", ctx.guild.id)
            if voice_cfg.auto_join_enabled:
                add_auto_join_channel(ctx.guild.id, target_channel.id)
                logger.info(f"Auto-join enabled for {target_channel.name} in guild {ctx.guild.id}")

            # Auto-start listening (always)
            engine = self._create_speech_listener(ctx)
            await engine.start_listening(vc)
            self.active_sinks[ctx.guild.id] = {
                'engine': engine,
                'sink': engine.get_sink()
            }

            # Start transcript session
            session_id = None
            members_in_channel = [m for m in target_channel.members if not m.bot]
            if members_in_channel:
                first_member = members_in_channel[0]
                session_id = self.transcript_manager.start_session(
                    channel_id=str(target_channel.id),
                    guild_id=str(ctx.guild.id),
                    guild_name=ctx.guild.name,
                    channel_name=target_channel.name,
                    first_user_id=str(first_member.id),
                    first_username=first_member.display_name
                )

            # Save voice state for persistence across restarts (with session_id)
            from bot.core.audio.voice_state import save_voice_state
            save_voice_state(ctx.guild.id, target_channel.id, session_id)

            await UserFeedback.success(ctx, f"Joined `{target_channel.name}` and started listening! 🎧\n*Auto-join enabled for this channel.*")
        except Exception as e:
            logger.error(f"Failed to join channel {target_channel.name}: {e}", exc_info=True)
            await UserFeedback.error(ctx, f"Failed to join `{target_channel.name}`: {str(e)}")

    @commands.command(help="Leave the voice channel")
    async def leave(self, ctx):
        vc = ctx.voice_client
        if not vc:
            return await UserFeedback.warning(ctx, "Not currently connected.")

        guild_id = ctx.guild.id

        # Cancel queue processor
        if guild_id in self.queue_tasks:
            self.queue_tasks[guild_id].cancel()
            del self.queue_tasks[guild_id]
        if guild_id in self.sound_queues:
            del self.sound_queues[guild_id]

        # Clean up audio source
        if guild_id in self.current_sources:
            try:
                self.current_sources[guild_id].cleanup()
            except:
                pass
            del self.current_sources[guild_id]

        # Add bot leave message to transcript before ending session
        channel_id = str(vc.channel.id) if vc.channel else None
        if channel_id:
            self.transcript_manager.add_bot_message(
                channel_id=channel_id,
                bot_id=str(self.bot.user.id),
                bot_name=self.bot.user.name,
                message_type="COMMAND",
                content=f"Left voice channel (requested by {ctx.author.display_name})"
            )
            self.transcript_manager.end_session(channel_id)

        await vc.disconnect()

        # Remove voice state for persistence
        from bot.core.audio.voice_state import remove_voice_state
        remove_voice_state(ctx.guild.id)

        await UserFeedback.success(ctx, "Left the voice channel.")

        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    @commands.command(help="Disable auto-join for a voice channel")
    async def unjoin(self, ctx, *, channel_input: str = None):
        """
        Disable auto-join for a voice channel.

        Usage:
            ~unjoin              - Disable auto-join for your current voice channel
            ~unjoin pubg         - Disable auto-join for channel named 'pubg'
        """
        from bot.core.audio.auto_join import remove_auto_join_channel, get_guild_auto_join_channels

        target_channel = None

        if channel_input:
            # Search for channel by name
            channel_name_lower = channel_input.lower()
            for channel in ctx.guild.voice_channels:
                if channel.name.lower() == channel_name_lower:
                    target_channel = channel
                    break

            # Try partial match if exact match not found
            if not target_channel:
                for channel in ctx.guild.voice_channels:
                    if channel_name_lower in channel.name.lower():
                        target_channel = channel
                        break

            if not target_channel:
                return await UserFeedback.error(ctx, f"Could not find voice channel: `{channel_input}`")
        else:
            # No argument provided, use caller's current channel
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await UserFeedback.warning(ctx, "You're not in a voice channel. Please specify a channel name.")
            target_channel = ctx.author.voice.channel

        # Remove auto-join
        removed = remove_auto_join_channel(ctx.guild.id, target_channel.id)

        if removed:
            await UserFeedback.success(ctx, f"Auto-join disabled for `{target_channel.name}`")
        else:
            await UserFeedback.info(ctx, f"`{target_channel.name}` didn't have auto-join enabled")

    @commands.command(name="autojoin", help="Manage auto-join channels")
    async def autojoin_cmd(self, ctx, action: str = None):
        """
        Manage auto-join channels.

        Usage:
            ~autojoin list       - Show all auto-join enabled channels
        """
        from bot.core.audio.auto_join import get_guild_auto_join_channels

        if action and action.lower() == "list":
            channel_ids = get_guild_auto_join_channels(ctx.guild.id)

            if not channel_ids:
                return await UserFeedback.info(ctx, "No auto-join channels configured")

            # Build channel list
            channel_names = []
            for channel_id in channel_ids:
                channel = ctx.guild.get_channel(int(channel_id))
                if channel:
                    channel_names.append(f"• {channel.name}")
                else:
                    channel_names.append(f"• Unknown channel (ID: {channel_id})")

            embed = discord.Embed(
                title="🎤 Auto-Join Channels",
                description="\n".join(channel_names),
                color=discord.Color.blue()
            )
            embed.set_footer(text=f"{len(channel_ids)} channel(s) configured")

            await ctx.send(embed=embed)
        else:
            await UserFeedback.info(ctx, "Usage: `~autojoin list` - Show all auto-join channels")

    @commands.command(help="Start listening")
    async def start(self, ctx):
        if not ctx.voice_client:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await UserFeedback.warning(ctx, "You're not in a voice channel!")
            channel = ctx.author.voice.channel
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
            if not self._keepalive_task:
                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())
        else:
            vc = ctx.voice_client

        engine = self._create_speech_listener(ctx)
        await engine.start_listening(vc)
        self.active_sinks[ctx.guild.id] = {
            'engine': engine,
            'sink': engine.get_sink()
        }
        await UserFeedback.success(ctx, "Listening...")

    @commands.command(help="Stop listening")
    async def stop(self, ctx):
        vc = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await UserFeedback.warning(ctx, "Not currently listening.")

        # Stop the speech engine
        sink_data = self.active_sinks.get(ctx.guild.id)
        if sink_data and isinstance(sink_data, dict):
            engine = sink_data.get('engine')
            if engine:
                await engine.stop_listening()

        vc.stop_listening()
        self.active_sinks.pop(ctx.guild.id, None)
        await UserFeedback.success(ctx, "Stopped listening.")

    @commands.command(help="Play a sound from a trigger word")
    async def play(self, ctx, *, input_text: str):
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await UserFeedback.warning(ctx, "Join a voice channel first!")

        soundboard_cog = self.bot.get_cog("Soundboard")
        if not soundboard_cog:
            return await UserFeedback.warning(ctx, "Soundboard cog not loaded.")

        # Get list of (soundfile, sound_key, volume, trigger_word) tuples
        files = soundboard_cog.get_soundfiles_for_text(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            text=input_text
        )

        if files:
            voice_channel_id = vc.channel.id if vc and vc.channel else None
            for soundfile, sound_key, volume, trigger_word in files:
                if os.path.isfile(soundfile):
                    await self.queue_sound(ctx.guild.id, soundfile, ctx.author, sound_key, volume, trigger_word, voice_channel_id)
            await UserFeedback.success(ctx, f"Queued {len(files)} sound(s).")
        else:
            await UserFeedback.info(ctx, f"No sounds found for: `{input_text}`")

    @commands.command(help="Show current sound queue")
    async def queue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues or self.sound_queues[guild_id].empty():
            return await UserFeedback.info(ctx, "Queue is empty.")
        await UserFeedback.info(ctx, f"{self.sound_queues[guild_id].qsize()} sound(s) in queue")

    @commands.command(help="Clear the sound queue")
    async def clearqueue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues:
            return await UserFeedback.info(ctx, "No queue exists.")
        old_size = self.sound_queues[guild_id].qsize()
        self.sound_queues[guild_id] = asyncio.Queue()
        await UserFeedback.success(ctx, f"Cleared {old_size} sound(s) from queue")


async def setup(bot):
    try:
        await bot.add_cog(VoiceSpeechCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")