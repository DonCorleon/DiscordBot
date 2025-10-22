# cogs/monitoring.py
"""
Monitoring and health check commands with data collection integration.
"""

import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, UTC
import psutil
from typing import Optional

from bot.base_cog import BaseCog, logger
from bot.core.errors import handle_errors, ErrorCategory, UserFeedback
from bot.core.admin.data_collector import get_data_collector


class MonitoringCog(BaseCog):
    """Health monitoring and status commands."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

        # Get the existing data collector instance
        self.data_collector = get_data_collector()

        # Start monitoring tasks
        self.monitor_health.start()

        logger.info("Monitoring cog initialized")

    async def cog_load(self):
        """Start data collection when cog loads."""
        await self.data_collector.start()
        logger.info("Data collection started")

    async def cog_unload(self):
        """Stop monitoring tasks."""
        self.monitor_health.cancel()
        await self.data_collector.stop()
        logger.info("Monitoring cog unloaded")

    @tasks.loop(seconds=60)
    async def monitor_health(self):
        """Monitor bot health and log warnings."""
        try:
            process = psutil.Process()
            memory_percent = process.memory_percent()
            cpu_percent = process.cpu_percent()

            # Log warnings if resources are high
            if memory_percent > 80:
                logger.warning(f"High memory usage: {memory_percent:.1f}%")
            if cpu_percent > 80:
                logger.warning(f"High CPU usage: {cpu_percent:.1f}%")

            # Check for stale connections
            voice_cog = self.bot.get_cog("VoiceSpeechCog")
            if voice_cog and hasattr(voice_cog, 'sound_queues'):
                for guild_id, queue in voice_cog.sound_queues.items():
                    if queue.qsize() > 50:
                        logger.warning(f"Large queue in guild {guild_id}: {queue.qsize()} items")

        except Exception as e:
            logger.error(f"Error in health monitor: {e}", exc_info=True)

    @monitor_health.before_loop
    async def before_monitor_health(self):
        """Wait for bot to be ready before monitoring."""
        await self.bot.wait_until_ready()

    @commands.command(name="health", help="Show bot health and resource usage")
    @handle_errors(category=ErrorCategory.INTERNAL)
    async def health(self, ctx):
        """Display bot health metrics."""

        # Get process info
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        memory_percent = process.memory_percent()
        cpu_percent = process.cpu_percent()

        # Get bot info
        total_members = sum(g.member_count for g in self.bot.guilds)
        voice_connections = sum(1 for g in self.bot.guilds if g.voice_client)

        # Calculate uptime
        uptime = datetime.now(UTC) - self.bot.start_time if hasattr(self.bot, 'start_time') else timedelta(0)
        uptime_str = str(uptime).split('.')[0]  # Remove microseconds

        # Create health embed
        embed = discord.Embed(
            title="🏥 Bot Health Status",
            color=self._get_health_color(memory_percent, cpu_percent),
            timestamp=datetime.utcnow()
        )

        # System resources
        embed.add_field(
            name="💻 System Resources",
            value=(
                f"**Memory:** {memory_mb:.1f} MB ({memory_percent:.1f}%)\n"
                f"**CPU:** {cpu_percent:.1f}%"
            ),
            inline=True
        )

        # Bot stats
        embed.add_field(
            name="📊 Bot Statistics",
            value=(
                f"**Guilds:** {len(self.bot.guilds)}\n"
                f"**Users:** {total_members:,}\n"
                f"**Commands:** {len(self.bot.commands)}"
            ),
            inline=True
        )

        # Voice info
        embed.add_field(
            name="🔊 Voice Status",
            value=f"**Active Connections:** {voice_connections}",
            inline=True
        )

        # Uptime
        embed.add_field(
            name="⏱️ Uptime",
            value=f"`{uptime_str}`",
            inline=True
        )

        # Latency
        embed.add_field(
            name="📡 Latency",
            value=f"`{self.bot.latency * 1000:.0f}ms`",
            inline=True
        )

        # Get command stats from data collector
        if self.data_collector:
            stats = self.data_collector.command_stats
            total_commands = sum(s.total_uses for s in stats.values())
            total_errors = sum(s.errors for s in stats.values())

            embed.add_field(
                name="📝 Commands",
                value=(
                    f"**Executed:** {total_commands:,}\n"
                    f"**Errors:** {total_errors}"
                ),
                inline=True
            )

        embed.set_footer(text="Health check completed")

        await ctx.send(embed=embed)

    def _get_health_color(self, memory_percent: float, cpu_percent: float) -> discord.Color:
        """Determine embed color based on resource usage."""
        if memory_percent > 80 or cpu_percent > 80:
            return discord.Color.red()
        elif memory_percent > 60 or cpu_percent > 60:
            return discord.Color.orange()
        else:
            return discord.Color.green()

    @commands.command(name="connections", help="Show active voice connections")
    @handle_errors(category=ErrorCategory.VOICE)
    async def connections(self, ctx):
        """Display all active voice connections."""

        voice_connections = []

        for guild in self.bot.guilds:
            if guild.voice_client:
                vc = guild.voice_client
                channel = vc.channel

                # Get queue info
                queue_size = 0
                voice_cog = self.bot.get_cog("VoiceSpeechCog")
                if voice_cog and hasattr(voice_cog, 'sound_queues'):
                    queue = voice_cog.sound_queues.get(guild.id)
                    if queue:
                        queue_size = queue.qsize()

                voice_connections.append({
                    "guild": guild.name,
                    "channel": channel.name,
                    "members": len(channel.members),
                    "playing": vc.is_playing(),
                    "queue": queue_size
                })

        if not voice_connections:
            await UserFeedback.info(ctx, "No active voice connections.")
            return

        embed = discord.Embed(
            title="🔊 Active Voice Connections",
            color=discord.Color.blue(),
            description=f"Connected to {len(voice_connections)} channel(s)"
        )

        for conn in voice_connections:
            status_icons = []
            if conn["playing"]:
                status_icons.append("▶️")
            if conn["queue"] > 0:
                status_icons.append(f"🎵({conn['queue']})")

            status = " ".join(status_icons) if status_icons else "⏸️ Idle"

            embed.add_field(
                name=f"📍 {conn['guild']}",
                value=(
                    f"**Channel:** `{conn['channel']}`\n"
                    f"**Members:** {conn['members']}\n"
                    f"**Status:** {status}"
                ),
                inline=False
            )

        await ctx.send(embed=embed)

    @commands.command(name="cmdstats", help="Show command usage statistics")
    @handle_errors(category=ErrorCategory.INTERNAL)
    async def command_stats(self, ctx, limit: int = 10):
        """Display command usage statistics."""

        if not self.data_collector:
            await UserFeedback.error(ctx, "Data collector not available.")
            return

        stats = self.data_collector.command_stats

        if not stats:
            await UserFeedback.info(ctx, "No command statistics available yet.")
            return

        # Sort by total uses
        sorted_stats = sorted(
            stats.values(),
            key=lambda s: s.total_uses,
            reverse=True
        )[:limit]

        embed = discord.Embed(
            title="📊 Command Statistics",
            color=discord.Color.blue(),
            description=f"Top {len(sorted_stats)} commands"
        )

        for stat in sorted_stats:
            success_rate = (
                ((stat.total_uses - stat.errors) / stat.total_uses * 100)
                if stat.total_uses > 0 else 0
            )

            embed.add_field(
                name=f"~{stat.command_name}",
                value=(
                    f"**Uses:** {stat.total_uses}\n"
                    f"**Errors:** {stat.errors}\n"
                    f"**Success Rate:** {success_rate:.1f}%\n"
                    f"**Avg Time:** {stat.avg_execution_time:.3f}s"
                ),
                inline=True
            )

        await ctx.send(embed=embed)

    @commands.command(name="logs", help="Show recent log entries")
    @commands.is_owner()
    async def logs(self, ctx, level: str = "all", lines: int = 20):
        """
        Display recent log entries.
        Usage: ~logs [level] [lines]
        Levels: all, info, warning, error, critical
        """

        if lines > 50:
            lines = 50  # Limit to prevent spam

        if not self.data_collector:
            await UserFeedback.error(ctx, "Data collector not available.")
            return

        log_entries = self.data_collector.get_logs(level=level, limit=lines)

        if not log_entries:
            await UserFeedback.info(ctx, f"No {level} logs found.")
            return

        # Color based on level
        color_map = {
            "INFO": discord.Color.blue(),
            "WARNING": discord.Color.orange(),
            "ERROR": discord.Color.red(),
            "CRITICAL": discord.Color.dark_red()
        }

        # Group logs into chunks to avoid message length limits
        chunks = []
        current_chunk = []
        current_length = 0

        for entry in log_entries:
            log_line = f"`{entry['timestamp']}` **[{entry['level']}]** {entry['message'][:100]}"
            line_length = len(log_line)

            if current_length + line_length > 1900:  # Discord limit ~2000 chars
                chunks.append(current_chunk)
                current_chunk = [log_line]
                current_length = line_length
            else:
                current_chunk.append(log_line)
                current_length += line_length

        if current_chunk:
            chunks.append(current_chunk)

        # Send embeds
        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"📋 Recent Logs ({level.upper()})" + (f" - Part {i + 1}" if len(chunks) > 1 else ""),
                description="\n".join(chunk),
                color=discord.Color.dark_grey(),
                timestamp=datetime.utcnow()
            )
            await ctx.send(embed=embed)

    @commands.command(name="dashboard", help="Get admin dashboard data summary", hidden=True)
    @commands.is_owner()
    async def dashboard(self, ctx):
        """Display comprehensive dashboard summary."""

        if not self.data_collector:
            await UserFeedback.error(ctx, "Data collector not available.")
            return

        data = self.data_collector.get_dashboard_data()

        embed = discord.Embed(
            title="📊 Admin Dashboard",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        # Bot info
        bot_info = data['bot_info']
        embed.add_field(
            name="🤖 Bot Status",
            value=(
                f"**Guilds:** {bot_info['guilds']}\n"
                f"**Users:** {bot_info['users']:,}\n"
                f"**Uptime:** {bot_info['uptime']}"
            ),
            inline=True
        )

        # Health
        if data['health']['current']:
            health = data['health']['current']
            embed.add_field(
                name="💻 Resources",
                value=(
                    f"**CPU:** {health['cpu_percent']:.1f}%\n"
                    f"**Memory:** {health['memory_mb']:.1f}MB\n"
                    f"**Connections:** {health['active_connections']}"
                ),
                inline=True
            )

        # Commands
        cmd_data = data['commands']
        embed.add_field(
            name="📝 Commands",
            value=(
                f"**Total:** {cmd_data['total_executed']:,}\n"
                f"**Errors:** {cmd_data['total_errors']}\n"
                f"**Per Minute:** {cmd_data['commands_per_minute']}"
            ),
            inline=True
        )

        # Top commands
        if cmd_data['top_commands']:
            top_3 = cmd_data['top_commands'][:3]
            top_text = "\n".join(
                f"`{cmd['command_name']}`: {cmd['total_uses']}"
                for cmd in top_3
            )
            embed.add_field(
                name="🔝 Top Commands",
                value=top_text,
                inline=False
            )

        # Recent errors
        if data['errors']['recent']:
            recent_errors = data['errors']['recent'][-3:]
            error_text = "\n".join(
                f"• {err.get('category', 'unknown')}: {err.get('message', 'N/A')[:50]}"
                for err in recent_errors
            )
            embed.add_field(
                name="⚠️ Recent Errors",
                value=error_text or "None",
                inline=False
            )

        embed.set_footer(text="Dashboard data is exported to admin_data/ directory")

        await ctx.send(embed=embed)

    @commands.command(name="ping", help="Check bot latency")
    async def ping(self, ctx):
        """Simple ping command to check bot responsiveness."""
        latency_ms = self.bot.latency * 1000

        # Determine color based on latency
        if latency_ms < 100:
            color = discord.Color.green()
            status = "Excellent"
        elif latency_ms < 200:
            color = discord.Color.blue()
            status = "Good"
        elif latency_ms < 300:
            color = discord.Color.orange()
            status = "Fair"
        else:
            color = discord.Color.red()
            status = "Poor"

        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"**Latency:** `{latency_ms:.0f}ms`\n**Status:** {status}",
            color=color
        )

        await ctx.send(embed=embed)


async def setup(bot):
    """Load the monitoring cog."""
    try:
        await bot.add_cog(MonitoringCog(bot))
        logger.info("Monitoring cog loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load monitoring cog: {e}", exc_info=True)