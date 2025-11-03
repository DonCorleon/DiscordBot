"""
Base TTS engine interface.

All TTS engines must inherit from TTSEngine and implement the required methods.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger("discordbot.tts_engines")


class TTSEngine(ABC):
    """Base class for TTS engines."""

    def __init__(self, bot):
        """
        Initialize TTS engine.

        Args:
            bot: Discord bot instance
        """
        self.bot = bot

    @abstractmethod
    async def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        volume: float = 1.0,
        guild_id: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate TTS audio and return file path.

        Args:
            text: Text to synthesize
            voice: Voice identifier (engine-specific)
            rate: Speech rate (words per minute or similar)
            volume: Volume level (0.0-2.0)
            guild_id: Guild ID for config access
            **kwargs: Additional engine-specific parameters

        Returns:
            Path to generated audio file (temp file)
        """
        pass

    @abstractmethod
    async def list_voices(self) -> List[Dict[str, Any]]:
        """
        List available voices for this engine.

        Returns:
            List of voice dictionaries with keys:
            - id: Voice identifier
            - name: Display name
            - language: Language code (e.g., "en-US")
            - gender: Optional gender
        """
        pass

    @abstractmethod
    def get_default_voice(self, guild_id: Optional[int] = None) -> Optional[str]:
        """
        Get the default voice for this engine.

        Args:
            guild_id: Guild ID for config access

        Returns:
            Voice identifier or None
        """
        pass

    def cleanup(self):
        """Cleanup resources. Override if needed."""
        pass
