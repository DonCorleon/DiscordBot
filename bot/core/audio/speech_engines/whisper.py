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
from typing import Optional
from .base import SpeechEngine, logger
from .base_sink import BaseSpeechSink
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
TIMEOUT_SECONDS = 30     # Transcription timeout


class WhisperSink(BaseSpeechSink):
    """
    Whisper-specific sink using BaseSpeechSink buffering logic.

    Only implements Whisper transcription - all buffering handled by base class.
    """

    def __init__(
        self,
        vc: discord.VoiceClient,
        callback,
        whisper_model,
        chunk_duration: float,
        chunk_overlap: float,
        processing_interval: float,
        executor: ThreadPoolExecutor,
        ducking_callback=None
    ):
        """
        Initialize Whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            whisper_model: Loaded Whisper model instance
            chunk_duration: Process audio every N seconds
            chunk_overlap: Overlap between chunks in seconds
            processing_interval: How often to check buffers for processing (seconds)
            executor: ThreadPoolExecutor for blocking Whisper calls
            ducking_callback: Optional callback for ducking events
        """
        # Initialize base class with common buffering logic
        super().__init__(
            vc=vc,
            callback=callback,
            chunk_duration=chunk_duration,
            chunk_overlap=chunk_overlap,
            processing_interval=processing_interval,
            executor=executor,
            ducking_callback=ducking_callback
        )

        # Whisper-specific: Store model
        self.whisper_model = whisper_model

    def transcribe_audio(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using Whisper (runs in thread pool).

        Args:
            pcm_data: Raw PCM audio bytes (stereo int16, 48kHz)
            member: Discord member who spoke
        """
        try:
            # Convert stereo int16 PCM to mono float32
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
            result = self.whisper_model.transcribe(audio_16k, fp16=False, language="en")
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

    def cleanup(self):
        """Cleanup Whisper-specific resources and call base cleanup."""
        super().cleanup()
        logger.debug(f"[Guild {self.vc.guild.id}] WhisperSink Whisper-specific cleanup complete")


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
            vc=voice_client,
            callback=self.callback,
            whisper_model=self.model,
            chunk_duration=speech_cfg.whisper_chunk_duration,
            chunk_overlap=speech_cfg.whisper_chunk_overlap,
            processing_interval=speech_cfg.whisper_processing_interval,
            executor=self.executor,
            ducking_callback=self.ducking_callback
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
