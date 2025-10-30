"""
Speech engine configuration schema.

Defines configurable parameters for speech recognition engines.
"""

from dataclasses import dataclass
from bot.core.config_base import ConfigBase, config_field


@dataclass
class SpeechConfig(ConfigBase):
    """Speech recognition engine configuration."""

    # Engine Selection
    engine: str = config_field(
        default="vosk",
        description="Speech recognition engine to use",
        category="Speech Recognition",
        guild_override=True,
        choices=["vosk", "whisper"]
    )

    # Vosk Settings
    vosk_model_path: str = config_field(
        default="data/speechrecognition/vosk",
        description="Path to Vosk model directory",
        category="Speech Recognition/Vosk",
        guild_override=False,
        admin_only=True
    )

    # Whisper Settings
    whisper_model: str = config_field(
        default="tiny.en",
        description="Whisper model size (requires openai-whisper, scipy)",
        category="Speech Recognition/Whisper",
        guild_override=False,
        admin_only=True,
        choices=["tiny.en", "base.en", "small.en", "medium.en"]
    )

    whisper_buffer_duration: float = config_field(
        default=3.0,
        description="Audio buffer duration in seconds (Whisper)",
        category="Speech Recognition/Whisper",
        guild_override=False,
        admin_only=True,
        min_value=1.0,
        max_value=10.0
    )

    whisper_debounce_seconds: float = config_field(
        default=1.0,
        description="Min seconds between transcriptions (Whisper)",
        category="Speech Recognition/Whisper",
        guild_override=False,
        admin_only=True,
        min_value=0.5,
        max_value=5.0
    )
