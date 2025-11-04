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
from typing import Optional, Dict
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
SAMPLE_RATE = 96000      # Discord's sample rate (stereo)
TARGET_SR = 16000        # Whisper expects 16kHz mono
TIMEOUT_SECONDS = 30     # Transcription timeout


class FasterWhisperSink(voice_recv.BasicSink):
    """
    Custom sink for capturing audio and processing with faster-whisper.

    Features:
    - Per-user audio buffering
    - Rolling buffer (keeps last N seconds)
    - Background transcription tasks per user
    - VAD support for filtering silence
    - GPU acceleration support
    """

    def __init__(
        self,
        vc,
        callback,
        model,
        buffer_duration: float,
        debounce_seconds: float,
        executor: ThreadPoolExecutor,
        ducking_callback=None
    ):
        """
        Initialize faster-whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            model: Loaded WhisperModel instance
            buffer_duration: Audio buffer duration in seconds
            debounce_seconds: Min seconds between transcriptions
            executor: ThreadPoolExecutor for blocking transcription calls
            ducking_callback: Optional callback for ducking events (guild_id, member, is_speaking)
        """
        super().__init__(asyncio.Event())
        self.vc = vc
        self.callback = callback
        self.model = model
        self.buffer_duration = buffer_duration
        self.debounce = debounce_seconds
        self.executor = executor
        self.ducking_callback = ducking_callback

        # Per-user state
        self.buffers: Dict[str, list] = {}              # {user_name: [audio_chunks]}
        self.last_transcription: Dict[str, float] = {}  # {user_name: timestamp}
        self.speaking_state: Dict[str, bool] = {}       # {user_name: bool}
        self.transcription_tasks: Dict[str, asyncio.Task] = {}  # {user_name: Task}
        self.loop = asyncio.get_running_loop()

        logger.info(f"[Guild {vc.guild.id}] FasterWhisperSink initialized (buffer={buffer_duration}s, debounce={debounce_seconds}s)")

    def write(self, source, data):
        """
        Called for every audio packet from Discord.

        Args:
            source: discord.Member object who is speaking
            data: VoiceData object containing PCM audio

        Buffers audio per user and starts transcription tasks.
        """
        if data.pcm is None:
            return

        member = source
        if not member or member.bot:
            return  # Ignore bots and None members

        user_name = str(member)

        # Initialize buffer for new users
        if user_name not in self.buffers:
            self.buffers[user_name] = []
            self.last_transcription[user_name] = 0
            self.speaking_state[user_name] = False

        # Add audio to buffer
        self.buffers[user_name].append(data.pcm)

        # Track speaking state for ducking
        if not self.speaking_state[user_name]:
            self.speaking_state[user_name] = True
            if self.ducking_callback:
                try:
                    self.ducking_callback(self.vc.guild.id, member, is_speaking=True)
                except Exception as e:
                    logger.error(f"Error in ducking callback (start): {e}", exc_info=True)

        # Maintain rolling buffer (keep last N seconds)
        max_chunks = int((self.buffer_duration * SAMPLE_RATE) / len(data.pcm))
        if len(self.buffers[user_name]) > max_chunks:
            self.buffers[user_name] = self.buffers[user_name][-max_chunks:]

        # Start transcription task if not already running
        if user_name not in self.transcription_tasks or self.transcription_tasks[user_name].done():
            self.transcription_tasks[user_name] = asyncio.run_coroutine_threadsafe(
                self._transcribe_user(user_name, member),
                self.loop
            )

    async def _transcribe_user(self, user_name: str, member: discord.Member):
        """
        Transcribe audio for a specific user (runs in background).

        Args:
            user_name: Username string
            member: Discord member object
        """
        # Debouncing - don't transcribe too frequently
        now = self.loop.time()
        if now - self.last_transcription[user_name] < self.debounce:
            return
        self.last_transcription[user_name] = now

        # VAD: Check if audio contains speech using RMS energy threshold
        # Get VAD settings from config (hot-swappable)
        from bot.config import config as bot_config
        speech_cfg = bot_config.config_manager.for_guild("Speech", self.vc.guild.id) if hasattr(bot_config, 'config_manager') else None

        if speech_cfg and speech_cfg.enable_vad:
            # Get buffered audio
            if not self.buffers[user_name]:
                return

            # Concatenate audio chunks
            pcm_data = b''.join(self.buffers[user_name])

            # Convert stereo int16 to mono float32 for VAD
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            audio_array = audio_array.astype(np.float32) / 32768.0  # Normalize to [-1.0, 1.0]

            # Convert stereo to mono (average channels)
            if len(audio_array) % 2 == 0:
                audio_array = audio_array.reshape(-1, 2).mean(axis=1)

            rms = np.sqrt(np.mean(audio_array ** 2))

            # Normalize threshold for float32 audio (Whisper uses normalized audio 0.0-1.0)
            # Vosk uses int16 audio (~0-1000), so we need to scale threshold
            # float32 typical speech RMS: ~0.01-0.1, int16 typical speech RMS: ~100-1000
            # Scale factor: 0.01 / 100 = 0.0001
            normalized_threshold = speech_cfg.vad_silence_threshold * 0.0001

            if rms < normalized_threshold:
                logger.debug(f"[Guild {self.vc.guild.id}] faster-whisper: Skipping silence for {user_name} (RMS: {rms:.4f}, threshold: {normalized_threshold:.4f})")
                self.buffers[user_name] = []  # Clear buffer
                return

        # Get buffered audio
        if not self.buffers[user_name]:
            return

        # Concatenate audio chunks
        pcm_data = b''.join(self.buffers[user_name])
        self.buffers[user_name] = []  # Clear buffer

        # Convert stereo int16 to mono float32
        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        audio_array = audio_array.astype(np.float32) / 32768.0  # Normalize to [-1.0, 1.0]

        # Convert stereo to mono (average channels)
        if len(audio_array) % 2 == 0:
            audio_array = audio_array.reshape(-1, 2).mean(axis=1)

        # Resample 96kHz → 16kHz for Whisper
        try:
            target_len = int(len(audio_array) * TARGET_SR / SAMPLE_RATE)
            audio_16k = resample(audio_array, target_len)
        except Exception as e:
            logger.warning(f"[Guild {self.vc.guild.id}] Resample failed for {user_name}: {e}")
            return

        # Transcribe in thread pool (blocking call)
        try:
            result = await asyncio.wait_for(
                self.loop.run_in_executor(
                    self.executor,
                    self._transcribe_audio,
                    audio_16k
                ),
                timeout=TIMEOUT_SECONDS
            )

            if result and result.strip():
                logger.info(f"[Guild {self.vc.guild.id}] faster-whisper transcribed {user_name}: {result}")
                # Invoke callback
                try:
                    self.callback(member, result)
                except Exception as e:
                    logger.error(f"Error in faster-whisper callback: {e}", exc_info=True)

        except asyncio.TimeoutError:
            logger.warning(f"[Guild {self.vc.guild.id}] faster-whisper transcription timeout for {user_name}")
        except Exception as e:
            logger.error(f"[Guild {self.vc.guild.id}] faster-whisper transcription error for {user_name}: {e}", exc_info=True)

    def _transcribe_audio(self, audio_array: np.ndarray) -> str:
        """
        Transcribe audio using faster-whisper (runs in thread pool).

        Args:
            audio_array: Numpy array of float32 audio samples (16kHz mono)

        Returns:
            Transcribed text string
        """
        try:
            # faster-whisper expects numpy array directly
            segments, info = self.model.transcribe(
                audio_array,
                beam_size=5,
                language="en",
                condition_on_previous_text=False
            )

            # Collect all segments into single text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text)

            return " ".join(text_parts).strip()

        except Exception as e:
            logger.error(f"faster-whisper transcription failed: {e}", exc_info=True)
            return ""

    def on_speaking_stop(self, user):
        """Handle user stopping speaking (called by voice client)."""
        user_name = str(user)

        if user_name in self.speaking_state:
            self.speaking_state[user_name] = False

            # Notify ducking callback
            if self.ducking_callback:
                try:
                    self.ducking_callback(self.vc.guild.id, user, is_speaking=False)
                except Exception as e:
                    logger.error(f"Error in ducking callback (stop): {e}", exc_info=True)

    def cleanup(self):
        """Cleanup resources."""
        # Cancel all pending transcription tasks
        for task in self.transcription_tasks.values():
            if not task.done():
                task.cancel()

        self.buffers.clear()
        self.last_transcription.clear()
        self.speaking_state.clear()
        self.transcription_tasks.clear()
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

        # Get config values
        speech_cfg = self.bot.config_manager.for_guild("Speech")

        # Create sink
        self.sink = FasterWhisperSink(
            voice_client,
            self.callback,
            self.model,
            buffer_duration=speech_cfg.faster_whisper_buffer_duration,
            debounce_seconds=speech_cfg.faster_whisper_debounce_seconds,
            executor=self.executor,
            ducking_callback=self.ducking_callback
        )

        # Attach to voice client
        voice_client.listen(self.sink)
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
