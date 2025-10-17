# base_cog_v2.py
"""
Enhanced base cog with integrated error handling and command tracking.
"""

import logging
import traceback
import time
from functools import wraps
from discord.ext import commands

from utils.error_handler import error_handler, ErrorSeverity, ErrorCategory
from utils.admin_data_collector import get_data_collector

# Configure logger
logger = logging.getLogger(f"discordbot.{__name__}")


def track_command(func):
    """
    Decorator to track command execution time and success/failure.
    Integrates with admin data collector.
    """

    @wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        command_name = ctx.command.name if ctx.command else func.__name__
        start_time = time.time()
        success = True

        try:
            result = await func(self, ctx, *args, **kwargs)
            return result
        except Exception as e:
            success = False
            raise
        finally:
            execution_time = time.time() - start_time

            # Record in data collector
            data_collector = get_data_collector()
            if data_collector:
                data_collector.record_command(command_name, execution_time, success)

            # Log execution time for slow commands
            if execution_time > 2.0:
                logger.warning(
                    f"Slow command execution: {command_name} took {execution_time:.2f}s"
                )

    return wrapper


class BaseCog(commands.Cog):
    """
    Enhanced base Cog class with automatic error handling and command tracking.
    All cogs should inherit from this class.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Automatically wrap all commands with tracking
        for command in self.get_commands():
            if not hasattr(command.callback, '_tracked'):
                command.callback = track_command(command.callback)
                command.callback._tracked = True

        logger.info(f"Loaded cog: {self.__class__.__name__}")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """
        Error handler for all commands in this cog.
        Uses centralized error handling system.
        """

        # Get the original error if wrapped
        original_error = getattr(error, 'original', error)

        # Record error in data collector
        data_collector = get_data_collector()
        if data_collector:
            error_data = {
                "command": ctx.command.name if ctx.command else "unknown",
                "error_type": type(original_error).__name__,
                "message": str(original_error),
                "guild_id": ctx.guild.id if ctx.guild else None,
                "user_id": ctx.author.id
            }
            data_collector.record_error(error_data)

        # Handle the error
        await error_handler.handle_command_error(ctx, error)

    def cog_unload(self):
        """
        Called when cog is unloaded.
        Override this in child classes for cleanup.
        """
        logger.info(f"Unloading cog: {self.__class__.__name__}")


# Backwards compatibility - export old name
def log_command_errors(func):
    """Legacy decorator - now redirects to track_command."""
    return track_command(func)