import discord
from discord.ext import commands
import edge_tts
import io
import asyncio

class EdgeTTS(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.voices = []
        self.voice_map = {}
        self.user_last_voice = {}  # user_id -> voice shortname

    async def load_voices(self):
        if not self.voices:
            self.voices = await edge_tts.list_voices()
            # Pick a few good default voices
            common = [v for v in self.voices if v["ShortName"] in [
                "en-US-AriaNeural", "en-US-GuyNeural", "en-GB-RyanNeural",
                "en-GB-SoniaNeural", "en-AU-NatashaNeural", "en-IN-NeerjaNeural"
            ]]
            self.voice_map = {i + 1: v["ShortName"] for i, v in enumerate(common)}

    @commands.command(name="voices", help="List available Edge TTS voices")
    async def list_voices(self, ctx):
        await self.load_voices()
        text = "\n".join([f"{i}. {name}" for i, name in self.voice_map.items()])
        await ctx.send(f"**Available Voices:**\n```{text}```")

    @commands.command(name="edge", help="Speak text in VC using Edge TTS")
    async def edge_tts(self, ctx, *, text_and_voice: str):
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
                await ctx.author.voice.channel.connect()
            else:
                return await ctx.send("⚠️ You must be in a voice channel.")

        vc = ctx.voice_client

        tts = edge_tts.Communicate(text, voice)
        audio_data = io.BytesIO()
        async for chunk in tts.stream():
            if chunk["type"] == "audio":
                audio_data.write(chunk["data"])
        audio_data.seek(0)

        source = discord.FFmpegPCMAudio(audio_data, pipe=True)
        vc.play(source)
        await ctx.send(f"💬 Speaking in **{voice}**")

    @commands.command(name="stopedge", help="Stop any playing TTS")
    async def stop_edge(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("🛑 Stopped playback.")
        else:
            await ctx.send("⚠️ Nothing is playing.")

async def setup(bot):
    await bot.add_cog(EdgeTTS(bot))
