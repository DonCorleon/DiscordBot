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