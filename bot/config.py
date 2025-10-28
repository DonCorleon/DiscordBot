# config.py
"""
Bot-level configuration file.

This file contains only bot-level settings that are needed during early bot
initialization, before ConfigManager is available:
- Discord token and command prefix
- Bot owner and admin system configuration
- System settings needed for bot startup (web dashboard, admin data collector)

All cog-specific settings are defined in their respective cog config schemas
and managed by the unified ConfigManager system.

Note: Some settings here (max_history, web dashboard) are duplicated in
SystemConfig for runtime configuration via ConfigManager, but need to be
here for bot startup before cogs are loaded.

For cog configuration, see:
- bot/cogs/*/config schemas using ConfigBase
- bot/core/config_system.py for ConfigManager
- Web UI at /config for runtime configuration
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BotConfig:
    """Bot-level configuration (not cog-specific)."""

    # Discord Configuration (REQUIRED in .env)
    token: str  # REQUIRED: DISCORD_TOKEN in .env
    command_prefix: str | list[str]  # REQUIRED: COMMAND_PREFIX in .env
    bot_owner_id: int  # REQUIRED: BOT_OWNER or BOT_OWNER_ID in .env

    # Admin System
    admin_user_ids: list[int] = None  # Auto-populated with bot_owner_id
    admin_role_ids: list[int] = None  # Optional admin roles

    @classmethod
    def from_env(cls):
        """Create config from environment variables.

        Raises:
            ValueError: If required environment variables are missing
        """
        # Required: Discord token
        token = os.getenv("DISCORD_TOKEN")
        if not token:
            raise ValueError("DISCORD_TOKEN is required in .env file")

        # Required: Command prefix
        prefix_str = os.getenv("COMMAND_PREFIX")
        if not prefix_str:
            raise ValueError("COMMAND_PREFIX is required in .env file")

        # If comma-separated, split into list
        if "," in prefix_str:
            command_prefix = [p.strip() for p in prefix_str.split(",") if p.strip()]
        else:
            command_prefix = prefix_str

        # Required: Bot owner ID (try both BOT_OWNER_ID and BOT_OWNER for compatibility)
        bot_owner_id = os.getenv("BOT_OWNER_ID") or os.getenv("BOT_OWNER")
        if not bot_owner_id:
            raise ValueError("BOT_OWNER or BOT_OWNER_ID is required in .env file")

        bot_owner_id = int(bot_owner_id)
        admin_user_ids = [bot_owner_id]  # Start with owner as admin

        return cls(
            token=token,
            command_prefix=command_prefix,
            # Admin system - read from .env
            bot_owner_id=bot_owner_id,
            admin_user_ids=admin_user_ids,
            admin_role_ids=[],
        )

    def display(self):
        """Display current configuration (safe for logging)."""
        prefix_display = ", ".join(self.command_prefix) if isinstance(self.command_prefix,
                                                                      list) else self.command_prefix
        return f"""
Bot Configuration (Bootstrap):
==================
Command Prefix: {prefix_display}
Bot Owner ID: {self.bot_owner_id}
Admin Users: {len(self.admin_user_ids) if self.admin_user_ids else 0}
Admin Roles: {len(self.admin_role_ids) if self.admin_role_ids else 0}

Note: All other settings (web dashboard, monitoring, cog-specific) are managed
      via ConfigManager and loaded after cogs are initialized.
      Use the web UI at /config or ~gc commands to configure settings.
"""


# Load Configuration
config = BotConfig.from_env()
