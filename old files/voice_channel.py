import discord
from discord.ext import commands, voice_recv
import asyncio
import numpy as np
import wave
from vosk import Model, KaldiRecognizer
import json
from base_cog import BaseCog, logger

# -----------------------
# Custom Voice Client with Keepalive
# -----------------------
class KeepAliveVoiceClient(voice_recv.VoiceRecvClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._keepalive_task = None

    async def connect(self, *args, **kwargs):
        result = await super().connect(*args, **kwargs)
        if self._keepalive_task:
            self._keepalive_task.cancel()
        self._keepalive_task = asyncio.create_task(self.udp_keepalive())
        return result

    async def udp_keepalive(self):
        """Send silence to keep UDP session alive"""
        # Wait 3 second to ensure UDP is ready
        await asyncio.sleep(3)

        silence = b'\xf8\xff\xfe'
        extended_silence = silence * 50  # ~1 second

        logger.info("Keepalive task started")

        while self.is_connected():
            try:
                self.send_audio_packet(extended_silence, encode=False)
                logger.info("Sending listen_Keep_Alive")
                await asyncio.sleep(15)
            except Exception as e:
                logger.error(f"[KeepAlive] Error: {e}")
                break

    async def disconnect(self, *args, **kwargs):
        if self._keepalive_task:
            self._keepalive_task.cancel()
        await super().disconnect(*args, **kwargs)

# -----------------------
# VoiceCog
# -----------------------
class VoiceCog(BaseCog):
    """Voice channel commands for recording and speech-to-text."""
    active_sinks = {}
    buffer_tasks = {}

    def __init__(self, bot):
        super().__init__(bot)
        self.vosk_model = Model("vosk/vosk-model-small-en-us-0.15")

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, user: discord.Member):
        try:
            logger.info(f"🎤 [Event] {user.display_name} started speaking")
        except Exception as e:
            logger.error(f"🎤 [Event] started speaking : {e}")

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, user: discord.Member):
        try:
            logger.info(f"🎤 [Event] {user.display_name} stoped speaking")
        except Exception as e:
            logger.error(f"🎤 [Event] stoped speaking : {e}")

    @commands.command(name="join")
    async def join(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send("⚠️ You are not in a voice channel!")

        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.send("✅ Already connected.")
            return

        # Use KeepAliveVoiceClient here
        vc: KeepAliveVoiceClient = await channel.connect(cls=KeepAliveVoiceClient, self_deaf=False)
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
        vc: KeepAliveVoiceClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        class VoskSink(voice_recv.AudioSink):
            def __init__(self, cog: "VoiceCog"):
                super().__init__()
                self.cog = cog
                self.buffers = {}
                self.MAX_BUFFER_SIZE = 16000 * 2 * 10  # ~10 seconds of 16-bit mono @16 kHz


            def write(self, user, data):
                if not data.pcm:
                    return
                pcm = np.frombuffer(data.pcm, dtype=np.int16)
                mono = pcm[::2]
                downsampled = mono[::3]
                sink_data = downsampled.tobytes()

                if user.id not in self.buffers:
                    self.buffers[user.id] = bytearray()
                self.buffers[user.id].extend(sink_data)
                if len(self.buffers[user.id]) > self.MAX_BUFFER_SIZE:
                    self.buffers[user.id] = self.buffers[user.id][-self.MAX_BUFFER_SIZE:]
                '''
                task_future = self.cog.buffer_tasks.get(user.id)
                if not task_future or task_future.done():
                    future = asyncio.run_coroutine_threadsafe(
                        self.cog.transcribe_user(user.id, self), self.cog.bot.loop
                    )
                    self.cog.buffer_tasks[user.id] = future
                '''

            def wants_opus(self):
                return False

            def cleanup(self):
                pass



        sink = VoskSink(self)
        vc.listen(sink)
        self.active_sinks[ctx.guild.id] = sink
        await ctx.send("🎙️ Started recording and transcribing (48→16 kHz fixed).")

    async def transcribe_user(self, user_id, sink: "VoskSink"):
        pass
        #recognizer = KaldiRecognizer(self.vosk_model, 16000)
        while user_id in sink.buffers and sink.buffers[user_id]:
            audio_bytes = bytes(sink.buffers[user_id])
            '''
            if recognizer.AcceptWaveform(audio_bytes):
                result_json = json.loads(recognizer.Result())
                text = result_json.get("text", "").strip()
                if text:
                    member = None
                    for guild in self.bot.guilds:
                        member = guild.get_member(user_id)
                        if member:
                            break
                    name = member.display_name if member else str(user_id)
                    logger.info(f"[Vosk] {name}: {text}")
                    #sink.buffers[user_id] = bytearray()
            else:
                json.loads(recognizer.PartialResult())
            await asyncio.sleep(0.1)
            '''

    @commands.command(name="stop")
    async def stop(self, ctx):
        vc: KeepAliveVoiceClient = ctx.voice_client
        if not vc or ctx.guild.id not in self.active_sinks:
            return await ctx.send("⚠️ Not currently recording.")

        sink = self.active_sinks.pop(ctx.guild.id)
        vc.stop_listening()

        for user_id, audio_bytes in sink.buffers.items():
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else str(user_id)
            filename = f"{name}_{user_id}.wav"
            with wave.open(filename, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_bytes)

        await ctx.send("🛑 Finished recording and saved WAV files.")


async def setup(bot):
    await bot.add_cog(VoiceCog(bot))
