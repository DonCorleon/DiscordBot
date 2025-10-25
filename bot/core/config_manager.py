"""
Config Manager for runtime configuration management.
Handles loading, validation, and hot-reloading of configuration settings.
"""

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("discordbot.config_manager")

RUNTIME_CONFIG_FILE = Path("data/config/runtime_config.json")
BACKUP_CONFIG_FILE = Path("data/config/runtime_config.backup.json")


class ConfigManager:
    """Manages runtime configuration with validation and hot-reload support."""

    # Define which settings require bot restart
    RESTART_REQUIRED = {
        "token", "command_prefix", "web_host", "web_port",
        "bot_owner_id"  # Changing owner requires restart for security
    }

    # Define validation rules for each setting
    VALIDATION_RULES = {
        # Float values with ranges
        "default_volume": {"type": float, "min": 0.0, "max": 2.0},
        "ducking_level": {"type": float, "min": 0.0, "max": 1.0},
        "voice_points_per_minute": {"type": float, "min": 0.0, "max": 1000.0},
        "tts_default_volume": {"type": float, "min": 0.0, "max": 2.0},
        "edge_tts_default_volume": {"type": float, "min": 0.0, "max": 2.0},
        "sound_playback_timeout": {"type": float, "min": 5.0, "max": 300.0},
        "activity_base_message_points_min": {"type": float, "min": 0.0, "max": 10.0},
        "activity_base_message_points_max": {"type": float, "min": 0.0, "max": 10.0},
        "activity_link_bonus_points": {"type": float, "min": 0.0, "max": 100.0},
        "activity_attachment_bonus_points": {"type": float, "min": 0.0, "max": 100.0},
        "activity_reaction_points": {"type": float, "min": 0.0, "max": 100.0},
        "activity_reply_points": {"type": float, "min": 0.0, "max": 100.0},

        # Integer values with ranges
        "max_history": {"type": int, "min": 100, "max": 10000},
        "health_collection_interval": {"type": int, "min": 1, "max": 60},
        "data_export_interval": {"type": int, "min": 1, "max": 300},
        "keepalive_interval": {"type": int, "min": 10, "max": 300},
        "ducking_transition_ms": {"type": int, "min": 0, "max": 1000},
        "auto_join_timeout": {"type": int, "min": 30, "max": 3600},
        "web_port": {"type": int, "min": 1024, "max": 65535},
        "weekly_recap_day": {"type": int, "min": 0, "max": 6},
        "weekly_recap_hour": {"type": int, "min": 0, "max": 23},
        "tts_default_rate": {"type": int, "min": 50, "max": 400},
        "tts_max_text_length": {"type": int, "min": 100, "max": 2000},
        "sound_queue_warning_size": {"type": int, "min": 10, "max": 500},
        "leaderboard_default_limit": {"type": int, "min": 5, "max": 100},
        "user_stats_channel_breakdown_limit": {"type": int, "min": 1, "max": 20},
        "user_stats_triggers_limit": {"type": int, "min": 1, "max": 20},
        "leaderboard_bar_chart_length": {"type": int, "min": 5, "max": 50},
        "weekly_recap_channel_id": {"type": int, "min": 0, "max": 9999999999999999999},

        # Boolean values
        "enable_admin_dashboard": {"type": bool},
        "ducking_enabled": {"type": bool},
        "enable_auto_disconnect": {"type": bool},
        "enable_speech_recognition": {"type": bool},
        "enable_weekly_recap": {"type": bool},
        "voice_tracking_enabled": {"type": bool},
        "auto_join_enabled": {"type": bool},
        "enable_web_dashboard": {"type": bool},
        "web_reload": {"type": bool},

        # String values with choices
        "log_level": {"type": str, "choices": ["DEBUG", "INFO", "WARNING", "ERROR"]},
        "voice_time_display_mode": {"type": str, "choices": ["ranges", "descriptions", "points_only"]},
        "voice_tracking_type": {"type": str, "choices": ["total", "unmuted", "speaking"]},
        "web_host": {"type": str},

        # String values (no validation)
        "command_prefix": {"type": str},
        "soundboard_dir": {"type": str},
        "log_dir": {"type": str},
        "admin_data_dir": {"type": str},
        "edge_tts_default_voice": {"type": str},
    }

    # Categorize settings for UI - matches user's specification
    CATEGORIES = {
        "Admin": [
            # Admin-only settings (1-3, 5, 11-12, 17-18, 22-25, 30-32)
            "command_prefix", "bot_owner_id",
            "keepalive_interval", "enable_auto_disconnect", "enable_speech_recognition",
            "enable_admin_dashboard", "enable_web_dashboard",
            "max_history", "health_collection_interval", "data_export_interval", "log_level",
            "soundboard_dir", "log_dir", "admin_data_dir"
        ],
        "Playback": [
            # Playback settings (4, 6-9, 47-48)
            "default_volume", "ducking_enabled", "ducking_level", "ducking_transition_ms",
            "auto_join_enabled", "auto_join_timeout",
            "sound_playback_timeout", "sound_queue_warning_size"
        ],
        "TTS": [
            # TTS settings (33-37)
            "tts_default_volume", "tts_default_rate", "tts_max_text_length",
            "edge_tts_default_volume", "edge_tts_default_voice"
        ],
        "Stats": [
            # Stats/Activity settings (13-16, 26-29, 38-43, 59-62)
            "voice_tracking_enabled", "voice_points_per_minute",
            "voice_time_display_mode", "voice_tracking_type",
            "enable_weekly_recap", "weekly_recap_channel_id",
            "weekly_recap_day", "weekly_recap_hour",
            "activity_base_message_points_min", "activity_base_message_points_max",
            "activity_link_bonus_points", "activity_attachment_bonus_points",
            "activity_reaction_points", "activity_reply_points",
            "leaderboard_default_limit", "user_stats_channel_breakdown_limit",
            "user_stats_triggers_limit", "leaderboard_bar_chart_length"
        ],
        "Web": [
            # Web dashboard settings (19-21)
            "web_host", "web_port", "web_reload"
        ]
    }

    def __init__(self, bot_config):
        """Initialize config manager with bot's config instance."""
        self.bot_config = bot_config
        self.runtime_overrides = self._load_runtime_config()

    def _load_runtime_config(self) -> Dict[str, Any]:
        """Load runtime configuration overrides from JSON file."""
        if not RUNTIME_CONFIG_FILE.exists():
            return {}

        try:
            with open(RUNTIME_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load runtime config: {e}")
            return {}

    def _save_runtime_config(self):
        """Save runtime configuration overrides to JSON file."""
        try:
            # Ensure directory exists
            RUNTIME_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(RUNTIME_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.runtime_overrides, f, indent=2)

            logger.info("Runtime config saved successfully")
        except Exception as e:
            logger.error(f"Failed to save runtime config: {e}")
            raise

    def create_backup(self):
        """Create backup of current runtime config."""
        try:
            if RUNTIME_CONFIG_FILE.exists():
                # Use copy() instead of copy2() to avoid metadata permission issues
                shutil.copy(RUNTIME_CONFIG_FILE, BACKUP_CONFIG_FILE)
                logger.info("Config backup created")
        except (PermissionError, OSError) as e:
            logger.warning(f"Could not create config backup (continuing anyway): {e}")
        except Exception as e:
            logger.error(f"Failed to create config backup: {e}")
            raise

    def restore_backup(self) -> bool:
        """Restore configuration from backup."""
        try:
            if BACKUP_CONFIG_FILE.exists():
                # Use copy() instead of copy2() to avoid metadata permission issues
                shutil.copy(BACKUP_CONFIG_FILE, RUNTIME_CONFIG_FILE)
                self.runtime_overrides = self._load_runtime_config()
                logger.info("Config restored from backup")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False

    def get_config_value(self, key: str) -> Any:
        """Get current value of a config setting (runtime override or default)."""
        # Check runtime overrides first
        if key in self.runtime_overrides:
            return self.runtime_overrides[key]

        # Fall back to bot config
        return getattr(self.bot_config, key, None)

    def get_all_settings(self) -> Dict[str, Any]:
        """Get all configuration settings with metadata."""
        settings = {}

        for category, keys in self.CATEGORIES.items():
            for key in keys:
                value = self.get_config_value(key)
                validation = self.VALIDATION_RULES.get(key, {})

                settings[key] = {
                    "value": value,
                    "category": category,
                    "type": validation.get("type", str).__name__,
                    "requires_restart": key in self.RESTART_REQUIRED,
                    "min": validation.get("min"),
                    "max": validation.get("max"),
                    "choices": validation.get("choices"),
                    "description": self._get_description(key)
                }

        return settings

    def _get_description(self, key: str) -> str:
        """Get human-readable description for a config key."""
        descriptions = {
            "command_prefix": "Bot command prefix (e.g., ~ or !)",
            "default_volume": "Default audio playback volume (0.0 to 2.0)",
            "keepalive_interval": "Seconds between voice keepalive packets",
            "ducking_enabled": "Auto-reduce volume when users speak",
            "ducking_level": "Volume reduction amount when ducking (0.0 to 1.0)",
            "ducking_transition_ms": "Smoothness of volume transitions (ms)",
            "auto_join_enabled": "Auto-join voice channels when users join",
            "auto_join_timeout": "Seconds before leaving empty voice channel",
            "enable_auto_disconnect": "Disconnect from voice when channel is empty",
            "enable_speech_recognition": "Enable voice transcription",
            "voice_tracking_enabled": "Track time users spend in voice",
            "voice_points_per_minute": "Points awarded per minute in voice",
            "voice_time_display_mode": "How to display voice time stats",
            "voice_tracking_type": "Type of voice time to track",
            "enable_admin_dashboard": "Enable pygame admin dashboard",
            "enable_web_dashboard": "Enable web-based admin interface",
            "web_host": "Web server bind address (0.0.0.0 or 127.0.0.1)",
            "web_port": "Web server port number",
            "web_reload": "Auto-reload web server on code changes",
            "max_history": "Maximum history entries to keep",
            "health_collection_interval": "Seconds between health metric collection",
            "data_export_interval": "Seconds between data exports",
            "log_level": "Logging verbosity level",
            "enable_weekly_recap": "Post weekly activity recaps",
            "weekly_recap_channel_id": "Channel ID for weekly recaps",
            "weekly_recap_day": "Day of week for recaps (0=Monday)",
            "weekly_recap_hour": "Hour of day for recaps (24h format)",
            # TTS settings
            "tts_default_volume": "Default TTS playback volume (0.0 to 2.0)",
            "tts_default_rate": "Default TTS speech rate (words per minute)",
            "tts_max_text_length": "Maximum text length for TTS messages",
            "edge_tts_default_volume": "Default Edge TTS volume (0.0 to 2.0)",
            "edge_tts_default_voice": "Default Edge TTS voice name",
            # Playback settings
            "sound_playback_timeout": "Max seconds to wait for sound playback",
            "sound_queue_warning_size": "Sound queue size threshold for warnings",
            # Activity points settings
            "activity_base_message_points_min": "Minimum points awarded for a message",
            "activity_base_message_points_max": "Maximum points awarded for a message",
            "activity_link_bonus_points": "Bonus points for messages with links",
            "activity_attachment_bonus_points": "Bonus points for messages with attachments",
            "activity_reaction_points": "Points awarded for each reaction",
            "activity_reply_points": "Points awarded for each reply",
            # Leaderboard settings
            "leaderboard_default_limit": "Default number of entries shown in leaderboard",
            "user_stats_channel_breakdown_limit": "Max channels shown in user stats breakdown",
            "user_stats_triggers_limit": "Max triggers shown in user stats",
            "leaderboard_bar_chart_length": "Character length of bar charts in leaderboard",
        }
        return descriptions.get(key, key.replace("_", " ").title())

    def validate_setting(self, key: str, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate a configuration setting.

        Returns:
            (valid, error_message) tuple
        """
        if key not in self.VALIDATION_RULES:
            return False, f"Unknown setting: {key}"

        rules = self.VALIDATION_RULES[key]
        expected_type = rules["type"]

        # Type validation
        try:
            if expected_type == bool:
                if not isinstance(value, bool):
                    return False, f"Must be a boolean (true/false)"
            elif expected_type == int:
                value = int(value)
            elif expected_type == float:
                value = float(value)
            elif expected_type == str:
                value = str(value)
        except (ValueError, TypeError):
            return False, f"Invalid type: expected {expected_type.__name__}"

        # Range validation
        if "min" in rules and value < rules["min"]:
            return False, f"Value must be at least {rules['min']}"
        if "max" in rules and value > rules["max"]:
            return False, f"Value must be at most {rules['max']}"

        # Choices validation
        if "choices" in rules and value not in rules["choices"]:
            return False, f"Must be one of: {', '.join(rules['choices'])}"

        return True, None

    def update_setting(self, key: str, value: Any) -> Tuple[bool, bool, Optional[str]]:
        """
        Update a configuration setting.

        Returns:
            (success, requires_restart, error_message) tuple
        """
        # Validate
        valid, error = self.validate_setting(key, value)
        if not valid:
            return False, False, error

        # Create backup before changing
        try:
            self.create_backup()
        except Exception as e:
            return False, False, f"Failed to create backup: {str(e)}"

        # Update runtime overrides
        self.runtime_overrides[key] = value

        # Save to disk
        try:
            self._save_runtime_config()
        except Exception as e:
            return False, False, f"Failed to save config: {str(e)}"

        # Apply to bot config if hot-reloadable
        requires_restart = key in self.RESTART_REQUIRED
        if not requires_restart:
            try:
                setattr(self.bot_config, key, value)
                logger.info(f"Hot-reloaded config: {key} = {value}")
            except Exception as e:
                logger.error(f"Failed to hot-reload {key}: {e}")

        return True, requires_restart, None
