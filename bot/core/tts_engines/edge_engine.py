"""
Edge TTS engine (Microsoft cloud TTS).

Uses edge-tts library for Microsoft's neural text-to-speech.
Quality: High (8/10) - Neural TTS
Requires: Internet connection
"""

import asyncio
import tempfile
import io
from typing import Optional, List, Dict, Any
from .base import TTSEngine, logger

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False
    logger.warning("edge-tts not installed. Install with: pip install edge-tts")


class EdgeEngine(TTSEngine):
    """Edge TTS-based engine."""

    # Common high-quality voices
    COMMON_VOICES = [
        "en-US-AriaNeural",
        "en-US-GuyNeural",
        "en-GB-RyanNeural",
        "en-GB-SoniaNeural",
        "en-AU-NatashaNeural",
        "en-IN-NeerjaNeural"
    ]

    def __init__(self, bot):
        super().__init__(bot)

        if not EDGE_TTS_AVAILABLE:
            raise ImportError("edge-tts is not available")

        self.voices_cache = None
        logger.info("EdgeEngine initialized")

    async def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        volume: float = 1.0,
        guild_id: Optional[int] = None,
        **kwargs
    ) -> str:
        """Generate TTS audio using Edge TTS."""
        # Get default voice if not provided
        if not voice:
            voice = self.get_default_voice(guild_id) or "en-US-AriaNeural"

        # Edge TTS rate is in percentage format (+X% or -X%)
        # Convert from words-per-minute to percentage if needed
        rate_str = "+0%"  # Default
        if rate:
            # Rough conversion: 150 wpm = normal (0%), each 50 wpm = ±50%
            percent = int(((rate - 150) / 150) * 100)
            rate_str = f"+{percent}%" if percent >= 0 else f"{percent}%"

        try:
            # Generate TTS audio
            tts = edge_tts.Communicate(text, voice, rate=rate_str)
            audio_data = io.BytesIO()

            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])

            audio_data.seek(0)

            # Save to temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            temp_file.write(audio_data.getvalue())
            temp_file.close()

            logger.info(f"[Guild {guild_id}] Edge TTS: Generated audio with voice {voice}")
            return temp_file.name

        except Exception as e:
            logger.error(f"Edge TTS generation failed: {e}", exc_info=True)
            raise

    async def list_voices(self) -> List[Dict[str, Any]]:
        """List available Edge TTS voices."""
        if self.voices_cache is None:
            try:
                all_voices = await edge_tts.list_voices()
                self.voices_cache = []

                for voice in all_voices:
                    # Handle different possible key names (API may vary)
                    voice_id = voice.get("ShortName") or voice.get("Name", "unknown")
                    voice_name = voice.get("FriendlyName") or voice.get("DisplayName") or voice_id
                    locale = voice.get("Locale") or voice.get("Language", "unknown")
                    gender = voice.get("Gender", "unknown")

                    self.voices_cache.append({
                        "id": voice_id,
                        "name": voice_name,
                        "language": locale,
                        "gender": gender
                    })

                logger.info(f"Cached {len(self.voices_cache)} Edge TTS voices")

            except Exception as e:
                logger.error(f"Failed to list Edge TTS voices: {e}", exc_info=True)
                # Log first voice structure for debugging
                try:
                    all_voices = await edge_tts.list_voices()
                    if all_voices:
                        logger.debug(f"Edge TTS voice structure example: {list(all_voices[0].keys())}")
                except:
                    pass
                self.voices_cache = []

        return self.voices_cache

    def get_default_voice(self, guild_id: Optional[int] = None) -> Optional[str]:
        """Get default voice from config."""
        if guild_id and hasattr(self.bot, 'config_manager'):
            default = self.bot.config_manager.get("TTS", "tts_voice_edge", guild_id)
            if default:
                return default
        return "en-US-AriaNeural"
