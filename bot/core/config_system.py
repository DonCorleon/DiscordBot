"""
New Configuration System - Phase 1

Declarative, self-documenting configuration system where cogs define their own
config schemas using dataclasses. Supports global and per-guild overrides with
hot-reload capability.

Design decisions:
- Nested JSON format: {"CogName": {"key": value}}
- Guild files by ID: 123456789.json
- Hybrid API with preference for property access (Option C)
- Minimal error logging with defaults on validation failure
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

logger = logging.getLogger("discordbot.config_system")

# Config file paths
BASE_CONFIG_FILE = Path("data/config/base_config.json")
GUILDS_CONFIG_DIR = Path("data/config/guilds")


@dataclass
class ConfigField:
    """
    Metadata for a single configuration field.

    Attributes:
        name: Field name (e.g., "default_volume")
        type: Python type (bool, int, float, str, etc.)
        default: Default value
        description: Human-readable description
        category: UI category (e.g., "Playback", "Admin", "TTS")
        guild_override: Whether this setting can be overridden per-guild
        admin_only: Whether this setting requires admin permissions to change
        requires_restart: Whether changing this requires bot restart
        min_value: Minimum value (for numeric types)
        max_value: Maximum value (for numeric types)
        choices: List of valid choices (for enums)
    """
    name: str
    type: Type
    default: Any
    description: str
    category: str
    guild_override: bool = False
    admin_only: bool = False
    requires_restart: bool = False
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    choices: Optional[List[Any]] = None

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate a value against this field's constraints.

        Returns:
            (is_valid, error_message)
        """
        # Type validation
        if not isinstance(value, self.type):
            try:
                # Try to convert
                value = self.type(value)
            except (ValueError, TypeError):
                return False, f"Expected {self.type.__name__}, got {type(value).__name__}"

        # Range validation for numeric types
        if self.min_value is not None and value < self.min_value:
            return False, f"Value {value} below minimum {self.min_value}"

        if self.max_value is not None and value > self.max_value:
            return False, f"Value {value} above maximum {self.max_value}"

        # Choice validation
        if self.choices is not None and value not in self.choices:
            return False, f"Value {value} not in valid choices: {self.choices}"

        return True, None


@dataclass
class CogConfigSchema:
    """
    Configuration schema for a cog.

    Attributes:
        cog_name: Name of the cog (e.g., "Soundboard")
        fields: Dictionary of field_name -> ConfigField
    """
    cog_name: str
    fields: Dict[str, ConfigField] = field(default_factory=dict)

    @classmethod
    def from_dataclass(cls, cog_name: str, config_class: Type) -> "CogConfigSchema":
        """
        Extract schema from a config dataclass.

        Args:
            cog_name: Name of the cog
            config_class: Dataclass with config fields

        Returns:
            CogConfigSchema instance
        """
        from dataclasses import fields as dataclass_fields

        schema = cls(cog_name=cog_name)

        for dc_field in dataclass_fields(config_class):
            # Get metadata from field (added via config_field() helper)
            metadata = dc_field.metadata if dc_field.metadata else {}

            config_field_obj = ConfigField(
                name=dc_field.name,
                type=dc_field.type,
                default=dc_field.default if dc_field.default is not None else dc_field.default_factory(),
                description=metadata.get("description", ""),
                category=metadata.get("category", "General"),
                guild_override=metadata.get("guild_override", False),
                admin_only=metadata.get("admin_only", False),
                requires_restart=metadata.get("requires_restart", False),
                min_value=metadata.get("min_value"),
                max_value=metadata.get("max_value"),
                choices=metadata.get("choices")
            )

            schema.fields[dc_field.name] = config_field_obj

        return schema


class ConfigProxy:
    """
    Proxy object that provides property access to config values.

    Implements Option C: cfg = manager.for_guild(cog, guild); volume = cfg.default_volume
    """

    def __init__(self, manager: "ConfigManager", cog_name: str, guild_id: Optional[int] = None):
        self._manager = manager
        self._cog_name = cog_name
        self._guild_id = guild_id

    def __getattr__(self, name: str) -> Any:
        """Allow property access: cfg.default_volume"""
        if name.startswith("_"):
            # Allow access to internal attributes
            return object.__getattribute__(self, name)

        return self._manager.get(self._cog_name, name, self._guild_id)

    def __setattr__(self, name: str, value: Any):
        """Allow property setting: cfg.default_volume = 0.5"""
        if name.startswith("_"):
            # Set internal attributes normally
            object.__setattr__(self, name, value)
        else:
            success, error = self._manager.set(self._cog_name, name, value, self._guild_id)
            if not success:
                raise ValueError(f"Failed to set {name}: {error}")


