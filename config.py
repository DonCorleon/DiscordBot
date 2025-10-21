# config.py
"""
Bot configuration file.
Centralized configuration for all bot features.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    """Main bot configuration."""

    # Discord Configuration
    token: str
    command_prefix: str | list[str] = "~"

    # Admin Interface Configuration
    # Set to False for headless servers (no pygame dashboard)
    enable_admin_dashboard: bool = True

    # Monitoring Configuration
    max_history: int = 1000
    health_collection_interval: int = 5
    data_export_interval: int = 10

    # Voice Configuration
    default_volume: float = 0.5
    keepalive_interval: int = 30

    # Audio Ducking Configuration
    ducking_enabled: bool = True  # Enable ducking by default
    ducking_level: float = 0.5  # 50% volume when ducked
    ducking_transition_ms: int = 50  # 50ms smooth transition

    # File Storage
    soundboard_dir: str = "soundboard"
    log_dir: str = "logs"
    admin_data_dir: str = "admin_data"

    # Logging Configuration
    log_level: str = "INFO"

    # Feature Flags
    enable_auto_disconnect: bool = True
    enable_speech_recognition: bool = True

    # Weekly Recap Configuration
    enable_weekly_recap: bool = False  # Disabled by default
    weekly_recap_channel_id: int = None  # Channel ID to post recaps
    weekly_recap_day: int = 0  # Day of week (0=Monday, 6=Sunday)
    weekly_recap_hour: int = 9  # Hour to post (24-hour format)

    # Admin System Configuration
    bot_owner_id: int = 696940351977422878  # Bot owner (can manage admins)
    admin_user_ids: list[int] = None  # User IDs with admin access
    admin_role_ids: list[int] = None  # Role IDs with admin access

    # Voice Time Tracking Configuration
    voice_tracking_enabled: bool = True  # Track voice channel time
    voice_points_per_minute: float = 0.0  # Points awarded per minute in voice (0 = disabled)
    voice_time_display_mode: str = "ranges"  # "ranges", "descriptions", or "points_only"
    voice_tracking_type: str = "total"  # "total", "unmuted", or "speaking"

    @classmethod
    def from_env(cls):
        """Create config from environment variables."""
        # Handle command prefix - support both single and multiple prefixes
        prefix_str = os.getenv("COMMAND_PREFIX", "~")
        # If comma-separated, split into list
        if "," in prefix_str:
            command_prefix = [p.strip() for p in prefix_str.split(",") if p.strip()]
        else:
            command_prefix = prefix_str

        return cls(
            token=os.getenv("DISCORD_TOKEN"),
            command_prefix=command_prefix,
            enable_admin_dashboard=os.getenv("ENABLE_ADMIN_DASHBOARD", "true").lower() == "true",
            max_history=int(os.getenv("MAX_HISTORY", "1000")),
            health_collection_interval=int(os.getenv("HEALTH_COLLECTION_INTERVAL", "5")),
            data_export_interval=int(os.getenv("DATA_EXPORT_INTERVAL", "10")),
            default_volume=float(os.getenv("DEFAULT_VOLUME", "0.5")),
            keepalive_interval=int(os.getenv("KEEPALIVE_INTERVAL", "30")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            # Audio ducking settings
            ducking_enabled=os.getenv("DUCKING_ENABLED", "true").lower() == "true",
            ducking_level=float(os.getenv("DUCKING_LEVEL", "0.5")),
            ducking_transition_ms=int(os.getenv("DUCKING_TRANSITION_MS", "50")),
            # Feature flags
            enable_auto_disconnect=os.getenv("ENABLE_AUTO_DISCONNECT", "true").lower() == "true",
            enable_speech_recognition=os.getenv("ENABLE_SPEECH_RECOGNITION", "true").lower() == "true",
            # Weekly recap settings
            enable_weekly_recap=os.getenv("ENABLE_WEEKLY_RECAP", "false").lower() == "true",
            weekly_recap_channel_id=int(os.getenv("WEEKLY_RECAP_CHANNEL_ID")) if os.getenv("WEEKLY_RECAP_CHANNEL_ID") else None,
            weekly_recap_day=int(os.getenv("WEEKLY_RECAP_DAY", "0")),  # Default Monday
            weekly_recap_hour=int(os.getenv("WEEKLY_RECAP_HOUR", "9")),  # Default 9 AM
            # Admin system - owner ID is hardcoded, admins loaded from file
            admin_user_ids=[696940351977422878],  # Start with owner as admin
            admin_role_ids=[],
            # Voice tracking settings
            voice_tracking_enabled=os.getenv("VOICE_TRACKING_ENABLED", "true").lower() == "true",
            voice_points_per_minute=float(os.getenv("VOICE_POINTS_PER_MINUTE", "0.0")),
            voice_time_display_mode=os.getenv("VOICE_TIME_DISPLAY_MODE", "ranges"),
            voice_tracking_type=os.getenv("VOICE_TRACKING_TYPE", "total"),
        )

    def display(self):
        """Display current configuration (safe for logging)."""
        prefix_display = ", ".join(self.command_prefix) if isinstance(self.command_prefix,
                                                                      list) else self.command_prefix
        return f"""
Bot Configuration:
==================
Command Prefix: {prefix_display}
Admin Dashboard: {'Enabled' if self.enable_admin_dashboard else 'Disabled (Headless Mode)'}
Max History: {self.max_history} entries
Health Collection: Every {self.health_collection_interval}s
Data Export: {'Every ' + str(self.data_export_interval) + 's' if self.enable_admin_dashboard else 'Disabled'}
Default Volume: {self.default_volume}
Audio Ducking: {'Enabled' if self.ducking_enabled else 'Disabled'} (Level: {int(self.ducking_level * 100)}%)
Log Level: {self.log_level}
Auto Disconnect: {self.enable_auto_disconnect}
Speech Recognition: {self.enable_speech_recognition}
"""


# Load Configuration
config = BotConfig.from_env()