"""
Base speech sink with proven buffering logic.

This base class implements the audio buffering and processing loop pattern
that works well in the Vosk engine. All speech engines inherit from this
and only need to implement the transcribe_audio() method.
"""

import asyncio
import time
import discord
from discord.ext import voice_recv
from collections import deque
import threading
from typing import Optional
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger("discordbot.base_sink")


class BaseSpeechSink(voice_recv.BasicSink, ABC):
    """
    Base sink for speech recognition engines.

    Implements proven buffering and processing logic from VoskSink.
    Subclasses only need to implement transcribe_audio().
    """

    # Audio constants (Discord's format)
    SAMPLE_RATE = 48000      # Discord's sample rate (48kHz stereo)
    CHANNELS = 2             # Stereo
    SAMPLE_WIDTH = 2         # 16-bit samples

    def __init__(
        self,
        vc,
        callback,
        chunk_duration: float,
        chunk_overlap: float,
        processing_interval: float,
        executor,
        ducking_callback=None
    ):
        """
        Initialize base speech sink.

        Args:
            vc: Voice client
            callback: Function called with (member, transcribed_text)
            chunk_duration: Process audio every N seconds
            chunk_overlap: Keep N seconds of audio for next chunk
            processing_interval: How often to check buffers (seconds)
            executor: ThreadPoolExecutor for blocking transcription
            ducking_callback: Optional callback for ducking (guild_id, member, is_speaking)
        """
        super().__init__(asyncio.Event())
        self.vc = vc
        self.callback = callback
        self.chunk_duration = chunk_duration
        self.chunk_overlap = chunk_overlap
        self.processing_interval = processing_interval
        self.executor = executor
        self.ducking_callback = ducking_callback

        # Thread-safe buffer management
        self.buffers = {}                    # {user_id: deque([pcm_bytes])}
        self.last_chunk_time = {}            # {user_id: timestamp}
        self.buffer_lock = threading.Lock()  # Thread lock for buffer access

        # Background processing task
        self._processing_task = None
        self._stop_processing = False

        logger.info(
            f"[Guild {vc.guild.id}] {self.__class__.__name__} initialized "
            f"(chunk={chunk_duration}s, overlap={chunk_overlap}s, interval={processing_interval}s)"
        )

    def write(self, user: discord.User, data: voice_recv.VoiceData):
        """
        Called for every audio packet from Discord (sync, must be FAST).

        Simply appends to buffer - no async operations, no event loop scheduling.
        Background task processes buffers periodically.
        """
        try:
            if not data.pcm:
                return

            # Ignore bots and None users
            if not user or user.bot:
                return

            # Fast synchronous buffer append with thread lock
            with self.buffer_lock:
                # Initialize user state on first packet
                if user.id not in self.buffers:
                    self.buffers[user.id] = deque()
                    self.last_chunk_time[user.id] = time.time()

                # Append audio to buffer (fast, no processing)
                self.buffers[user.id].append(data.pcm)

        except Exception as e:
            logger.error(f"{self.__class__.__name__} write error: {e}", exc_info=True)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_state(self, member: discord.Member, speaking: bool):
        """Handle member starting speaking."""
        if member.bot:
            return

        if speaking:
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

        # Process any remaining audio (thread-safe)
        with self.buffer_lock:
            if member.id in self.buffers and self.buffers[member.id]:
                pcm_data = b''.join(self.buffers[member.id])
                self.buffers[member.id].clear()

                if pcm_data:
                    self.vc.loop.run_in_executor(
                        self.executor,
                        self.transcribe_audio,
                        pcm_data,
                        member
                    )

        # Notify ducking callback
        if self.ducking_callback:
            try:
                self.ducking_callback(self.vc.guild.id, member, is_speaking=False)
            except Exception as e:
                logger.error(f"Error in ducking callback (stop): {e}", exc_info=True)

    def start_processing(self):
        """Start background task to process audio buffers periodically."""
        if self._processing_task is None or self._processing_task.done():
            self._stop_processing = False
            self._processing_task = asyncio.create_task(self._process_buffers_loop())
            logger.info(f"[Guild {self.vc.guild.id}] Started {self.__class__.__name__} buffer processing task")

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
                                bytes_per_second = self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH
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

                    # Process in thread pool (blocking transcription call)
                    self.vc.loop.run_in_executor(
                        self.executor,
                        self.transcribe_audio,
                        pcm_data,
                        member
                    )

        except asyncio.CancelledError:
            logger.info(f"[Guild {self.vc.guild.id}] {self.__class__.__name__} buffer processing task cancelled")
            raise
        except Exception as e:
            logger.error(f"[Guild {self.vc.guild.id}] Error in {self.__class__.__name__} buffer processing: {e}", exc_info=True)

    @abstractmethod
    def transcribe_audio(self, pcm_data: bytes, member: discord.Member):
        """
        Transcribe audio using the specific speech recognition engine.

        This method runs in a thread pool and should be blocking.
        Subclasses must implement this method.

        Args:
            pcm_data: Raw PCM audio bytes (stereo int16, 96kHz)
            member: Discord member who spoke
        """
        pass

    def cleanup(self):
        """Cleanup resources and stop background task."""
        self._stop_processing = True
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()
        self.buffers.clear()
        self.last_chunk_time.clear()
        logger.debug(f"[Guild {self.vc.guild.id}] {self.__class__.__name__} cleaned up")

    def wants_opus(self) -> bool:
        """We want PCM audio, not Opus."""
        return False
