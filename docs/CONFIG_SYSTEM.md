# Configuration System - Developer Guide

**Status:** Phase 2 Complete ✅ (All Cogs Migrated)
**Version:** 2.0
**Last Updated:** October 2025

---

## Table of Contents

1. [Overview](#overview)
2. [Configuration Scope](#configuration-scope)
3. [Quick Start](#quick-start)
4. [Core Concepts](#core-concepts)
5. [API Reference](#api-reference)
6. [Examples](#examples)
7. [Best Practices](#best-practices)
8. [Migrated Cogs](#migrated-cogs)

---

## Overview

The new configuration system provides a declarative, self-documenting way to define and manage bot configuration with:

- ✅ **Type-safe** config with autocomplete support
- ✅ **Guild-specific overrides** with clear hierarchy
- ✅ **Hot-reload** for instant config updates
- ✅ **Automatic validation** with sensible defaults
- ✅ **Minimal boilerplate** for cog developers
- ✅ **Auto-generated web UI** from schemas
- ✅ **Inline schemas** - Config defined directly in cog files

### Design Principles

1. **Defaults in code, overrides on disk** - Only changed values are saved
2. **Clear hierarchy**: `default → global → guild`
3. **Fail gracefully** - Invalid configs log errors and use defaults
4. **Property access** - Clean, Pythonic API with IDE support
5. **Inline schemas** - No separate config files, schemas live with cogs

---

## Configuration Scope

### What Goes in ConfigManager (Guild-Overridable Settings)

Use the new ConfigManager for **cog-specific settings** that should support per-guild customization:
- Audio playback settings (volume, ducking, etc.)
- TTS voice and rate preferences
- Activity tracking and points
- Leaderboard display options
- Auto-join behavior

✅ **Rule of thumb:** If a guild admin should be able to customize it, use ConfigManager.

### What Stays in bot.config (System-Level Settings)

Keep these in `bot.config.BotConfig` (NOT migrated to ConfigManager):
- **Discord credentials** (token, bot_owner_id)
- **Command prefix** (affects command parsing)
- **Web dashboard** (host, port, enable/disable)
- **Monitoring** (health intervals, data export)
- **File paths** (log_dir, admin_data_dir)
- **Feature flags** (enable_admin_dashboard, enable_speech_recognition)
- **Logging** (log_level)

❌ **Rule of thumb:** If it affects the bot process itself (not guild behavior), keep it in BotConfig.

---

## Quick Start

### 1. Define Your Config Schema

```python
# bot/cogs/audio/soundboard_config.py
from dataclasses import dataclass
from bot.core.config_base import ConfigBase, config_field

@dataclass
class SoundboardConfig(ConfigBase):
    """Soundboard configuration schema."""

    default_volume: float = config_field(
        default=0.5,
        description="Default playback volume for sounds",
        category="Playback",
        guild_override=True,
        min_value=0.0,
        max_value=2.0
    )

    ducking_enabled: bool = config_field(
        default=True,
        description="Auto-reduce volume when users speak",
        category="Playback",
        guild_override=True
    )

    soundboard_dir: str = config_field(
        default="data/soundboard",
        description="Directory containing sound files",
        category="Admin",
        admin_only=True,
        requires_restart=True
    )
```

### 2. Register Schema in Your Cog

```python
# bot/cogs/audio/soundboard.py
from bot.base_cog import BaseCog
from bot.core.config_system import CogConfigSchema
from .soundboard_config import SoundboardConfig

class SoundboardCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)

        # Register config schema
        schema = CogConfigSchema.from_dataclass("Soundboard", SoundboardConfig)
        bot.config_manager.register_schema("Soundboard", schema)
```

### 3. Use Config in Your Code

```python
async def play_sound(self, guild_id: int, sound_name: str):
    # ✅ Recommended: Property access (Option C)
    cfg = self.bot.config_manager.for_guild("Soundboard", guild_id)
    volume = cfg.default_volume
    ducking = cfg.ducking_enabled

    # Alternative: Direct lookup (Option A - for dynamic keys)
    # volume = self.bot.config_manager.get("Soundboard", "default_volume", guild_id)

    # Use the config values
    source = discord.PCMVolumeTransformer(source, volume=volume)
    # ...
```

---

## Core Concepts

### Configuration Hierarchy

Values are resolved in this order (later values override earlier ones):

```
Default (in code) → Global Override → Guild Override
```

**Example:**
```python
# Default in code
default_volume = 0.5

# Global override (in data/config/base_config.json)
{"Soundboard": {"default_volume": 0.7}}

# Guild override (in data/config/guilds/123456789.json)
{"Soundboard": {"default_volume": 0.3}}

# Result:
manager.get("Soundboard", "default_volume")         # → 0.7 (global)
manager.get("Soundboard", "default_volume", 123456) # → 0.3 (guild)
manager.get("Soundboard", "default_volume", 999999) # → 0.7 (global)
```

### File Structure

```
data/config/
├── base_config.json          # Global overrides (nested JSON)
│   └── {"CogName": {"key": value}}
└── guilds/
    ├── 123456789.json        # Guild-specific overrides
    ├── 987654321.json
    └── ...
```

### Guild Override Control

Use `guild_override=True` to allow per-guild customization:

```python
# Can be overridden per-guild
volume: float = config_field(
    default=0.5,
    guild_override=True  # ← Allows guild overrides
)

# Global only (cannot be overridden per-guild)
api_key: str = config_field(
    default="",
    guild_override=False,  # ← Global only
    admin_only=True
)
```

---

## API Reference

### `config_field()` Function

```python
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
) -> Any
```

**Parameters:**
- `default`: Default value for this field
- `description`: Human-readable description (shown in web UI)
- `category`: UI category (`"Playback"`, `"Admin"`, `"TTS"`, `"Stats"`, etc.)
- `guild_override`: Whether this can be overridden per-guild
- `admin_only`: Whether this requires admin permissions to change
- `requires_restart`: Whether changing this requires bot restart
- `min_value`: Minimum value (for numeric types)
- `max_value`: Maximum value (for numeric types)
- `choices`: List of valid choices (for enum-like fields)

### ConfigManager Methods

#### `get(cog_name, key, guild_id=None)`

Get a config value with hierarchy applied.

```python
volume = manager.get("Soundboard", "default_volume", guild_id=123)
```

#### `set(cog_name, key, value, guild_id=None)`

Set a config value with validation.

```python
success, error = manager.set("Soundboard", "default_volume", 0.8, guild_id=123)
if not success:
    print(f"Validation failed: {error}")
```

#### `for_guild(cog_name, guild_id=None)`

Get a config proxy for property access (recommended).

```python
cfg = manager.for_guild("Soundboard", guild_id=123)
volume = cfg.default_volume  # Property access with autocomplete!
ducking = cfg.ducking_enabled
```

#### `save()`

Save all configs to disk.

```python
manager.save()
```

#### `reload(guild_id=None)`

Reload configs from disk (hot-reload).

```python
manager.reload()              # Reload all
manager.reload(guild_id=123)  # Reload specific guild
```

---

## Examples

### Example 1: Simple Config

```python
from dataclasses import dataclass
from bot.core.config_base import ConfigBase, config_field

@dataclass
class MyConfig(ConfigBase):
    """My cog configuration."""

    enabled: bool = config_field(
        default=True,
        description="Enable this feature",
        category="General"
    )

# In cog:
from bot.core.config_system import CogConfigSchema

schema = CogConfigSchema.from_dataclass("MyCog", MyConfig)
bot.config_manager.register_schema("MyCog", schema)

# Use:
cfg = bot.config_manager.for_guild("MyCog")
if cfg.enabled:
    # Do something
    pass
```

### Example 2: Numeric Range

```python
volume: float = config_field(
    default=0.5,
    description="Audio volume (0.0 to 1.0)",
    category="Audio",
    guild_override=True,
    min_value=0.0,
    max_value=1.0
)
```

### Example 3: Choices (Enum)

```python
mode: str = config_field(
    default="auto",
    description="Operation mode",
    category="General",
    choices=["auto", "manual", "disabled"]
)
```

### Example 4: Admin-Only Setting

```python
api_key: str = config_field(
    default="",
    description="API key for external service",
    category="Admin",
    admin_only=True,
    requires_restart=True
)
```

### Example 5: Guild-Specific Override

```python
# Set different volumes for different guilds
manager.set("Soundboard", "default_volume", 0.7)              # Global
manager.set("Soundboard", "default_volume", 0.3, guild_id=123)  # Guild 123
manager.set("Soundboard", "default_volume", 0.9, guild_id=456)  # Guild 456

# Get values
cfg_global = manager.for_guild("Soundboard")
print(cfg_global.default_volume)  # → 0.7

cfg_123 = manager.for_guild("Soundboard", guild_id=123)
print(cfg_123.default_volume)  # → 0.3

cfg_456 = manager.for_guild("Soundboard", guild_id=456)
print(cfg_456.default_volume)  # → 0.9
```

---

## Best Practices

### 1. Use Descriptive Field Names

```python
# ✅ Good
default_volume: float
tts_default_rate: int
auto_join_enabled: bool

# ❌ Bad
vol: float
rate: int
aj: bool
```

### 2. Provide Clear Descriptions

```python
# ✅ Good
description="Default playback volume for sounds (0.0 = muted, 1.0 = normal)"

# ❌ Bad
description="Volume"
```

### 3. Use Appropriate Categories

Standard categories:
- `"Playback"` - Audio/sound playback settings
- `"Admin"` - Administrative settings
- `"TTS"` - Text-to-speech settings
- `"Stats"` - Statistics and tracking
- `"General"` - General settings

### 4. Set Sensible Defaults

Defaults should work "out of the box" for most users.

```python
# ✅ Good defaults
default_volume: float = config_field(default=0.5, ...)  # 50% volume
enabled: bool = config_field(default=True, ...)          # Enabled by default

# ❌ Bad defaults (require configuration)
api_key: str = config_field(default="", ...)  # Empty string won't work
```

### 5. Use Validation Constraints

```python
# Prevent invalid values
volume: float = config_field(
    default=0.5,
    min_value=0.0,    # Can't be negative
    max_value=2.0,    # Cap at 200%
    ...
)

timeout: int = config_field(
    default=30,
    min_value=5,      # At least 5 seconds
    max_value=300,    # At most 5 minutes
    ...
)
```

### 6. Mark Settings That Require Restart

```python
database_url: str = config_field(
    default="sqlite:///bot.db",
    requires_restart=True,  # ← Can't hot-reload this
    ...
)
```

### 7. Prefer Property Access (Option C)

```python
# ✅ Recommended: Property access
cfg = manager.for_guild("MyCog", guild_id)
value = cfg.my_setting  # Autocomplete works!

# ⚠️ Acceptable: Direct lookup (for dynamic keys)
value = manager.get("MyCog", "my_setting", guild_id)
```

---

## Migration Guide

### Migrating from Old Config System

**Before (Old System):**
```python
class MyCog(BaseCog):
    def some_method(self, guild_id):
        volume = self.bot.config.default_volume
        # Global only, no guild overrides
```

**After (New System):**
```python
# 1. Create config schema
@dataclass
class MyConfig(ConfigBase):
    default_volume: float = config_field(
        default=0.5,
        description="Default volume",
        category="Audio",
        guild_override=True
    )

# 2. Register in cog __init__
class MyCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        schema = CogConfigSchema.from_dataclass("MyCog", MyConfig)
        bot.config_manager.register_schema("MyCog", schema)

    def some_method(self, guild_id):
        cfg = self.bot.config_manager.for_guild("MyCog", guild_id)
        volume = cfg.default_volume
        # Now supports guild overrides!
```

---

## Troubleshooting

### Config Value Not Updating

**Problem:** Changed config in web UI but value not updating in code.

**Solution:** Check if the setting has `requires_restart=True`. If so, restart the bot. Otherwise, the config should hot-reload automatically.

### Validation Error

**Problem:** Getting validation errors when setting config.

**Solution:** Check the `min_value`, `max_value`, and `choices` constraints in your config field definition. The error message will tell you what went wrong.

### Guild Override Not Working

**Problem:** Guild-specific config not being applied.

**Solution:** Make sure the field has `guild_override=True` in the config_field() definition.

---

## Testing

Run unit tests:

```bash
python -m unittest tests.test_config_system -v
```

All 17 tests should pass:
- ConfigField validation (types, ranges, choices)
- ConfigManager hierarchy (default → global → guild)
- ConfigManager caching (O(1) lookups)
- ConfigManager save/load (nested JSON format)
- ConfigManager hot-reload
- Config proxy (Option C property access)

---

## Migrated Cogs

**Phase 2 Complete:** All cogs successfully migrated! 🎉

### Summary

**5 Cogs Migrated** with **32 Total Settings**

| Cog | Settings | Category | Guild Override |
|-----|----------|----------|----------------|
| **Soundboard** | 7 | Playback, Admin | ✅ |
| **TTS** | 3 | TTS | ✅ |
| **EdgeTTS** | 2 | TTS | ✅ |
| **Activity** | 18 | Stats | ✅ |
| **Voice** | 2 | Playback | ✅ |

### Detailed Breakdown

#### Soundboard (7 settings)
- `default_volume` - Playback volume (0.0-2.0)
- `ducking_enabled` - Auto-reduce volume when users speak
- `ducking_level` - Volume reduction level (0.0-1.0)
- `ducking_transition_ms` - Smooth transition time (10-500ms)
- `sound_playback_timeout` - Max playback wait time (5-300s)
- `sound_queue_warning_size` - Queue size threshold (10-500)
- `soundboard_dir` - Sound files directory (admin-only, requires restart)

#### TTS (3 settings)
- `tts_default_volume` - TTS playback volume (0.0-2.0)
- `tts_default_rate` - Speech rate in WPM (50-400)
- `tts_max_text_length` - Max message length (50-2000, admin-only)

#### EdgeTTS (2 settings)
- `edge_tts_default_volume` - Edge TTS volume (0.0-2.0)
- `edge_tts_default_voice` - Default voice (e.g., en-US-AriaNeural)

#### Activity (18 settings)

**Voice Tracking (4):**
- `voice_tracking_enabled` - Enable voice time tracking
- `voice_points_per_minute` - Points per minute in voice (0.0-10.0)
- `voice_time_display_mode` - Display mode (ranges/descriptions/points_only)
- `voice_tracking_type` - Tracking type (total/unmuted/speaking)

**Weekly Recap (4):**
- `enable_weekly_recap` - Enable weekly activity recaps
- `weekly_recap_channel_id` - Channel ID for recaps
- `weekly_recap_day` - Day of week (0=Monday, 6=Sunday)
- `weekly_recap_hour` - Hour to post (0-23)

**Activity Points (6):**
- `activity_base_message_points_min` - Min message points (0.0-10.0)
- `activity_base_message_points_max` - Max message points (0.0-10.0)
- `activity_link_bonus_points` - Link bonus (0.0-10.0)
- `activity_attachment_bonus_points` - Attachment bonus (0.0-10.0)
- `activity_reaction_points` - Reaction points (0.0-10.0)
- `activity_reply_points` - Reply points (0.0-10.0)

**Leaderboard (4):**
- `leaderboard_default_limit` - Default entries shown (1-50)
- `user_stats_channel_breakdown_limit` - Channels in breakdown (1-20)
- `user_stats_triggers_limit` - Top triggers shown (1-20)
- `leaderboard_bar_chart_length` - Bar chart length (5-50)

#### Voice (2 settings)
- `auto_join_enabled` - Enable auto-join for voice channels
- `auto_disconnect_timeout` - Leave timeout for empty channels (0-3600s)

### Migration Status

- ✅ **Phase 1:** Core infrastructure complete
- ✅ **Phase 2:** All cogs migrated (5/5)
- ⏭️  **Phase 3:** Old system remains for backwards compatibility
- 🔮 **Future:** Deprecate old `bot.config` for cog settings

---

**Questions?** Check the examples above or refer to the inline documentation in the code.
