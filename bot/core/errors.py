# utils/error_handler.py
"""
Centralized error handling system with user-friendly messages and detailed logging.
"""

import asyncio
import logging
import traceback
import sys
from enum import Enum
from typing import Optional, Callable, Any
from functools import wraps
from datetime import datetime
import discord
from discord.ext import commands

logger = logging.getLogger("discordbot.error_handler")


class ErrorSeverity(Enum):
    """Error severity levels for monitoring."""
    LOW = "low"  # Expected errors (user mistakes)
    MEDIUM = "medium"  # Unexpected but recoverable
    HIGH = "high"  # Service degradation
    CRITICAL = "critical"  # System failure


class ErrorCategory(Enum):
    """Categories for error classification."""
    USER_INPUT = "user_input"
    VOICE = "voice"
    AUDIO = "audio"
    DATABASE = "database"
    PERMISSION = "permission"
    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    INTERNAL = "internal"
    RATE_LIMIT = "rate_limit"


class BotError(Exception):
    """Base exception for bot errors with user-facing messages."""

    def __init__(
            self,
            user_message: str,
            log_message: str = None,
            category: ErrorCategory = ErrorCategory.INTERNAL,
            severity: ErrorSeverity = ErrorSeverity.MEDIUM,
            original_error: Exception = None
    ):
        self.user_message = user_message
        self.log_message = log_message or user_message
        self.category = category
        self.severity = severity
        self.original_error = original_error
        super().__init__(self.log_message)


# Specific error types
class UserInputError(BotError):
    """Errors caused by invalid user input."""

    def __init__(self, user_message: str, log_message: str = None):
        super().__init__(
            user_message,
            log_message,
            ErrorCategory.USER_INPUT,
            ErrorSeverity.LOW
        )


class VoiceError(BotError):
    """Errors related to voice connections."""

    def __init__(self, user_message: str, log_message: str = None):
        super().__init__(
            user_message,
            log_message,
            ErrorCategory.VOICE,
            ErrorSeverity.MEDIUM
        )


class AudioError(BotError):
    """Errors related to audio playback."""

    def __init__(self, user_message: str, log_message: str = None):
        super().__init__(
            user_message,
            log_message,
            ErrorCategory.AUDIO,
            ErrorSeverity.MEDIUM
        )


class DatabaseError(BotError):
    """Errors related to database operations."""

    def __init__(self, user_message: str, log_message: str = None):
        super().__init__(
            user_message,
            log_message,
            ErrorCategory.DATABASE,
            ErrorSeverity.HIGH
        )


