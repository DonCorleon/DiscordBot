# utils/admin_data_collector.py
"""
Data collector for admin monitoring and web dashboard.
Collects and stores metrics, logs, health data, and user info for real-time monitoring.
VERSION 3: Uses user_id as primary key to prevent duplicates from name changes.
"""

import json
import asyncio
from datetime import datetime, timedelta, UTC
from collections import deque, defaultdict
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import psutil
import logging
from bot.config import config

logger = logging.getLogger("discordbot.admin_data")


@dataclass
class HealthMetric:
    """Single health metric data point."""
    timestamp: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    active_connections: int
    queue_sizes: Dict[str, int]
    commands_per_minute: int


@dataclass
class ConnectionInfo:
    """Information about a voice connection."""
    guild_id: int
    guild_name: str
    channel_name: str
    connected_at: str
    members_count: int
    is_listening: bool
    is_playing: bool
    queue_size: int


@dataclass
class CommandStats:
    """Statistics for a command."""
    command_name: str
    total_uses: int
    errors: int
    avg_execution_time: float
    last_used: str


class AdminDataCollector:
    """
    Collects real-time data for admin monitoring interface.
    Stores data in memory and optionally exports to JSON for external access.
    """

    def __init__(self, bot, max_history: int = 1000, enable_export: bool = True):
        self.bot = bot
        self.enable_export = enable_export

        # Get config values (with fallbacks)
        sys_cfg = bot.config_manager.for_guild("System") if hasattr(bot, 'config_manager') else None
        self.max_history = sys_cfg.max_history if sys_cfg else max_history
        max_transcriptions = sys_cfg.admin_max_transcriptions if sys_cfg else 500

        # Time-series data (use configured limits)
        self.health_history: deque = deque(maxlen=self.max_history)
        self.command_history: deque = deque(maxlen=self.max_history)
        self.error_history: deque = deque(maxlen=self.max_history)
        self.transcription_history: deque = deque(maxlen=max_transcriptions)

        # Current state
        self.current_connections: Dict[int, ConnectionInfo] = {}
        self.command_stats: Dict[str, CommandStats] = {}

        # User information with avatars - KEYED BY USER_ID (v3 change)
        self.user_info: Dict[str, Dict] = {}  # {user_id: {username, display_name, avatar_url, etc}}

        # Counters
        self.commands_this_minute = 0
        self.last_minute_reset = datetime.now()

        # Data export path (default used until ConfigManager updates it in main.py on_ready)
        self.export_dir = None
        if self.enable_export:
            self.export_dir = Path("data/admin")  # Default, updated from SystemConfig.admin_data_dir
            self.export_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Data export enabled - {self.export_dir} directory created")
        else:
            logger.info("Data export disabled - running in headless mode")

        # Background tasks
        self.collection_task: Optional[asyncio.Task] = None
        self.export_task: Optional[asyncio.Task] = None

        # WebSocket manager for web dashboard (set by web server)
        self.websocket_manager = None

        # Load existing transcriptions from file if available
        self._load_existing_transcriptions()

        logger.info("Admin data collector v3 initialized (user_id based)")

    def _load_existing_transcriptions(self):
        """Load existing transcriptions from file on startup for persistence."""
        if not self.export_dir:
            return

        transcriptions_file = self.export_dir / "transcriptions.json"
        if transcriptions_file.exists():
            try:
                with open(transcriptions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    existing = data.get("transcriptions", [])

                    # Load existing transcriptions into deque (preserves order)
                    for transcription in existing:
                        self.transcription_history.append(transcription)

                    logger.info(f"Loaded {len(existing)} existing transcriptions from file")
            except Exception as e:
                logger.error(f"Failed to load existing transcriptions: {e}")

    async def start(self):
        """Start background data collection tasks."""
        if not self.collection_task or self.collection_task.done():
            self.collection_task = asyncio.create_task(self._collection_loop())

        if self.enable_export:
            if not self.export_task or self.export_task.done():
                self.export_task = asyncio.create_task(self._export_loop())
                logger.info("Data export task started")

        logger.info("Admin data collection started")

    async def stop(self):
        """Stop background tasks."""
        if self.collection_task and not self.collection_task.done():
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass

        if self.export_task and not self.export_task.done():
            self.export_task.cancel()
            try:
                await self.export_task
            except asyncio.CancelledError:
                pass

        logger.info("Admin data collection stopped")

    async def _collection_loop(self):
        """Collect metrics every N seconds."""
        await self.bot.wait_until_ready()

        try:
            while True:
                await self._collect_health_metrics()
                await self._update_connection_info()
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Collection loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in collection loop: {e}", exc_info=True)

    async def _export_loop(self):
        """Export data to JSON files every N seconds."""
        await self.bot.wait_until_ready()

        try:
            while True:
                await self._export_data()
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            logger.info("Export loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in export loop: {e}", exc_info=True)

    async def _collect_health_metrics(self):
        """Collect system and bot health metrics."""
        try:
            process = psutil.Process()
            cpu_percent = process.cpu_percent()
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = process.memory_percent()

            active_connections = sum(1 for guild in self.bot.guilds if guild.voice_client)

            queue_sizes = {}
            voice_cog = self.bot.get_cog("VoiceSpeechCog")
            if voice_cog and hasattr(voice_cog, 'sound_queues'):
                queue_sizes = {
                    str(guild_id): queue.qsize()
                    for guild_id, queue in voice_cog.sound_queues.items()
                }

            now = datetime.now()
            if (now - self.last_minute_reset).seconds >= 60:
                self.commands_this_minute = 0
                self.last_minute_reset = now

            metric = HealthMetric(
                timestamp=now.isoformat(),
                cpu_percent=cpu_percent,
                memory_mb=memory_mb,
                memory_percent=memory_percent,
                active_connections=active_connections,
                queue_sizes=queue_sizes,
                commands_per_minute=self.commands_this_minute
            )

            self.health_history.append(asdict(metric))

        except Exception as e:
            logger.error(f"Error collecting health metrics: {e}", exc_info=True)

    async def _update_connection_info(self):
        """Update current voice connection information."""
        try:
            self.current_connections.clear()

            voice_cog = self.bot.get_cog("VoiceSpeechCog")
            if not voice_cog:
                return

            for guild in self.bot.guilds:
                if not guild.voice_client:
                    continue

                vc = guild.voice_client
                channel = vc.channel
                guild_id = guild.id

                is_listening = guild_id in getattr(voice_cog, 'active_sinks', {})
                is_playing = vc.is_playing()
                queue_size = 0

                if hasattr(voice_cog, 'sound_queues') and guild_id in voice_cog.sound_queues:
                    queue_size = voice_cog.sound_queues[guild_id].qsize()

                connected_at = datetime.now().isoformat()

                conn_info = ConnectionInfo(
                    guild_id=guild_id,
                    guild_name=guild.name,
                    channel_name=channel.name,
                    connected_at=connected_at,
                    members_count=len(channel.members),
                    is_listening=is_listening,
                    is_playing=is_playing,
                    queue_size=queue_size
                )

                self.current_connections[guild_id] = conn_info

        except Exception as e:
            logger.error(f"Error updating connection info: {e}", exc_info=True)

    def update_user_info(self, user):
        """
        Update user information including avatar URL.
        Call this whenever a user is active (speaking, commands, etc).
        V3: Uses user_id as the primary key (permanent identifier).
        """
        try:
            user_id = str(user.id)  # V3: Use user_id as key
            username = str(user)

            # Get avatar URL
            if hasattr(user, 'avatar') and user.avatar:
                avatar_url = user.avatar.url
            elif hasattr(user, 'default_avatar'):
                avatar_url = user.default_avatar.url
            else:
                # Fallback for older Discord.py versions
                discriminator = getattr(user, 'discriminator', '0')
                if discriminator == '0' or discriminator is None:
                    # New username system (no discriminator)
                    avatar_url = f"https://cdn.discordapp.com/embed/avatars/{user.id % 6}.png"
                else:
                    # Old system with discriminator
                    avatar_url = f"https://cdn.discordapp.com/embed/avatars/{int(discriminator) % 5}.png"

            # Get display name
            display_name = username
            if hasattr(user, 'display_name'):
                display_name = user.display_name
            elif hasattr(user, 'global_name') and user.global_name:
                display_name = user.global_name

            # V3: Store by user_id (not username)
            self.user_info[user_id] = {
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "discriminator": getattr(user, 'discriminator', '0'),
                "last_seen": datetime.now().isoformat()
            }

            logger.debug(f"Updated user info for {user_id} ({display_name}): {avatar_url}")

        except Exception as e:
            logger.error(f"Error updating user info for {user}: {e}", exc_info=True)

    def broadcast_event(self, event_type: str, data: Dict[str, Any]):
        """
        Send event immediately to web dashboard clients via WebSocket.
        Non-blocking - creates task if manager is available.
        """
        if self.websocket_manager and hasattr(self.websocket_manager, 'get_connection_count'):
            connection_count = self.websocket_manager.get_connection_count()
            logger.info(f"Broadcasting {event_type} event to {connection_count} WebSocket clients")

            if connection_count > 0:
                # Use bot's event loop to schedule the coroutine
                try:
                    loop = self.bot.loop
                    if loop and loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.websocket_manager.broadcast({
                                "type": event_type,
                                "data": data,
                                "timestamp": datetime.now().isoformat()
                            }),
                            loop
                        )
                        logger.debug(f"Successfully queued broadcast for {event_type}")
                    else:
                        logger.warning(f"Bot loop not running, cannot broadcast {event_type}")
                except Exception as e:
                    logger.error(f"Failed to broadcast event {event_type}: {e}", exc_info=True)
            else:
                logger.debug(f"No WebSocket clients connected, skipping {event_type} broadcast")
        else:
            logger.debug(f"WebSocket manager not available for {event_type} broadcast")

    def record_command(self, command_name: str, execution_time: float, success: bool):
        """Record a command execution."""
        self.commands_this_minute += 1

        if command_name not in self.command_stats:
            self.command_stats[command_name] = CommandStats(
                command_name=command_name,
                total_uses=0,
                errors=0,
                avg_execution_time=0.0,
                last_used=datetime.now().isoformat()
            )

        stats = self.command_stats[command_name]
        stats.total_uses += 1
        if not success:
            stats.errors += 1

        stats.avg_execution_time = (
                (stats.avg_execution_time * (stats.total_uses - 1) + execution_time)
                / stats.total_uses
        )
        stats.last_used = datetime.now().isoformat()

        self.command_history.append({
            "timestamp": datetime.now().isoformat(),
            "command": command_name,
            "execution_time": execution_time,
            "success": success
        })

        # Broadcast command event to web dashboard
        self.broadcast_event("command", {
            "name": command_name,
            "execution_time": execution_time,
            "success": success
        })

    def record_error(self, error_data: dict):
        """Record an error occurrence."""
        self.error_history.append({
            "timestamp": datetime.now().isoformat(),
            **error_data
        })

    def record_transcription(self, transcription_data: dict):
        """
        Record a voice transcription.

        Args:
            transcription_data: Dict with timestamp, guild_id, guild, channel_id, channel,
                               user_id, user, text, triggers
        """
        self.transcription_history.append(transcription_data)

        # Broadcast transcription event to web dashboard in real-time
        # Convert IDs to strings for JavaScript compatibility
        broadcast_data = transcription_data.copy()
        if "guild_id" in broadcast_data:
            broadcast_data["guild_id"] = str(broadcast_data["guild_id"])
        if "channel_id" in broadcast_data:
            broadcast_data["channel_id"] = str(broadcast_data["channel_id"])

        self.broadcast_event("transcription", broadcast_data)

    async def _export_data(self):
        """Export all collected data to JSON files."""
        if not self.enable_export or not self.export_dir:
            return

        try:
            with open(self.export_dir / "health.json", "w") as f:
                json.dump({
                    "current": self.health_history[-1] if self.health_history else None,
                    "history": list(self.health_history)
                }, f, indent=2)

            with open(self.export_dir / "connections.json", "w") as f:
                json.dump({
                    "connections": [asdict(conn) for conn in self.current_connections.values()]
                }, f, indent=2)

            # Get export limits from config (hot-swappable)
            sys_cfg = self.bot.config_manager.for_guild("System") if hasattr(self.bot, 'config_manager') else None
            commands_limit = sys_cfg.admin_recent_commands_limit if sys_cfg else 100
            errors_limit = sys_cfg.admin_recent_errors_limit if sys_cfg else 100

            with open(self.export_dir / "commands.json", "w") as f:
                json.dump({
                    "stats": [asdict(stats) for stats in self.command_stats.values()],
                    "recent_history": list(self.command_history)[-commands_limit:]
                }, f, indent=2)

            with open(self.export_dir / "errors.json", "w") as f:
                json.dump({
                    "recent": list(self.error_history)[-errors_limit:]
                }, f, indent=2)

            # V3: Export user info keyed by user_id
            with open(self.export_dir / "user_info.json", "w") as f:
                json.dump({
                    "users": self.user_info,  # V3: Simple - keyed by user_id
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)

            # Export transcriptions (last 500)
            with open(self.export_dir / "transcriptions.json", "w") as f:
                json.dump({
                    "transcriptions": list(self.transcription_history),
                    "count": len(self.transcription_history),
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)

            # Calculate uptime
            uptime_seconds = None
            uptime_str = "Unknown"
            if hasattr(self.bot, 'start_time'):
                uptime_delta = datetime.now(UTC) - self.bot.start_time
                uptime_seconds = int(uptime_delta.total_seconds())

                # Format uptime as human-readable string
                days = uptime_seconds // 86400
                hours = (uptime_seconds % 86400) // 3600
                minutes = (uptime_seconds % 3600) // 60
                seconds = uptime_seconds % 60

                if days > 0:
                    uptime_str = f"{days}d {hours}h {minutes}m"
                elif hours > 0:
                    uptime_str = f"{hours}h {minutes}m"
                elif minutes > 0:
                    uptime_str = f"{minutes}m {seconds}s"
                else:
                    uptime_str = f"{seconds}s"

            # Get latency (in milliseconds)
            latency_ms = round(self.bot.latency * 1000, 1) if self.bot.latency is not None else None

            with open(self.export_dir / "summary.json", "w") as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "bot_info": {
                        "guilds": len(self.bot.guilds),
                        "users": sum(g.member_count for g in self.bot.guilds),
                        "commands_loaded": len(self.bot.commands),
                        "cogs_loaded": len(self.bot.cogs),
                        "uptime": uptime_str,
                        "uptime_seconds": uptime_seconds,
                        "latency_ms": latency_ms
                    },
                    "health": {
                        "cpu_percent": self.health_history[-1]["cpu_percent"] if self.health_history else 0,
                        "memory_mb": self.health_history[-1]["memory_mb"] if self.health_history else 0,
                        "active_connections": len(self.current_connections),
                        "total_commands": sum(s.total_uses for s in self.command_stats.values()),
                        "total_errors": sum(s.errors for s in self.command_stats.values())
                    }
                }, f, indent=2)

        except Exception as e:
            logger.error(f"Error exporting data: {e}", exc_info=True)

    def get_dashboard_data(self) -> dict:
        """Get all data formatted for dashboard display."""
        return {
            "timestamp": datetime.now().isoformat(),
            "health": {
                "current": self.health_history[-1] if self.health_history else None,
                "history_1m": list(self.health_history)[-12:],
                "history_5m": list(self.health_history)[-60:],
            },
            "connections": {
                "active": [asdict(conn) for conn in self.current_connections.values()],
                "count": len(self.current_connections)
            },
            "commands": {
                "total_executed": sum(s.total_uses for s in self.command_stats.values()),
                "total_errors": sum(s.errors for s in self.command_stats.values()),
                "commands_per_minute": self.commands_this_minute,
                "top_commands": sorted(
                    [asdict(s) for s in self.command_stats.values()],
                    key=lambda x: x["total_uses"],
                    reverse=True
                )[:10],
                "recent": list(self.command_history)[-20:]
            },
            "errors": {
                "recent": list(self.error_history)[-20:],
                "total": len(self.error_history)
            },
            "bot_info": {
                "guilds": len(self.bot.guilds),
                "users": sum(g.member_count for g in self.bot.guilds),
                "commands_loaded": len(self.bot.commands),
                "cogs_loaded": len(self.bot.cogs),
                "uptime": str(datetime.now() - self.bot.start_time) if hasattr(self.bot, 'start_time') else "Unknown"
            }
        }

    def get_logs(self, level: str = "all", limit: int = 100) -> List[dict]:
        """Get recent log entries."""
        log_file = Path("logs/discordbot.log")
        if not log_file.exists():
            return []

        logs = []
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()[-limit:]

                for line in lines:
                    if not line.strip():
                        continue

                    try:
                        parts = line.split("]", 2)
                        if len(parts) >= 3:
                            timestamp = parts[0].strip("[")
                            log_level = parts[1].strip("[ ")
                            message = parts[2].strip()

                            if level != "all" and log_level.lower() != level.lower():
                                continue

                            logs.append({
                                "timestamp": timestamp,
                                "level": log_level,
                                "message": message
                            })
                    except:
                        continue

        except Exception as e:
            logger.error(f"Error reading logs: {e}")

        return logs


# Global instance
_data_collector: Optional[AdminDataCollector] = None


def get_data_collector() -> Optional[AdminDataCollector]:
    """Get the global data collector instance."""
    return _data_collector


def initialize_data_collector(bot, max_history: int = 1000, enable_export: bool = True):
    """Initialize the global data collector."""
    global _data_collector
    _data_collector = AdminDataCollector(bot, max_history=max_history, enable_export=enable_export)
    return _data_collector