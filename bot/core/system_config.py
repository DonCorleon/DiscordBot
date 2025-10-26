"""
System-level configuration schema.

This module defines the SystemConfig schema for bot-wide settings like
token, command prefix, logging, web dashboard, etc.
"""

from dataclasses import dataclass
from bot.core.config_base import ConfigBase, config_field
from bot.core.config_system import validate_ip_address


@dataclass
class SystemConfig(ConfigBase):
    """System-level bot configuration (bot owner only, no guild overrides)."""

    # Bot Owner Settings
    token: str = config_field(
        default="",
        description="Discord bot token (REQUIRED - set via DISCORD_TOKEN in .env)",
        category="Bot Owner",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        env_only=True  # Security: only read from .env, never save to JSON
    )

    command_prefix: str = config_field(
        default="~",
        description="Bot command prefix (e.g., ~, !, $)",
        category="Bot Owner",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    bot_owner_id: int = config_field(
        default=696940351977422878,
        description="Discord user ID of the bot owner (set via BOT_OWNER in .env)",
        category="Bot Owner",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=0,
        is_large_int=True,  # Discord snowflake ID
        env_only=True  # Security: only read from .env, never save to JSON
    )

    # Admin System Settings
    log_level: str = config_field(
        default="INFO",
        description="Logging level for bot output (set via LOG_LEVEL in .env for startup)",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        env_only=True  # Must be in .env to take effect at startup
    )

    log_dir: str = config_field(
        default="data/logs",
        description="Directory for log files",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    admin_data_dir: str = config_field(
        default="data/admin",
        description="Directory for admin dashboard data",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    # Monitoring Settings
    max_history: int = config_field(
        default=1000,
        description="Maximum history entries to keep in memory",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=100,
        max_value=10000
    )

    health_collection_interval: int = config_field(
        default=5,
        description="Seconds between health data collection",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=1,
        max_value=60
    )

    data_export_interval: int = config_field(
        default=10,
        description="Seconds between admin dashboard JSON exports (health, commands, errors, etc.)",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=5,
        max_value=300
    )

    logs_max_lines: int = config_field(
        default=50,
        description="Maximum log lines to display in Discord ~logs command (prevents spam)",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=10,
        max_value=200
    )

    # Feature Flags
    enable_auto_disconnect: bool = config_field(
        default=True,
        description="Enable auto-disconnect from empty voice channels",
        category="Admin/Features",
        guild_override=False,
        admin_only=True
    )

    enable_speech_recognition: bool = config_field(
        default=True,
        description="Enable speech recognition in voice channels",
        category="Admin/Features",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    # Web Dashboard Settings
    enable_web_dashboard: bool = config_field(
        default=False,
        description="Enable web-based admin dashboard",
        category="Admin/Web",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    web_host: str = config_field(
        default="0.0.0.0",
        description="Web dashboard host (0.0.0.0 = all interfaces, 127.0.0.1 = local only)",
        category="Admin/Web",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        validator=validate_ip_address
    )

    web_port: int = config_field(
        default=8000,
        description="Web dashboard port",
        category="Admin/Web",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=1024,
        max_value=65535
    )

    web_reload: bool = config_field(
        default=False,
        description="Auto-reload web dashboard on code changes (development only)",
        category="Admin/Web",
        guild_override=False,
        admin_only=True,
        requires_restart=True
    )

    # Voice/Audio Settings
    keepalive_interval: int = config_field(
        default=30,
        description="Seconds between keepalive packets in voice channels",
        category="Admin/Voice",
        guild_override=False,
        admin_only=True,
        min_value=10,
        max_value=300
    )

    # Audio Engine Settings (Technical - shouldn't need changing)
    audio_sample_rate: int = config_field(
        default=48000,
        description="Audio sample rate in Hz (Discord standard is 48000)",
        category="Admin/Audio",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=8000,
        max_value=192000
    )

    audio_channels: int = config_field(
        default=2,
        description="Number of audio channels (1=mono, 2=stereo)",
        category="Admin/Audio",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=1,
        max_value=2
    )

    audio_chunk_size: int = config_field(
        default=960,
        description="Audio chunk size in frames (960 = 20ms at 48kHz)",
        category="Admin/Audio",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=480,
        max_value=4800
    )

    audio_duck_transition_ms: int = config_field(
        default=50,
        description="Transition time for volume ducking in milliseconds",
        category="Admin/Audio",
        guild_override=False,
        admin_only=True,
        min_value=10,
        max_value=500
    )
