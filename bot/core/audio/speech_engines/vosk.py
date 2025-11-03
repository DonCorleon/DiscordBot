"""
Vosk speech recognition engine.

Fast, local speech recognition using Vosk library directly.
Best for low-latency real-time applications.

Implementation based on direct AudioSink usage for full control.
"""

import asyncio
import json
import discord
from discord.ext import voice_recv
import numpy as np
import time
from typing import Optional
from collections import deque, defaultdict
from concurrent.futures import ThreadPoolExecutor
from .base import SpeechEngine, logger

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logger.warning("Vosk not installed. Install with: pip install vosk")


class VoskSink(voice_recv.AudioSink):
    """
    Custom AudioSink for Vosk speech recognition.

    Processes audio chunks and transcribes using Vosk's KaldiRecognizer.
    Based on proven pattern from user's working implementation.
    """

    CHUNK_TIME = 4  # Process audio every 4 seconds
    OVERLAP_TIME = 0.5  # Keep 0.5s overlap between chunks
    SAMPLE_RATE = 48000  # Discord's sample rate
    CHANNELS = 2  # Stereo
    SAMPLE_WIDTH = 2  # 16-bit audio

    def __init__(
        self,
        vc: discord.VoiceClient,
        callback,
        vosk_model,
        executor: ThreadPoolExecutor,
        ducking_callback=None
    ):
        """
        Initialize Vosk sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            vosk_model: Loaded Vosk Model instance
            executor: ThreadPoolExecutor for blocking Vosk calls
            ducking_callback: Optional callback for ducking events
        """
        super().__init__()
        self.vc = vc
        self.callback = callback
        self.vosk_model = vosk_model
        self.executor = executor
        self.ducking_callback = ducking_callback

        # Per-user state
        self.buffers = {}  # {user_id: deque([audio_chunks])}
        self.recognizers = {}  # {user_id: KaldiRecognizer}
        self.last_chunk_time = {}  # {user_id: timestamp}
        self.user_locks = defaultdict(asyncio.Lock)

        logger.info(f"[Guild {vc.guild.id}] VoskSink initialized")

    def write(self, user: discord.User, data: voice_recv.VoiceData):
        """
        Called for every audio packet from Discord.

        Buffers audio per user and processes chunks periodically.
        """
        try:
            if not data.pcm:
                return

            async def process_user_audio():
                async with self.user_locks[user.id]:
                    # Initialize user state
                    if user.id not in self.buffers:
                        self.buffers[user.id] = deque()
                        self.last_chunk_time[user.id] = time.time()
                        # Don't create recognizer here - will be created in executor thread
                        # for thread safety (KaldiRecognizer is not thread-safe)

                    # Add audio to buffer
                    self.buffers[user.id].append(data.pcm)

                    # Check if it's time to process this chunk
                    if time.time() - self.last_chunk_time[user.id] >= self.CHUNK_TIME:
                        # Concatenate all buffered audio
                        pcm_data = b''.join(self.buffers[user.id])

                        # Keep overlap for next chunk (prevents missing words)
                        bytes_per_second = self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH
                        overlap_bytes = int(bytes_per_second * self.OVERLAP_TIME)
                        self.buffers[user.id] = deque([pcm_data[-overlap_bytes:]])
                        self.last_chunk_time[user.id] = time.time()

                        # Get member object
                        member = self.vc.guild.get_member(user.id)
                        if not member:
                            return

                        # Process in thread pool (blocking Vosk call)
                        recognizer = self.recognizers.get(user.id)
                        self.vc.loop.run_in_executor(
                            self.executor,
                            self.transcribe_user,
                            pcm_data,
                            member,
                            recognizer
                        )

            asyncio.run_coroutine_threadsafe(process_user_audio(), self.vc.loop)

        except Exception as e:
            logger.error(f"VoskSink write error: {e}", exc_info=True)

    def transcribe_user(self, pcm_data: bytes, member: discord.Member, recognizer: Optional[KaldiRecognizer]):
        """
        Transcribe audio using Vosk (runs in thread pool).

        Args:
            pcm_data: Raw PCM audio bytes (stereo)
            member: Discord member who spoke
            recognizer: KaldiRecognizer instance for this user (or None to create new)
        """
        # Ensure recognizer exists (create in executor thread for thread safety)
        if recognizer is None:
            try:
                recognizer = KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
                self.recognizers[member.id] = recognizer
            except Exception as e:
                logger.error(f"Failed to create recognizer for {member.display_name}: {e}", exc_info=True)
                return

        try:
            # Convert stereo to mono
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            if len(audio_array) % 2 != 0:
                audio_array = audio_array[:-1]
            audio_array = audio_array.reshape(-1, 2)
            mono_audio = audio_array.mean(axis=1).astype(np.int16)
        except Exception as e:
            logger.error(f"Audio processing error for {member.display_name}: {e}", exc_info=True)
            return

        # VAD: Check if audio contains speech using RMS energy threshold
        # Calculate RMS (Root Mean Square) energy
        rms = np.sqrt(np.mean(mono_audio.astype(np.float32) ** 2))

        # Threshold for silence detection (typical speech is > 500 RMS)
        # Adjust based on your environment (lower = more sensitive, higher = less sensitive)
        SILENCE_THRESHOLD = 300

        if rms < SILENCE_THRESHOLD:
            logger.debug(f"[Guild {self.vc.guild.id}] Vosk: Skipping silence for {member.display_name} (RMS: {rms:.1f})")
            return

        try:
            # Feed to Vosk
            recognizer.AcceptWaveform(mono_audio.tobytes())
            vosk_result = json.loads(recognizer.Result())
            vosk_text = vosk_result.get("text", "").strip()

            # CRITICAL: Reset recognizer after Result() to clear internal state
            # Vosk's KaldiRecognizer accumulates state and must be reset
            # or recreated after each Result() call to prevent assertion failures
            recognizer.Reset()
        except Exception as e:
            logger.error(f"Vosk transcription error for {member.display_name}: {e}", exc_info=True)
            # Try to reset recognizer on error to clear corrupted state
            try:
                recognizer.Reset()
            except Exception:
                pass
            return

        if vosk_text:
            logger.info(f"[Guild {self.vc.guild.id}] Vosk transcribed {member.display_name}: {vosk_text}")
            # Invoke callback
            try:
                self.callback(member, vosk_text)
            except Exception as e:
                logger.error(f"Error in Vosk callback: {e}", exc_info=True)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member):
        """Handle member starting to speak."""
        if member.bot:
            return
        logger.debug(f"[Guild {self.vc.guild.id}] 🎤 {member.display_name} started speaking")

        # Notify ducking callback
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, is_speaking=True)
            except Exception as e:
                logger.error(f"Error in ducking callback (start): {e}", exc_info=True)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
        """Handle member stopping speaking."""
        if member.bot:
            return
        logger.debug(f"[Guild {self.vc.guild.id}] 🔇 {member.display_name} stopped speaking")

        # Process any remaining audio
        if member.id in self.buffers and self.buffers[member.id]:
            pcm_data = b''.join(self.buffers[member.id])
            self.buffers[member.id].clear()
            recognizer = self.recognizers.get(member.id)
            if pcm_data and recognizer:
                self.vc.loop.run_in_executor(
                    self.executor,
                    self.transcribe_user,
                    pcm_data,
                    member,
                    recognizer
                )

        # Notify ducking callback
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, is_speaking=False)
            except Exception as e:
                logger.error(f"Error in ducking callback (stop): {e}", exc_info=True)

    def cleanup(self):
        """Cleanup resources."""
        self.buffers.clear()
        self.recognizers.clear()
        self.last_chunk_time.clear()
        logger.debug(f"[Guild {self.vc.guild.id}] VoskSink cleaned up")

    def wants_opus(self) -> bool:
        """We want PCM audio, not Opus."""
        return False


