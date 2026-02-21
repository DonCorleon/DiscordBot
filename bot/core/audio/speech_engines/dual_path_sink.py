"""
Dual-path audio sink wrapper.

Wraps VoskSink as a child for fast trigger matching, and adds an internal
quality transcription path using faster-whisper for accurate full-utterance
transcripts. The quality path is fully fault-isolated — if it breaks at any
point, the fast Vosk path continues working exactly as before.
"""

import time
import threading
import logging
import numpy as np
import discord
from discord.ext import voice_recv
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger("discordbot.speech_engines")


class DualPathSink(voice_recv.AudioSink):
    """
    Wrapper sink that delegates audio to VoskSink (child) for fast triggers,
    and buffers full utterances internally for quality transcription.

    Architecture:
    - VoskSink is registered as a child via super().__init__(vosk_sink)
    - Router's register_events() walks walk_children() and registers both
      DualPathSink's and VoskSink's @listener methods independently
    - write() calls vosk_sink.write() FIRST, then buffers for quality path
    - Quality transcription runs in a separate ThreadPoolExecutor
    """

    SAMPLE_RATE = 48000  # Discord's sample rate
    CHANNELS = 2         # Stereo
    SAMPLE_WIDTH = 2     # 16-bit audio

    def __init__(self, vosk_sink, quality_callback, quality_model, quality_config):
        """
        Initialize dual-path sink.

        Args:
            vosk_sink: VoskSink instance (registered as child)
            quality_callback: Function called with (member, text) for quality transcripts
            quality_model: Loaded faster-whisper WhisperModel instance, or None to disable
            quality_config: Dict with quality path settings (beam_size, max_workers)
        """
        # Register vosk_sink as child — router will discover its listeners
        super().__init__(vosk_sink)
        self.vosk_sink = vosk_sink

        self.quality_callback = quality_callback
        self.quality_model = quality_model
        self.quality_config = quality_config or {}

        # Quality path state
        self._quality_enabled = quality_model is not None
        self._quality_buffers = {}  # {user_id: list[bytes]}
        self._quality_speaking = set()  # user_ids currently speaking
        self._quality_lock = threading.Lock()

        # Separate executor for quality path — can't starve Vosk's executor
        max_workers = self.quality_config.get("max_workers", 2)
        self._quality_executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="quality-transcribe"
        ) if self._quality_enabled else None

        if self._quality_enabled:
            logger.info(
                f"DualPathSink initialized: quality path ENABLED "
                f"(model={quality_config.get('model', '?')}, "
                f"beam_size={quality_config.get('beam_size', 5)}, "
                f"max_workers={max_workers})"
            )
        else:
            logger.info("DualPathSink initialized: quality path DISABLED (no model)")

    def wants_opus(self) -> bool:
        """We want PCM audio, not Opus."""
        return False

    def write(self, user, data):
        """
        Called for every audio packet. Delegates to VoskSink FIRST,
        then buffers a copy for quality path (fault-isolated).
        """
        # === FAST PATH FIRST (always) ===
        self.vosk_sink.write(user, data)

        # === QUALITY PATH BUFFER (isolated) ===
        if not self._quality_enabled:
            return

        try:
            pcm = data.pcm
            if not pcm:
                return

            with self._quality_lock:
                if user.id in self._quality_speaking:
                    if user.id not in self._quality_buffers:
                        self._quality_buffers[user.id] = []
                    self._quality_buffers[user.id].append(bytes(pcm))
        except Exception:
            # Never let quality buffering break the write path
            pass

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member):
        """Track speaking start for quality buffering."""
        if not self._quality_enabled or member.bot:
            return

        try:
            with self._quality_lock:
                self._quality_speaking.add(member.id)
                self._quality_buffers[member.id] = []
            logger.debug(f"[Quality] {member.display_name} started speaking, buffering")
        except Exception:
            pass

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
        """Join full utterance and submit for quality transcription."""
        if not self._quality_enabled or member.bot:
            return

        try:
            with self._quality_lock:
                self._quality_speaking.discard(member.id)
                chunks = self._quality_buffers.pop(member.id, None)

            if not chunks:
                logger.debug(f"[Quality] {member.display_name} stopped speaking, no audio buffered")
                return

            pcm_data = b''.join(chunks)

            # Check minimum duration (0.5s for quality path — short utterances aren't worth it)
            bytes_per_second = self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH
            duration = len(pcm_data) / bytes_per_second
            if duration < 0.5:
                logger.debug(f"[Quality] Skipping short utterance from {member.display_name} ({duration:.2f}s)")
                return

            # Submit to quality executor
            self._quality_executor.submit(self._quality_transcribe, pcm_data, member, duration)

        except Exception as e:
            logger.error(f"[Quality] Error handling speaking stop for {member.display_name}: {e}", exc_info=True)

    def _quality_transcribe(self, pcm_data, member, audio_duration):
        """
        Transcribe full utterance with faster-whisper (runs in quality executor).

        Every step is wrapped in try/except — errors never propagate.
        """
        start_time = time.time()

        try:
            # Convert stereo PCM to mono float32
            audio_array = np.frombuffer(pcm_data, dtype=np.int16)
            if len(audio_array) % 2 != 0:
                audio_array = audio_array[:-1]
            audio_array = audio_array.reshape(-1, 2)
            mono_audio = audio_array.mean(axis=1).astype(np.float32) / 32768.0
        except Exception as e:
            logger.error(f"[Quality] Audio conversion error for {member.display_name}: {e}", exc_info=True)
            return

        try:
            # Resample 48kHz -> 16kHz using resampy
            import resampy
            resampled = resampy.resample(mono_audio, self.SAMPLE_RATE, 16000)
        except ImportError:
            logger.error("[Quality] resampy not installed. Install with: pip install resampy")
            return
        except Exception as e:
            logger.error(f"[Quality] Resample error for {member.display_name}: {e}", exc_info=True)
            return

        try:
            # Transcribe with quality parameters
            beam_size = self.quality_config.get("beam_size", 5)
            segments, info = self.quality_model.transcribe(
                resampled,
                beam_size=beam_size,
                vad_filter=True,
                temperature=0,
                no_speech_threshold=0.6,
                compression_ratio_threshold=2.2,
                repetition_penalty=1.2,
                language="en"
            )

            # Collect all segment texts
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts).strip()
        except Exception as e:
            logger.error(f"[Quality] Transcription error for {member.display_name}: {e}", exc_info=True)
            return

        if not full_text:
            logger.debug(f"[Quality] No speech detected for {member.display_name} ({audio_duration:.1f}s audio)")
            return

        elapsed = time.time() - start_time
        logger.info(
            f"[Quality] Transcribed {member.display_name}: \"{full_text}\" "
            f"(audio={audio_duration:.1f}s, processing={elapsed:.1f}s)"
        )

        # Invoke callback (fault-isolated)
        try:
            self.quality_callback(member, full_text)
        except Exception as e:
            logger.error(f"[Quality] Callback error: {e}", exc_info=True)

    def cleanup(self):
        """Cleanup quality path resources. VoskSink cleanup is handled separately."""
        if self._quality_executor:
            self._quality_executor.shutdown(wait=False)
            self._quality_executor = None

        with self._quality_lock:
            self._quality_buffers.clear()
            self._quality_speaking.clear()

        self._quality_enabled = False
        logger.debug("DualPathSink quality path cleaned up")
