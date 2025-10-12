import discord
from discord.ext import commands, voice_recv
import os
from datetime import datetime, UTC
from bottoken import TOKEN
import logging
from logging.handlers import TimedRotatingFileHandler

os.makedirs("logs", exist_ok=True)

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

file_handler = TimedRotatingFileHandler(
    "logs/discordbot.log",
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Clear handlers for all discrod logging and implement mine
for name, log in logging.root.manager.loggerDict.items():
    if name.startswith("discord"):
        if isinstance(log, logging.Logger):
            log.handlers.clear()
            log.setLevel(logging.INFO)
            log.addHandler(console_handler)
            log.addHandler(file_handler)
            log.propagate = False

# Configure YOUR bot's logger
logger = logging.getLogger("discordbot")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False


class IgnoreRTCPFilter(logging.Filter):
    def filter(self, record):
        # Suppress only the specific unwanted message
        msg = getattr(record, "msg", "")
        if "Received unexpected rtcp packet" in str(msg):
            return False
        return True

# Apply the filter to the voice_recv logger
logging.getLogger("discord.ext.voice_recv.reader").addFilter(IgnoreRTCPFilter())


logger.info("Bot starting...")


# -----------------------
# Bot setup
# -----------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="~", intents=intents, help_command=None)
bot.start_time = datetime.now(UTC)

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
'''
@bot.event
async def on_message(message):
    # Ignore messages from bots
    if message.author.bot:
        return

    if message.guild is None:
        # Message is in a DM
        logger.info(f"Received DM from {message.author}: {message.content}")

        # Construct a context
        ctx = await bot.get_context(message)

        # Assign a dummy guild if commands rely on ctx.guild.id
        if not ctx.guild:
            ctx.guild = type("Guild", (), {"id": "DM"})()  # dummy guild object

        # Process commands
        await bot.process_commands(message)
    else:
        # Message is in a guild
        logger.info(f"Guild {message.guild.id} - {message.author}: {message.content}")
        await bot.process_commands(message)
'''

# -----------------------
# Run the bot
# -----------------------
bot.run(TOKEN)
