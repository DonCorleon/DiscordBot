"""
Pluggable speech recognition engines.

Provides abstraction for swapping between different speech recognition
implementations (Vosk, Whisper, etc.) without changing voice connection logic.
"""

from .base import SpeechEngine
from .vosk import VoskEngine
from .whisper import WhisperEngine
from .config import SpeechConfig
import logging

logger = logging.getLogger("discordbot.speech_engines")


def create_speech_engine(
    bot,
    callback,
    engine_type: str = "vosk",
    ducking_callback=None
) -> SpeechEngine:
    """
    Factory function to create speech recognition engines.

    Args:
        bot: Discord bot instance
        callback: Function called with (member, transcribed_text) when speech is recognized
        engine_type: Engine to use ("vosk" or "whisper")
        ducking_callback: Optional callback for audio ducking events (guild_id, member, is_speaking)

    Returns:
        SpeechEngine instance

    Raises:
        ValueError: If engine_type is unknown
        NotImplementedError: If engine is not yet implemented (e.g., whisper)
    """

    if engine_type == "vosk":
        # Get Vosk config from bot's ConfigManager
        try:
            speech_cfg = bot.config_manager.for_guild("Speech")
            model_path = speech_cfg.vosk_model_path
        except Exception:
            # Fallback to defaults if config not available
            model_path = "data/speechrecognition/vosk"

        return VoskEngine(
            bot,
            callback,
            model_path=model_path,
            ducking_callback=ducking_callback
        )

    elif engine_type == "whisper":
        # Get Whisper config from bot's ConfigManager
        try:
            speech_cfg = bot.config_manager.for_guild("Speech")
            model_size = speech_cfg.whisper_model
            buffer_duration = speech_cfg.whisper_buffer_duration
            debounce_seconds = speech_cfg.whisper_debounce_seconds
        except Exception:
            # Fallback to defaults
            model_size = "tiny.en"
            buffer_duration = 3.0
            debounce_seconds = 1.0

        return WhisperEngine(
            bot,
            callback,
            model_size=model_size,
            buffer_duration=buffer_duration,
            debounce_seconds=debounce_seconds,
            ducking_callback=ducking_callback
        )

    else:
        raise ValueError(
            f"Unknown speech engine: '{engine_type}'. "
            f"Valid options: 'vosk', 'whisper'"
        )


__all__ = [
    "SpeechEngine",
    "VoskEngine",
    "WhisperEngine",
    "SpeechConfig",
    "create_speech_engine",
]
