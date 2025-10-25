"""
Configuration Management API endpoints.
Provides endpoints for viewing and updating bot configuration with validation.
"""

import logging
from typing import Dict, Any, Union
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

logger = logging.getLogger("discordbot.web.config")

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

# Will be set by main app
config_manager = None
guild_config_manager = None
bot_instance = None


def set_config_manager(manager):
    """Set the config manager instance."""
    global config_manager
    config_manager = manager
    logger.info("Config manager registered with API")


def set_guild_config_manager(manager):
    """Set the guild config manager instance."""
    global guild_config_manager
    guild_config_manager = manager
    logger.info("Guild config manager registered with API")


def set_bot_instance(bot):
    """Set the bot instance."""
    global bot_instance
    bot_instance = bot
    logger.info("Bot instance registered with config API")


class ConfigUpdate(BaseModel):
    """Model for configuration update requests."""
    key: str
    value: Any


@router.get("/")
async def get_all_config():
    """
    Get all configuration settings with metadata.

    Returns settings grouped by category with validation rules and current values.
    """
    # TODO: Replace with new ConfigManager in Phase 1
    # For now, return a basic structure using guild_config_manager
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        from bot.core.guild_config_manager import GUILD_OVERRIDABLE_SETTINGS

        # Build settings from GUILD_OVERRIDABLE_SETTINGS
        categorized = {}
        for key, metadata in GUILD_OVERRIDABLE_SETTINGS.items():
            category = metadata.get("category", "General")
            if category not in categorized:
                categorized[category] = {}

            categorized[category][key] = {
                "key": key,
                "value": guild_config_manager.config_defaults.get(key),
                "type": metadata.get("type", "string"),
                "description": metadata.get("description", ""),
                "category": category,
                "guild_override": True,
                "admin_only": metadata.get("admin_only", False),
                "min": metadata.get("min"),
                "max": metadata.get("max"),
                "options": metadata.get("options")
            }

        return {
            "categories": categorized,
            "total_settings": sum(len(settings) for settings in categorized.values())
        }

    except Exception as e:
        logger.error(f"Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}")
