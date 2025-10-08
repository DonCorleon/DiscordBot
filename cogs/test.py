from discord.ext import commands
import traceback

from base_cog import BaseCog, logger

class Test(BaseCog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        await ctx.send("Pong Bro!")

async def setup(bot):
    try:
        await bot.add_cog(Test(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception:
        logger.error("Failed to load cog %s:\n%s", __name__, traceback.format_exc())