class ConfigManager:
    """
    Central configuration manager.

    Manages config schemas, global overrides, guild overrides, and provides
    a unified API for config access with hierarchy: default -> global -> guild
    """

    def __init__(self):
        """Initialize the config manager."""
        self.schemas: Dict[str, CogConfigSchema] = {}
        self.global_overrides: Dict[str, Dict[str, Any]] = {}  # {cog_name: {key: value}}
        self.guild_overrides: Dict[int, Dict[str, Dict[str, Any]]] = {}  # {guild_id: {cog_name: {key: value}}}
        self._cache: Dict[Tuple[str, str, Optional[int]], Any] = {}  # (cog, key, guild) -> value

        # Load existing configs
        self._load_global_config()
        self._load_guild_configs()

    def register_schema(self, cog_name: str, schema: CogConfigSchema):
        """
        Register a cog's config schema.

        Args:
            cog_name: Name of the cog
            schema: CogConfigSchema instance
        """
        self.schemas[cog_name] = schema
        logger.info(f"Registered config schema for {cog_name} ({len(schema.fields)} fields)")

    def get(self, cog_name: str, key: str, guild_id: Optional[int] = None) -> Any:
        """
        Get config value with hierarchy: default -> global -> guild.

        Args:
            cog_name: Name of the cog
            key: Config key
            guild_id: Optional guild ID for guild-specific override

        Returns:
            Config value (with hierarchy applied)
        """
        # Check cache first (O(1) lookup)
        cache_key = (cog_name, key, guild_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get schema
        if cog_name not in self.schemas:
            logger.error(f"ERROR: Invalid config cog '{cog_name}', using None")
            return None

        schema = self.schemas[cog_name]
        if key not in schema.fields:
            logger.error(f"ERROR: Invalid config '{key}' for cog '{cog_name}', using None")
            return None

        field_meta = schema.fields[key]

        # Hierarchy: default -> global -> guild
        value = field_meta.default

        # Apply global override
        if cog_name in self.global_overrides and key in self.global_overrides[cog_name]:
            value = self.global_overrides[cog_name][key]

        # Apply guild override (if applicable)
        if guild_id is not None and field_meta.guild_override:
            if guild_id in self.guild_overrides:
                if cog_name in self.guild_overrides[guild_id]:
                    if key in self.guild_overrides[guild_id][cog_name]:
                        value = self.guild_overrides[guild_id][cog_name][key]

        # Cache the result
        self._cache[cache_key] = value

        return value

    def set(self, cog_name: str, key: str, value: Any, guild_id: Optional[int] = None) -> Tuple[bool, Optional[str]]:
        """
        Set config value with validation.

        Args:
            cog_name: Name of the cog
            key: Config key
            value: New value
            guild_id: Optional guild ID for guild-specific override

        Returns:
            (success, error_message)
        """
        # Get schema
        if cog_name not in self.schemas:
            return False, f"Unknown cog: {cog_name}"

        schema = self.schemas[cog_name]
        if key not in schema.fields:
            return False, f"Unknown config key: {key}"

        field_meta = schema.fields[key]

        # Validate value
        is_valid, error = field_meta.validate(value)
        if not is_valid:
            logger.error(f"ERROR: Invalid config '{key}': {value} ({error}), using default: {field_meta.default}")
            return False, error

        # Convert value to correct type if needed
        try:
            value = field_meta.type(value)
        except (ValueError, TypeError) as e:
            logger.error(f"ERROR: Invalid config '{key}': {value} ({e}), using default: {field_meta.default}")
            return False, str(e)

        # Set value
        if guild_id is None:
            # Global override
            if cog_name not in self.global_overrides:
                self.global_overrides[cog_name] = {}
            self.global_overrides[cog_name][key] = value
        else:
            # Guild override
            if not field_meta.guild_override:
                return False, f"Setting '{key}' does not support guild overrides"

            if guild_id not in self.guild_overrides:
                self.guild_overrides[guild_id] = {}
            if cog_name not in self.guild_overrides[guild_id]:
                self.guild_overrides[guild_id][cog_name] = {}
            self.guild_overrides[guild_id][cog_name][key] = value

        # Invalidate cache
        self._invalidate_cache(cog_name, key, guild_id)

        return True, None

    def for_guild(self, cog_name: str, guild_id: Optional[int] = None) -> ConfigProxy:
        """
        Get a config proxy for property access (Option C).

        Example:
            cfg = manager.for_guild("Soundboard", guild_id)
            volume = cfg.default_volume  # Property access with autocomplete

        Args:
            cog_name: Name of the cog
            guild_id: Optional guild ID

        Returns:
            ConfigProxy instance
        """
        return ConfigProxy(self, cog_name, guild_id)

    def get_schema(self, cog_name: str) -> Optional[CogConfigSchema]:
        """Get the config schema for a cog."""
        return self.schemas.get(cog_name)

    def requires_restart(self, cog_name: str, key: str) -> bool:
        """Check if a setting requires restart."""
        if cog_name not in self.schemas:
            return False
        schema = self.schemas[cog_name]
        if key not in schema.fields:
            return False
        return schema.fields[key].requires_restart

    def save(self):
        """Save all configs to disk (nested JSON format)."""
        try:
            # Save global config
            self._save_global_config()

            # Save guild configs
            self._save_guild_configs()

            logger.info("Configuration saved successfully")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}", exc_info=True)
            raise

    def reload(self, guild_id: Optional[int] = None):
        """
        Reload configs from disk.

        Args:
            guild_id: If specified, reload only that guild's config
        """
        if guild_id is None:
            # Reload all
            self._load_global_config()
            self._load_guild_configs()
            self._cache.clear()
            logger.info("Reloaded all configurations")
        else:
            # Reload specific guild
            self._load_guild_config(guild_id)
            # Invalidate cache for this guild
            self._cache = {k: v for k, v in self._cache.items() if k[2] != guild_id}
            logger.info(f"Reloaded configuration for guild {guild_id}")

    def _load_global_config(self):
        """Load global config from base_config.json."""
        if not BASE_CONFIG_FILE.exists():
            logger.info("No base config file found, using defaults")
            self.global_overrides = {}
            return

        try:
            with open(BASE_CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.global_overrides = json.load(f)
            logger.info(f"Loaded global config ({len(self.global_overrides)} cogs)")
        except Exception as e:
            logger.error(f"Failed to load global config: {e}")
            self.global_overrides = {}

    def _save_global_config(self):
        """Save global config to base_config.json."""
        # Ensure directory exists
        BASE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(BASE_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.global_overrides, f, indent=2, ensure_ascii=False)

    def _load_guild_configs(self):
        """Load all guild configs from guilds/ directory."""
        if not GUILDS_CONFIG_DIR.exists():
            logger.info("No guild configs directory found")
            self.guild_overrides = {}
            return

        self.guild_overrides = {}

        for guild_file in GUILDS_CONFIG_DIR.glob("*.json"):
            try:
                guild_id = int(guild_file.stem)
                self._load_guild_config(guild_id)
            except ValueError:
                logger.warning(f"Invalid guild config filename: {guild_file.name}")

        logger.info(f"Loaded {len(self.guild_overrides)} guild configs")

    def _load_guild_config(self, guild_id: int):
        """Load a specific guild's config."""
        guild_file = GUILDS_CONFIG_DIR / f"{guild_id}.json"

        if not guild_file.exists():
            if guild_id in self.guild_overrides:
                del self.guild_overrides[guild_id]
            return

        try:
            with open(guild_file, 'r', encoding='utf-8') as f:
                self.guild_overrides[guild_id] = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load guild config {guild_id}: {e}")

    def _save_guild_configs(self):
        """Save all guild configs to guilds/ directory."""
        # Ensure directory exists
        GUILDS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        for guild_id, config in self.guild_overrides.items():
            guild_file = GUILDS_CONFIG_DIR / f"{guild_id}.json"

            # Only save if there are actual overrides
            if config:
                with open(guild_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
            else:
                # Delete file if no overrides
                if guild_file.exists():
                    guild_file.unlink()

    def _invalidate_cache(self, cog_name: str, key: str, guild_id: Optional[int]):
        """Invalidate cache entries for a specific key."""
        # Invalidate global entry
        cache_key = (cog_name, key, None)
        if cache_key in self._cache:
            del self._cache[cache_key]

        # Invalidate guild entry if specified
        if guild_id is not None:
            cache_key = (cog_name, key, guild_id)
            if cache_key in self._cache:
                del self._cache[cache_key]
