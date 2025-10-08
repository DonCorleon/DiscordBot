import discord
from discord.ext import commands, voice_recv
import wave
import asyncio
from base_cog import BaseCog, logger


class VoiceCog(BaseCog):
    """Voice channel commands for recording and speech-to-text."""

    active_sinks = {}  # Keep track of sinks per guild

    @commands.command(name="join")
    async def join(self, ctx):
        """Join the user's voice channel with voice_recv enabled."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("⚠️ You are not in a voice channel!")

        channel = ctx.author.voice.channel

        if ctx.voice_client:
            await ctx.send("✅ Already connected.")
            return

        # ✅ Use VoiceRecvClient instead of normal VoiceClient
        vc: voice_recv.VoiceRecvClient = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)
        await ctx.send(f"✅ Joined `{channel.name}` and ready to receive audio.")

    @commands.command(name="leave")
    async def leave(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("👋 Left the voice channel.")
        else:
            await ctx.send("⚠️ Not connected to a voice channel.")

    @commands.command(name="listen")
    async def listen(self, ctx):
        """Start recording PCM audio from users indefinitely."""
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        class PCMSink(voice_recv.AudioSink):
            def __init__(self):
                super().__init__()
                self.buffers = {}

            def write(self, user, data):
                if user.id not in self.buffers:
                    self.buffers[user.id] = bytearray()
                self.buffers[user.id].extend(data.pcm)

            def wants_opus(self) -> bool:
                return False  # receive PCM

            def cleanup(self):
                pass

        sink = PCMSink()
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink

        await ctx.send("🎙️ Started recording. Use `~stop` to finish.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop recording and save audio to WAV files."""
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently recording.")

        sink = self.active_sinks.pop(ctx.guild.id)
        vc.stop_listening()

        for user_id, audio_bytes in sink.buffers.items():
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else str(user_id)
            filename = f"{name}_{user_id}.wav"

            with wave.open(filename, "wb") as wf:
                wf.setnchannels(2)
                wf.setsampwidth(2)
                wf.setframerate(48000)
                wf.writeframes(audio_bytes)

        await ctx.send("🛑 Finished recording and saved WAV files.")


async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
