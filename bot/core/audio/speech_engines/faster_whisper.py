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
from typing import Optional
from .base import SpeechEngine, logger
from .base_sink import BaseSpeechSink
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
TIMEOUT_SECONDS = 30     # Transcription timeout


class FasterWhisperSink(BaseSpeechSink):
    """
    Faster-Whisper-specific sink using BaseSpeechSink buffering logic.

    Only implements faster-whisper transcription - all buffering handled by base class.
    """

    def __init__(
        self,
        vc: discord.VoiceClient,
        callback,
        faster_whisper_model,
        chunk_duration: float,
        chunk_overlap: float,
        processing_interval: float,
        executor: ThreadPoolExecutor,
        ducking_callback=None
    ):
        """
        Initialize faster-whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            faster_whisper_model: Loaded WhisperModel instance
            chunk_duration: Process audio every N seconds
            chunk_overlap: Overlap between chunks in seconds
            processing_interval: How often to check buffers for processing (seconds)
            executor: ThreadPoolExecutor for blocking transcription calls
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

        # Faster-Whisper-specific: Store model
        self.faster_whisper_model = faster_whisper_model

    def transcribe_audio(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using faster-whisper (runs in thread pool).

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
            segments, info = self.faster_whisper_model.transcribe(
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

    def cleanup(self):
        """Cleanup faster-whisper-specific resources and call base cleanup."""
        super().cleanup()
        logger.debug(f"[Guild {self.vc.guild.id}] FasterWhisperSink faster-whisper-specific cleanup complete")


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

        # Get config values
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        # Create sink
        self.sink = FasterWhisperSink(
            vc=voice_client,
            callback=self.callback,
            faster_whisper_model=self.model,
            chunk_duration=speech_cfg.faster_whisper_chunk_duration,
            chunk_overlap=speech_cfg.faster_whisper_chunk_overlap,
            processing_interval=speech_cfg.faster_whisper_processing_interval,
            executor=self.executor,
            ducking_callback=self.ducking_callback
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
