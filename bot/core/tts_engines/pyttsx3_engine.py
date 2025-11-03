"""
Pyttsx3 TTS engine (local, espeak/SAPI/nsss).

Uses pyttsx3 library for offline text-to-speech.
Quality: Low (espeak) to Medium (SAPI on Windows)
"""

import asyncio
import tempfile
from typing import Optional, List, Dict, Any
from .base import TTSEngine, logger

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False
    logger.warning("pyttsx3 not installed. Install with: pip install pyttsx3")


class Pyttsx3Engine(TTSEngine):
    """Pyttsx3-based TTS engine."""

    def __init__(self, bot):
        super().__init__(bot)

        if not PYTTSX3_AVAILABLE:
            raise ImportError("pyttsx3 is not available")

        # Discover available voices
        self.available_voices = self._discover_voices()
        logger.info(f"Pyttsx3Engine initialized with {len(self.available_voices)} voices")

    def _discover_voices(self) -> List[Dict[str, Any]]:
        """Discover all available pyttsx3 voices."""
        try:
            engine = pyttsx3.init()
            system_voices = engine.getProperty("voices")
            discovered = []

            for voice in system_voices:
                voice_id = voice.id
                display_name = voice.name if hasattr(voice, 'name') else voice_id

                voice_info = {
                    "id": voice_id,
                    "name": display_name,
                    "language": str(voice.languages[0]) if hasattr(voice, "languages") and voice.languages else "unknown",
                    "gender": str(voice.gender) if hasattr(voice, "gender") else "unknown",
                }

                discovered.append(voice_info)

            del engine
            return discovered

        except Exception as e:
            logger.error(f"Failed to discover pyttsx3 voices: {e}", exc_info=True)
            return []

    async def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        volume: float = 1.0,
        guild_id: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate TTS audio using pyttsx3."""
        loop = asyncio.get_running_loop()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.close()

        # Get default rate from config if not provided
        if rate is None:
            rate = 150
            if guild_id and hasattr(self.bot, 'config_manager'):
                rate = self.bot.config_manager.get("TTS", "tts_default_rate", guild_id)

        def generate_tts():
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)

            # Set voice if provided
            if voice:
                engine.setProperty("voice", voice)
                logger.info(f"[Guild {guild_id}] Pyttsx3: Using voice {voice}")
            else:
                logger.info(f"[Guild {guild_id}] Pyttsx3: Using system default voice")

            engine.save_to_file(text, temp_file.name)
            engine.runAndWait()
            # Don't call stop() - causes segfaults

        await loop.run_in_executor(None, generate_tts)
        return temp_file.name

    async def list_voices(self) -> List[Dict[str, Any]]:
        """List available pyttsx3 voices."""
        return self.available_voices

    def get_default_voice(self, guild_id: Optional[int] = None) -> Optional[str]:
        """Get default voice from config."""
        if guild_id and hasattr(self.bot, 'config_manager'):
            return self.bot.config_manager.get("TTS", "tts_default_voice", guild_id)
        return None
