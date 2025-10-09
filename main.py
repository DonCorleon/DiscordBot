import discord
from discord.ext import commands, voice_recv
import os
from datetime import datetime, UTC
from bottoken import TOKEN

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
    "logs/discordbot.log",
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
logger = logging.getLogger("discordbot")
logger.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False  # prevent double logging

# -----------------------
# Enable detailed voice_recv logging
# -----------------------
#'''
# Let Discord internals use DEBUG level
discord.utils.setup_logging(level=logging.DEBUG, root=False)


# Attach handlers to all voice_recv components
for name in [
    "discord.ext.voice_recv",
    "discord.ext.voice_recv.router",
    "discord.ext.voice_recv.reader",
    "discord.ext.voice_recv.rtp",
    "discord.gateway",
]:
    log = logging.getLogger(name)
    log.setLevel(logging.DEBUG)
    log.addHandler(console_handler)
    log.addHandler(file_handler)
    log.propagate = False

# Optional ultra-verbose packet tracing
logging.addLevelName(5, "TRACE")
logging.getLogger("discord.ext.voice_recv.reader").setLevel(5)
#'''

# -----------------------
# Bot setup
# -----------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="~", intents=intents)
bot.start_time = datetime.now(UTC)

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            await bot.load_extension(f"cogs.{filename[:-3]}")
            print(f"Loaded cog: {filename[:-3]}")

@bot.event
async def on_socket_raw_receive(msg):
        # Log all raw websocket messages to see what's happening at 2min mark
        if 'VOICE' in str(msg):
            print(f"Voice event: {msg}")
        else:
            print(f"{msg}")
# -----------------------
# Run the bot
# -----------------------
bot.run(TOKEN)
