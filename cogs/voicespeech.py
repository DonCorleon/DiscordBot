"""
Updated VoiceSpeechCog with PyAudio and audio ducking support.
"""

import json
import discord
from discord.ext import commands, voice_recv
from discord.ext.voice_recv.extras import speechrecognition as dsr
import asyncio
import os
from base_cog import BaseCog, logger
from utils.pyaudio_player import PyAudioPlayer


class VoiceSpeechCog(BaseCog):
    """
    Voice and speech recognition cog with audio ducking.
    Automatically reduces volume when users speak.
    """

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.active_sinks = {}
        self._keepalive_interval = 30
        self._keepalive_task = None
        self.sound_queues = {}  # {guild_id: asyncio.Queue}
        self.queue_tasks = {}  # {guild_id: Task}

        # PyAudio players per guild
        self.audio_players = {}  # {guild_id: PyAudioPlayer}

        # Ducking configuration per guild
        self.ducking_config = {}  # {guild_id: {"enabled": bool, "level": float}}

        # Track speaking users per guild
        self.speaking_users = {}  # {guild_id: set(user_ids)}

    def _get_or_create_player(self, guild_id: int) -> PyAudioPlayer:
        """Get or create a PyAudio player for a guild."""
        if guild_id not in self.audio_players:
            # Get ducking configuration
            config = self.ducking_config.get(guild_id, {"enabled": True, "level": 0.5})

            player = PyAudioPlayer(
                ducking_level=config["level"],
                duck_transition_ms=50
            )
            self.audio_players[guild_id] = player
            logger.info(
                f"[Guild {guild_id}] Created PyAudio player (ducking: {config['enabled']}, level: {config['level'] * 100}%)")

        return self.audio_players[guild_id]

    def _cleanup_player(self, guild_id: int):
        """Clean up PyAudio player for a guild."""
        if guild_id in self.audio_players:
            self.audio_players[guild_id].cleanup()
            del self.audio_players[guild_id]
            logger.debug(f"[Guild {guild_id}] Cleaned up PyAudio player")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        if before.channel is None:
            return
        if not member.guild.voice_client:
            return
        bot_channel = member.guild.voice_client.channel
        if before.channel.id != bot_channel.id:
            return
        members_in_channel = [m for m in bot_channel.members if not m.bot]
        if len(members_in_channel) == 0:
            logger.info(f"[{member.guild.name}] All users left, auto-disconnecting")
            guild_id = member.guild.id

            # Cancel queue processor
            if guild_id in self.queue_tasks:
                self.queue_tasks[guild_id].cancel()
                del self.queue_tasks[guild_id]
            if guild_id in self.sound_queues:
                del self.sound_queues[guild_id]

            # Stop listening
            if guild_id in self.active_sinks:
                try:
                    member.guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"[{member.guild.name}] Error stopping listener: {e}")
                del self.active_sinks[guild_id]

            # Clean up audio player
            self._cleanup_player(guild_id)

            # Clear speaking users
            if guild_id in self.speaking_users:
                del self.speaking_users[guild_id]

            try:
                await member.guild.voice_client.disconnect()
                logger.info(f"[{member.guild.name}] Auto-disconnected")
            except Exception as e:
                logger.error(f"[{member.guild.name}] Error disconnecting: {e}")

    async def cog_unload(self):
        logger.info("Unloading VoiceSpeechCog...")

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

        # Stop listening
        for guild_id, sink in list(self.active_sinks.items()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                try:
                    guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"Error stopping sink for guild {guild_id}: {e}")

        # Disconnect from voice
        for guild in self.bot.guilds:
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting from guild {guild.id}: {e}")

        # Clean up all audio players
        for guild_id in list(self.audio_players.keys()):
            self._cleanup_player(guild_id)

        self.active_sinks.clear()
        self.sound_queues.clear()
        self.queue_tasks.clear()
        self.speaking_users.clear()
        logger.info("VoiceSpeechCog cleanup complete.")

    async def _process_sound_queue(self, guild_id: int, default_volume: float = 0.5):
        """Process the sound queue for a guild."""
        queue = self.sound_queues[guild_id]
        player = self._get_or_create_player(guild_id)

        try:
            while True:
                soundfile, sound_key, volume, vc, user_id = await queue.get()

                if not vc or not vc.is_connected():
                    logger.warning(f"[Guild {guild_id}] Voice client disconnected, skipping {soundfile}")
                    queue.task_done()
                    continue

                if not os.path.isfile(soundfile):
                    logger.error(f"[Guild {guild_id}] Sound file missing: {soundfile}")
                    queue.task_done()
                    continue

                # Calculate effective volume
                effective_volume = volume * default_volume

                # Set up playback completion event
                event = asyncio.Event()

                def on_playback_finished():
                    """Callback when playback finishes."""
                    logger.debug(f"[Guild {guild_id}] Finished playing '{soundfile}'")
                    self.bot.loop.call_soon_threadsafe(event.set)

                try:
                    # Play using PyAudio with ducking support
                    player.play(
                        soundfile,
                        volume=effective_volume,
                        on_finished=on_playback_finished
                    )

                    logger.info(f"[Guild {guild_id}] ▶️ Playing '{soundfile}' (volume: {effective_volume:.2f})")

                    # Update soundboard play stats
                    soundboard_cog = self.bot.get_cog("Soundboard")
                    if soundboard_cog and sound_key:
                        soundboard_cog.increment_play_stats(guild_id, soundfile, str(user_id))

                    # Wait for playback to finish
                    try:
                        await asyncio.wait_for(event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.error(f"[Guild {guild_id}] Playback timeout for '{soundfile}'")
                        player.stop()

                except Exception as e:
                    logger.error(f"[Guild {guild_id}] Error playing '{soundfile}': {e}", exc_info=True)

                finally:
                    queue.task_done()

        except asyncio.CancelledError:
            logger.info(f"[Guild {guild_id}] Queue processor cancelled")
            raise
        except Exception as e:
            logger.critical(f"[Guild {guild_id}] Unexpected error: {e}", exc_info=True)

    async def queue_sound(self, guild_id: int, soundfile: str, user: discord.User, sound_key: str = None,
                          volume: float = 1.0):
        """Queue a sound for playback."""
        if guild_id not in self.sound_queues:
            self.sound_queues[guild_id] = asyncio.Queue()
            self.queue_tasks[guild_id] = asyncio.create_task(self._process_sound_queue(guild_id))

        await self.sound_queues[guild_id].put((soundfile, sound_key, volume, user.guild.voice_client, user.id))
        logger.debug(
            f"[Guild {guild_id}] Queued '{soundfile}' (volume: {volume:.2f}, queue size: {self.sound_queues[guild_id].qsize()})")

    def _handle_user_speaking_start(self, guild_id: int, user_id: int):
        """Handle when a user starts speaking."""
        # Initialize speaking users set if needed
        if guild_id not in self.speaking_users:
            self.speaking_users[guild_id] = set()

        # Add user to speaking set
        self.speaking_users[guild_id].add(user_id)

        # Check if ducking is enabled
        config = self.ducking_config.get(guild_id, {"enabled": True, "level": 0.5})
        if not config["enabled"]:
            return

        # Duck the audio if player exists and is playing
        if guild_id in self.audio_players:
            player = self.audio_players[guild_id]
            if player.is_playing:
                player.duck()
                logger.debug(f"[Guild {guild_id}] Ducking audio (user {user_id} speaking)")

    def _handle_user_speaking_stop(self, guild_id: int, user_id: int):
        """Handle when a user stops speaking."""
        if guild_id not in self.speaking_users:
            return

        # Remove user from speaking set
        self.speaking_users[guild_id].discard(user_id)

        # Check if ducking is enabled
        config = self.ducking_config.get(guild_id, {"enabled": True, "level": 0.5})
        if not config["enabled"]:
            return

        # Unduck only if no one else is speaking
        if not self.speaking_users[guild_id] and guild_id in self.audio_players:
            player = self.audio_players[guild_id]
            if player.is_playing:
                player.unduck()
                logger.debug(f"[Guild {guild_id}] Unducking audio (no users speaking)")

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
                        if guild_id in self.audio_players:
                            player = self.audio_players[guild_id]
                            if player.is_playing:
                                continue

                        silence = b'\xf8\xff\xfe'
                        vc.send_audio_packet(silence, encode=False)
                    except Exception as e:
                        logger.error(f"[Guild {guild_id}] Keepalive error: {e}", exc_info=True)
                await asyncio.sleep(self._keepalive_interval)
        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled")
            raise

    def _create_speech_listener(self, ctx):
        """Create a speech recognition listener with ducking support."""
        guild_id = ctx.guild.id

        def text_callback(user: discord.User, text: str):
            try:
                result = json.loads(text)
                transcribed_text = result.get("text", "").strip()
                if not transcribed_text:
                    return

                guild_name = ctx.guild.name

                logger.info(
                    f"\033[92m[{guild_name}] [{user.id}] [{user.display_name}] : {transcribed_text}\033[0m"
                )

                # Update user info in data collector
                from utils.admin_data_collector import get_data_collector
                data_collector = get_data_collector()
                if data_collector:
                    data_collector.update_user_info(user)

                soundboard_cog = self.bot.get_cog("Soundboard")
                if not soundboard_cog:
                    return

                files = soundboard_cog.get_soundfiles_for_text(ctx.guild.id, user.id, transcribed_text)
                if files:
                    async def queue_all():
                        for soundfile, sound_key, volume in files:
                            if os.path.isfile(soundfile):
                                await self.queue_sound(ctx.guild.id, soundfile, user, sound_key, volume)

                    asyncio.run_coroutine_threadsafe(queue_all(), self.bot.loop)

            except Exception as e:
                logger.error(f"Error in text_callback: {e}", exc_info=True)

        class SRListener(dsr.SpeechRecognitionSink):
            def __init__(self, parent_cog):
                super().__init__(default_recognizer="vosk", phrase_time_limit=10, text_cb=text_callback)
                self.parent_cog = parent_cog

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_start(self, member: discord.Member):
                logger.debug(f"🎤 {member.display_name} started speaking")
                # Trigger ducking
                self.parent_cog._handle_user_speaking_start(guild_id, member.id)

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_stop(self, member: discord.Member):
                logger.debug(f"🔇 {member.display_name} stopped speaking")
                # Stop ducking
                self.parent_cog._handle_user_speaking_stop(guild_id, member.id)

        return SRListener(self)

    @commands.command(help="Configure audio ducking settings")
    async def ducking(self, ctx, setting: str = None, value: str = None):
        """
        Configure audio ducking when users speak.

        Usage:
            ~ducking - Show current settings
            ~ducking on/off - Enable/disable ducking
            ~ducking level <0-100> - Set ducking level (default 50%)

        Examples:
            ~ducking on
            ~ducking level 30
            ~ducking off
        """
        guild_id = ctx.guild.id

        # Get current config
        if guild_id not in self.ducking_config:
            self.ducking_config[guild_id] = {"enabled": True, "level": 0.5}

        config = self.ducking_config[guild_id]

        # Show current settings
        if setting is None:
            status = "✅ Enabled" if config["enabled"] else "❌ Disabled"
            level_percent = int(config["level"] * 100)

            embed = discord.Embed(
                title="🔊 Audio Ducking Settings",
                color=discord.Color.blue()
            )
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Duck Level", value=f"{level_percent}%", inline=True)
            embed.add_field(
                name="ℹ️ Info",
                value="Ducking automatically reduces audio volume when users speak.",
                inline=False
            )
            embed.set_footer(text="Use ~ducking on/off or ~ducking level <0-100>")

            return await ctx.send(embed=embed)

        # Handle on/off
        if setting.lower() in ["on", "enable", "enabled", "yes"]:
            config["enabled"] = True

            # Update player if exists
            if guild_id in self.audio_players:
                self.audio_players[guild_id].set_ducking_level(config["level"])

            await ctx.send(f"✅ Audio ducking **enabled** (level: {int(config['level'] * 100)}%)")
            return

        if setting.lower() in ["off", "disable", "disabled", "no"]:
            config["enabled"] = False

            # Unduck if currently ducked
            if guild_id in self.audio_players:
                self.audio_players[guild_id].unduck()

            await ctx.send("❌ Audio ducking **disabled**")
            return

        # Handle level setting
        if setting.lower() in ["level", "amount", "volume"]:
            if value is None:
                return await ctx.send("❌ Please specify a level between 0-100. Example: `~ducking level 50`")

            try:
                level_percent = int(value)
                if not 0 <= level_percent <= 100:
                    return await ctx.send("❌ Level must be between 0 and 100")

                config["level"] = level_percent / 100.0

                # Update player if exists
                if guild_id in self.audio_players:
                    self.audio_players[guild_id].set_ducking_level(config["level"])

                await ctx.send(f"🔊 Ducking level set to **{level_percent}%**")

            except ValueError:
                await ctx.send("❌ Invalid level. Please use a number between 0-100")
            return

        await ctx.send("❌ Invalid setting. Use: `~ducking on/off` or `~ducking level <0-100>`")

    @commands.command(help="Join a voice channel (optional: channel name or ID)")
    async def join(self, ctx, *, channel_input: str = None):
        # If already connected
        if ctx.voice_client:
            return await ctx.send("✅ Already connected to a voice channel.")

        # Determine which channel to join
        target_channel = None

        if channel_input:
            # Try to find channel by ID first
            try:
                channel_id = int(channel_input)
                target_channel = ctx.guild.get_channel(channel_id)
                if target_channel and not isinstance(target_channel, discord.VoiceChannel):
                    return await ctx.send(f"❌ Channel with ID `{channel_id}` is not a voice channel.")
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
                return await ctx.send(f"❌ Could not find voice channel: `{channel_input}`")
        else:
            # No argument provided, join caller's channel
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.send("⚠️ You're not in a voice channel. Please specify a channel name or ID.")
            target_channel = ctx.author.voice.channel

        # Connect to the channel
        try:
            vc = await target_channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)

            # Start keepalive task if not already running
            if not self._keepalive_task:
                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())

            # Auto-start listening ONLY if a channel was specified
            if channel_input:
                sink = self._create_speech_listener(ctx)
                vc.listen(sink)
                self.active_sinks[ctx.guild.id] = sink
                await ctx.send(f"✅ Joined `{target_channel.name}` and started listening! 🎧")
            else:
                await ctx.send(f"✅ Joined `{target_channel.name}` and ready to listen.")
        except Exception as e:
            logger.error(f"Failed to join channel {target_channel.name}: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to join `{target_channel.name}`: {str(e)}")

    @commands.command(help="Leave the voice channel")
    async def leave(self, ctx):
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Not currently connected.")

        guild_id = ctx.guild.id

        # Cancel queue processor
        if guild_id in self.queue_tasks:
            self.queue_tasks[guild_id].cancel()
            del self.queue_tasks[guild_id]
        if guild_id in self.sound_queues:
            del self.sound_queues[guild_id]

        # Clean up audio player
        self._cleanup_player(guild_id)

        await vc.disconnect()
        await ctx.send("👋 Left the voice channel.")

        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    @commands.command(help="Start listening")
    async def start(self, ctx):
        if not ctx.voice_client:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.send("⚠️ You're not in a voice channel!")
            channel = ctx.author.voice.channel
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
            if not self._keepalive_task:
                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())
        else:
            vc = ctx.voice_client

        sink = self._create_speech_listener(ctx)
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink
        await ctx.send("🎧 Listening...")

    @commands.command(help="Stop listening")
    async def stop(self, ctx):
        vc = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently listening.")
        vc.stop_listening()
        self.active_sinks.pop(ctx.guild.id, None)
        await ctx.send("🛑 Stopped listening.")

    @commands.command(help="Play a sound from a trigger word")
    async def play(self, ctx, *, input_text: str):
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        soundboard_cog = self.bot.get_cog("Soundboard")
        if not soundboard_cog:
            return await ctx.send("⚠️ Soundboard cog not loaded.")

        # Get list of (soundfile, sound_key, volume) tuples
        files = soundboard_cog.get_soundfiles_for_text(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            text=input_text
        )

        if files:
            for soundfile, sound_key, volume in files:
                if os.path.isfile(soundfile):
                    await self.queue_sound(ctx.guild.id, soundfile, ctx.author, sound_key, volume)
            await ctx.send(f"▶️ Queued {len(files)} sound(s).")
        else:
            await ctx.send(f"⚠️ No sounds found for: `{input_text}`")

    @commands.command(help="Show current sound queue")
    async def queue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues or self.sound_queues[guild_id].empty():
            return await ctx.send("🔭 Queue is empty.")
        await ctx.send(f"🎵 {self.sound_queues[guild_id].qsize()} sound(s) in queue")

    @commands.command(help="Clear the sound queue")
    async def clearqueue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues:
            return await ctx.send("🔭 No queue exists.")
        old_size = self.sound_queues[guild_id].qsize()
        self.sound_queues[guild_id] = asyncio.Queue()
        await ctx.send(f"🗑️ Cleared {old_size} sound(s) from queue")


async def setup(bot):
    try:
        await bot.add_cog(VoiceSpeechCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")