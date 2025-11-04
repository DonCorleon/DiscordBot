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
        description="Speech recognition engine to use (requires listener restart: leave and rejoin voice)",
        category="Audio/Speech Recognition",
        guild_override=True,
        choices=["vosk", "whisper", "faster-whisper"],
        requires_restart=True
    )

    # Voice Activity Detection (VAD) Settings
    enable_vad: bool = config_field(
        default=True,
        description="Enable Voice Activity Detection to skip silence (improves performance and accuracy)",
        category="Audio/Speech Recognition/VAD",
        guild_override=True
    )

    vad_silence_threshold: float = config_field(
        default=100.0,
        description="VAD silence threshold - lower = more sensitive (processes more audio), higher = less sensitive (skips more silence)",
        category="Audio/Speech Recognition/VAD",
        guild_override=False,
        admin_only=True,
        min_value=10.0,
        max_value=1000.0
    )

    # Vosk Settings
    vosk_model_path: str = config_field(
        default="data/speechrecognition/vosk",
        description="Path to Vosk model directory",
        category="Audio/Speech Recognition/Vosk",
        guild_override=True,
        admin_only=True,
        requires_restart=True
    )

    vosk_chunk_duration: float = config_field(
        default=4.0,
        description="Process audio every N seconds (Vosk)",
        category="Audio/Speech Recognition/Vosk",
        guild_override=False,
        admin_only=True,
        min_value=1.0,
        max_value=10.0
    )

    vosk_chunk_overlap: float = config_field(
        default=0.5,
        description="Overlap between chunks in seconds to prevent missing words (Vosk)",
        category="Audio/Speech Recognition/Vosk",
        guild_override=False,
        admin_only=True,
        min_value=0.0,
        max_value=2.0
    )

    vosk_processing_interval: float = config_field(
        default=0.1,
        description="How often to check audio buffers for processing in seconds (lower = more responsive, higher = less CPU)",
        category="Audio/Speech Recognition/Vosk",
        guild_override=False,
        admin_only=True,
        min_value=0.05,
        max_value=0.5
    )

    # Whisper Settings
    whisper_model: str = config_field(
        default="tiny.en",
        description="Whisper model size",
        category="Audio/Speech Recognition/Whisper",
        guild_override=True,
        choices=["tiny.en", "base.en", "small.en", "medium.en"],
        requires_restart=True
    )

    whisper_buffer_duration: float = config_field(
        default=3.0,
        description="Audio buffer duration in seconds (Whisper)",
        category="Audio/Speech Recognition/Whisper",
        guild_override=False,
        admin_only=True,
        min_value=1.0,
        max_value=10.0
    )

    whisper_debounce_seconds: float = config_field(
        default=1.0,
        description="Min seconds between transcriptions (Whisper)",
        category="Audio/Speech Recognition/Whisper",
        guild_override=False,
        admin_only=True,
        min_value=0.5,
        max_value=5.0
    )

    # Faster-Whisper Settings (CTranslate2 backend - 4x faster than openai-whisper)
    faster_whisper_model: str = config_field(
        default="base",
        description="faster-whisper model size (larger = more accurate but slower)",
        category="Audio/Speech Recognition/Faster-Whisper",
        guild_override=True,
        choices=["tiny", "base", "small", "medium", "large-v2", "large-v3"],
        requires_restart=True
    )

    faster_whisper_device: str = config_field(
        default="cpu",
        description="Compute device for faster-whisper (cuda requires NVIDIA GPU with CUDA toolkit)",
        category="Audio/Speech Recognition/Faster-Whisper",
        guild_override=False,
        admin_only=True,
        choices=["cpu", "cuda"],
        requires_restart=True
    )

    faster_whisper_compute_type: str = config_field(
        default="int8",
        description="Compute precision for faster-whisper (int8 = fastest, float32 = most accurate)",
        category="Audio/Speech Recognition/Faster-Whisper",
        guild_override=False,
        admin_only=True,
        choices=["int8", "int8_float16", "float16", "float32"],
        requires_restart=True
    )

    faster_whisper_buffer_duration: float = config_field(
        default=3.0,
        description="Audio buffer duration in seconds (faster-whisper)",
        category="Audio/Speech Recognition/Faster-Whisper",
        guild_override=False,
        admin_only=True,
        min_value=1.0,
        max_value=10.0
    )

    faster_whisper_debounce_seconds: float = config_field(
        default=1.0,
        description="Min seconds between transcriptions (faster-whisper)",
        category="Audio/Speech Recognition/Faster-Whisper",
        guild_override=False,
        admin_only=True,
        min_value=0.5,
        max_value=5.0
    )
