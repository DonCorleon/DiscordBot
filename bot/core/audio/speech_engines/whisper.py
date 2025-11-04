"""
Whisper speech recognition engine.

Higher accuracy speech recognition using OpenAI's Whisper model.
Trade-off: Higher latency than Vosk, but better transcription quality.

Implementation based on ResilientWhisperSink pattern with:
- Per-user audio buffering
- Rolling 3-second buffer
- Resampling from 96kHz to 16kHz
- Resilient error handling with auto-restart
"""

import asyncio
import discord
from discord.ext import voice_recv
import time
import threading
from typing import Optional
from collections import deque
from .base import SpeechEngine, logger
from concurrent.futures import ThreadPoolExecutor

try:
    import whisper
    import numpy as np
    from scipy.signal import resample
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    logger.warning(
        "Whisper dependencies not installed. Install with: uv add openai-whisper scipy"
    )


# Audio constants
SAMPLE_RATE = 48000      # Discord's sample rate (48kHz stereo)
TARGET_SR = 16000        # Whisper expects 16kHz
CHANNELS = 2             # Stereo
SAMPLE_WIDTH = 2         # 16-bit samples


class WhisperSink(voice_recv.BasicSink):
    """
    Custom sink for capturing audio and processing with Whisper.

    Uses Vosk's proven periodic buffering pattern.
    """

    def __init__(
        self,
        vc,
        callback,
        model,
        executor: ThreadPoolExecutor,
        ducking_callback=None,
        chunk_duration: float = 4.0,
        chunk_overlap: float = 0.5,
        processing_interval: float = 0.1
    ):
        """
        Initialize Whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            model: Loaded Whisper model
            executor: ThreadPoolExecutor for blocking Whisper calls
            ducking_callback: Optional callback for ducking events
            chunk_duration: Process audio every N seconds
            chunk_overlap: Overlap between chunks in seconds
            processing_interval: How often to check buffers for processing (seconds)
        """
        super().__init__(asyncio.Event())
        self.vc = vc
        self.callback = callback
        self.model = model
        self.executor = executor
        self.ducking_callback = ducking_callback

        # Configurable timing parameters (same as Vosk)
        self.chunk_duration = chunk_duration
        self.chunk_overlap = chunk_overlap
        self.processing_interval = processing_interval

        # Per-user state (thread-safe with threading.Lock)
        self.buffers = {}  # {user_id: deque([pcm_bytes])}
        self.last_chunk_time = {}  # {user_id: timestamp}
        self.buffer_lock = threading.Lock()  # Thread lock for buffer access

        # Background processing task
        self._processing_task = None
        self._stop_processing = False

        logger.info(f"[Guild {vc.guild.id}] WhisperSink initialized (chunk={chunk_duration}s, overlap={chunk_overlap}s, interval={processing_interval}s)")

    def write(self, source, data):
        """
        Called for every audio packet from Discord (sync, must be FAST).

        Simply appends to buffer - no async operations, no event loop scheduling.
        Background task processes buffers periodically.
        """
        try:
            if not data.pcm:
                return

            # source is the discord.Member object
            member = source
            if not member or member.bot:
                return

            # Fast synchronous buffer append with thread lock
            with self.buffer_lock:
                # Initialize user state on first packet
                if member.id not in self.buffers:
                    self.buffers[member.id] = deque()
                    self.last_chunk_time[member.id] = time.time()

                # Append audio to buffer (fast, no processing)
                self.buffers[member.id].append(data.pcm)

        except Exception as e:
            logger.error(f"WhisperSink write error: {e}", exc_info=True)

    def transcribe_user(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using Whisper (runs in thread pool).

        Args:
            pcm_data: Raw PCM audio bytes (stereo int16)
            member: Discord member who spoke
        """
        try:
            # Convert stereo int16 to mono float32
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            if len(audio_array) % 2 != 0:
                audio_array = audio_array[:-1]
            audio_array = audio_array.reshape(-1, 2)
            mono_audio = audio_array.mean(axis=1).astype(np.float32) / 32768.0  # Normalize to [-1.0, 1.0]
        except Exception as e:
            logger.error(f"Audio processing error for {member.display_name}: {e}", exc_info=True)
            return

        # VAD: Check if audio contains speech using RMS energy threshold
        from bot.config import config as bot_config
        speech_cfg = bot_config.config_manager.for_guild("Speech", self.vc.guild.id) if hasattr(bot_config, 'config_manager') else None

        if speech_cfg and speech_cfg.enable_vad:
            rms = np.sqrt(np.mean(mono_audio ** 2))

            # Normalize threshold for float32 audio (Whisper uses normalized audio 0.0-1.0)
            # Vosk uses int16 audio (~0-1000), so we need to scale threshold
            # float32 typical speech RMS: ~0.01-0.1, int16 typical speech RMS: ~100-1000
            # Scale factor: 0.01 / 100 = 0.0001
            normalized_threshold = speech_cfg.vad_silence_threshold * 0.0001

            if rms < normalized_threshold:
                logger.debug(f"[Guild {self.vc.guild.id}] Whisper: Skipping silence for {member.display_name} (RMS: {rms:.4f}, threshold: {normalized_threshold:.4f})")
                return

        # Resample 48kHz → 16kHz for Whisper
        try:
            target_len = int(len(mono_audio) * TARGET_SR / SAMPLE_RATE)
            audio_16k = resample(mono_audio, target_len)
        except Exception as e:
            logger.warning(f"[Guild {self.vc.guild.id}] Resample failed for {member.display_name}: {e}")
            return

        # Transcribe with Whisper (blocking call, runs in thread pool)
        try:
            result = self.model.transcribe(audio_16k, fp16=False, language="en")
            whisper_text = result["text"].strip()
        except Exception as e:
            logger.error(f"Whisper transcription error for {member.display_name}: {e}", exc_info=True)
            return

        if whisper_text:
            logger.info(f"[Guild {self.vc.guild.id}] Whisper transcribed {member.display_name}: {whisper_text}")
            # Invoke callback
            try:
                self.callback(member, whisper_text)
            except Exception as e:
                logger.error(f"Error in Whisper callback: {e}", exc_info=True)

    def start_processing(self):
        """Start background task to process audio buffers periodically."""
        if self._processing_task is None or self._processing_task.done():
            self._stop_processing = False
            self._processing_task = asyncio.create_task(self._process_buffers_loop())
            logger.info(f"[Guild {self.vc.guild.id}] Started Whisper buffer processing task")

    async def _process_buffers_loop(self):
        """Background task that periodically checks and processes audio buffers."""
        try:
            while not self._stop_processing:
                await asyncio.sleep(self.processing_interval)

                # Get snapshot of users to process (thread-safe)
                with self.buffer_lock:
                    users_to_process = []
                    current_time = time.time()

                    for user_id, buffer in list(self.buffers.items()):
                        # Check if enough time has elapsed for this user
                        if current_time - self.last_chunk_time.get(user_id, 0) >= self.chunk_duration:
                            if buffer:  # Only process if buffer has data
                                # Concatenate all buffered audio
                                pcm_data = b''.join(buffer)

                                # Keep overlap for next chunk (prevents missing words)
                                bytes_per_second = SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH
                                overlap_bytes = int(bytes_per_second * self.chunk_overlap)
                                self.buffers[user_id] = deque([pcm_data[-overlap_bytes:]]) if len(pcm_data) > overlap_bytes else deque()
                                self.last_chunk_time[user_id] = current_time

                                # Add to processing list
                                users_to_process.append((user_id, pcm_data))

                # Process users outside the lock
                for user_id, pcm_data in users_to_process:
                    # Get member object
                    member = self.vc.guild.get_member(user_id)
                    if not member:
                        continue

                    # Process in thread pool (blocking Whisper call)
                    self.vc.loop.run_in_executor(
                        self.executor,
                        self.transcribe_user,
                        pcm_data,
                        member
                    )

        except asyncio.CancelledError:
            logger.info(f"[Guild {self.vc.guild.id}] Whisper buffer processing task cancelled")
            raise
        except Exception as e:
            logger.error(f"[Guild {self.vc.guild.id}] Error in Whisper buffer processing: {e}", exc_info=True)

    @voice_recv.BasicSink.listener()
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

    @voice_recv.BasicSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
        """Handle member stopping speaking."""
        if member.bot:
            return
        logger.debug(f"[Guild {self.vc.guild.id}] 🔇 {member.display_name} stopped speaking")

        # Process any remaining audio (thread-safe)
        with self.buffer_lock:
            if member.id in self.buffers and self.buffers[member.id]:
                pcm_data = b''.join(self.buffers[member.id])
                self.buffers[member.id].clear()

                if pcm_data:
                    self.vc.loop.run_in_executor(
                        self.executor,
                        self.transcribe_user,
                        pcm_data,
                        member
                    )

        # Notify ducking callback
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, is_speaking=False)
            except Exception as e:
                logger.error(f"Error in ducking callback (stop): {e}", exc_info=True)

    def cleanup(self):
        """Cleanup resources and stop background task."""
        self._stop_processing = True
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        self.buffers.clear()
        self.last_chunk_time.clear()
        logger.debug(f"[Guild {self.vc.guild.id}] WhisperSink cleaned up")


class WhisperEngine(SpeechEngine):
    """
    Whisper-based speech recognition engine.

    Uses OpenAI's Whisper model for high-accuracy transcription.
    Best for scenarios where accuracy is more important than latency.

    Features:
    - Per-user audio buffering and processing
    - Rolling buffer to prevent missing words
    - Resilient error handling with auto-restart
    - Audio resampling (96kHz → 16kHz)
    - Configurable model size and buffer settings
    """

    def __init__(
        self,
        bot,
        callback,
        model_size: str = "tiny.en",
        buffer_duration: float = 3.0,
        debounce_seconds: float = 1.0,
        ducking_callback=None
    ):
        """
        Initialize Whisper engine.

        Args:
            bot: Discord bot instance
            callback: Function called with (member, transcribed_text)
            model_size: Whisper model size (tiny.en, base.en, small.en, etc.)
            buffer_duration: Audio buffer duration in seconds
            debounce_seconds: Min seconds between transcriptions
            ducking_callback: Optional callback for audio ducking events
        """
        super().__init__(bot, callback)

        if not WHISPER_AVAILABLE:
            raise ImportError(
                "Whisper dependencies not available. Install with: uv add openai-whisper scipy"
            )

        self.model_size = model_size
        self.buffer_duration = buffer_duration
        self.debounce_seconds = debounce_seconds
        self.ducking_callback = ducking_callback
        self.sink = None
        self.model = None
        self.executor = ThreadPoolExecutor(max_workers=4)

        logger.info(f"WhisperEngine initialized (model={model_size}, buffer={buffer_duration}s)")

    async def start_listening(self, voice_client):
        """
        Start Whisper speech recognition.

        Loads the Whisper model (if not already loaded) and creates a WhisperSink
        to capture and process audio.
        """
        if not WHISPER_AVAILABLE:
            raise ImportError("Whisper dependencies not available")

        # Load model on first use (lazy loading)
        if self.model is None:
            logger.info(f"Loading Whisper model '{self.model_size}'...")
            try:
                # Load from data/speechrecognition/whisper/ directory
                import os
                download_root = os.path.join("data", "speechrecognition", "whisper")
                os.makedirs(download_root, exist_ok=True)

                self.model = whisper.load_model(self.model_size, download_root=download_root)
                logger.info(f"Whisper model '{self.model_size}' loaded successfully from {download_root}")
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}", exc_info=True)
                raise

        # Get Whisper config from ConfigManager
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        # Create and attach WhisperSink
        self.sink = WhisperSink(
            voice_client,
            self.callback,
            self.model,
            self.executor,
            ducking_callback=self.ducking_callback,
            chunk_duration=speech_cfg.whisper_chunk_duration,
            chunk_overlap=speech_cfg.whisper_chunk_overlap,
            processing_interval=speech_cfg.whisper_processing_interval
        )

        # Attach to voice client
        voice_client.listen(self.sink)

        # Start background buffer processing task
        self.sink.start_processing()

        self._is_listening = True

        logger.info(f"[Guild {voice_client.guild.id}] Started Whisper speech recognition")
        return self.sink

    async def stop_listening(self):
        """
        Stop Whisper speech recognition and cleanup resources.
        """
        if self.sink:
            self.sink.cleanup()
            self.sink = None

        # Note: Don't shutdown executor here - it may be reused if listening restarts
        # Executor will be cleaned up when the engine is destroyed

        self._is_listening = False
        logger.info("Stopped Whisper speech recognition")

    def get_sink(self) -> Optional[voice_recv.BasicSink]:
        """Get the Whisper sink instance."""
        return self.sink

    def __del__(self):
        """Cleanup executor on engine destruction."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
