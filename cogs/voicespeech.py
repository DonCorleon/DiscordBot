import json
import discord
from discord import FFmpegPCMAudio
from discord.ext import commands, voice_recv
from discord.ext.voice_recv.extras import speechrecognition as dsr
import asyncio
import os
from base_cog import BaseCog, logger


class VoiceSpeechCog(BaseCog):

    def __init__(self, bot):
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
            if guild_id in self.queue_tasks:
                self.queue_tasks[guild_id].cancel()
                del self.queue_tasks[guild_id]
            if guild_id in self.sound_queues:
                del self.sound_queues[guild_id]
            if guild_id in self.active_sinks:
                try:
                    member.guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"[{member.guild.name}] Error stopping listener: {e}")
                del self.active_sinks[guild_id]
            try:
                await member.guild.voice_client.disconnect()
                logger.info(f"[{member.guild.name}] Auto-disconnected")
            except Exception as e:
                logger.error(f"[{member.guild.name}] Error disconnecting: {e}")

    async def cog_unload(self):
        logger.info("Unloading VoiceSpeechCog...")
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
        for guild_id, task in list(self.queue_tasks.items()):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        for guild_id, sink in list(self.active_sinks.items()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                try:
                    guild.voice_client.stop_listening()
                except Exception as e:
                    logger.error(f"Error stopping sink for guild {guild_id}: {e}")
        for guild in self.bot.guilds:
            if guild.voice_client:
                try:
                    await guild.voice_client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting from guild {guild.id}: {e}")
        self.active_sinks.clear()
        self.sound_queues.clear()
        self.queue_tasks.clear()
        logger.info("VoiceSpeechCog cleanup complete.")

    async def _process_sound_queue(self, guild_id: int):
        queue = self.sound_queues[guild_id]
        try:
            while True:
                soundfile, vc, user_id = await queue.get()
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
                        logger.error(f"[Guild {guild_id}] FFmpeg playback error for '{soundfile}': {error}", exc_info=error)
                    else:
                        logger.debug(f"[Guild {guild_id}] Finished playing '{soundfile}'")
                    self.bot.loop.call_soon_threadsafe(event.set)

                source = FFmpegPCMAudio(soundfile)
                vc.play(source, after=after_callback)
                logger.info(f"[Guild {guild_id}] ▶️ Playing '{soundfile}'")

                # Update soundboard play stats
                soundboard_cog = self.bot.get_cog("Soundboard")
                if soundboard_cog:
                    soundboard_cog.increment_play_stats(guild_id, soundfile, user_id)

                try:
                    await asyncio.wait_for(event.wait(), timeout=30.0)
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

    async def queue_sound(self, guild_id: int, soundfile: str, user: discord.User):
        if guild_id not in self.sound_queues:
            self.sound_queues[guild_id] = asyncio.Queue()
            self.queue_tasks[guild_id] = asyncio.create_task(self._process_sound_queue(guild_id))
        await self.sound_queues[guild_id].put((soundfile, user.guild.voice_client, user.id))
        logger.debug(f"[Guild {guild_id}] Queued '{soundfile}' (queue size: {self.sound_queues[guild_id].qsize()})")

    async def _keepalive_loop(self):
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
                        if vc.is_playing():
                            continue
                        silence = b'\xf8\xff\xfe'
                        vc.send_audio_packet(silence, encode=False)
                    except Exception as e:
                        logger.error(f"[Guild {guild_id}] Keepalive error: {e}", exc_info=True)
                await asyncio.sleep(self._keepalive_interval)
        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled")
            raise

    @commands.command(help="Join caller's voice channel")
    async def join(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("⚠️ You're not in a voice channel.")
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            return await ctx.send("✅ Already connected.")
        vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
        await ctx.send(f"✅ Joined `{channel.name}` and ready to listen.")
        if not self._keepalive_task:
            self._keepalive_task = self.bot.loop.create_task(self._keepalive_loop())

    @commands.command(help="Leave the voice channel")
    async def leave(self, ctx):
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Not currently connected.")
        guild_id = ctx.guild.id
        if guild_id in self.queue_tasks:
            self.queue_tasks[guild_id].cancel()
            del self.queue_tasks[guild_id]
        if guild_id in self.sound_queues:
            del self.sound_queues[guild_id]
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

        def text_callback(user: discord.User, text: str):
            try:
                result = json.loads(text)
                transcribed_text = result.get("text", "").strip()
                if not transcribed_text:
                    return

                guild_name = ctx.guild.name
                logger.info(
                    f"\033[92m[{guild_name}] [{user.display_name}] : {transcribed_text}\033[0m")

                soundboard_cog = self.bot.get_cog("Soundboard")
                if not soundboard_cog:
                    return

                files = soundboard_cog.get_soundfiles_for_text(ctx.guild.id, user.id, transcribed_text)
                valid_files = [f for f in files if os.path.isfile(f)]
                if valid_files:
                    async def queue_all():
                        for f in valid_files:
                            await self.queue_sound(ctx.guild.id, f, user)
                    asyncio.run_coroutine_threadsafe(queue_all(), self.bot.loop)
            except Exception as e:
                logger.error(f"Error in text_callback: {e}", exc_info=True)

        class SRListener(dsr.SpeechRecognitionSink):
            def __init__(self):
                super().__init__(default_recognizer="vosk", phrase_time_limit=10, text_cb=text_callback)

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_start(self, member: discord.Member):
                logger.debug(f"🎤 {member.display_name} started speaking")

            @voice_recv.AudioSink.listener()
            def on_voice_member_speaking_stop(self, member: discord.Member):
                logger.debug(f"🔇 {member.display_name} stopped speaking")

        sink = SRListener()
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink
        await ctx.send("🎧 Listening and transcribing...")

    @commands.command(help="Stop listening")
    async def stop(self, ctx):
        vc = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently listening.")
        vc.stop_listening()
        self.active_sinks.pop(ctx.guild.id, None)
        await ctx.send("🛑 Stopped listening.")

    @commands.command(help="Play a sound from a word/phrase")
    async def play(self, ctx, *, input_text: str):
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        soundboard_cog = self.bot.get_cog("Soundboard")
        if not soundboard_cog:
            return await ctx.send("⚠️ Soundboard cog not loaded.")

        files = soundboard_cog.get_soundfiles_for_text(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            text=input_text
        )
        valid_files = [f for f in files if os.path.isfile(f)]
        if valid_files:
            for f in valid_files:
                await self.queue_sound(ctx.guild.id, f, ctx.author)
            await ctx.send(f"▶️ Queued {len(valid_files)} sound(s).")
        else:
            await ctx.send(f"⚠️ No sounds found for: `{input_text}`")

    @commands.command(help="Show current sound queue")
    async def queue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues or self.sound_queues[guild_id].empty():
            return await ctx.send("📭 Queue is empty.")
        await ctx.send(f"🎵 {self.sound_queues[guild_id].qsize()} sound(s) in queue")

    @commands.command(help="Clear the sound queue")
    async def clearqueue(self, ctx):
        guild_id = ctx.guild.id
        if guild_id not in self.sound_queues:
            return await ctx.send("📭 No queue exists.")
        old_size = self.sound_queues[guild_id].qsize()
        self.sound_queues[guild_id] = asyncio.Queue()
        await ctx.send(f"🗑️ Cleared {old_size} sound(s) from queue")


async def setup(bot):
    try:
        await bot.add_cog(VoiceSpeechCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")
