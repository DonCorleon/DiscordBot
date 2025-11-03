"""
TTS engine factory.

Creates the appropriate TTS engine based on configuration.
"""

from .base import TTSEngine, logger


def create_tts_engine(bot, engine_type: str = "pyttsx3") -> TTSEngine:
    """
    Create a TTS engine instance.

    Args:
        bot: Discord bot instance
        engine_type: Engine type ("pyttsx3", "edge", "piper")

    Returns:
        TTSEngine instance

    Raises:
        ValueError: If engine_type is unknown
        ImportError: If engine dependencies are missing
    """
    engine_type = engine_type.lower()

    if engine_type == "pyttsx3":
        from .pyttsx3_engine import Pyttsx3Engine
        return Pyttsx3Engine(bot)

    elif engine_type == "edge":
        from .edge_engine import EdgeEngine
        return EdgeEngine(bot)

    elif engine_type == "piper":
        from .piper_engine import PiperEngine
        return PiperEngine(bot)

    else:
        raise ValueError(f"Unknown TTS engine: {engine_type}")
