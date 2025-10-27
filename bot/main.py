import discord
from discord.ext import commands, voice_recv
import os
from datetime import datetime, UTC
import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

# Load .env file FIRST (before any config imports)
load_dotenv()

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

# Configure YOUR bot's logger with log level from environment
log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
log_level = getattr(logging, log_level_name, logging.INFO)

logger = logging.getLogger("discordbot")
logger.setLevel(log_level)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.propagate = False

# Also apply to discord loggers
for name, log in logging.root.manager.loggerDict.items():
    if name.startswith("discord"):
        if isinstance(log, logging.Logger):
            log.setLevel(log_level)


def update_log_level(level_name: str):
    """Update log level for all bot loggers dynamically."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    logger.setLevel(level)
    for name, log in logging.root.manager.loggerDict.items():
        if name.startswith("discord"):
            if isinstance(log, logging.Logger):
                log.setLevel(level)
    logger.info(f"Updated log level to {level_name.upper()}")


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
    enable_export=True  # Always enable export for web dashboard and debugging
)


async def rejoin_saved_voice_channels():
    """
    Rejoin voice channels from saved state if users are present.
    Called on bot startup to restore voice connections.
    """
    try:
        from bot.core.audio.voice_state import load_voice_state

        voice_state = load_voice_state()
        if not voice_state:
            logger.info("No saved voice channels to rejoin")
            return

        rejoined_count = 0
        skipped_count = 0
        skipped_details = []  # Track skipped channels with details

        for guild_id_str, state_data in voice_state.items():
            try:
                guild_id = int(guild_id_str)
                channel_id = int(state_data.get("channel_id"))

                # Get guild and channel
                guild = bot.get_guild(guild_id)
                if not guild:
                    logger.warning(f"Guild {guild_id} not found, skipping rejoin")
                    skipped_count += 1
                    skipped_details.append(f"Guild {guild_id} (not found)")
                    continue

                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.VoiceChannel):
                    logger.warning(f"Voice channel {channel_id} not found in {guild.name}, skipping rejoin")
                    skipped_count += 1
                    skipped_details.append(f"{guild.name}:#{channel_id} (channel not found)")
                    continue

                # Check if there are non-bot users in the channel
                users_in_channel = [m for m in channel.members if not m.bot]
                if not users_in_channel:
                    logger.info(f"No users in {channel.name} ({guild.name}), skipping rejoin")
                    skipped_count += 1
                    skipped_details.append(f"{guild.name}:#{channel.name} (no users)")
                    continue

                # Check if already connected
                if guild.voice_client and guild.voice_client.is_connected():
                    logger.info(f"Already connected to voice in {guild.name}, skipping rejoin")
                    skipped_count += 1
                    skipped_details.append(f"{guild.name}:#{channel.name} (already connected)")
                    continue

                # Rejoin the channel
                logger.info(f"Rejoining {channel.name} in {guild.name} ({len(users_in_channel)} users present)")
                vc = await channel.connect(cls=voice_recv.VoiceRecvClient, self_deaf=False)

                # Start listening for speech (get the VoiceSpeechCog)
                voice_cog = bot.get_cog("VoiceSpeechCog")
                if voice_cog:
                    # Start keepalive task if needed
                    if not voice_cog._keepalive_task:
                        voice_cog._keepalive_task = bot.loop.create_task(voice_cog._keepalive_loop())

                    # Create a minimal context object for speech listener
                    class AutoRejoinContext:
                        def __init__(self, guild, voice_client):
                            self.guild = guild
                            self.voice_client = voice_client

                    ctx = AutoRejoinContext(guild, vc)
                    sink = voice_cog._create_speech_listener(ctx)
                    vc.listen(sink)
                    voice_cog.active_sinks[guild_id] = sink
                    logger.info(f"✅ Rejoined and started listening in {channel.name} ({guild.name})")
                else:
                    logger.warning(f"Rejoined {channel.name} but VoiceSpeech cog not available")

                rejoined_count += 1

            except Exception as e:
                logger.error(f"Failed to rejoin voice channel in guild {guild_id_str}: {e}")
                skipped_count += 1
                # Try to get guild/channel names for error case
                try:
                    guild = bot.get_guild(int(guild_id_str))
                    channel_id = int(state_data.get("channel_id"))
                    if guild:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            skipped_details.append(f"{guild.name}:#{channel.name} (error: {str(e)[:50]})")
                        else:
                            skipped_details.append(f"{guild.name}:#{channel_id} (error)")
                    else:
                        skipped_details.append(f"Guild {guild_id_str} (error)")
                except:
                    skipped_details.append(f"Guild {guild_id_str} (error)")
                continue

        if rejoined_count > 0:
            logger.info(f"🔊 Rejoined {rejoined_count} voice channel(s) from saved state")
        if skipped_count > 0:
            logger.info(f"⏭️  Skipped {skipped_count} channel(s): {', '.join(skipped_details)}")

    except Exception as e:
        logger.error(f"Error loading saved voice channels: {e}", exc_info=True)


@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    # Start data collection
    await data_collector.start()

    # Initialize unified config system BEFORE loading cogs
    from bot.core.config_system import ConfigManager
    config_manager = ConfigManager()
    bot.config_manager = config_manager  # Make accessible to cogs
    logger.info("⚙️ Unified configuration system initialized")

    # Load cogs from new structure (cogs can now register schemas)
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

    # Apply system config settings from ConfigManager
    try:
        sys_cfg = config_manager.for_guild("System")

        # Update log level from config
        update_log_level(sys_cfg.log_level)

        # Log feature flags
        if sys_cfg.enable_web_dashboard:
            logger.info(f"🌐 Web dashboard enabled on {sys_cfg.web_host}:{sys_cfg.web_port}")
        else:
            logger.info("🖥️  Running in headless mode - Web dashboard disabled")

        logger.info(f"🎮 Command prefix: {sys_cfg.command_prefix}")
        logger.info(f"🔊 Keepalive interval: {sys_cfg.keepalive_interval}s")

    except Exception as e:
        logger.warning(f"Could not apply system config settings: {e}")

    # Connect web dashboard to data collector if enabled
    if config.enable_web_dashboard:
        try:
            from web.websocket_manager import manager
            from web.app import set_bot_instance
            from web.routes.config import (
                set_config_manager,
                set_bot_instance as set_config_bot
            )

            data_collector.websocket_manager = manager
            set_bot_instance(bot)

            # Register config manager and bot instance with web API
            set_config_manager(config_manager)  # Unified config system
            set_config_bot(bot)  # Register bot with config routes for guilds list

            logger.info("🌐 Web dashboard connected to data collector")
        except Exception as e:
            logger.error(f"Failed to connect web dashboard: {e}", exc_info=True)

    # Rejoin voice channels from saved state if users are present
    await rejoin_saved_voice_channels()


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
