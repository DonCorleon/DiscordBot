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

    log_rotation_interval: int = config_field(
        default=1,
        description="Days between log file rotation (midnight rotation)",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=1,
        max_value=30
    )

    log_backup_count: int = config_field(
        default=7,
        description="Number of daily log backup files to retain",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        requires_restart=True,
        min_value=1,
        max_value=365
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

    # Monitoring Intervals and Thresholds
    monitor_health_interval: int = config_field(
        default=60,
        description="Seconds between health monitoring checks (CPU/memory warnings)",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=30,
        max_value=600
    )

    high_memory_threshold: int = config_field(
        default=80,
        description="Memory usage percentage threshold for warnings",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=95
    )

    high_cpu_threshold: int = config_field(
        default=80,
        description="CPU usage percentage threshold for warnings",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=95
    )

    large_queue_warning_size: int = config_field(
        default=50,
        description="Sound queue size threshold for warnings in health monitoring",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=10,
        max_value=500
    )

    # Health Status Color Thresholds
    health_color_warning_memory: int = config_field(
        default=80,
        description="Memory percentage threshold for red health status color",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=95
    )

    health_color_warning_cpu: int = config_field(
        default=80,
        description="CPU percentage threshold for red health status color",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=95
    )

    health_color_caution_memory: int = config_field(
        default=60,
        description="Memory percentage threshold for orange health status color",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=30,
        max_value=80
    )

    health_color_caution_cpu: int = config_field(
        default=60,
        description="CPU percentage threshold for orange health status color",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=30,
        max_value=80
    )

    # Log Display Settings
    logs_chunk_char_limit: int = config_field(
        default=1900,
        description="Character limit per Discord embed for log chunks",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=500,
        max_value=4000
    )

    log_message_truncate_length: int = config_field(
        default=100,
        description="Maximum characters to show per log message in logs command",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=500
    )

    # Ping Status Thresholds
    ping_excellent_threshold: int = config_field(
        default=100,
        description="Milliseconds threshold for 'Excellent' ping status",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=50,
        max_value=200
    )

    ping_good_threshold: int = config_field(
        default=200,
        description="Milliseconds threshold for 'Good' ping status",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=100,
        max_value=300
    )

    ping_fair_threshold: int = config_field(
        default=300,
        description="Milliseconds threshold for 'Fair' ping status",
        category="Admin/Monitoring",
        guild_override=False,
        admin_only=True,
        min_value=200,
        max_value=500
    )

    # System Update Settings
    update_git_output_truncate: int = config_field(
        default=400,
        description="Maximum characters to show from git pull output",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        min_value=100,
        max_value=2000
    )

    update_shutdown_delay: int = config_field(
        default=2,
        description="Seconds to wait before shutting down after update",
        category="Admin/System",
        guild_override=False,
        admin_only=True,
        min_value=1,
        max_value=10
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
