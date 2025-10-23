import discord
from discord.ext import commands, voice_recv
import os
from datetime import datetime, UTC
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from bot.config import config
from bot.core.admin.data_collector import initialize_data_collector

# IMPORTANT: Change to project root so model/ directory can be found
project_root = Path(__file__).parent.parent
os.chdir(project_root)

# Create data directories (relative to project root)
(project_root / "data" / "logs").mkdir(parents=True, exist_ok=True)

formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

file_handler = TimedRotatingFileHandler(
    str(project_root / "data" / "logs" / "discordbot.log"),
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


class ConnectionErrorFilter(logging.Filter):
    """Filter to suppress verbose connection error tracebacks and show cleaner messages."""
    def filter(self, record):
        msg = getattr(record, "msg", "")

        # Suppress the verbose "Attempting a reconnect" traceback
        if "Attempting a reconnect" in str(msg) and record.exc_info:
            # Log a cleaner message without the full traceback
            if record.exc_info and record.exc_info[1]:
                exc = record.exc_info[1]
                exc_type = type(exc).__name__

                # Create a cleaner log message
                if "DNS" in exc_type or "getaddrinfo failed" in str(exc):
                    logger.warning(f"Connection lost (DNS resolution failure) - Retrying...")
                elif "Connection" in exc_type:
                    logger.warning(f"Connection lost ({exc_type}) - Retrying...")
                else:
                    logger.warning(f"Connection lost - Retrying...")

            # Suppress the original verbose message
            return False

        return True

# Apply the filter to the voice_recv logger
logging.getLogger("discord.ext.voice_recv.reader").addFilter(IgnoreRTCPFilter())

# Apply connection error filter to discord.client logger
logging.getLogger("discord.client").addFilter(ConnectionErrorFilter())


logger.info("Bot starting...")


# -----------------------
# Bot setup
# -----------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=config.command_prefix, intents=intents, help_command=None)
bot.start_time = datetime.now(UTC)

# Initialize data collector with config settings
data_collector = initialize_data_collector(
    bot,
    max_history=config.max_history,
    enable_export=config.enable_admin_dashboard
)

@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    # Start data collection
    await data_collector.start()

    # Load cogs from new structure
    cog_domains = ["activity", "audio", "admin", "utility"]
    cogs_base = os.path.join(os.path.dirname(__file__), "cogs")

    for domain in cog_domains:
        domain_path = os.path.join(cogs_base, domain)
        if os.path.exists(domain_path):
            for filename in os.listdir(domain_path):
                if filename.endswith(".py") and not filename.startswith("__"):
                    await bot.load_extension(f"bot.cogs.{domain}.{filename[:-3]}")

    # Load top-level cog files (like errors.py)
    if os.path.exists(cogs_base):
        for filename in os.listdir(cogs_base):
            if filename.endswith(".py") and not filename.startswith("__"):
                await bot.load_extension(f"bot.cogs.{filename[:-3]}")
    if config.enable_admin_dashboard:
        logger.info("📊 Admin dashboard enabled - Data exporting to data/admin/")
    else:
        logger.info("🖥️  Running in headless mode - Admin dashboard disabled")

    # Connect web dashboard to data collector if enabled
    if config.enable_web_dashboard:
        try:
            from web.websocket_manager import manager
            data_collector.websocket_manager = manager
            logger.info("🌐 Web dashboard connected to data collector")
        except Exception as e:
            logger.error(f"Failed to connect web dashboard: {e}")


@bot.event
async def on_disconnect():
    """Handle bot disconnection from Discord."""
    logger.warning("⚠️ Disconnected from Discord")


@bot.event
async def on_resumed():
    """Handle bot resuming connection to Discord."""
    logger.info("✅ Reconnected to Discord (session resumed)")


@bot.event
async def on_connect():
    """Handle initial connection to Discord."""
    logger.info("🔗 Connected to Discord gateway")

# -----------------------
# Run the bot
# -----------------------

async def start_web_server():
    """Start the web dashboard server."""
    if config.enable_web_dashboard:
        try:
            from web.app import run_server
            logger.info(f"🌐 Starting web dashboard on {config.web_host}:{config.web_port}")
            await run_server(
                host=config.web_host,
                port=config.web_port,
                reload=config.web_reload
            )
        except Exception as e:
            logger.error(f"Failed to start web server: {e}", exc_info=True)


async def main():
    """Main async entry point."""
    try:
        # Start web server in background if enabled
        if config.enable_web_dashboard:
            import asyncio
            asyncio.create_task(start_web_server())
            logger.info("🌐 Web server starting in background...")

        # Start bot
        async with bot:
            await bot.start(config.token)

    except KeyboardInterrupt:
        logger.info("Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        if not bot.is_closed():
            await bot.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
