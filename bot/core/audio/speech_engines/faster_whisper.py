"""
Faster-Whisper speech recognition engine.

High-speed, accurate speech recognition using faster-whisper (CTranslate2 backend).
Up to 4x faster than openai-whisper with same accuracy, lower memory usage.

Implementation based on WhisperSink pattern with:
- Per-user audio buffering
- Rolling buffer with configurable duration
- Resampling from Discord's 96kHz to Whisper's 16kHz
- VAD (Voice Activity Detection) support
- GPU acceleration support
"""

import asyncio
import discord
from discord.ext import voice_recv
import numpy as np
import time
import threading
from typing import Optional
from collections import deque
from .base import SpeechEngine, logger
from concurrent.futures import ThreadPoolExecutor

try:
    from faster_whisper import WhisperModel
    from scipy.signal import resample
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.warning(
        "faster-whisper dependencies not installed. Install with: pip install faster-whisper scipy"
    )


# Audio constants
SAMPLE_RATE = 48000      # Discord's sample rate (48kHz stereo)
TARGET_SR = 16000        # Whisper expects 16kHz mono
CHANNELS = 2             # Stereo
SAMPLE_WIDTH = 2         # 16-bit samples


class FasterWhisperSink(voice_recv.BasicSink):
    """
    Custom sink for capturing audio and processing with faster-whisper.

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
        Initialize faster-whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            model: Loaded WhisperModel instance
            executor: ThreadPoolExecutor for blocking transcription calls
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

        logger.info(f"[Guild {vc.guild.id}] FasterWhisperSink initialized (chunk={chunk_duration}s, overlap={chunk_overlap}s, interval={processing_interval}s)")

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
            logger.error(f"FasterWhisperSink write error: {e}", exc_info=True)

    def transcribe_user(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using faster-whisper (runs in thread pool).

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
                logger.debug(f"[Guild {self.vc.guild.id}] faster-whisper: Skipping silence for {member.display_name} (RMS: {rms:.4f}, threshold: {normalized_threshold:.4f})")
                return

        # Resample 48kHz → 16kHz for Whisper
        try:
            target_len = int(len(mono_audio) * TARGET_SR / SAMPLE_RATE)
            audio_16k = resample(mono_audio, target_len)
        except Exception as e:
            logger.warning(f"[Guild {self.vc.guild.id}] Resample failed for {member.display_name}: {e}")
            return

        # Transcribe with faster-whisper (blocking call, runs in thread pool)
        try:
            # faster-whisper expects numpy array directly
            segments, info = self.model.transcribe(
                audio_16k,
                beam_size=5,
                language="en",
                condition_on_previous_text=False
            )

            # Collect all segments into single text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            faster_whisper_text = " ".join(text_parts).strip()
        except Exception as e:
            logger.error(f"faster-whisper transcription error for {member.display_name}: {e}", exc_info=True)
            return

        if faster_whisper_text:
            logger.info(f"[Guild {self.vc.guild.id}] faster-whisper transcribed {member.display_name}: {faster_whisper_text}")
            # Invoke callback
            try:
                self.callback(member, faster_whisper_text)
            except Exception as e:
                logger.error(f"Error in faster-whisper callback: {e}", exc_info=True)

    def start_processing(self):
        """Start background task to process audio buffers periodically."""
        if self._processing_task is None or self._processing_task.done():
            self._stop_processing = False
            self._processing_task = asyncio.create_task(self._process_buffers_loop())
            logger.info(f"[Guild {self.vc.guild.id}] Started faster-whisper buffer processing task")

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

                    # Process in thread pool (blocking faster-whisper call)
                    self.vc.loop.run_in_executor(
                        self.executor,
                        self.transcribe_user,
                        pcm_data,
                        member
                    )

        except asyncio.CancelledError:
            logger.info(f"[Guild {self.vc.guild.id}] faster-whisper buffer processing task cancelled")
            raise
        except Exception as e:
            logger.error(f"[Guild {self.vc.guild.id}] Error in faster-whisper buffer processing: {e}", exc_info=True)

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
        logger.debug(f"[Guild {self.vc.guild.id}] FasterWhisperSink cleaned up")

    def wants_opus(self) -> bool:
        """We want PCM audio, not Opus."""
        return False


class FasterWhisperEngine(SpeechEngine):
    """
    faster-whisper speech recognition engine.

    Uses CTranslate2 backend for 4x faster inference than openai-whisper.
    Supports both CPU and GPU acceleration.
    """

    def __init__(
        self,
        bot,
        callback,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        ducking_callback=None
    ):
        """
        Initialize faster-whisper engine.

        Args:
            bot: Discord bot instance
            callback: Function called with (member, transcribed_text)
            model_size: Model size (tiny, base, small, medium, large-v2, large-v3)
            device: "cpu" or "cuda"
            compute_type: "int8", "int8_float16", "float16", "float32"
            ducking_callback: Optional callback for audio ducking events
        """
        super().__init__(bot, callback)

        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("faster-whisper not available. Install with: pip install faster-whisper scipy")

        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.ducking_callback = ducking_callback
        self.sink = None
        self.model = None
        self.executor = ThreadPoolExecutor(max_workers=2)

        logger.info(f"FasterWhisperEngine initialized (model={model_size}, device={device}, compute_type={compute_type})")

    async def start_listening(self, voice_client):
        """Start faster-whisper speech recognition."""
        if not FASTER_WHISPER_AVAILABLE:
            raise ImportError("faster-whisper not available")

        # Load model on first use (lazy loading)
        if self.model is None:
            logger.info(f"Loading faster-whisper model '{self.model_size}' on {self.device}...")
            try:
                # Download to local directory (data/speechrecognition/faster-whisper/)
                import os
                download_root = os.path.join("data", "speechrecognition", "faster-whisper")
                os.makedirs(download_root, exist_ok=True)

                self.model = WhisperModel(
                    self.model_size,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=download_root
                )
                logger.info(f"faster-whisper model '{self.model_size}' loaded successfully from {download_root}")
            except Exception as e:
                logger.error(f"Failed to load faster-whisper model: {e}", exc_info=True)
                raise

        # Get config from ConfigManager
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        # Create sink
        self.sink = FasterWhisperSink(
            voice_client,
            self.callback,
            self.model,
            self.executor,
            ducking_callback=self.ducking_callback,
            chunk_duration=speech_cfg.speech_chunk_duration,
            chunk_overlap=speech_cfg.speech_chunk_overlap,
            processing_interval=speech_cfg.speech_processing_interval
        )

        # Attach to voice client
        voice_client.listen(self.sink)

        # Start background buffer processing task
        self.sink.start_processing()

        self._is_listening = True

        logger.info(f"[Guild {voice_client.guild.id}] Started faster-whisper speech recognition")
        return self.sink

    async def stop_listening(self):
        """Stop faster-whisper speech recognition and cleanup resources."""
        if self.sink:
            self.sink.cleanup()
            self.sink = None
        self._is_listening = False
        logger.info("Stopped faster-whisper speech recognition")

    def get_sink(self):
        """Get the current audio sink."""
        return self.sink
