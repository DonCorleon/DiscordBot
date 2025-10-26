"""
Discord audio source with ducking support.
"""

import discord
import numpy as np
from bot.core.audio.player import PyAudioPlayer
import logging

logger = logging.getLogger("discordbot.discord_audio_source")


class DuckedAudioSource(discord.AudioSource):
    """
    Discord audio source with real-time ducking support.
    Integrates PyAudioPlayer's ducking with Discord's audio streaming.
    """

    def __init__(
        self,
        file_path: str,
        volume: float = 1.0,
        ducking_level: float = 0.5,
        duck_transition_ms: int = 50,
        sample_rate: int = 48000,
        channels: int = 2,
        chunk_size: int = 960
    ):
        """
        Initialize ducked audio source.

        Args:
            file_path: Path to audio file
            volume: Base volume (0.0-1.0)
            ducking_level: Volume multiplier when ducked (0.0-1.0)
            duck_transition_ms: Transition time for volume changes
            sample_rate: Audio sample rate in Hz (default: 48000)
            channels: Number of audio channels (default: 2)
            chunk_size: Audio chunk size in frames (default: 960)
        """
        self.file_path = file_path
        self.player = PyAudioPlayer(
            sample_rate=sample_rate,
            channels=channels,
            chunk_size=chunk_size,
            ducking_level=ducking_level,
            duck_transition_ms=duck_transition_ms
        )

        # Load and convert audio
        logger.debug(f"Loading audio: {file_path}")
        self.audio_data, self.duration_ms = self.player._convert_to_discord_format(file_path)
        logger.debug(f"Loaded {len(self.audio_data)} bytes, duration: {self.duration_ms}ms")

        # Set initial volume
        self.player.set_volume(volume)

        # Playback state
        self.offset = 0
        self.chunk_size = 960 * 2 * 2  # 20ms at 48kHz, stereo, int16 (960 samples * 2 channels * 2 bytes)
        self.finished = False

    def read(self) -> bytes:
        """
        Read next 20ms chunk of audio.
        Called by Discord ~50 times per second.
        """
        if self.finished or self.offset >= len(self.audio_data):
            return b''

        # Get next chunk
        chunk = self.audio_data[self.offset:self.offset + self.chunk_size]

        if not chunk or len(chunk) == 0:
            self.finished = True
            return b''

        # Pad if necessary (last chunk might be smaller)
        if len(chunk) < self.chunk_size:
            chunk = chunk + b'\x00' * (self.chunk_size - len(chunk))

        # Apply volume/ducking with smooth transitions
        chunk = self.player._apply_volume(chunk)

        self.offset += self.chunk_size

        return chunk

    def is_opus(self) -> bool:
        """Discord asks if this is Opus encoded (it's not, it's PCM)."""
        return False

    def cleanup(self):
        """Clean up resources."""
        self.player.cleanup()
        logger.debug(f"Cleaned up audio source: {self.file_path}")

    def duck(self):
        """Reduce volume (user speaking)."""
        self.player.duck()

    def unduck(self):
        """Restore volume (user stopped speaking)."""
        self.player.unduck()

    def set_volume(self, volume: float):
        """Set base volume."""
        self.player.set_volume(volume)