from discord.ext import commands
import traceback

from base_cog import BaseCog, logger

class Monitors(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    @commands.command()
    async def pang(self, ctx):
        await ctx.send("Pang Bro!")

async def setup(bot):
    try:
        await bot.add_cog(Monitors(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception:
        logger.error("Failed to load cog %s:\n%s", __name__, traceback.format_exc())