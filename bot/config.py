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
    soundboard_dir: str = "data/soundboard"
    log_dir: str = "data/logs"
    admin_data_dir: str = "data/admin"

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

    # Auto-Join Configuration
    auto_join_enabled: bool = True  # Enable auto-join for voice channels
    auto_join_timeout: int = 300  # Seconds to wait before leaving empty channel (default: 5 minutes)

    # Web Dashboard Configuration
    enable_web_dashboard: bool = False  # Enable web-based admin dashboard (disabled by default)
    web_host: str = "0.0.0.0"  # Listen on all interfaces (use 127.0.0.1 for local only)
    web_port: int = 8000  # Port for web dashboard
    web_reload: bool = False  # Auto-reload on code changes (development only)

    # TTS Configuration (per-guild configurable)
    tts_default_volume: float = 1.5  # Default TTS playback volume
    tts_default_rate: int = 150  # Default TTS speech rate (words per minute)
    tts_max_text_length: int = 500  # Maximum text length for TTS

    # Edge TTS Configuration (per-guild configurable)
    edge_tts_default_volume: float = 1.5  # Default Edge TTS volume
    edge_tts_default_voice: str = "en-US-AriaNeural"  # Default Edge TTS voice

    # Audio Playback Configuration
    sound_playback_timeout: float = 30.0  # Max seconds to wait for sound playback
    sound_queue_warning_size: int = 50  # Queue size threshold for warnings

    # Activity Points Configuration (per-guild configurable)
    activity_base_message_points_min: float = 0.8  # Min points for a message
    activity_base_message_points_max: float = 1.2  # Max points for a message
    activity_link_bonus_points: float = 2.0  # Bonus points for message with link
    activity_attachment_bonus_points: float = 2.0  # Bonus points for attachment
    activity_reaction_points: float = 1.0  # Points for reactions
    activity_reply_points: float = 1.0  # Points for replies

    # Leaderboard Configuration (per-guild configurable)
    leaderboard_default_limit: int = 10  # Default number of leaderboard entries
    user_stats_channel_breakdown_limit: int = 5  # Channel breakdown limit in user stats
    user_stats_triggers_limit: int = 5  # Top triggers limit in user stats
    leaderboard_bar_chart_length: int = 15  # Bar chart length in leaderboard

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
            # Auto-join settings
            auto_join_enabled=os.getenv("AUTO_JOIN_ENABLED", "true").lower() == "true",
            auto_join_timeout=int(os.getenv("AUTO_JOIN_TIMEOUT", "300")),
            # Web dashboard settings
            enable_web_dashboard=os.getenv("ENABLE_WEB_DASHBOARD", "false").lower() == "true",
            web_host=os.getenv("WEB_HOST", "0.0.0.0"),
            web_port=int(os.getenv("WEB_PORT", "8000")),
            web_reload=os.getenv("WEB_RELOAD", "false").lower() == "true",
            # TTS settings
            tts_default_volume=float(os.getenv("TTS_DEFAULT_VOLUME", "1.5")),
            tts_default_rate=int(os.getenv("TTS_DEFAULT_RATE", "150")),
            tts_max_text_length=int(os.getenv("TTS_MAX_TEXT_LENGTH", "500")),
            # Edge TTS settings
            edge_tts_default_volume=float(os.getenv("EDGE_TTS_DEFAULT_VOLUME", "1.5")),
            edge_tts_default_voice=os.getenv("EDGE_TTS_DEFAULT_VOICE", "en-US-AriaNeural"),
            # Audio playback settings
            sound_playback_timeout=float(os.getenv("SOUND_PLAYBACK_TIMEOUT", "30.0")),
            sound_queue_warning_size=int(os.getenv("SOUND_QUEUE_WARNING_SIZE", "50")),
            # Activity points settings
            activity_base_message_points_min=float(os.getenv("ACTIVITY_BASE_MESSAGE_POINTS_MIN", "0.8")),
            activity_base_message_points_max=float(os.getenv("ACTIVITY_BASE_MESSAGE_POINTS_MAX", "1.2")),
            activity_link_bonus_points=float(os.getenv("ACTIVITY_LINK_BONUS_POINTS", "2.0")),
            activity_attachment_bonus_points=float(os.getenv("ACTIVITY_ATTACHMENT_BONUS_POINTS", "2.0")),
            activity_reaction_points=float(os.getenv("ACTIVITY_REACTION_POINTS", "1.0")),
            activity_reply_points=float(os.getenv("ACTIVITY_REPLY_POINTS", "1.0")),
            # Leaderboard settings
            leaderboard_default_limit=int(os.getenv("LEADERBOARD_DEFAULT_LIMIT", "10")),
            user_stats_channel_breakdown_limit=int(os.getenv("USER_STATS_CHANNEL_BREAKDOWN_LIMIT", "5")),
            user_stats_triggers_limit=int(os.getenv("USER_STATS_TRIGGERS_LIMIT", "5")),
            leaderboard_bar_chart_length=int(os.getenv("LEADERBOARD_BAR_CHART_LENGTH", "15")),
        )

    def display(self):
        """Display current configuration (safe for logging)."""
        prefix_display = ", ".join(self.command_prefix) if isinstance(self.command_prefix,
                                                                      list) else self.command_prefix
        return f"""
Bot Configuration:
==================
Command Prefix: {prefix_display}
Max History: {self.max_history} entries
Health Collection: Every {self.health_collection_interval}s
Data Export: Every {self.data_export_interval}s
Default Volume: {self.default_volume}
Audio Ducking: {'Enabled' if self.ducking_enabled else 'Disabled'} (Level: {int(self.ducking_level * 100)}%)
Log Level: {self.log_level}
Auto Disconnect: {self.enable_auto_disconnect}
Speech Recognition: {self.enable_speech_recognition}
"""


# Load Configuration
config = BotConfig.from_env()