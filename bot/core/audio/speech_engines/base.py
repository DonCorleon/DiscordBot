"""
Abstract base class for pluggable speech recognition engines.

Allows swapping between different speech recognition implementations
(Vosk, Whisper, Google STT, etc.) without changing voice connection logic.
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional, Any
import discord
import logging

logger = logging.getLogger("discordbot.speech_engines")


class SpeechEngine(ABC):
    """
    Abstract base for speech recognition engines.

    Each engine implementation handles:
    - Audio capture from Discord voice
    - Speech-to-text processing
    - Callback invocation with results
    """

    def __init__(self, bot, callback: Callable[[discord.Member, str], None]):
        """
        Initialize speech engine.

        Args:
            bot: Discord bot instance (for config access, etc.)
            callback: Function called with (member, transcribed_text) when speech is recognized
        """
        self.bot = bot
        self.callback = callback
        self._is_listening = False

    @abstractmethod
    async def start_listening(self, voice_client) -> Any:
        """
        Start speech recognition on a voice client.

        Args:
            voice_client: Discord VoiceRecvClient instance

        Returns:
            Sink instance or other reference (implementation-specific)
        """
        pass

    @abstractmethod
    async def stop_listening(self) -> None:
        """
        Stop speech recognition and cleanup resources.

        Should cancel any background tasks, close connections, etc.
        """
        pass

    @abstractmethod
    def get_sink(self) -> Optional[Any]:
        """
        Get the voice_recv sink instance if applicable.

        Returns:
            Sink instance or None if engine doesn't use voice_recv sinks
        """
        pass

    @property
    def is_listening(self) -> bool:
        """Check if engine is currently listening."""
        return self._is_listening

    def _invoke_callback(self, member: discord.Member, text: str):
        """
        Safely invoke the transcription callback.

        Args:
            member: Discord member who spoke
            text: Transcribed text
        """
        try:
            self.callback(member, text)
        except Exception as e:
            logger.error(f"Error in speech callback: {e}", exc_info=True)
