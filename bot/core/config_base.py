"""
Configuration Base Classes and Helpers

Provides helper functions and base classes for cog developers to define
configuration schemas with minimal boilerplate.

Example usage:
    @dataclass
    class SoundboardConfig(ConfigBase):
        default_volume: float = config_field(
            default=0.5,
            description="Default playback volume",
            category="Playback",
            guild_override=True,
            min_value=0.0,
            max_value=2.0
        )
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type, Union


def config_field(
    default: Any,
    description: str,
    category: str = "General",
    guild_override: bool = False,
    admin_only: bool = False,
    requires_restart: bool = False,
    min_value: Optional[Union[int, float]] = None,
    max_value: Optional[Union[int, float]] = None,
    choices: Optional[List[Any]] = None,
) -> Any:
    """
    Helper function to define a config field with metadata.

    This function provides a clean, minimal-boilerplate way for cog developers
    to define configuration fields with all necessary metadata.

    Args:
        default: Default value for this field
        description: Human-readable description
        category: UI category (e.g., "Playback", "Admin", "TTS", "Stats")
        guild_override: Whether this setting can be overridden per-guild
        admin_only: Whether this setting requires admin permissions
        requires_restart: Whether changing this requires bot restart
        min_value: Minimum value (for numeric types)
        max_value: Maximum value (for numeric types)
        choices: List of valid choices (for enum-like fields)

    Returns:
        A dataclass field with metadata attached

    Example:
        >>> @dataclass
        >>> class MyConfig(ConfigBase):
        >>>     volume: float = config_field(
        >>>         default=0.5,
        >>>         description="Audio volume",
        >>>         category="Playback",
        >>>         guild_override=True,
        >>>         min_value=0.0,
        >>>         max_value=1.0
        >>>     )
    """
    metadata = {
        "description": description,
        "category": category,
        "guild_override": guild_override,
        "admin_only": admin_only,
        "requires_restart": requires_restart,
        "min_value": min_value,
        "max_value": max_value,
        "choices": choices,
    }

    return field(default=default, metadata=metadata)


@dataclass
class ConfigBase:
    """
    Base class for cog configuration schemas.

    Cog developers should inherit from this class and define their config
    fields using the `config_field()` helper function.

    The ConfigManager will automatically discover and register these schemas.

    Example:
        >>> from dataclasses import dataclass
        >>> from bot.core.config_base import ConfigBase, config_field
        >>>
        >>> @dataclass
        >>> class SoundboardConfig(ConfigBase):
        >>>     '''Soundboard configuration schema'''
        >>>
        >>>     default_volume: float = config_field(
        >>>         default=0.5,
        >>>         description="Default playback volume for sounds",
        >>>         category="Playback",
        >>>         guild_override=True,
        >>>         min_value=0.0,
        >>>         max_value=2.0
        >>>     )
        >>>
        >>>     ducking_enabled: bool = config_field(
        >>>         default=True,
        >>>         description="Auto-reduce volume when users speak",
        >>>         category="Playback",
        >>>         guild_override=True
        >>>     )
        >>>
        >>>     soundboard_dir: str = config_field(
        >>>         default="data/soundboard",
        >>>         description="Directory containing sound files",
        >>>         category="Admin",
        >>>         admin_only=True,
        >>>         requires_restart=True
        >>>     )
        >>>
        >>> # In the cog:
        >>> class SoundboardCog(BaseCog):
        >>>     def __init__(self, bot):
        >>>         super().__init__(bot)
        >>>         # Register config schema
        >>>         schema = CogConfigSchema.from_dataclass("Soundboard", SoundboardConfig)
        >>>         bot.config_manager.register_schema("Soundboard", schema)
        >>>
        >>>     async def play_sound(self, guild_id: int):
        >>>         # Option C: Property access (recommended)
        >>>         cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
        >>>         volume = cfg.default_volume
        >>>         ducking = cfg.ducking_enabled
        >>>
        >>>         # Option A: Direct lookup (for dynamic keys)
        >>>         # volume = self.bot.config_manager.get("Soundboard", "default_volume", guild_id)
    """

    def __init__(self, config_manager: "ConfigManager", cog_name: str):
        """
        Initialize config for a cog.

        Args:
            config_manager: The global ConfigManager instance
            cog_name: Name of the cog
        """
        from bot.core.config_system import CogConfigSchema

        # Register schema
        schema = CogConfigSchema.from_dataclass(cog_name, self.__class__)
        config_manager.register_schema(cog_name, schema)

        self._config_manager = config_manager
        self._cog_name = cog_name

    def get(self, key: str, guild_id: Optional[int] = None) -> Any:
        """
        Get a config value (Option A - for dynamic keys).

        Args:
            key: Config key
            guild_id: Optional guild ID

        Returns:
            Config value
        """
        return self._config_manager.get(self._cog_name, key, guild_id)

    def set(self, key: str, value: Any, guild_id: Optional[int] = None) -> tuple[bool, Optional[str]]:
        """
        Set a config value.

        Args:
            key: Config key
            value: New value
            guild_id: Optional guild ID

        Returns:
            (success, error_message)
        """
        return self._config_manager.set(self._cog_name, key, value, guild_id)

    def for_guild(self, guild_id: Optional[int] = None) -> "ConfigProxy":
        """
        Get a config proxy for property access (Option C - recommended).

        Example:
            cfg = self.config.for_guild(guild_id)
            volume = cfg.default_volume  # Property access with autocomplete

        Args:
            guild_id: Optional guild ID

        Returns:
            ConfigProxy instance
        """
        return self._config_manager.for_guild(self._cog_name, guild_id)


# Type hint imports for documentation
if __name__ != "__main__":
    from bot.core.config_system import ConfigManager, ConfigProxy
