"""
Admin management system for the bot.
Handles loading, saving, and checking admin permissions.
"""
import json
from pathlib import Path
from typing import List, Set
from bot.base_cog import logger
from bot.config import config

ADMIN_FILE = "data/config/admins.json"


def load_admins() -> dict:
    """Load admin configuration from file."""
    try:
        if not Path(ADMIN_FILE).exists():
            # Create default admin file with owner
            default_admins = {
                "user_ids": [config.bot_owner_id],
                "role_ids": []
            }
            save_admins(default_admins)
            return default_admins

        with open(ADMIN_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure owner is always in admin list
        if config.bot_owner_id not in data.get("user_ids", []):
            data["user_ids"].append(config.bot_owner_id)
            save_admins(data)

        return data

    except Exception as e:
        logger.error(f"Error loading admins: {e}", exc_info=True)
        # Return default with owner only
        return {
            "user_ids": [config.bot_owner_id],
            "role_ids": []
        }


def save_admins(admin_data: dict):
    """Save admin configuration to file."""
    try:
        # Ensure owner is always included
        if config.bot_owner_id not in admin_data.get("user_ids", []):
            admin_data["user_ids"].append(config.bot_owner_id)

        with open(ADMIN_FILE, "w", encoding="utf-8") as f:
            json.dump(admin_data, f, indent=2)

        logger.info(f"Saved admin configuration: {len(admin_data['user_ids'])} users, {len(admin_data['role_ids'])} roles")

    except Exception as e:
        logger.error(f"Error saving admins: {e}", exc_info=True)
        raise


def is_admin(user_id: int, user_roles: List[int] = None) -> bool:
    """
    Check if a user is an admin.

    Args:
        user_id: Discord user ID
        user_roles: List of role IDs the user has

    Returns:
        True if user is an admin, False otherwise
    """
    admin_data = load_admins()

    # Check if user ID is in admin list
    if user_id in admin_data.get("user_ids", []):
        return True

    # Check if user has any admin roles
    if user_roles:
        admin_roles = set(admin_data.get("role_ids", []))
        user_role_set = set(user_roles)
        if admin_roles & user_role_set:  # Intersection
            return True

    return False


def is_owner(user_id: int) -> bool:
    """Check if user is the bot owner."""
    return user_id == config.bot_owner_id


def add_admin_user(user_id: int) -> bool:
    """
    Add a user to the admin list.

    Args:
        user_id: Discord user ID to add

    Returns:
        True if added, False if already admin
    """
    admin_data = load_admins()

    if user_id in admin_data["user_ids"]:
        return False  # Already admin

    admin_data["user_ids"].append(user_id)
    save_admins(admin_data)
    logger.info(f"Added admin user: {user_id}")
    return True


def remove_admin_user(user_id: int) -> bool:
    """
    Remove a user from the admin list.

    Args:
        user_id: Discord user ID to remove

    Returns:
        True if removed, False if not in admin list or is owner
    """
    # Can't remove owner
    if user_id == config.bot_owner_id:
        return False

    admin_data = load_admins()

    if user_id not in admin_data["user_ids"]:
        return False  # Not in admin list

    admin_data["user_ids"].remove(user_id)
    save_admins(admin_data)
    logger.info(f"Removed admin user: {user_id}")
    return True


def add_admin_role(role_id: int) -> bool:
    """
    Add a role to the admin list.

    Args:
        role_id: Discord role ID to add

    Returns:
        True if added, False if already admin role
    """
    admin_data = load_admins()

    if role_id in admin_data["role_ids"]:
        return False  # Already admin role

    admin_data["role_ids"].append(role_id)
    save_admins(admin_data)
    logger.info(f"Added admin role: {role_id}")
    return True


def remove_admin_role(role_id: int) -> bool:
    """
    Remove a role from the admin list.

    Args:
        role_id: Discord role ID to remove

    Returns:
        True if removed, False if not in admin list
    """
    admin_data = load_admins()

    if role_id not in admin_data["role_ids"]:
        return False  # Not in admin list

    admin_data["role_ids"].remove(role_id)
    save_admins(admin_data)
    logger.info(f"Removed admin role: {role_id}")
    return True


def get_admin_users() -> List[int]:
    """Get list of admin user IDs."""
    admin_data = load_admins()
    return admin_data.get("user_ids", [])


def get_admin_roles() -> List[int]:
    """Get list of admin role IDs."""
    admin_data = load_admins()
    return admin_data.get("role_ids", [])
