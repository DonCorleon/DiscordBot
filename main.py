import discord
from discord.ext import commands
import os
from datetime import datetime, UTC

from token import TOKEN

# -----------------------
# Logging setup
# -----------------------
import logging
from logging.handlers import TimedRotatingFileHandler

os.makedirs("logs", exist_ok=True)

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# --- File handler ---
file_handler = TimedRotatingFileHandler(
    f"logs/discordbot.log",
    when="midnight",
    interval=1,
    backupCount=7,
    encoding="utf-8"
)
file_handler.setFormatter(formatter)

# --- Console handler ---
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# --- discord bot logger ---
# Enable detailed logs for discord.ext.voice_recv
logging.getLogger("discord.ext.voice_recv").setLevel(logging.DEBUG)

# (Optional) enable lower-level internals if you want packet traces
logging.getLogger("discord.voice_recv").setLevel(logging.DEBUG)
logging.getLogger("discord.gateway").setLevel(logging.DEBUG)


logger = logging.getLogger("discordbot")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False  # Prevent double logging from root logger

# --- Basic setup ---
intents = discord.Intents.default()
intents.message_content = True  # Needed for text commands
intents.members = True

bot = commands.Bot(command_prefix="~", intents=intents)
bot.start_time = datetime.now(UTC)

# --- Load Cogs automatically ---
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")

# --- Run the bot ---
bot.run(TOKEN)
