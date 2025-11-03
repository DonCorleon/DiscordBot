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
from typing import Optional, Dict
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
SAMPLE_RATE = 96000      # Discord's sample rate
TARGET_SR = 16000        # Whisper expects 16kHz
TIMEOUT_SECONDS = 30     # Transcription timeout


class WhisperSink(voice_recv.BasicSink):
    """
    Custom sink for capturing audio and processing with Whisper.

    Features:
    - Per-user audio buffering
    - Rolling buffer (keeps last N seconds)
    - Background transcription tasks per user
    - Resilient error handling with auto-restart
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
        Initialize Whisper sink.

        Args:
            vc: Voice client
            callback: Function called with (member, text) when speech is recognized
            model: Loaded Whisper model
            buffer_duration: Audio buffer duration in seconds
            debounce_seconds: Min seconds between transcriptions
            executor: ThreadPoolExecutor for blocking Whisper calls
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

        logger.info(f"[Guild {vc.guild.id}] WhisperSink initialized (buffer={buffer_duration}s, debounce={debounce_seconds}s)")

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

        # source is the discord.Member object directly
        member = source
        if not member or member.bot:
            return

        user_name = member.name

        # Initialize per-user state
        self.buffers.setdefault(user_name, [])
        self.last_transcription.setdefault(user_name, 0)

        # Convert PCM bytes to float32 numpy array
        try:
            pcm_float = np.frombuffer(data.pcm, dtype=np.int16).astype(np.float32) / 32768.0
            if pcm_float.size == 0:
                return
        except Exception as e:
            logger.debug(f"Failed to convert PCM data for {user_name}: {e}")
            return

        # Add to user's buffer
        self.buffers[user_name].append(pcm_float)

        # Start transcription task if not running
        if user_name not in self.transcription_tasks or self.transcription_tasks[user_name].done():
            self.transcription_tasks[user_name] = self.loop.create_task(
                self._resilient_transcribe(user_name, member)
            )

    async def _resilient_transcribe(self, user_name: str, member: discord.Member):
        """
        Background loop per user - keeps retrying on errors.

        This resilient loop ensures transcription continues even if individual
        transcription attempts fail or timeout.
        """
        while True:
            chunks = self.buffers.get(user_name, [])
            if not chunks:
                await asyncio.sleep(1.0)
                continue

            try:
                # 30 second timeout per transcription attempt
                await asyncio.wait_for(
                    self._transcribe_user(user_name, member),
                    timeout=TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                logger.warning(f"[Guild {self.vc.guild.id}] Whisper transcription timeout for {user_name}, restarting task...")
                self.buffers[user_name] = []  # Clear buffer on timeout
            except Exception:
                logger.exception(f"[Guild {self.vc.guild.id}] Transcription loop crashed for {user_name}, restarting...")
                self.buffers[user_name] = []  # Clear buffer on error

            await asyncio.sleep(0.1)

    async def _transcribe_user(self, user_name: str, member: discord.Member):
        """
        Process audio buffer for one user.

        Implements rolling buffer, resampling, debouncing, and Whisper transcription.
        """
        buffer_samples = int(self.buffer_duration * SAMPLE_RATE)  # e.g., 3 seconds at 96kHz

        chunks = self.buffers.get(user_name, [])
        if not chunks:
            return

        # Concatenate all chunks
        try:
            audio_array = np.concatenate(chunks)
        except Exception as e:
            logger.debug(f"Failed to concatenate audio for {user_name}: {e}")
            self.buffers[user_name] = []
            return

        # Keep only last N seconds (rolling buffer)
        if len(audio_array) > buffer_samples:
            audio_array = audio_array[-buffer_samples:]

        if len(audio_array) == 0:
            return

        # Debouncing - don't transcribe too frequently
        now = self.loop.time()
        if now - self.last_transcription[user_name] < self.debounce:
            return
        self.last_transcription[user_name] = now

        # VAD: Check if audio contains speech using RMS energy threshold
        # Calculate RMS (Root Mean Square) energy of the float32 audio
        rms = np.sqrt(np.mean(audio_array ** 2))

        # Threshold for silence detection (normalized float32 audio: ~0.01-0.1 for speech)
        # Adjust based on your environment (lower = more sensitive, higher = less sensitive)
        SILENCE_THRESHOLD = 0.01

        if rms < SILENCE_THRESHOLD:
            logger.debug(f"[Guild {self.vc.guild.id}] Whisper: Skipping silence for {user_name} (RMS: {rms:.4f})")
            self.buffers[user_name] = []  # Clear buffer
            return

        # Resample 96kHz → 16kHz for Whisper
        try:
            target_len = int(len(audio_array) * TARGET_SR / SAMPLE_RATE)
            audio_16k = resample(audio_array, target_len)
        except Exception as e:
            logger.warning(f"[Guild {self.vc.guild.id}] Resample failed for {user_name}: {e}")
            self.buffers[user_name] = []
            return

        # Run Whisper in thread pool (blocking operation)
        try:
            result = await self.loop.run_in_executor(
                self.executor,
                lambda: self.model.transcribe(audio_16k, fp16=False, language="en")
            )
            text = result["text"].strip()
        except Exception as e:
            logger.warning(f"[Guild {self.vc.guild.id}] Whisper transcription failed for {user_name}: {e}")
            text = ""

        # Clear buffer after transcription
        self.buffers[user_name] = []

        if not text:
            return

        # Invoke callback with transcribed text
        logger.info(f"[Guild {self.vc.guild.id}] 🗣 Whisper transcribed {user_name}: {text}")
        try:
            self.callback(member, text)
        except Exception as e:
            logger.error(f"[Guild {self.vc.guild.id}] Error in Whisper callback: {e}", exc_info=True)

    @voice_recv.BasicSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member):
        """Track when users start speaking (for ducking integration)."""
        logger.debug(f"[Guild {self.vc.guild.id}] 🗣️ {member.name} started talking")
        self.speaking_state[member.name] = True

        # Notify ducking callback if provided
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, True)
            except Exception as e:
                logger.error(f"Error in ducking callback (start): {e}", exc_info=True)

    @voice_recv.BasicSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
        """Track when users stop speaking (for ducking integration)."""
        logger.debug(f"[Guild {self.vc.guild.id}] 🔇 {member.name} stopped talking")
        self.speaking_state[member.name] = False

        # Notify ducking callback if provided
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, False)
            except Exception as e:
                logger.error(f"Error in ducking callback (stop): {e}", exc_info=True)

    def cleanup(self):
        """Cancel all transcription tasks and cleanup resources."""
        logger.info(f"[Guild {self.vc.guild.id}] Cleaning up WhisperSink...")

        # Cancel all transcription tasks
        for user, task in self.transcription_tasks.items():
            if not task.done():
                task.cancel()
                logger.debug(f"Cancelled transcription task for {user}")

        # Clear buffers
        self.buffers.clear()
        self.last_transcription.clear()
        self.speaking_state.clear()
        self.transcription_tasks.clear()


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

        # Create and attach WhisperSink
        self.sink = WhisperSink(
            voice_client,
            self.callback,
            self.model,
            self.buffer_duration,
            self.debounce_seconds,
            self.executor,
            ducking_callback=self.ducking_callback
        )

        voice_client.listen(self.sink)
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