class VoskEngine(SpeechEngine):
    """
    Vosk-based speech recognition engine.

    Uses Vosk library directly with custom AudioSink for full control.
    Provides fast, local speech recognition with minimal latency.
    """

    def __init__(
        self,
        bot,
        callback,
        model_path: str = "data/speechrecognition/vosk",
        ducking_callback=None
    ):
        """
        Initialize Vosk engine.

        Args:
            bot: Discord bot instance
            callback: Function called with (member, transcribed_text)
            model_path: Path to Vosk model directory
            ducking_callback: Optional callback for audio ducking events
        """
        super().__init__(bot, callback)

        if not VOSK_AVAILABLE:
            raise ImportError("Vosk not available. Install with: pip install vosk")

        self.model_path = model_path
        self.ducking_callback = ducking_callback
        self.sink = None
        self.model = None
        self.executor = ThreadPoolExecutor(max_workers=4)

        logger.info(f"VoskEngine initialized (model={model_path})")

    async def start_listening(self, voice_client):
        """Start Vosk speech recognition."""
        if not VOSK_AVAILABLE:
            raise ImportError("Vosk not available")

        # Load model on first use (lazy loading)
        if self.model is None:
            logger.info(f"Loading Vosk model from '{self.model_path}'...")
            try:
                self.model = Model(self.model_path)
                logger.info(f"Vosk model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load Vosk model: {e}", exc_info=True)
                raise

        # Create VoskSink
        self.sink = VoskSink(
            voice_client,
            self.callback,
            self.model,
            self.executor,
            ducking_callback=self.ducking_callback
        )

        # Attach to voice client
        voice_client.listen(self.sink)
        self._is_listening = True

        logger.info(f"[Guild {voice_client.guild.id}] Started Vosk speech recognition")
        return self.sink

    async def stop_listening(self):
        """Stop Vosk speech recognition and cleanup resources."""
        if self.sink:
            self.sink.cleanup()
            self.sink = None

        self._is_listening = False
        logger.info("Stopped Vosk speech recognition")

    def get_sink(self) -> Optional[voice_recv.AudioSink]:
        """Get the Vosk sink instance."""
        return self.sink

    def __del__(self):
        """Cleanup executor on engine destruction."""
        if hasattr(self, 'executor'):
            # Use wait=True to prevent segfaults from forcefully killing threads
            # that are executing Vosk native code
            self.executor.shutdown(wait=True)