class ErrorHandler:
    """Central error handling with logging and user notifications."""

    # User-friendly messages for common errors
    USER_MESSAGES = {
        "default": "❌ Something went wrong. The issue has been logged.",
        "voice_not_connected": "⚠️ I'm not connected to a voice channel.",
        "user_not_in_voice": "⚠️ You need to be in a voice channel first.",
        "permission_denied": "⚠️ I don't have permission to do that.",
        "file_not_found": "⚠️ That file couldn't be found.",
        "invalid_input": "⚠️ Invalid input. Please check your command.",
        "rate_limited": "⚠️ Slow down! You're doing that too quickly.",
        "database_error": "❌ A database error occurred. Please try again later.",
        "network_error": "❌ Network issue detected. Please try again.",
        "audio_error": "⚠️ Audio playback failed.",
        "timeout": "⏱️ The operation timed out. Please try again.",
    }

    def __init__(self):
        self.error_count = 0
        self.errors_by_category = {}
        self.last_errors = []  # Keep last 100 errors for admin interface
        self.max_error_history = 100

    def log_error(
            self,
            error: Exception,
            context: dict = None,
            severity: ErrorSeverity = ErrorSeverity.MEDIUM,
            category: ErrorCategory = ErrorCategory.INTERNAL
    ):
        """Log an error with full context."""

        self.error_count += 1

        # Track by category
        cat_name = category.value
        self.errors_by_category[cat_name] = self.errors_by_category.get(cat_name, 0) + 1

        # Build detailed log message
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "error_type": type(error).__name__,
            "severity": severity.value,
            "category": category.value,
            "message": str(error),
        }

        if context:
            log_data["context"] = context

        # Add to history for admin interface
        self.last_errors.append(log_data)
        if len(self.last_errors) > self.max_error_history:
            self.last_errors.pop(0)

        # Log based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical(
                f"CRITICAL ERROR: {error}\n"
                f"Context: {context}\n"
                f"Traceback: {traceback.format_exc()}"
            )
        elif severity == ErrorSeverity.HIGH:
            logger.error(
                f"HIGH SEVERITY: {error}\n"
                f"Context: {context}\n"
                f"Traceback: {traceback.format_exc()}"
            )
        elif severity == ErrorSeverity.MEDIUM:
            logger.error(f"Error: {error}\nContext: {context}")
        else:  # LOW
            logger.warning(f"Minor error: {error}\nContext: {context}")

    async def handle_command_error(
            self,
            ctx: commands.Context,
            error: Exception,
            custom_message: str = None
    ) -> bool:
        """
        Handle errors during command execution.
        Returns True if error was handled, False if should propagate.
        """

        # Extract context information
        context = {
            "command": ctx.command.name if ctx.command else "unknown",
            "guild": ctx.guild.name if ctx.guild else "DM",
            "guild_id": ctx.guild.id if ctx.guild else None,
            "user": str(ctx.author),
            "user_id": ctx.author.id,
            "channel": str(ctx.channel),
        }

        user_message = custom_message or self.USER_MESSAGES["default"]

        # Handle specific Discord.py errors
        if isinstance(error, commands.CommandNotFound):
            return True  # Silently ignore

        elif isinstance(error, commands.MissingRequiredArgument):
            user_message = f"⚠️ Missing required argument: `{error.param.name}`"
            self.log_error(error, context, ErrorSeverity.LOW, ErrorCategory.USER_INPUT)

        elif isinstance(error, commands.BadArgument):
            user_message = "⚠️ Invalid argument provided."
            self.log_error(error, context, ErrorSeverity.LOW, ErrorCategory.USER_INPUT)

        elif isinstance(error, commands.MissingPermissions):
            user_message = "⚠️ You don't have permission to use this command."
            self.log_error(error, context, ErrorSeverity.LOW, ErrorCategory.PERMISSION)

        elif isinstance(error, commands.BotMissingPermissions):
            user_message = "⚠️ I don't have the required permissions."
            self.log_error(error, context, ErrorSeverity.MEDIUM, ErrorCategory.PERMISSION)

        elif isinstance(error, commands.CommandOnCooldown):
            user_message = f"⏱️ Command on cooldown. Try again in {error.retry_after:.1f}s."
            self.log_error(error, context, ErrorSeverity.LOW, ErrorCategory.RATE_LIMIT)

        elif isinstance(error, commands.MaxConcurrencyReached):
            user_message = "⚠️ Too many people are using this command right now."
            self.log_error(error, context, ErrorSeverity.MEDIUM, ErrorCategory.RATE_LIMIT)

        elif isinstance(error, discord.Forbidden):
            user_message = "⚠️ I don't have permission to do that."
            self.log_error(error, context, ErrorSeverity.MEDIUM, ErrorCategory.PERMISSION)

        elif isinstance(error, discord.HTTPException):
            user_message = "❌ A network error occurred. Please try again."
            self.log_error(error, context, ErrorSeverity.HIGH, ErrorCategory.NETWORK)

        # Handle custom bot errors
        elif isinstance(error, BotError):
            user_message = error.user_message
            self.log_error(
                error,
                context,
                error.severity,
                error.category
            )

        # Handle unexpected errors
        else:
            user_message = self.USER_MESSAGES["default"]
            self.log_error(error, context, ErrorSeverity.HIGH, ErrorCategory.INTERNAL)

        # Send user-friendly message
        try:
            await ctx.send(user_message, delete_after=10)
        except Exception as send_error:
            logger.error(f"Failed to send error message: {send_error}")

        return True

    def get_stats(self) -> dict:
        """Get error statistics for admin interface."""
        return {
            "total_errors": self.error_count,
            "by_category": self.errors_by_category.copy(),
            "recent_errors": self.last_errors[-10:],  # Last 10
        }


# Global error handler instance
error_handler = ErrorHandler()


def handle_errors(
        user_message: str = None,
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM
):
    """
    Decorator for command error handling with custom messages.

    Usage:
        @handle_errors(user_message="Failed to play sound", category=ErrorCategory.AUDIO)
        async def play_sound(self, ctx, sound_name: str):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(self, ctx: commands.Context, *args, **kwargs) -> Any:
            try:
                return await func(self, ctx, *args, **kwargs)
            except BotError as e:
                # Our custom errors already have messages
                await error_handler.handle_command_error(ctx, e)
            except Exception as e:
                # Wrap unexpected errors
                wrapped_error = BotError(
                    user_message=user_message or error_handler.USER_MESSAGES["default"],
                    log_message=f"Error in {func.__name__}: {str(e)}",
                    category=category,
                    severity=severity,
                    original_error=e
                )
                await error_handler.handle_command_error(ctx, wrapped_error)

        return wrapper

    return decorator


def safe_operation(
        fallback_value: Any = None,
        log_message: str = None,
        severity: ErrorSeverity = ErrorSeverity.LOW
):
    """
    Decorator for non-command operations that should fail gracefully.

    Usage:
        @safe_operation(fallback_value=[], log_message="Failed to load sounds")
        def load_sounds(self):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                error_handler.log_error(
                    e,
                    context={"function": func.__name__, "args": str(args)},
                    severity=severity,
                    category=ErrorCategory.INTERNAL
                )
                return fallback_value

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_handler.log_error(
                    e,
                    context={"function": func.__name__, "args": str(args)},
                    severity=severity,
                    category=ErrorCategory.INTERNAL
                )
                return fallback_value

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# User Feedback System
# ============================================================================

