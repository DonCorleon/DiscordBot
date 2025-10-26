# edge-tts.py
import discord
from discord.ext import commands
import edge_tts
import io
import asyncio
from dataclasses import dataclass
from bot.base_cog import BaseCog, logger
from bot.core.config_base import ConfigBase, config_field


# -------- Configuration Schema --------

@dataclass
class EdgeTTSConfig(ConfigBase):
    """Edge TTS (Microsoft Text-to-Speech) configuration schema."""

    edge_tts_default_volume: float = config_field(
        default=1.5,
        description="Default Edge TTS playback volume (0.0 = muted, 1.0 = normal, 2.0 = 200%)",
        category="TextToSpeech/Edge",
        guild_override=True,
        min_value=0.0,
        max_value=2.0
    )

    edge_tts_default_voice: str = config_field(
        default="en-US-AriaNeural",
        description="Default Edge TTS voice (e.g., en-US-AriaNeural, en-GB-RyanNeural)",
        category="TextToSpeech/Edge",
        guild_override=True,
        choices=[
            "en-US-AriaNeural",
            "en-US-GuyNeural",
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural",
            "en-AU-NatashaNeural",
            "en-IN-NeerjaNeural"
        ]
    )


class EdgeTTS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Register config schema
        from bot.core.config_system import CogConfigSchema
        schema = CogConfigSchema.from_dataclass("EdgeTTS", EdgeTTSConfig)
        bot.config_manager.register_schema("EdgeTTS", schema)
        logger.info("Registered EdgeTTS config schema")

        self.voices = []
        self.voice_map = {}
        self.user_last_voice = {}  # user_id -> voice shortname

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

    @commands.command(name="edgevoices", help="List available Edge TTS voices")
    async def list_voices(self, ctx):
        """List the quick-select voices."""
        await self.load_voices()
        text = "\n".join([f"{i}. {name}" for i, name in self.voice_map.items()])
        await ctx.send(f"**Available Voices:**\n```{text}```")

    @commands.command(name="edge", help="Speak text in VC using Edge TTS")
    async def edge_tts(self, ctx, *, text_and_voice: str):
        """
        Speak text using Microsoft Edge TTS.
        Usage: ~edge <text> [voice_number]
        Example: ~edge Hello world 1
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

        # Get default voice from unified config manager
        default_voice = "en-US-AriaNeural"
        if hasattr(self.bot, 'config_manager'):
            default_voice = self.bot.config_manager.get("EdgeTTS", "edge_tts_default_voice", ctx.guild.id)

        # Determine voice
        if voice_num and voice_num in self.voice_map:
            voice = self.voice_map[voice_num]
            self.user_last_voice[user_id] = voice  # remember choice
        elif user_id in self.user_last_voice:
            voice = self.user_last_voice[user_id]
        else:
            voice = default_voice

        # CRITICAL: Use ctx.voice_client which is guild-specific
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("⚠️ You must be in a voice channel.")

        # This voice client is automatically guild-specific from ctx
        vc = ctx.voice_client

        # Generate TTS audio
        try:
            tts = edge_tts.Communicate(text, voice)
            audio_data = io.BytesIO()
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            audio_data.seek(0)
        except Exception as e:
            logger.error(f"[Guild {ctx.guild.id}] Edge TTS generation failed: {e}", exc_info=True)
            return await ctx.send(f"❌ Failed to generate speech: {str(e)}")

        # Get volume from unified config manager
        volume = 1.5  # default
        if hasattr(self.bot, 'config_manager'):
            volume = self.bot.config_manager.get("EdgeTTS", "edge_tts_default_volume", ctx.guild.id)

        # Play audio to THIS guild's voice client only
        source = discord.FFmpegPCMAudio(audio_data, pipe=True)
        source = discord.PCMVolumeTransformer(source, volume=volume)

        # The vc.play() call only affects THIS guild because vc is guild-specific
        vc.play(source)

        # Log for debugging
        logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Playing Edge TTS in #{vc.channel.name} with voice '{voice}'")

        await ctx.send(f"💬 Speaking in **{voice}**")

    @commands.command(name="stopedge", help="Stop any playing TTS")
    async def stop_edge(self, ctx):
        """Stop Edge TTS playback in THIS guild only."""
        # ctx.voice_client is guild-specific, so this only stops in the current guild
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Stopped Edge TTS playback")
            await ctx.send("🛑 Stopped playback.")
        else:
            await ctx.send("⚠️ Nothing is currently playing in this guild.")


async def setup(bot):
    try:
        await bot.add_cog(EdgeTTS(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")