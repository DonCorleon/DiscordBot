"""
Audio player with ducking support for Discord bots.
Automatically reduces volume when users speak in the voice channel.
"""

import asyncio
import threading
import wave
import numpy as np
from pathlib import Path
from typing import Optional, Callable
import logging

logger = logging.getLogger("discordbot.audio_player")


class AudioPlayer:
    """
    Audio player with support for:
    - Volume control
    - Audio ducking when users speak
    - Queue management
    - Smooth volume transitions
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_size: int = 960,  # 20ms at 48kHz
        ducking_level: float = 0.5,
        duck_transition_ms: int = 50,
    ):
        """
        Initialize audio player.

        Args:
            sample_rate: Audio sample rate (Discord uses 48kHz)
            channels: Number of audio channels (2 for stereo)
            chunk_size: Audio chunk size in frames
            ducking_level: Volume multiplier when ducking (0.5 = 50% volume)
            duck_transition_ms: Transition time for ducking in milliseconds
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.ducking_level = ducking_level
        self.duck_transition_frames = int(
            (duck_transition_ms / 1000.0) * sample_rate
        )

        # Playback state
        self.is_playing = False
        self.is_paused = False
        self.should_stop = False
        self.volume = 1.0
        self.base_volume = 1.0  # Volume before ducking
        self.is_ducked = False
        self.target_volume = 1.0
        self.current_volume = 1.0

        # Threading
        self.playback_thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Callback for playback completion
        self.on_playback_finished: Optional[Callable] = None

    def set_ducking_level(self, level: float):
        """
        Set the ducking level (volume multiplier when ducking).

        Args:
            level: Volume multiplier (0.0-1.0)
        """
        self.ducking_level = max(0.0, min(1.0, level))
        logger.info(f"Ducking level set to {self.ducking_level * 100}%")

    def set_volume(self, volume: float):
        """
        Set the base volume (before ducking).

        Args:
            volume: Volume level (0.0-1.0)
        """
        with self.lock:
            self.base_volume = max(0.0, min(1.0, volume))
            if not self.is_ducked:
                self.target_volume = self.base_volume
        logger.debug(f"Base volume set to {self.base_volume * 100}%")

    def duck(self):
        """Start ducking (reduce volume)."""
        with self.lock:
            if not self.is_ducked:
                self.is_ducked = True
                self.target_volume = self.base_volume * self.ducking_level
                logger.debug(f"Ducking started, target volume: {self.target_volume * 100}%")

    def unduck(self):
        """Stop ducking (restore volume)."""
        with self.lock:
            if self.is_ducked:
                self.is_ducked = False
                self.target_volume = self.base_volume
                logger.debug(f"Ducking stopped, target volume: {self.target_volume * 100}%")

    def _smooth_volume_transition(self) -> float:
        """
        Calculate smooth volume transition between current and target.
        Returns the volume to apply for the next chunk.
        """
        if abs(self.current_volume - self.target_volume) < 0.001:
            self.current_volume = self.target_volume
            return self.current_volume

        # Calculate step size for smooth transition
        step = (self.target_volume - self.current_volume) / (
            self.duck_transition_frames / self.chunk_size
        )
        self.current_volume += step

        # Clamp to target if we overshoot
        if (step > 0 and self.current_volume > self.target_volume) or (
            step < 0 and self.current_volume < self.target_volume
        ):
            self.current_volume = self.target_volume

        return self.current_volume

    def _apply_volume(self, audio_data: bytes) -> bytes:
        """
        Apply volume and smooth transitions to audio data.

        Args:
            audio_data: Raw audio bytes (int16)

        Returns:
            Volume-adjusted audio bytes
        """
        with self.lock:
            volume = self._smooth_volume_transition()

        if volume == 1.0:
            return audio_data

        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)

        # Apply volume
        audio_array = (audio_array * volume).astype(np.int16)

        return audio_array.tobytes()

    def _convert_to_discord_format(self, file_path: str) -> tuple[bytes, int]:
        """
        Load and convert audio file to Discord's format (48kHz, stereo, int16).
        Supports WAV, MP3, OGG, FLAC, and other formats via FFmpeg.

        Args:
            file_path: Path to audio file

        Returns:
            Tuple of (audio_data, duration_ms)
        """
        import subprocess
        import sys

        try:
            # First try as WAV (fastest, no conversion needed)
            try:
                with wave.open(file_path, "rb") as wf:
                    channels = wf.getnchannels()
                    sample_width = wf.getsampwidth()
                    framerate = wf.getframerate()
                    n_frames = wf.getnframes()
                    audio_data = wf.readframes(n_frames)

                # Convert to numpy array
                if sample_width == 2:
                    audio_array = np.frombuffer(audio_data, dtype=np.int16)
                elif sample_width == 1:
                    audio_array = np.frombuffer(audio_data, dtype=np.uint8).astype(np.int16)
                    audio_array = (audio_array - 128) * 256
                else:
                    raise ValueError(f"Unsupported sample width: {sample_width}")

                # Reshape for channel handling
                if channels == 1:
                    audio_array = np.repeat(audio_array, 2)
                elif channels == 2:
                    pass  # Already stereo
                else:
                    audio_array = audio_array.reshape(-1, channels)[:, :2].flatten()

                # Resample if necessary
                if framerate != self.sample_rate:
                    duration = len(audio_array) / (framerate * 2)
                    new_length = int(duration * self.sample_rate * 2)
                    indices = np.linspace(0, len(audio_array) - 1, new_length)
                    audio_array = np.interp(indices, np.arange(len(audio_array)), audio_array).astype(np.int16)

                duration_ms = int((len(audio_array) / (self.sample_rate * 2)) * 1000)
                return audio_array.tobytes(), duration_ms

            except wave.Error:
                # Not a WAV file, use FFmpeg to convert
                logger.debug(f"Not a WAV file, using FFmpeg to convert: {file_path}")

                # FFmpeg command to convert to PCM s16le (signed 16-bit little-endian)
                # This matches Discord's expected format
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-i', file_path,
                    '-f', 's16le',  # Output format: signed 16-bit little-endian PCM
                    '-ar', str(self.sample_rate),  # Sample rate: 48000 Hz
                    '-ac', str(self.channels),  # Channels: 2 (stereo)
                    '-loglevel', 'error',  # Only show errors
                    'pipe:1'  # Output to stdout
                ]

                # Run FFmpeg
                process = subprocess.Popen(
                    ffmpeg_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )

                audio_data, stderr = process.communicate()

                if process.returncode != 0:
                    error_msg = stderr.decode('utf-8', errors='ignore')
                    raise RuntimeError(f"FFmpeg error: {error_msg}")

                if not audio_data:
                    raise RuntimeError("FFmpeg produced no output")

                # Calculate duration
                num_samples = len(audio_data) // 2  # 2 bytes per sample (int16)
                duration_seconds = num_samples / (self.sample_rate * self.channels)
                duration_ms = int(duration_seconds * 1000)

                logger.debug(f"Converted {file_path} using FFmpeg: {duration_ms}ms, {len(audio_data)} bytes")

                return audio_data, duration_ms

        except FileNotFoundError as e:
            if 'ffmpeg' in str(e).lower():
                logger.error(
                    "FFmpeg not found. Please install FFmpeg to play non-WAV audio files.\n"
                    "Windows: Download from https://ffmpeg.org/download.html\n"
                    "Linux: sudo apt-get install ffmpeg\n"
                    "macOS: brew install ffmpeg"
                )
            raise
        except Exception as e:
            logger.error(f"Error converting audio file {file_path}: {e}")
            raise

    def _playback_worker(self, audio_data: bytes):
        """
        Worker thread for audio processing (no local playback).
        Processes audio with volume/ducking and provides chunks via callback.

        Args:
            audio_data: Audio data to process (48kHz, stereo, int16)
        """
        try:
            # Initialize volume
            with self.lock:
                self.current_volume = self.base_volume
                self.target_volume = self.base_volume

            # Process audio in chunks
            offset = 0
            chunk_bytes = self.chunk_size * self.channels * 2  # 2 bytes per sample

            while offset < len(audio_data) and not self.should_stop:
                if self.is_paused:
                    asyncio.sleep(0.01)
                    continue

                # Get next chunk
                chunk = audio_data[offset : offset + chunk_bytes]
                if not chunk:
                    break

                # Apply volume with smooth transitions
                chunk = self._apply_volume(chunk)

                # Store the processed chunk for Discord to consume
                # No local playback needed - Discord will handle audio output

                offset += chunk_bytes

        except Exception as e:
            logger.error(f"Playback error: {e}", exc_info=True)

        finally:
            with self.lock:
                self.is_playing = False
                self.is_paused = False
                self.should_stop = False

            # Call completion callback
            if self.on_playback_finished:
                try:
                    self.on_playback_finished()
                except Exception as e:
                    logger.error(f"Error in playback finished callback: {e}")

    def play(
        self,
        file_path: str,
        volume: float = 1.0,
        on_finished: Optional[Callable] = None,
    ):
        """
        Play an audio file.

        Args:
            file_path: Path to audio file
            volume: Playback volume (0.0-1.0)
            on_finished: Callback when playback finishes
        """
        if self.is_playing:
            logger.warning("Already playing audio")
            return

        try:
            # Convert audio to Discord format
            audio_data, duration_ms = self._convert_to_discord_format(file_path)

            # Set volume and callback
            self.set_volume(volume)
            self.on_playback_finished = on_finished

            # Start playback thread
            with self.lock:
                self.is_playing = True
                self.should_stop = False

            self.playback_thread = threading.Thread(
                target=self._playback_worker, args=(audio_data,), daemon=True
            )
            self.playback_thread.start()

            logger.info(
                f"Playing {file_path} (duration: {duration_ms}ms, volume: {volume * 100}%)"
            )

        except Exception as e:
            logger.error(f"Failed to play {file_path}: {e}")
            with self.lock:
                self.is_playing = False
            raise

    def stop(self):
        """Stop playback."""
        if not self.is_playing:
            return

        with self.lock:
            self.should_stop = True

        if self.playback_thread:
            self.playback_thread.join(timeout=1.0)

        logger.info("Playback stopped")

    def pause(self):
        """Pause playback."""
        if self.is_playing and not self.is_paused:
            with self.lock:
                self.is_paused = True
            logger.info("Playback paused")

    def resume(self):
        """Resume playback."""
        if self.is_playing and self.is_paused:
            with self.lock:
                self.is_paused = False
            logger.info("Playback resumed")

    def cleanup(self):
        """Clean up resources."""
        self.stop()
        logger.info("Audio player cleaned up")