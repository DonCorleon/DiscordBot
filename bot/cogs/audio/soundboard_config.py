"""
Soundboard Configuration Schema

Defines all configurable settings for the Soundboard cog with proper
validation, descriptions, and guild-override support.
"""

from dataclasses import dataclass
from bot.core.config_base import ConfigBase, config_field


@dataclass
class SoundboardConfig(ConfigBase):
    """Soundboard configuration schema."""

    # Playback Settings
    default_volume: float = config_field(
        default=0.5,
        description="Default playback volume for sounds (0.0 = muted, 1.0 = normal, 2.0 = 200%)",
        category="Playback",
        guild_override=True,
        min_value=0.0,
        max_value=2.0
    )

    ducking_enabled: bool = config_field(
        default=True,
        description="Auto-reduce volume when users speak to prevent drowning out voices",
        category="Playback",
        guild_override=True
    )

    ducking_level: float = config_field(
        default=0.5,
        description="Volume reduction level when ducking (0.0 = mute, 1.0 = no reduction)",
        category="Playback",
        guild_override=True,
        min_value=0.0,
        max_value=1.0
    )

    ducking_transition_ms: int = config_field(
        default=50,
        description="Smooth transition time for ducking in milliseconds",
        category="Playback",
        guild_override=True,
        min_value=10,
        max_value=500
    )

    sound_playback_timeout: float = config_field(
        default=30.0,
        description="Maximum seconds to wait for sound playback before timeout",
        category="Playback",
        guild_override=True,
        admin_only=True,
        min_value=5.0,
        max_value=300.0
    )

    sound_queue_warning_size: int = config_field(
        default=50,
        description="Queue size threshold for warnings (prevents queue flooding)",
        category="Playback",
        guild_override=True,
        admin_only=True,
        min_value=10,
        max_value=500
    )

    # Admin Settings
    soundboard_dir: str = config_field(
        default="data/soundboard",
        description="Directory containing sound files",
        category="Admin",
        guild_override=False,  # Global only
        admin_only=True,
        requires_restart=True
    )
