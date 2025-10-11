import logging
import traceback
from functools import wraps
from discord.ext import commands

# Configure logger
logger = logging.getLogger(f"discordbot.{__name__}")

def log_command_errors(func):
    @wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        try:
            return await func(self, ctx, *args, **kwargs)
        except Exception as e:
            logger.error("Error in command '%s':\n%s", ctx.command, traceback.format_exc())
    return wrapper

class BaseCog(commands.Cog):
    """Base Cog class to inherit in all cogs for automatic error logging."""

    def __init__(self, bot: commands.Bot):
        #super().__init__(bot)
        self.bot = bot

        # Automatically wrap all commands in this cog
        for command in self.get_commands():
            command.callback = log_command_errors(command.callback)

        #logger.info(f"Loaded cog: {self.__class__.__name__}")

    async def cog_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Log full traceback
        logger.error("Error in command '%s':\n%s", ctx.command, traceback.format_exc())

        # Send a friendly message to the same channel
        await ctx.send(f"⚠️ Command `{ctx.command}` encountered an error:\n`{error}`")
