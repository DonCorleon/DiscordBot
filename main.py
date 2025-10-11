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

# Remove default Discord handlers before adding yours
for name in ["discord", "discord.client", "discord.gateway", "discord.voice_state"]:
    log = logging.getLogger(name)
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

# -----------------------
# Run the bot
# -----------------------
bot.run(TOKEN)
