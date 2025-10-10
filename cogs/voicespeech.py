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
        self.bot = bot
        self.active_sinks = {}
        self._keepalive_interval = 30
        self._keepalive_task = None

    def cog_unload(self):
        if self._keepalive_task:
            self._keepalive_task.cancel()

    # -----------------------------
    # ASYNC UDP KEEPALIVE FUCKING
    # -----------------------------
    async def _keepalive_loop(self):
        await self.bot.wait_until_ready()
        try:
            while True:
                for guild_id, sink in list(self.active_sinks.items()):
                    guild = self.bot.get_guild(guild_id)
                    if not guild or not guild.voice_client:
                        logger.warning(f"guild not found")
                        continue

                    vc = guild.voice_client
                    if vc.is_playing():
                        logger.warning(f"Sound is playing")
                        continue
                    silence = b'\xf8\xff\xfe'

                    try:
                        vc.send_audio_packet(silence, encode=False)
                        logger.info(f"[{guild.name}] Keepalive sent.")
                    except Exception as e:
                        logger.error(f"[KeepAlive] Error in guild {guild.name}: {e}")

                await asyncio.sleep(self._keepalive_interval)
        except asyncio.CancelledError:
            logger.info("Keepalive loop cancelled.")

    async def play_sound(self, vc: voice_recv.VoiceRecvClient, word: str):
        """Plays a sound from SOUNDBOARD without blocking."""
        sound_file = SOUNDBOARD.get(word.lower())
        if not sound_file or not os.path.isfile(sound_file):
            logger.warning(f"No sound for {word} or file missing.")
            return

        # Wait if already playing
        while vc.is_playing():
            await asyncio.sleep(0.1)

        try:
            source = FFmpegPCMAudio(sound_file)
            vc.play(source, after=lambda e: logger.info(f"Finished playing {sound_file}: {e}" if e else ""))
            logger.info(f"▶️ Playing sound for '{word}'")
        except Exception as e:
            logger.error(f"Error playing sound {sound_file}: {e}")
    # -----------------------------
    # COMMANDS
    # -----------------------------
    @commands.command(help="Join caller's voice channel")
    async def join(self, ctx):
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
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Not currently connected.")
        await vc.disconnect()
        await ctx.send("👋 Left the voice channel.")
        logger.info("Disconnected from voice channel.")
        if self._keepalive_task:
            self._keepalive_task.cancel()
            self._keepalive_task = None

    @commands.command(help="Listen to cunts!")
    async def start(self, ctx):
        """Start listening and transcribing speech."""
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        def text_callback(user: discord.User, text: str):
            result = json.loads(text)
            word = result.get("text", "").strip()
            if not word:
                return

            logger.info(f"\033[92m {user.display_name}: {word}\033[0m")

            guild = self.bot.get_guild(ctx.guild.id)
            if not guild or not guild.voice_client:
                return

            vc = guild.voice_client

            # Schedule coroutine safely from another thread
            def schedule():
                asyncio.create_task(self.play_sound(vc, word))

            self.bot.loop.call_soon_threadsafe(schedule)

        class SRListener(dsr.SpeechRecognitionSink):
            def __init__(self):
                super().__init__(
                    default_recognizer="vosk",
                    phrase_time_limit=10,
                    text_cb=text_callback  # pass closure directly
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
        """Stop listening and cleanup."""
        vc = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently listening.")

        vc.stop_listening()
        self.active_sinks.pop(ctx.guild.id, None)
        await ctx.send("🛑 Stopped listening.")
        logger.info("Stopped listening and cleared sink.")

    @commands.command(help="Play a sound from a word or phrase")
    async def play(self, ctx, *, word: str):
        """Plays a sound associated with a word/phrase."""
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        sound_file = SOUNDBOARD.get(word.lower())
        if not sound_file or not os.path.isfile(sound_file):
            return await ctx.send(f"⚠️ No sound mapped for `{word}` or file missing.")

        # Check if the bot is already playing something
        if vc.is_playing():
            return await ctx.send("⚠️ Already playing audio. Please wait.")

        # Use FFmpegPCMAudio for playback
        try:
            source = discord.FFmpegPCMAudio(sound_file)
            vc.play(source, after=lambda e: logger.info(f"Finished playing {sound_file}: {e}" if e else ""))
            await ctx.send(f"▶️ Playing `{word}` sound!")
        except Exception as e:
            logger.error(f"Error playing sound {sound_file}: {e}")
            await ctx.send(f"⚠️ Failed to play `{word}` sound.")

async def setup(bot):
    try:
        await bot.add_cog(VoiceSpeechCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")
