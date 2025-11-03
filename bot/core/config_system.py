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
import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type, Union

logger = logging.getLogger("discordbot.config_system")

# Import migration system
try:
    from bot.core.config_migrations import migrate_config
    MIGRATIONS_AVAILABLE = True
except ImportError:
    logger.warning("Config migrations module not available")
    MIGRATIONS_AVAILABLE = False

# Config file paths
BASE_CONFIG_FILE = Path("data/config/base_config.json")
GUILDS_CONFIG_DIR = Path("data/config/guilds")


def validate_ip_address(value: str) -> Tuple[bool, str]:
    """
    Validate IP address format (IPv4 or IPv6).

    Returns:
        (is_valid, error_message)
    """
    try:
        ipaddress.ip_address(value)
        return True, ""
    except ValueError as e:
        return False, f"Invalid IP address: {e}"


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
        validator: Custom validation function (value -> (bool, error_msg))
        is_large_int: Whether this is a large integer (e.g., Discord ID) that should be serialized as string for JS
        env_only: Whether this field should ONLY be read from environment variables (never saved to JSON)
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
    validator: Optional[Callable[[Any], Tuple[bool, str]]] = None
    is_large_int: bool = False
    env_only: bool = False

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

        # Custom validator
        if self.validator is not None:
            is_valid, error_msg = self.validator(value)
            if not is_valid:
                return False, error_msg

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
                choices=metadata.get("choices"),
                validator=metadata.get("validator"),
                is_large_int=metadata.get("is_large_int", False),
                env_only=metadata.get("env_only", False)
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

        # Hierarchy: default -> global override -> environment variable -> guild override
        value = field_meta.default

        # Apply global override (from JSON file)
        if cog_name in self.global_overrides and key in self.global_overrides[cog_name]:
            value = self.global_overrides[cog_name][key]

        # Apply environment variable override (if exists)
        # Special case mappings for legacy env var names
        env_var_mappings = {
            ("System", "token"): "DISCORD_TOKEN",
            ("System", "bot_owner_id"): "BOT_OWNER",
            ("System", "command_prefix"): "COMMAND_PREFIX",
            ("System", "max_history"): "MAX_HISTORY",
            ("System", "log_level"): "LOG_LEVEL",
            ("System", "enable_web_dashboard"): "ENABLE_WEB_DASHBOARD",
            ("System", "web_host"): "WEB_HOST",
            ("System", "web_port"): "WEB_PORT",
            ("Soundboard", "default_volume"): "DEFAULT_VOLUME",
            ("Activity", "voice_tracking_enabled"): "VOICE_TRACKING_ENABLED",
            ("Activity", "voice_points_per_minute"): "VOICE_POINTS_PER_MINUTE",
            ("Activity", "voice_time_display_mode"): "VOICE_TIME_DISPLAY_MODE",
            ("Activity", "voice_tracking_type"): "VOICE_TRACKING_TYPE",
        }
        env_var_name = env_var_mappings.get((cog_name, key), f"{cog_name.upper()}_{key.upper()}")
        env_value = os.getenv(env_var_name)
        if env_value is not None:
            # Convert env string to appropriate type
            try:
                if field_meta.type == bool:
                    value = env_value.lower() in ('true', '1', 'yes', 'on')
                elif field_meta.type == int:
                    value = int(env_value)
                elif field_meta.type == float:
                    value = float(env_value)
                elif field_meta.type == list:
                    value = [v.strip() for v in env_value.split(',') if v.strip()]
                else:
                    value = env_value
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse env var {env_var_name}={env_value}: {e}")

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

        # Reject changes to env-only fields
        if field_meta.env_only:
            return False, f"Field '{key}' can only be set via environment variables (.env file)"

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
                config_data = json.load(f)

            # Apply migrations if available
            if MIGRATIONS_AVAILABLE:
                # Flatten config for migration (Voice.auto_join_timeout format)
                flat_config = self._flatten_config(config_data)
                migrated_flat, applied = migrate_config(flat_config)

                if applied:
                    logger.info(f"Applied {len(applied)} config migrations to global config:")
                    for migration in applied:
                        logger.info(f"  - {migration}")

                    # Unflatten back to nested format
                    config_data = self._unflatten_config(migrated_flat)

                    # Save migrated config
                    with open(BASE_CONFIG_FILE, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)

            self.global_overrides = config_data
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
                config_data = json.load(f)

            # Apply migrations if available
            if MIGRATIONS_AVAILABLE:
                # Flatten config for migration (Voice.auto_join_timeout format)
                flat_config = self._flatten_config(config_data)
                migrated_flat, applied = migrate_config(flat_config)

                if applied:
                    logger.info(f"Applied {len(applied)} config migrations to guild {guild_id}:")
                    for migration in applied:
                        logger.info(f"  - {migration}")

                    # Unflatten back to nested format
                    config_data = self._unflatten_config(migrated_flat)

                    # Save migrated config
                    with open(guild_file, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, indent=2, ensure_ascii=False)

            self.guild_overrides[guild_id] = config_data
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

    def _flatten_config(self, nested_config: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Flatten nested config to migration format.

        Input:  {"Voice": {"auto_join_timeout": 300}}
        Output: {"Voice.auto_join_timeout": 300}
        """
        flat = {}
        for cog_name, cog_config in nested_config.items():
            if isinstance(cog_config, dict):
                for key, value in cog_config.items():
                    flat[f"{cog_name}.{key}"] = value
        return flat

    def _unflatten_config(self, flat_config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Unflatten config from migration format back to nested.

        Input:  {"Voice.auto_disconnect_timeout": 300}
        Output: {"Voice": {"auto_disconnect_timeout": 300}}
        """
        nested = {}
        for flat_key, value in flat_config.items():
            if "." in flat_key:
                cog_name, key = flat_key.split(".", 1)
                if cog_name not in nested:
                    nested[cog_name] = {}
                nested[cog_name][key] = value
        return nested
