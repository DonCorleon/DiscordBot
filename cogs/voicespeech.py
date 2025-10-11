import json

import discord
from discord import FFmpegPCMAudio
from discord.ext import commands, voice_recv
from discord.ext.voice_recv.extras import speechrecognition as dsr
import asyncio
import os
from base_cog import BaseCog, logger
from soundboard.soundboard import SOUNDBOARD


class VoiceSpeechCog(BaseCog):

    def __init__(self, bot):
        """
        Initialize the VoiceSpeech cog.

        Sets up:
        - Sound queue system (per-guild)
        - Keepalive task for maintaining voice connections
        - Active sinks tracking for speech recognition
        - Voice state update listener for auto-disconnect
        """
        super().__init__(bot)
        self.bot = bot
        self.active_sinks = {}
        self._keepalive_interval = 30
        self._keepalive_task = None
        self.sound_queues = {}  # {guild_id: asyncio.Queue}
        self.queue_tasks = {}  # {guild_id: Task}

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState):
        """
        Monitor voice state changes to auto-disconnect when alone.

        Flow:
        1. Check if bot is in a voice channel in this guild
        2. If someone left the channel, check if bot is now alone
        3. If alone (only bot remains), auto-disconnect and cleanup

        This prevents the bot from staying in empty channels.
        """
        # Only care if someone left a channel
        if before.channel is None:
            return

        # Check if bot is in a voice channel in this guild
        if not member.guild.voice_client:
            return

        bot_channel = member.guild.voice_client.channel

        # Check if the member left the bot's channel
        if before.channel.id != bot_channel.id:
            return

        # Count non-bot members in the channel
        members_in_channel = [m for m in bot_channel.members if not m.bot]

        if len(members_in_channel) == 0:
            logger.info(f"[{member.guild.name}] All users left, auto-disconnecting")

            # Cleanup
            guild_id = member.guild.id

            # Cancel queue processor
            if guild_id in self.queue_tasks:
                self.queue_tasks[guild_id].cancel()
                del self.queue_tasks[guild_id]

            # Clear sound queue
            if guild_id in self.sound_queues:
                del self.sound_queues[guild_id]

            # Stop listening if active
            if guild_id in self.active_sinks:
                try:
                    member.guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"[{member.guild.name}] Error stopping listener during auto-disconnect: {e}")
                del self.active_sinks[guild_id]

            # Disconnect
            try:
                await member.guild.voice_client.disconnect()
                logger.info(f"[{member.guild.name}] Auto-disconnected from empty channel")
            except Exception as e:
                logger.error(f"[{member.guild.name}] Error disconnecting: {e}")

    async def cog_unload(self):
        """
        Clean up all running tasks when cog is unloaded/reloaded.

        Flow:
        1. Cancel and await keepalive task
        2. Cancel all guild queue processor tasks
        3. Stop all active speech recognition sinks
        4. Disconnect from all voice channels
        5. Clear all data structures

        This ensures no orphaned tasks or connections remain after reload.
        """
        logger.info("Unloading VoiceSpeechCog, cleaning up tasks...")

        # Cancel keepalive task
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass

        # Cancel all queue processing tasks
        for guild_id, task in list(self.queue_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop all active sinks
        for guild_id, sink in list(self.active_sinks.items()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                try:
                    guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"Error stopping listener for guild {guild_id}: {e}")

        # Disconnect from all voice channels
        for guild in self.bot.guilds:
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting from guild {guild.id}: {e}")

        # Clear all data structures
        self.active_sinks.clear()
        self.sound_queues.clear()
        self.queue_tasks.clear()

        logger.info("VoiceSpeechCog cleanup complete.")

    # -----------------------------
    # SOUND QUEUE SYSTEM
    # -----------------------------
    async def _process_sound_queue(self, guild_id: int):
        """
        Process sounds from a guild's queue sequentially.

        Flow:
        1. Wait for a sound to be added to the queue
        2. Validate voice client is still connected
        3. Load sound file from SOUNDBOARD mapping
        4. Play sound via FFmpeg and wait for completion
        5. Mark task as done and repeat

        This runs continuously until cancelled (on cog unload or voice disconnect).
        Each guild has its own queue processor to handle sounds independently.

        Args:
            guild_id: Discord guild ID to process sounds for
        """
        queue = self.sound_queues[guild_id]

        try:
            while True:
                word = None
                try:
                    # Wait for next sound in queue
                    word, vc = await queue.get()

                    # Check if voice client is still valid
                    if not vc or not vc.is_connected():
                        logger.warning(f"[Guild {guild_id}] Voice client disconnected, skipping sound '{word}'")
                        continue

                    sound_file = SOUNDBOARD.get(word.lower())
                    if not sound_file:
                        logger.warning(f"[Guild {guild_id}] No sound mapping for '{word}'")
                        continue

                    if not os.path.isfile(sound_file):
                        logger.error(f"[Guild {guild_id}] Sound file missing: {sound_file}")
                        continue

                    # Play the sound
                    event = asyncio.Event()

                    def after_callback(error):
                        if error:
                            logger.error(f"[Guild {guild_id}] FFmpeg playback error for '{word}': {error}",
                                         exc_info=error)
                        else:
                            logger.debug(f"[Guild {guild_id}] Finished playing '{word}'")
                        self.bot.loop.call_soon_threadsafe(event.set)

                    source = FFmpegPCMAudio(sound_file)
                    vc.play(source, after=after_callback)
                    logger.info(f"[Guild {guild_id}] ▶️ Playing '{word}'")

                    # Wait for playback to finish with timeout
                    try:
                        await asyncio.wait_for(event.wait(), timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.error(f"[Guild {guild_id}] Playback timeout for '{word}' - stopping")
                        if vc.is_playing():
                            vc.stop()

                except Exception as e:
                    logger.error(f"[Guild {guild_id}] Error processing sound '{word}': {e}", exc_info=True)
                finally:
                    # Always mark task as done after processing (or error)
                    queue.task_done()

        except asyncio.CancelledError:
            logger.info(f"[Guild {guild_id}] Queue processor cancelled")
            raise
        except Exception as e:
            logger.critical(f"[Guild {guild_id}] Unexpected error in queue processor: {e}", exc_info=True)

    async def queue_sound(self, guild_id: int, word: str, vc: voice_recv.VoiceRecvClient):
        """
        Add a sound to the guild's playback queue.

        Flow:
        1. Check if queue exists for this guild
        2. If not, create queue and start processor task
        3. Add (word, voice_client) tuple to queue
        4. Log queue size for monitoring

        This is non-blocking - sounds are queued instantly and played by the processor.

        Args:
            guild_id: Discord guild ID
            word: Word/phrase to map to a sound file
            vc: Voice client to play sound through
        """
        try:
            # Create queue if it doesn't exist
            if guild_id not in self.sound_queues:
                logger.info(f"[Guild {guild_id}] Creating new sound queue")
                self.sound_queues[guild_id] = asyncio.Queue()
                # Start queue processor
                self.queue_tasks[guild_id] = asyncio.create_task(
                    self._process_sound_queue(guild_id)
                )

            # Add to queue
            await self.sound_queues[guild_id].put((word, vc))
            queue_size = self.sound_queues[guild_id].qsize()
            logger.debug(f"[Guild {guild_id}] Queued '{word}' (queue size: {queue_size})")
        except Exception as e:
            logger.error(f"[Guild {guild_id}] Failed to queue sound '{word}': {e}", exc_info=True)
            raise

    # -----------------------------
    # ASYNC UDP KEEPALIVE
    # -----------------------------
    async def _keepalive_loop(self):
        """
        Maintain voice connections by sending periodic silence packets.

        Flow:
        1. Wait for bot to be ready
        2. Every 30 seconds, iterate through all active sinks
        3. If bot is not currently playing audio, send a silence packet
        4. This prevents Discord from timing out the voice connection

        Runs continuously until cancelled (on cog unload or bot shutdown).
        Required because Discord closes voice connections after ~5 minutes of inactivity.
        """
        await self.bot.wait_until_ready()
        logger.info("Keepalive loop started")
        try:
            while True:
                for guild_id, sink in list(self.active_sinks.items()):
                    try:
                        guild = self.bot.get_guild(guild_id)
                        if not guild:
                            logger.warning(f"[Guild {guild_id}] Guild not found, skipping keepalive")
                            continue

                        if not guild.voice_client:
                            logger.warning(f"[{guild.name}] No voice client, skipping keepalive")
                            continue

                        vc = guild.voice_client
                        if vc.is_playing():
                            continue

                        silence = b'\xf8\xff\xfe'
                        vc.send_audio_packet(silence, encode=False)
                        logger.debug(f"[{guild.name}] Keepalive sent")
                    except Exception as e:
                        logger.error(f"[Guild {guild_id}] Keepalive error: {e}", exc_info=True)

                await asyncio.sleep(self._keepalive_interval)
        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled")
            raise
        except Exception as e:
            logger.critical(f"Unexpected error in keepalive loop: {e}", exc_info=True)

    # -----------------------------
    # COMMANDS
    # -----------------------------
    @commands.command(help="Join caller's voice channel")
    async def join(self, ctx):
        """
        Join the voice channel of the user who called the command.

        Flow:
        1. Validate user is in a voice channel
        2. Check if bot is already connected
        3. Connect to channel with VoiceRecvClient (enables voice receiving)
        4. Start keepalive loop if not already running

        Note: Does not start listening yet - use ~start command for that.
        """
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("⚠️ You're not in a voice channel.")

        channel = ctx.author.voice.channel
        if ctx.voice_client:
            return await ctx.send("✅ Already connected.")

        vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
        await ctx.send(f"✅ Joined `{channel.name}` and ready to listen.")
        logger.info(f"Joined voice channel: {channel.name}")
        if not self._keepalive_task:
            self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())

    @commands.command(help="Leave the voice channel")
    async def leave(self, ctx):
        """
        Disconnect from the voice channel and cleanup resources.

        Flow:
        1. Check if bot is connected to voice
        2. Cancel and cleanup queue processor for this guild
        3. Disconnect from voice channel
        4. Cancel keepalive task if running
        """
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Not currently connected.")

        # Clean up queue
        guild_id = ctx.guild.id
        if guild_id in self.queue_tasks:
            self.queue_tasks[guild_id].cancel()
            del self.queue_tasks[guild_id]
        if guild_id in self.sound_queues:
            del self.sound_queues[guild_id]

        await vc.disconnect()
        await ctx.send("👋 Left the voice channel.")
        logger.info("Disconnected from voice channel.")
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    @commands.command(help="Listen to cunts!")
    async def start(self, ctx):
        """
        Start listening and transcribing speech in voice channel.

        Flow:
        1. Check if bot is connected, if not auto-join user's channel
        2. Validate bot is connected to voice
        3. Create SpeechRecognitionSink with Vosk recognizer
        4. Set up text_callback to handle transcription results
        5. Register speaking start/stop listeners
        6. Attach sink to voice client to begin listening
        7. Store sink in active_sinks for keepalive tracking

        When users speak:
        - on_voice_member_speaking_start: Logs when user starts
        - Audio is captured and sent to Vosk for transcription
        - text_callback: Receives transcribed text, queues corresponding sound
        - on_voice_member_speaking_stop: Logs when user stops
        """
        # Auto-join if not connected
        if not ctx.voice_client:
            if not ctx.author.voice or not ctx.author.voice.channel:
                return await ctx.send("⚠️ You're not in a voice channel!")

            channel = ctx.author.voice.channel
            vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
            logger.info(f"Auto-joined voice channel: {channel.name}")
            if not self._keepalive_task:
                self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())
        else:
            vc = ctx.voice_client

        def text_callback(user: discord.User, text: str):
            try:
                result = json.loads(text)
                transcribed_text = result.get("text", "").strip()
                if not transcribed_text:
                    logger.debug(f"[{user.display_name}] Empty transcription result")
                    return

                logger.info(f"\033[92m[{ctx.guild.name}] {user.display_name}: {transcribed_text}\033[0m")

                guild = self.bot.get_guild(ctx.guild.id)
                if not guild:
                    logger.error(f"Guild {ctx.guild.id} not found in text_callback")
                    return

                if not guild.voice_client:
                    logger.warning(f"[{guild.name}] No voice client in text_callback")
                    return

                vc = guild.voice_client

                # Split transcription into words and check each one
                words = transcribed_text.lower().split()
                found_words = []

                for word in words:
                    sound_file = SOUNDBOARD.get(word)
                    if sound_file and os.path.isfile(sound_file):
                        found_words.append(word)

                # Queue all found sounds
                if found_words:
                    async def queue_all():
                        try:
                            for word in found_words:
                                await self.queue_sound(ctx.guild.id, word, vc)
                            logger.info(
                                f"[{guild.name}] Queued {len(found_words)} sound(s) from speech: {', '.join(found_words)}")
                        except Exception as e:
                            logger.error(f"[{guild.name}] Failed to queue sounds from transcription: {e}",
                                         exc_info=True)

                    asyncio.run_coroutine_threadsafe(queue_all(), self.bot.loop)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse transcription JSON: {text[:100]}", exc_info=True)
            except Exception as e:
                logger.error(f"Error in text_callback: {e}", exc_info=True)

        class SRListener(dsr.SpeechRecognitionSink):
            def __init__(self):
                super().__init__(
                    default_recognizer="vosk",
                    phrase_time_limit=10,
                    text_cb=text_callback
                )

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_start(self, member: discord.Member):
                logger.info(f"🎤 {member.display_name} started speaking")

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_stop(self, member: discord.Member):
                logger.info(f"🔇 {member.display_name} stopped speaking")

        sink = SRListener()
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink

        await ctx.send("🎧 Listening and transcribing with SpeechRecognition...")
        logger.info("Started SpeechRecognition listening.")

    @commands.command(help="Stop listening to cunts")
    async def stop(self, ctx):
        """
        Stop listening and cleanup speech recognition.

        Flow:
        1. Validate bot is currently listening
        2. Stop the voice client's listening sink
        3. Remove sink from active_sinks tracking

        Note: Does not disconnect from voice - use ~leave for that.
        """
        vc = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently listening.")

        vc.stop_listening()
        self.active_sinks.pop(ctx.guild.id, None)
        await ctx.send("🛑 Stopped listening.")
        logger.info("Stopped listening and cleared sink.")

    @commands.command(help="Play a sound from a word or phrase")
    async def play(self, ctx, *, input_text: str):
        """
        Manually play sounds associated with words/phrases.

        Flow:
        1. Validate bot is connected to voice
        2. Split input into individual words
        3. Check each word against SOUNDBOARD mapping
        4. Queue all found sounds for playback
        5. Notify user of queued sounds

        Args:
            input_text: Word(s) or sentence to look up in SOUNDBOARD

        Example:
            ~play hello
            ~play hello world goodbye
        """
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        # Split input into words and check each one
        words = input_text.lower().split()
        found_sounds = []
        missing_words = []

        for word in words:
            sound_file = SOUNDBOARD.get(word)
            if sound_file and os.path.isfile(sound_file):
                found_sounds.append(word)
                await self.queue_sound(ctx.guild.id, word, vc)
            else:
                missing_words.append(word)

        # Build response message
        if found_sounds and missing_words:
            await ctx.send(
                f"🎵 Queued {len(found_sounds)} sound(s): {', '.join(found_sounds)}\n⚠️ No sounds for: {', '.join(missing_words)}")
        elif found_sounds:
            await ctx.send(f"▶️ Queued {len(found_sounds)} sound(s): {', '.join(found_sounds)}")
        else:
            await ctx.send(f"⚠️ No sounds found for any words in: `{input_text}`")

    @commands.command(help="Show current sound queue")
    async def queue(self, ctx):
        """
        Display the current sound queue size.

        Shows how many sounds are waiting to be played.
        Useful for checking if the queue is backed up.
        """
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues or self.sound_queues[guild_id].empty():
            return await ctx.send("📭 Queue is empty.")

        queue_size = self.sound_queues[guild_id].qsize()
        await ctx.send(f"🎵 {queue_size} sound(s) in queue")

    @commands.command(help="Clear the sound queue")
    async def clearqueue(self, ctx):
        """
        Clear all queued sounds without stopping current playback.

        Flow:
        1. Check if a queue exists for this guild
        2. Get current queue size for logging
        3. Replace queue with new empty queue
        4. Notify user of how many sounds were cleared

        Note: Does not stop currently playing sound, only clears pending ones.
        """
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues:
            return await ctx.send("📭 No queue exists.")

        # Create new empty queue
        old_size = self.sound_queues[guild_id].qsize()
        self.sound_queues[guild_id] = asyncio.Queue()

        await ctx.send(f"🗑️ Cleared {old_size} sound(s) from queue")


async def setup(bot):
    """
    Load the VoiceSpeechCog into the bot.

    Called by discord.py when loading this cog.
    Handles any errors during cog initialization.
    """
    try:
        await bot.add_cog(VoiceSpeechCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")