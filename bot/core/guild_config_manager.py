"""
Guild Configuration Manager for per-guild settings.
Handles guild-specific overrides for configurable settings.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("discordbot.guild_config_manager")

GUILD_CONFIG_FILE = Path("data/config/guild_configs.json")


class GuildConfigManager:
    """Manages per-guild configuration overrides."""

    # Define which settings can be overridden per-guild
    GUILD_OVERRIDABLE_SETTINGS = {
        # Playback settings (4, 6-9)
        "default_volume",
        "ducking_enabled",
        "ducking_level",
        "ducking_transition_ms",
        "auto_join_enabled",
        "auto_join_timeout",
        # TTS settings (33-37)
        "tts_default_volume",
        "tts_default_rate",
        "tts_max_text_length",
        "edge_tts_default_volume",
        "edge_tts_default_voice",
        # Playback/Admin settings (47-48)
        "sound_playback_timeout",
        "sound_queue_warning_size",
        # Stats settings (13-16, 26-29, 38-43, 59-62)
        "voice_tracking_enabled",
        "voice_points_per_minute",
        "voice_time_display_mode",
        "voice_tracking_type",
        "enable_weekly_recap",
        "weekly_recap_channel_id",
        "weekly_recap_day",
        "weekly_recap_hour",
        "activity_base_message_points_min",
        "activity_base_message_points_max",
        "activity_link_bonus_points",
        "activity_attachment_bonus_points",
        "activity_reaction_points",
        "activity_reply_points",
        "leaderboard_default_limit",
        "user_stats_channel_breakdown_limit",
        "user_stats_triggers_limit",
        "leaderboard_bar_chart_length",
    }

    def __init__(self, global_config):
        """
        Initialize guild config manager.

        Args:
            global_config: The global BotConfig instance
        """
        self.global_config = global_config
        self.guild_configs = self._load_guild_configs()

    def _load_guild_configs(self) -> Dict[str, Dict[str, Any]]:
        """Load guild configurations from JSON file."""
        if not GUILD_CONFIG_FILE.exists():
            logger.info("No guild configs file found, starting with empty configs")
            return {}

        try:
            with open(GUILD_CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"Loaded configs for {len(data)} guilds")
            return data
        except Exception as e:
            logger.error(f"Failed to load guild configs: {e}")
            return {}

    def _save_guild_configs(self):
        """Save guild configurations to JSON file."""
        try:
            # Ensure directory exists
            GUILD_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(GUILD_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.guild_configs, f, indent=2)

            logger.info("Guild configs saved successfully")
        except Exception as e:
            logger.error(f"Failed to save guild configs: {e}")
            raise

    def get_guild_config(self, guild_id: int, key: str) -> Any:
        """
        Get a configuration value for a guild.

        Args:
            guild_id: Discord guild ID
            key: Configuration key

        Returns:
            Guild-specific value if set, otherwise global default
        """
        guild_id_str = str(guild_id)

        # Check if key can be overridden per-guild
        if key not in self.GUILD_OVERRIDABLE_SETTINGS:
            # Not a guild-overridable setting, return global value
            return getattr(self.global_config, key, None)

        # Check for guild override
        if guild_id_str in self.guild_configs:
            if key in self.guild_configs[guild_id_str]:
                return self.guild_configs[guild_id_str][key]

        # Fall back to global config
        return getattr(self.global_config, key, None)

    def set_guild_config(self, guild_id: int, key: str, value: Any) -> tuple[bool, str]:
        """
        Set a guild-specific configuration override.

        Args:
            guild_id: Discord guild ID
            key: Configuration key
            value: New value

        Returns:
            (success, error_message) tuple
        """
        # Check if setting can be overridden per-guild
        if key not in self.GUILD_OVERRIDABLE_SETTINGS:
            return False, f"Setting '{key}' cannot be overridden per-guild"

        guild_id_str = str(guild_id)

        # Create guild config if it doesn't exist
        if guild_id_str not in self.guild_configs:
            self.guild_configs[guild_id_str] = {}

        # Set the override
        self.guild_configs[guild_id_str][key] = value

        # Save to disk
        try:
            self._save_guild_configs()
            logger.info(f"Guild {guild_id} set {key} = {value}")
            return True, None
        except Exception as e:
            return False, f"Failed to save: {str(e)}"

    def reset_guild_config(self, guild_id: int, key: str) -> tuple[bool, str]:
        """
        Reset a guild config setting to use global default.

        Args:
            guild_id: Discord guild ID
            key: Configuration key

        Returns:
            (success, error_message) tuple
        """
        guild_id_str = str(guild_id)

        if guild_id_str not in self.guild_configs:
            return False, f"No guild config found for guild {guild_id}"

        if key not in self.guild_configs[guild_id_str]:
            return False, f"Setting '{key}' is not overridden for this guild"

        # Remove the override
        del self.guild_configs[guild_id_str][key]

        # Clean up empty guild configs
        if not self.guild_configs[guild_id_str]:
            del self.guild_configs[guild_id_str]

        # Save to disk
        try:
            self._save_guild_configs()
            logger.info(f"Guild {guild_id} reset {key} to global default")
            return True, None
        except Exception as e:
            return False, f"Failed to save: {str(e)}"

    def get_all_guild_config(self, guild_id: int) -> Dict[str, Any]:
        """
        Get all configuration settings for a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary of all settings (guild overrides + global defaults)
        """
        result = {}

        # Get all guild-overridable settings
        for key in self.GUILD_OVERRIDABLE_SETTINGS:
            result[key] = {
                "value": self.get_guild_config(guild_id, key),
                "is_override": self.is_guild_override(guild_id, key),
                "global_default": getattr(self.global_config, key, None)
            }

        return result

    def is_guild_override(self, guild_id: int, key: str) -> bool:
        """
        Check if a setting is overridden for a guild.

        Args:
            guild_id: Discord guild ID
            key: Configuration key

        Returns:
            True if setting is overridden, False otherwise
        """
        guild_id_str = str(guild_id)
        return (guild_id_str in self.guild_configs and
                key in self.guild_configs[guild_id_str])

    def get_overridable_settings(self) -> list[str]:
        """
        Get list of all settings that can be overridden per-guild.

        Returns:
            List of setting keys
        """
        return sorted(list(self.GUILD_OVERRIDABLE_SETTINGS))
