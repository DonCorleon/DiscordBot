# cogs/global_error_handler.py
"""
Global error handler cog that catches all unhandled errors.
"""

import discord
from discord.ext import commands
import traceback
import sys

from base_cog import BaseCog, logger
from utils.error_handler import error_handler, ErrorSeverity, ErrorCategory


class GlobalErrorHandler(BaseCog):
    """Handles all unhandled command errors globally."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        logger.info("Global error handler initialized")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """
        Global error handler for all command errors.
        This will catch any errors that aren't handled by individual commands.
        """

        # If error was already handled in the command, don't handle again
        if hasattr(ctx.command, 'on_error'):
            return

        # If cog has its own error handler, let it handle
        cog = ctx.cog
        if cog and cog._get_overridden_method(cog.cog_command_error) is not None:
            return

        # Get the original error if it's wrapped
        error = getattr(error, 'original', error)

        # Handle the error using our error handler
        await error_handler.handle_command_error(ctx, error)

    @commands.Cog.listener()
    async def on_error(self, event_method: str, *args, **kwargs):
        """
        Global error handler for non-command errors (events).
        """
        error_info = sys.exc_info()
        error = error_info[1]

        context = {
            "event": event_method,
            "args": str(args)[:200],  # Truncate long args
        }

        error_handler.log_error(
            error,
            context=context,
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.INTERNAL
        )

        logger.error(
            f"Error in event '{event_method}':\n"
            f"{''.join(traceback.format_exception(*error_info))}"
        )

    @commands.command(name="errorstats", hidden=True)
    @commands.is_owner()
    async def error_stats(self, ctx):
        """Show error statistics (owner only)."""
        stats = error_handler.get_stats()

        embed = discord.Embed(
            title="📊 Error Statistics",
            color=discord.Color.red()
        )

        embed.add_field(
            name="Total Errors",
            value=f"`{stats['total_errors']}`",
            inline=True
        )

        if stats['by_category']:
            categories = "\n".join(
                f"**{cat}**: {count}"
                for cat, count in sorted(
                    stats['by_category'].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5]  # Top 5
            )
            embed.add_field(
                name="Top Categories",
                value=categories or "None",
                inline=False
            )

        if stats['recent_errors']:
            recent = stats['recent_errors'][-3:]  # Last 3
            recent_text = "\n".join(
                f"• **{e['category']}** - {e['error_type']}: {e['message'][:50]}"
                for e in recent
            )
            embed.add_field(
                name="Recent Errors",
                value=recent_text or "None",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    """Load the global error handler."""
    try:
        await bot.add_cog(GlobalErrorHandler(bot))
        logger.info("Global error handler loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load global error handler: {e}", exc_info=True)