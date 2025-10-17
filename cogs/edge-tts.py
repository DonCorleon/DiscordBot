"""
Updated Edge TTS Cog with ducking support via queue system.
"""

import discord
from discord.ext import commands
import edge_tts
import tempfile
import asyncio
import os
from base_cog import BaseCog, logger


class EdgeTTS(BaseCog):
    """Edge TTS Cog with queue integration and ducking support."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.voices = []
        self.voice_map = {}
        self.user_last_voice = {}  # user_id -> voice shortname
        self.volume = 1.5

    async def load_voices(self):
        """Load available Edge TTS voices."""
        if not self.voices:
            self.voices = await edge_tts.list_voices()
            # Pick a few good default voices
            common = [v for v in self.voices if v["ShortName"] in [
                "en-US-AriaNeural", "en-US-GuyNeural", "en-GB-RyanNeural",
                "en-GB-SoniaNeural", "en-AU-NatashaNeural", "en-IN-NeerjaNeural"
            ]]
            self.voice_map = {i + 1: v["ShortName"] for i, v in enumerate(common)}

    @commands.command(name="voices_edge", help="List available Edge TTS voices")
    async def list_voices(self, ctx):
        """List the available Edge TTS voices."""
        await self.load_voices()
        text = "\n".join([f"{i}. {name}" for i, name in self.voice_map.items()])

        embed = discord.Embed(
            title="🎙️ Available Edge TTS Voices",
            description=f"```{text}```",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Use the number at the end of your message: ~edge Hello world 1")
        await ctx.send(embed=embed)

    async def generate_edge_tts_file(self, text: str, voice: str) -> str:
        """Generate Edge TTS audio and save to temp file. Returns filepath."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        temp_file.close()

        try:
            tts = edge_tts.Communicate(text, voice)
            await tts.save(temp_file.name)
            logger.debug(f"Generated Edge TTS: {temp_file.name}")
            return temp_file.name
        except Exception as e:
            logger.error(f"Failed to generate Edge TTS: {e}")
            # Clean up temp file on error
            try:
                os.unlink(temp_file.name)
            except:
                pass
            raise

    @commands.command(name="edge", help="Speak text in VC using Edge TTS with ducking support")
    async def edge_tts(self, ctx, *, text_and_voice: str):
        """
        Speak text using Edge TTS. Now with ducking support!

        Usage:
            ~edge Hello world
            ~edge Hello world 1  (use voice #1)
        """
        await self.load_voices()

        user_id = ctx.author.id
        parts = text_and_voice.split()
        voice_num = None
        text = text_and_voice

        # If last arg is a number, treat it as a voice index
        if parts and parts[-1].isdigit():
            voice_num = int(parts[-1])
            text = " ".join(parts[:-1])

        # Determine voice
        if voice_num and voice_num in self.voice_map:
            voice = self.voice_map[voice_num]
            self.user_last_voice[user_id] = voice  # remember choice
        elif user_id in self.user_last_voice:
            voice = self.user_last_voice[user_id]
        else:
            voice = "en-US-AriaNeural"

        if not ctx.voice_client:
            if ctx.author.voice:
                # Get VoiceSpeechCog to join properly
                voice_cog = self.bot.get_cog("VoiceSpeechCog")
                if voice_cog:
                    # Use the join command context
                    from discord.ext import voice_recv
                    await ctx.author.voice.channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
                else:
                    return await ctx.send("❌ Voice system not available!")
            else:
                return await ctx.send("⚠️ You must be in a voice channel.")

        try:
            # Generate the TTS audio file
            await ctx.send(f"🔄 Generating speech with **{voice}**...")
            filepath = await self.generate_edge_tts_file(text, voice)

            # Queue it for playback WITH DUCKING SUPPORT
            voice_cog = self.bot.get_cog("VoiceSpeechCog")
            if not voice_cog:
                return await ctx.send("❌ Voice system not available!")

            await voice_cog.queue_sound(ctx.guild.id, filepath, ctx.author, None, self.volume)
            await ctx.send(f"💬 Queued Edge TTS: **{voice}** (with ducking support!)")
            logger.info(f"[{ctx.guild.name}] Queued Edge TTS with voice {voice}")

        except Exception as e:
            logger.error(f"Failed to generate/queue Edge TTS: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to generate speech: {str(e)}")

    @commands.command(name="stopedge", help="Stop any playing audio")
    async def stop_edge(self, ctx):
        """Stop currently playing audio."""
        voice_cog = self.bot.get_cog("VoiceSpeechCog")
        if not voice_cog:
            return await ctx.send("❌ Voice system not available!")

        guild_id = ctx.guild.id

        # Stop current playback
        if guild_id in voice_cog.audio_players:
            player = voice_cog.audio_players[guild_id]
            if player.is_playing:
                player.stop()
                await ctx.send("🛑 Stopped playback.")
            else:
                await ctx.send("⚠️ Nothing is playing.")
        else:
            await ctx.send("⚠️ Nothing is playing.")


async def setup(bot):
    try:
        await bot.add_cog(EdgeTTS(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")