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


def safe_serialize_value(value: Any, is_large_int: bool = False) -> Any:
    """
    Serialize config values safely for JSON/JavaScript.
    Converts large integers (like Discord IDs) to strings to prevent precision loss.

    Args:
        value: The value to serialize
        is_large_int: Whether this is marked as a large int field (Discord IDs, etc.)
    """
    # Convert large integers to strings if flagged or if value is very large
    if isinstance(value, int) and (is_large_int or abs(value) > 9007199254740991):
        return str(value)
    return value

router = APIRouter(prefix="/api/v1/config", tags=["Configuration"])

# Will be set by main app
config_manager = None
bot_instance = None


def set_config_manager(manager):
    """Set the unified config manager instance."""
    global config_manager
    config_manager = manager
    logger.info("Unified config manager registered with API")


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
    Uses the new ConfigManager (Phase 2).
    """
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        # Get all registered schemas from ConfigManager
        # Build hierarchical category structure: {"Admin": {"Web": {...}, "System": {...}}}
        categorized = {}

        for cog_name, schema in config_manager.schemas.items():
            for field_name, field_meta in schema.fields.items():
                category = field_meta.category

                # Parse hierarchical category (e.g., "Admin/Web" → ["Admin", "Web"])
                category_parts = category.split("/") if "/" in category else [category]

                # Navigate/create nested structure
                current_level = categorized
                for i, part in enumerate(category_parts):
                    if i == len(category_parts) - 1:
                        # Last part - this is where settings go
                        if part not in current_level:
                            current_level[part] = {}
                    else:
                        # Intermediate part - create nested dict if needed
                        if part not in current_level:
                            current_level[part] = {}
                        elif not isinstance(current_level[part], dict):
                            # Convert to dict with _settings key if it was a settings dict
                            current_level[part] = {"_settings": current_level[part]}
                        current_level = current_level[part]

                # Get current value (global default)
                current_value = config_manager.get(cog_name, field_name)

                # Map Python types to API types
                type_name = "string"
                if field_meta.type == bool:
                    type_name = "boolean"
                elif field_meta.type in (int, float):
                    type_name = "number"

                setting_key = f"{cog_name}.{field_name}"

                # Add setting to the correct nested location
                target_category = categorized
                for part in category_parts[:-1]:
                    target_category = target_category[part]

                # Add to the final category level
                final_category = category_parts[-1]
                target_category[final_category][setting_key] = {
                    "key": setting_key,
                    "cog": cog_name,
                    "field": field_name,
                    "value": safe_serialize_value(current_value, field_meta.is_large_int),
                    "default": safe_serialize_value(field_meta.default, field_meta.is_large_int),
                    "type": type_name,
                    "description": field_meta.description,
                    "category": category,
                    "guild_override": field_meta.guild_override,
                    "admin_only": field_meta.admin_only,
                    "requires_restart": field_meta.requires_restart,
                    "min": field_meta.min_value,
                    "max": field_meta.max_value,
                    "choices": field_meta.choices,
                    "is_large_int": field_meta.is_large_int
                }

        # Count settings recursively in nested structure
        def count_settings(obj):
            count = 0
            for key, value in obj.items():
                if isinstance(value, dict):
                    # Check if this is a setting (has 'key' field) or a category
                    if 'key' in value:
                        count += 1
                    else:
                        # It's a category, recurse
                        count += count_settings(value)
            return count

        return {
            "categories": categorized,
            "total_settings": count_settings(categorized)
        }

    except Exception as e:
        logger.error(f"Error getting config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{key}")
async def get_config_setting(key: str):
    """Get a specific configuration setting (global)."""
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        # Parse key: "CogName.field_name"
        if "." not in key:
            raise HTTPException(status_code=400, detail=f"Invalid key format. Expected 'CogName.field_name', got '{key}'")

        cog_name, field_name = key.split(".", 1)

        # Validate the setting exists
        if cog_name not in config_manager.schemas:
            raise HTTPException(status_code=404, detail=f"Cog '{cog_name}' not found")

        schema = config_manager.schemas[cog_name]
        if field_name not in schema.fields:
            raise HTTPException(status_code=404, detail=f"Setting '{field_name}' not found in cog '{cog_name}'")

        field_meta = schema.fields[field_name]

        # Get current global value
        current_value = config_manager.get(cog_name, field_name)

        # Map Python types to API types
        type_name = "string"
        if field_meta.type == bool:
            type_name = "boolean"
        elif field_meta.type in (int, float):
            type_name = "number"

        return {
            "key": key,
            "cog": cog_name,
            "field": field_name,
            "value": current_value,
            "default": field_meta.default,
            "type": type_name,
            "description": field_meta.description,
            "category": field_meta.category,
            "guild_override": field_meta.guild_override,
            "admin_only": field_meta.admin_only,
            "requires_restart": field_meta.requires_restart,
            "min": field_meta.min_value,
            "max": field_meta.max_value,
            "choices": field_meta.choices
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/")
async def update_config_setting(request: Request):
    """
    Update a global configuration setting.

    Validates the new value and applies it. Returns whether a restart is required.
    """
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        body = await request.json()
        logger.info(f"Received global config update: body={body}")

        if body is None or "key" not in body or "value" not in body:
            raise HTTPException(status_code=400, detail="Missing 'key' or 'value' in request body")

        full_key = body["key"]  # e.g., "Soundboard.default_volume"
        value = body["value"]

        # Parse the key into cog_name and field_name
        if "." not in full_key:
            raise HTTPException(status_code=400, detail=f"Invalid key format. Expected 'CogName.field_name', got '{full_key}'")

        cog_name, field_name = full_key.split(".", 1)

        # Validate the setting exists
        if cog_name not in config_manager.schemas:
            raise HTTPException(status_code=404, detail=f"Cog '{cog_name}' not found")

        schema = config_manager.schemas[cog_name]
        if field_name not in schema.fields:
            raise HTTPException(status_code=404, detail=f"Setting '{field_name}' not found in cog '{cog_name}'")

        field_meta = schema.fields[field_name]

        # Check if setting requires restart
        requires_restart = field_meta.requires_restart

        # Get old value before changing
        old_value = config_manager.get(cog_name, field_name)

        # Convert string back to int if needed (for large Discord IDs and other large ints)
        if field_meta.type == int and isinstance(value, str) and field_meta.is_large_int:
            try:
                value = int(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid integer value: {value}")

        # Set the value (validates automatically)
        success, error = config_manager.set(cog_name, field_name, value)

        if not success:
            raise HTTPException(status_code=400, detail=f"Validation failed: {error}")

        # Log the change
        logger.info(f"Config changed via web UI: {full_key} | old: {old_value} -> new: {value}")

        # Save to disk
        config_manager.save()

        return {
            "success": True,
            "key": full_key,
            "cog": cog_name,
            "field": field_name,
            "value": value,
            "old_value": old_value,
            "requires_restart": requires_restart,
            "message": f"Successfully updated {full_key}" + (" (restart required)" if requires_restart else "")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating global config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


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
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        # Get all settings from all registered schemas
        # Build hierarchical category structure
        categorized = {}
        total_settings = 0

        for cog_name, schema in config_manager.schemas.items():
            for field_name, field_meta in schema.fields.items():
                # Only include guild-overridable settings
                if not field_meta.guild_override:
                    continue

                category = field_meta.category

                # Parse hierarchical category (e.g., "Admin/Web" → ["Admin", "Web"])
                category_parts = category.split("/") if "/" in category else [category]

                # Navigate/create nested structure
                current_level = categorized
                for i, part in enumerate(category_parts):
                    if i == len(category_parts) - 1:
                        # Last part - this is where settings go
                        if part not in current_level:
                            current_level[part] = {}
                    else:
                        # Intermediate part - create nested dict if needed
                        if part not in current_level:
                            current_level[part] = {}
                        elif not isinstance(current_level[part], dict):
                            # Convert to dict with _settings key if it was a settings dict
                            current_level[part] = {"_settings": current_level[part]}
                        current_level = current_level[part]

                # Get guild-specific value (with hierarchy: default -> global -> guild)
                current_value = config_manager.get(cog_name, field_name, guild_id)
                global_value = config_manager.get(cog_name, field_name)

                # Check if this is a guild override
                is_override = False
                if guild_id in config_manager.guild_overrides:
                    if cog_name in config_manager.guild_overrides[guild_id]:
                        if field_name in config_manager.guild_overrides[guild_id][cog_name]:
                            is_override = True

                setting_key = f"{cog_name}.{field_name}"

                # Add setting to the correct nested location
                target_category = categorized
                for part in category_parts[:-1]:
                    target_category = target_category[part]

                # Add to the final category level
                final_category = category_parts[-1]
                target_category[final_category][setting_key] = {
                    "key": setting_key,
                    "cog": cog_name,
                    "field": field_name,
                    "value": current_value,
                    "is_override": is_override,
                    "global_default": global_value,
                    "type": field_meta.type.__name__,
                    "description": field_meta.description,
                    "min": field_meta.min_value,
                    "max": field_meta.max_value,
                    "choices": field_meta.choices
                }
                total_settings += 1

        return {
            "guild_id": guild_id,
            "categories": categorized,
            "total_settings": total_settings
        }

    except Exception as e:
        logger.error(f"Error getting guild config for {guild_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/guild/{guild_id}/{key}")
async def get_guild_config_setting(guild_id: int, key: str):
    """Get a specific configuration setting for a guild."""
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        # Parse key: "CogName.field_name"
        if "." not in key:
            raise HTTPException(status_code=400, detail=f"Invalid key format. Expected 'CogName.field_name', got '{key}'")

        cog_name, field_name = key.split(".", 1)

        # Validate the setting exists
        if cog_name not in config_manager.schemas:
            raise HTTPException(status_code=404, detail=f"Cog '{cog_name}' not found")

        schema = config_manager.schemas[cog_name]
        if field_name not in schema.fields:
            raise HTTPException(status_code=404, detail=f"Setting '{field_name}' not found in cog '{cog_name}'")

        field_meta = schema.fields[field_name]

        # Check if guild-overridable
        if not field_meta.guild_override:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' cannot be overridden per-guild")

        # Get values
        guild_value = config_manager.get(cog_name, field_name, guild_id)
        global_value = config_manager.get(cog_name, field_name)

        # Check if guild override exists
        is_override = False
        if guild_id in config_manager.guild_overrides:
            if cog_name in config_manager.guild_overrides[guild_id]:
                if field_name in config_manager.guild_overrides[guild_id][cog_name]:
                    is_override = True

        return {
            "key": key,
            "value": guild_value,
            "is_override": is_override,
            "global_default": global_value
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
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        body = await request.json()
        logger.info(f"Received guild config update: guild_id={guild_id}, body={body}")

        if body is None or "key" not in body or "value" not in body:
            raise HTTPException(status_code=400, detail="Missing 'key' or 'value' in request body")

        full_key = body["key"]  # e.g., "Soundboard.default_volume"
        value = body["value"]

        # Parse the key
        if "." not in full_key:
            raise HTTPException(status_code=400, detail=f"Invalid key format. Expected 'CogName.field_name', got '{full_key}'")

        cog_name, field_name = full_key.split(".", 1)

        # Validate the setting exists
        if cog_name not in config_manager.schemas:
            raise HTTPException(status_code=404, detail=f"Cog '{cog_name}' not found")

        schema = config_manager.schemas[cog_name]
        if field_name not in schema.fields:
            raise HTTPException(status_code=404, detail=f"Setting '{field_name}' not found in cog '{cog_name}'")

        field_meta = schema.fields[field_name]

        # Check if guild-overridable
        if not field_meta.guild_override:
            raise HTTPException(status_code=400, detail=f"Setting '{full_key}' cannot be overridden per-guild")

        # Get old value before changing
        old_value = config_manager.get(cog_name, field_name, guild_id)

        # Set the guild-specific value (validates automatically)
        success, error = config_manager.set(cog_name, field_name, value, guild_id)

        if not success:
            raise HTTPException(status_code=400, detail=f"Validation failed: {error}")

        # Log the change
        logger.info(f"Config changed via web UI (guild {guild_id}): {full_key} | old: {old_value} -> new: {value}")

        # Save to disk
        config_manager.save()

        return {
            "success": True,
            "guild_id": guild_id,
            "key": full_key,
            "cog": cog_name,
            "field": field_name,
            "value": value,
            "old_value": old_value,
            "message": f"Successfully updated {full_key} for guild {guild_id}"
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
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        # Parse key: "CogName.field_name"
        if "." not in key:
            raise HTTPException(status_code=400, detail=f"Invalid key format. Expected 'CogName.field_name', got '{key}'")

        cog_name, field_name = key.split(".", 1)

        # Validate the setting exists
        if cog_name not in config_manager.schemas:
            raise HTTPException(status_code=404, detail=f"Cog '{cog_name}' not found")

        schema = config_manager.schemas[cog_name]
        if field_name not in schema.fields:
            raise HTTPException(status_code=404, detail=f"Setting '{field_name}' not found in cog '{cog_name}'")

        # Check if guild override exists
        if guild_id not in config_manager.guild_overrides:
            raise HTTPException(status_code=400, detail=f"No overrides found for guild {guild_id}")

        if cog_name not in config_manager.guild_overrides[guild_id]:
            raise HTTPException(status_code=400, detail=f"No overrides for cog '{cog_name}' in guild {guild_id}")

        if field_name not in config_manager.guild_overrides[guild_id][cog_name]:
            raise HTTPException(status_code=400, detail=f"Setting '{key}' is not overridden for guild {guild_id}")

        # Remove the override
        del config_manager.guild_overrides[guild_id][cog_name][field_name]

        # Clean up empty dicts
        if not config_manager.guild_overrides[guild_id][cog_name]:
            del config_manager.guild_overrides[guild_id][cog_name]
        if not config_manager.guild_overrides[guild_id]:
            del config_manager.guild_overrides[guild_id]

        # Invalidate cache
        config_manager._invalidate_cache(cog_name, field_name, guild_id)

        # Save to disk
        config_manager.save()

        # Get new value after reset (will use global default)
        new_value = config_manager.get(cog_name, field_name, guild_id)

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
    if not config_manager:
        raise HTTPException(status_code=503, detail="Config manager not initialized")

    try:
        settings = []

        for cog_name, schema in config_manager.schemas.items():
            for field_name, field_meta in schema.fields.items():
                if field_meta.guild_override:
                    settings.append(f"{cog_name}.{field_name}")

        return {
            "settings": sorted(settings),
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
