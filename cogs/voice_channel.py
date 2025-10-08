import discord
from discord.ext import commands, voice_recv
import wave
import asyncio
import numpy as np
from vosk import Model, KaldiRecognizer
import json
from base_cog import BaseCog, logger

class VoiceCog(BaseCog):
    """Voice channel commands for recording and speech-to-text."""

    active_sinks = {}   # guild.id -> sink
    buffer_tasks = {}   # user_id -> asyncio.Task

    def __init__(self, bot):
        super().__init__(bot)
        self.vosk_model = Model("vosk/vosk-model-small-en-us-0.15")  # path to your Vosk model

    @commands.command(name="join")
    async def join(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("⚠️ You are not in a voice channel!")

        channel = ctx.author.voice.channel

        if ctx.voice_client:
            await ctx.send("✅ Already connected.")
            return

        # ✅ Use VoiceRecvClient instead of normal VoiceClient
        vc: voice_recv.VoiceRecvClient = await channel.connect(
            cls=voice_recv.VoiceRecvClient, self_deaf=False
        )
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
        vc: voice_recv.VoiceRecvClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        class VoskSink(voice_recv.AudioSink):
            def __init__(self, cog: "VoiceCog"):
                super().__init__()
                self.cog = cog
                self.buffers = {}  # user_id -> bytearray
                self.transcribed_lengths = {}  # user_id -> bytes

            def write(self, user, data):
                if not data.pcm:
                    return

                # Convert PCM to numpy array
                pcm_array = np.frombuffer(data.pcm, dtype=np.int16)
                if pcm_array.size == 0:
                    return  # skip empty audio
                rms = np.sqrt(np.mean(pcm_array ** 2))
                if rms < 500:  # skip silence
                    return

                if user.id not in self.buffers:
                    self.buffers[user.id] = bytearray()
                    self.transcribed_lengths[user.id] = 0

                self.buffers[user.id].extend(data.pcm)

                # Limit buffer to 10 seconds at 16kHz
                max_bytes = 10 * 16000 * 2
                if len(self.buffers[user.id]) > max_bytes:
                    self.buffers[user.id] = self.buffers[user.id][-max_bytes:]

                # Start async transcription task if not running
                task_future = self.cog.buffer_tasks.get(user.id)
                if not task_future or task_future.done():
                    # Thread-safe scheduling
                    future = asyncio.run_coroutine_threadsafe(
                        self.cog.transcribe_user(user.id, self), self.cog.bot.loop
                    )
                    self.cog.buffer_tasks[user.id] = future

            def wants_opus(self) -> bool:
                return False  # receive PCM

            def cleanup(self):
                pass

        sink = VoskSink(self)
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink
        await ctx.send("🎙️ Started recording and transcribing.")

    async def transcribe_user(self, user_id, sink: "VoskSink"):
        recognizer = KaldiRecognizer(self.vosk_model, 16000)

        while user_id in sink.buffers and sink.buffers[user_id]:
            audio_bytes = bytes(sink.buffers[user_id])

            if recognizer.AcceptWaveform(audio_bytes):
                result_json = json.loads(recognizer.Result())
                text = result_json.get("text", "").strip()
                if text:
                    # Find the member object
                    member = None
                    for guild in self.bot.guilds:
                        member = guild.get_member(user_id)
                        if member:
                            break
                    name = member.display_name if member else str(user_id)
                    logger.info(f"[Vosk] {name}: {text}")

                    # Drop audio that was transcribed
                    sink.buffers[user_id] = bytearray()
                    # If you want to remove only processed bytes, you'd calculate offsets here
                    # consumed_bytes = ...
                    # sink.buffers[user_id] = sink.buffers[user_id][consumed_bytes:]
            else:
                # Partial results are available here
                partial_json = json.loads(recognizer.PartialResult())
                partial_text = partial_json.get("partial", "")
                if partial_text:
                    # logger.debug(f"[Vosk Partial] {user_id}: {partial_text}")
                    pass  # can log or ignore partial text

            await asyncio.sleep(0.1)

    @commands.command(name="stop")
    async def stop(self, ctx):
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
                wf.setnchannels(1)  # mono
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_bytes)

        await ctx.send("🛑 Finished recording and saved WAV files.")

async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