class UserFeedback:
    """Enhanced user interaction with embeds and reactions."""

    @staticmethod
    async def success(ctx: commands.Context, message: str, delete_after: int = None):
        """Send a success message."""
        embed = discord.Embed(
            description=f"✅ {message}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed, delete_after=delete_after)

    @staticmethod
    async def error(ctx: commands.Context, message: str, delete_after: int = 10):
        """Send an error message."""
        embed = discord.Embed(
            description=f"❌ {message}",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed, delete_after=delete_after)

    @staticmethod
    async def warning(ctx: commands.Context, message: str, delete_after: int = None):
        """Send a warning message."""
        embed = discord.Embed(
            description=f"⚠️ {message}",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed, delete_after=delete_after)

    @staticmethod
    async def info(ctx: commands.Context, message: str, delete_after: int = None):
        """Send an info message."""
        embed = discord.Embed(
            description=f"ℹ️ {message}",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, delete_after=delete_after)

    @staticmethod
    async def loading(ctx: commands.Context, message: str = "Processing..."):
        """Send a loading message and return it for later editing."""
        embed = discord.Embed(
            description=f"⏳ {message}",
            color=discord.Color.blue()
        )
        return await ctx.send(embed=embed)

    @staticmethod
    async def confirm(
            ctx: commands.Context,
            message: str,
            timeout: int = 30
    ) -> bool:
        """
        Ask user for confirmation with reactions.
        Returns True if confirmed, False if denied or timeout.
        """
        embed = discord.Embed(
            description=f"❓ {message}\n\nReact with ✅ to confirm or ❌ to cancel.",
            color=discord.Color.blue()
        )
        msg = await ctx.send(embed=embed)

        await msg.add_reaction("✅")
        await msg.add_reaction("❌")

        def check(reaction, user):
            return (
                    user == ctx.author
                    and str(reaction.emoji) in ["✅", "❌"]
                    and reaction.message.id == msg.id
            )

        try:
            reaction, user = await ctx.bot.wait_for(
                "reaction_add",
                timeout=timeout,
                check=check
            )
            await msg.delete()
            return str(reaction.emoji) == "✅"
        except asyncio.TimeoutError:
            await msg.delete()
            return False


# ============================================================================
# Progress Tracking (for long operations)
# ============================================================================

class ProgressTracker:
    """Track and display progress for long-running operations."""

    def __init__(self, ctx: commands.Context, total: int, description: str = "Processing"):
        self.ctx = ctx
        self.total = total
        self.current = 0
        self.description = description
        self.message = None

    async def start(self):
        """Initialize the progress message."""
        embed = self._create_embed()
        self.message = await self.ctx.send(embed=embed)

    async def update(self, increment: int = 1):
        """Update progress."""
        self.current += increment
        if self.message:
            embed = self._create_embed()
            await self.message.edit(embed=embed)

    async def complete(self, final_message: str = "Complete!"):
        """Mark as complete and update message."""
        if self.message:
            embed = discord.Embed(
                description=f"✅ {final_message}",
                color=discord.Color.green()
            )
            await self.message.edit(embed=embed)
            await asyncio.sleep(3)
            await self.message.delete()

    def _create_embed(self) -> discord.Embed:
        """Create progress bar embed."""
        percentage = (self.current / self.total) * 100
        bar_length = 20
        filled = int((self.current / self.total) * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)

        embed = discord.Embed(
            title=self.description,
            description=f"`{bar}` {percentage:.1f}%\n{self.current}/{self.total}",
            color=discord.Color.blue()
        )
        return embed


# ============================================================================
# Validation Helpers
# ============================================================================

class ValidationError(UserInputError):
    """Raised when validation fails."""
    pass


class Validator:
    """Input validation utilities."""

    @staticmethod
    def require_voice_connection(ctx: commands.Context):
        """Ensure bot is in voice channel."""
        if not ctx.voice_client:
            raise VoiceError(
                "I'm not connected to a voice channel.",
                f"Voice check failed in guild {ctx.guild.id}"
            )

    @staticmethod
    def require_user_in_voice(ctx: commands.Context):
        """Ensure user is in voice channel."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            raise VoiceError(
                "You need to be in a voice channel first.",
                f"User {ctx.author.id} not in voice"
            )

    @staticmethod
    def require_same_voice_channel(ctx: commands.Context):
        """Ensure user and bot are in same voice channel."""
        if not ctx.voice_client or not ctx.author.voice:
            raise VoiceError("We need to be in the same voice channel.")

        if ctx.voice_client.channel.id != ctx.author.voice.channel.id:
            raise VoiceError(
                "We need to be in the same voice channel.",
                f"User {ctx.author.id} in different channel"
            )

    @staticmethod
    def validate_file_exists(filepath: str):
        """Check if file exists."""
        from pathlib import Path
        if not Path(filepath).exists():
            raise AudioError(
                "Audio file not found.",
                f"Missing file: {filepath}"
            )

    @staticmethod
    def validate_audio_format(filename: str):
        """Validate audio file format."""
        valid_extensions = [".mp3", ".wav", ".ogg", ".m4a", ".flac"]
        if not any(filename.lower().endswith(ext) for ext in valid_extensions):
            raise ValidationError(
                f"Invalid audio format. Supported: {', '.join(valid_extensions)}",
                f"Invalid format: {filename}"
            )