async def get_config_setting(key: str):
    """Get a specific configuration setting."""
    # TODO: Replace with new ConfigManager in Phase 1
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        from bot.core.guild_config_manager import GUILD_OVERRIDABLE_SETTINGS

        if key not in GUILD_OVERRIDABLE_SETTINGS:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

        metadata = GUILD_OVERRIDABLE_SETTINGS[key]
        return {
            "key": key,
            "value": guild_config_manager.config_defaults.get(key),
            "type": metadata.get("type", "string"),
            "description": metadata.get("description", ""),
            "category": metadata.get("category", "General"),
            "guild_override": True,
            "admin_only": metadata.get("admin_only", False),
            "min": metadata.get("min"),
            "max": metadata.get("max"),
            "options": metadata.get("options")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/")
async def update_config_setting(request: Request):
    """
    Update a configuration setting.

    Validates the new value and applies it. Returns whether a restart is required.
    """
    # TODO: Implement with new ConfigManager in Phase 1
    # For now, return not implemented
    raise HTTPException(
        status_code=501,
        detail="Global config updates not implemented yet. Use per-guild config endpoints instead."
    )


@router.post("/backup")
async def create_config_backup():
    """Create a backup of the current configuration."""
    # TODO: Implement with new ConfigManager in Phase 1
    raise HTTPException(
        status_code=501,
        detail="Config backup not implemented yet. Will be available in Phase 1."
    )


@router.post("/restore")
async def restore_config_backup():
    """Restore configuration from the most recent backup."""
    # TODO: Implement with new ConfigManager in Phase 1
    raise HTTPException(
        status_code=501,
        detail="Config restore not implemented yet. Will be available in Phase 1."
    )


@router.post("/restart")
async def request_bot_restart():
    """
    Request a bot restart (for settings that require it).

    Note: This endpoint returns success but doesn't actually restart the bot.
    The user must manually restart the bot process.
    """
    return {
        "success": True,
        "message": "Please manually restart the bot to apply changes",
        "note": "Automatic bot restart is not implemented for safety"
    }


# ============================================================================
# Guild-Specific Configuration Endpoints
# ============================================================================

@router.get("/guild/{guild_id}")
async def get_guild_config(guild_id: int):
    """
    Get all configuration settings for a specific guild.

    Returns both guild-specific overrides and global defaults.
    """
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        settings = guild_config_manager.get_all_guild_config(guild_id)

        # Group by category matching user's specification
        categories = {
            "Playback": [
                "default_volume", "ducking_enabled", "ducking_level",
                "ducking_transition_ms", "auto_join_enabled", "auto_join_timeout",
                "sound_playback_timeout", "sound_queue_warning_size"
            ],
            "TTS": [
                "tts_default_volume", "tts_default_rate", "tts_max_text_length",
                "edge_tts_default_volume", "edge_tts_default_voice"
            ],
            "Stats": [
                "voice_tracking_enabled", "voice_points_per_minute",
                "voice_time_display_mode", "voice_tracking_type",
                "enable_weekly_recap", "weekly_recap_channel_id",
                "weekly_recap_day", "weekly_recap_hour",
                "activity_base_message_points_min", "activity_base_message_points_max",
                "activity_link_bonus_points", "activity_attachment_bonus_points",
                "activity_reaction_points", "activity_reply_points",
                "leaderboard_default_limit", "user_stats_channel_breakdown_limit",
                "user_stats_triggers_limit", "leaderboard_bar_chart_length"
            ]
        }

        categorized = {}
        for category, keys in categories.items():
            categorized[category] = {}
            for key in keys:
                if key in settings:
                    categorized[category][key] = settings[key]

        return {
            "guild_id": guild_id,
            "categories": categorized,
            "total_settings": len(settings)
        }

    except Exception as e:
        logger.error(f"Error getting guild config for {guild_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guild/{guild_id}/{key}")
async def get_guild_config_setting(guild_id: int, key: str):
    """Get a specific configuration setting for a guild."""
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        value = guild_config_manager.get_guild_config(guild_id, key)
        is_override = guild_config_manager.is_guild_override(guild_id, key)

        all_settings = guild_config_manager.get_all_guild_config(guild_id)
        if key not in all_settings:
            raise HTTPException(status_code=404, detail=f"Setting '{key}' not found or not overridable")

        return {
            "key": key,
            "value": value,
            "is_override": is_override,
            "global_default": all_settings[key]["global_default"]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting guild setting {guild_id}/{key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/guild/{guild_id}")
async def update_guild_config_setting(guild_id: int, request: Request):
    """
    Update a guild-specific configuration setting.

    Creates an override for the specified guild.
    """
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        body = await request.json()
        logger.info(f"Received guild config update: guild_id={guild_id}, body={body}")

        if body is None or "key" not in body or "value" not in body:
            raise HTTPException(status_code=400, detail="Missing 'key' or 'value' in request body")

        key = body["key"]
        value = body["value"]

        # Validate through global config manager if available
        if config_manager:
            valid, error = config_manager.validate_setting(key, value)
            if not valid:
                raise HTTPException(status_code=400, detail=f"Validation failed: {error}")

        # Set guild config
        success, error = guild_config_manager.set_guild_config(guild_id, key, value)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "guild_id": guild_id,
            "key": key,
            "value": value,
            "message": f"Successfully updated {key} for guild {guild_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating guild setting: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/guild/{guild_id}/{key}")
async def reset_guild_config_setting(guild_id: int, key: str):
    """
    Reset a guild-specific configuration setting to global default.

    Removes the guild override for this setting.
    """
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        success, error = guild_config_manager.reset_guild_config(guild_id, key)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        # Get new value after reset
        new_value = guild_config_manager.get_guild_config(guild_id, key)

        return {
            "success": True,
            "guild_id": guild_id,
            "key": key,
            "new_value": new_value,
            "message": f"Reset {key} to global default for guild {guild_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting guild setting: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds/overridable")
async def get_overridable_settings():
    """Get list of all settings that can be overridden per-guild."""
    if not guild_config_manager:
        raise HTTPException(status_code=503, detail="Guild config manager not initialized")

    try:
        settings = guild_config_manager.get_overridable_settings()
        return {
            "settings": settings,
            "count": len(settings)
        }

    except Exception as e:
        logger.error(f"Error getting overridable settings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guilds/list")
async def get_guilds_list():
    """Get list of all guilds the bot is in."""
    if not bot_instance:
        raise HTTPException(status_code=503, detail="Bot instance not initialized")

    try:
        guilds = []
        for guild in bot_instance.guilds:
            guilds.append({
                "id": str(guild.id),
                "name": guild.name,
                "member_count": guild.member_count,
                "icon": str(guild.icon.url) if guild.icon else None
            })

        return {
            "guilds": guilds,
            "count": len(guilds)
        }

    except Exception as e:
        logger.error(f"Error getting guilds list: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
