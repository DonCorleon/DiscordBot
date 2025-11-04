"""
Vosk speech recognition engine.

Fast, local speech recognition using Vosk library directly.
Best for low-latency real-time applications.
"""

import json
import discord
import numpy as np
import threading
from typing import Optional
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from .base import SpeechEngine, logger
from .base_sink import BaseSpeechSink

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    logger.warning("Vosk not installed. Install with: pip install vosk")


class VoskSink(BaseSpeechSink):
    """
    Vosk-specific sink using BaseSpeechSink buffering logic.

    Only implements Vosk transcription - all buffering handled by base class.
    """

    def __init__(
        self,
        vc: discord.VoiceClient,
        callback,
        vosk_model,
        chunk_duration: float,
        chunk_overlap: float,
        processing_interval: float,
        executor: ThreadPoolExecutor,
        ducking_callback=None
    ):
        """
        Initialize Vosk sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            vosk_model: Loaded Vosk Model instance
            chunk_duration: Process audio every N seconds
            chunk_overlap: Overlap between chunks in seconds
            processing_interval: How often to check buffers for processing (seconds)
            executor: ThreadPoolExecutor for blocking Vosk calls
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

        # Vosk-specific: Store model and recognizers
        self.vosk_model = vosk_model
        self.recognizers = {}  # {user_id: KaldiRecognizer}
        self.recognizer_locks = defaultdict(threading.Lock)

    def transcribe_audio(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using Vosk (runs in thread pool).

        Args:
            pcm_data: Raw PCM audio bytes (stereo)
            member: Discord member who spoke
        """
        # Use per-user lock to serialize access to recognizer
        # This prevents race conditions while maintaining context across chunks
        with self.recognizer_locks[member.id]:
            # Get or create recognizer for this user
            if member.id not in self.recognizers:
                try:
                    self.recognizers[member.id] = KaldiRecognizer(self.vosk_model, self.SAMPLE_RATE)
                    logger.debug(f"Created new recognizer for {member.display_name}")
                except Exception as e:
                    logger.error(f"Failed to create recognizer for {member.display_name}: {e}", exc_info=True)
                    return

            recognizer = self.recognizers[member.id]

            try:
                # Convert stereo to mono (outside lock - no state access)
                audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                if len(audio_array) % 2 != 0:
                    audio_array = audio_array[:-1]
                audio_array = audio_array.reshape(-1, 2)
                mono_audio = audio_array.mean(axis=1).astype(np.int16)
            except Exception as e:
                logger.error(f"Audio processing error for {member.display_name}: {e}", exc_info=True)
                return

            # VAD: Check if audio contains speech using RMS energy threshold
            # Get VAD settings from config (hot-swappable)
            from bot.config import config as bot_config
            speech_cfg = bot_config.config_manager.for_guild("Speech", self.vc.guild.id) if hasattr(bot_config, 'config_manager') else None

            if speech_cfg and speech_cfg.enable_vad:
                # Calculate RMS (Root Mean Square) energy
                rms = np.sqrt(np.mean(mono_audio.astype(np.float32) ** 2))

                # Check against threshold
                if rms < speech_cfg.vad_silence_threshold:
                    logger.debug(f"[Guild {self.vc.guild.id}] Vosk: Skipping silence for {member.display_name} (RMS: {rms:.1f}, threshold: {speech_cfg.vad_silence_threshold})")
                    return

            try:
                # Feed to Vosk (inside lock - accesses recognizer state)
                # IMPORTANT: Always call Result() after AcceptWaveform(), not PartialResult()
                # The working pattern is: AcceptWaveform() -> Result() -> Reset()
                recognizer.AcceptWaveform(mono_audio.tobytes())
                vosk_result = json.loads(recognizer.Result())
                vosk_text = vosk_result.get("text", "").strip()

                # CRITICAL: Reset recognizer after Result() to clear internal state
                # Vosk's KaldiRecognizer accumulates state and must be reset
                # after each Result() call to prevent assertion failures
                recognizer.Reset()
            except Exception as e:
                logger.error(f"Vosk transcription error for {member.display_name}: {e}", exc_info=True)
                # Reset on error to clear any corrupted state
                try:
                    recognizer.Reset()
                except:
                    pass
                return

            if vosk_text:
                logger.info(f"[Guild {self.vc.guild.id}] Vosk transcribed {member.display_name}: {vosk_text}")
                # Invoke callback (outside lock - callback doesn't touch recognizer)
                try:
                    self.callback(member, vosk_text)
                except Exception as e:
                    logger.error(f"Error in Vosk callback: {e}", exc_info=True)

    def cleanup(self):
        """Cleanup Vosk-specific resources and call base cleanup."""
        super().cleanup()
        self.recognizers.clear()
        logger.debug(f"[Guild {self.vc.guild.id}] VoskSink Vosk-specific cleanup complete")


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

        # Get Vosk config from ConfigManager
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        # Create VoskSink with config values
        self.sink = VoskSink(
            vc=voice_client,
            callback=self.callback,
            vosk_model=self.model,
            chunk_duration=speech_cfg.vosk_chunk_duration,
            chunk_overlap=speech_cfg.vosk_chunk_overlap,
            processing_interval=speech_cfg.vosk_processing_interval,
            executor=self.executor,
            ducking_callback=self.ducking_callback
        )

        # Attach to voice client
        voice_client.listen(self.sink)

        # Start background buffer processing task
        self.sink.start_processing()

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
