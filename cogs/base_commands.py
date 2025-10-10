import discord
from discord.ext import commands
from datetime import datetime, UTC
import os

from base_cog import BaseCog, logger

class GeneralCog(BaseCog):
    """General bot commands like status, help, info, and reload."""

    reload_time = datetime.now(UTC)

    @commands.command(name="status", help="Tells you if im alive, and how long for...")
    async def status(self, ctx):
        """Shows basic bot status and uptime."""

        local_start = self.bot.start_time.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        uptime = datetime.now(UTC) - self.bot.start_time
        since_reload = datetime.now(UTC) - self.reload_time
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green(),
            description=(
                f"**Online and operational...kinda!**\n"
                f"📅 **Started:** `{local_start}\n`"
                f"🕒 **Uptime:** `{str(uptime).split('.')[0]}`\n"
                f"♻️ **Last Reload:** `{str(since_reload).split('.')[0]}`"
            ),
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="help", help="show this sucker")
    async def helpme(self, ctx):
        """Displays a dynamic help message with available commands grouped by cog."""
        embed = discord.Embed(
            title="🧭 Bot Commands",
            color=discord.Color.blue(),
            description="Here's a list of available commands grouped by category:"
        )

        # Group commands by cog
        cogs = {}
        for command in self.bot.commands:
            if command.hidden:
                continue
            cog_name = command.cog_name or "No Category"
            if cog_name not in cogs:
                cogs[cog_name] = []
            cogs[cog_name].append(command)

        # Add commands grouped by cog to the embed
        for cog_name, commands_list in cogs.items():
            value_lines = []
            for command in commands_list:
                usage = f"`~{command.name} {command.signature}`" if command.signature else f"`~{command.name}`"
                desc = command.help or "No description available."
                value_lines.append(f"{usage} — {desc}")
            embed.add_field(name=cog_name, value="\n".join(value_lines), inline=False)

        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="info", help="Project information")
    async def info(self, ctx):
        """List dependencies from pyproject.toml without versions."""
        try:
            deps = []
            in_deps = False
            with open("pyproject.toml", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("dependencies = ["):
                        in_deps = True
                        if line.endswith("]"):
                            dep_line = line[line.index("[") + 1:line.index("]")]
                            dep_line = dep_line.strip().strip('"').split(",")
                            deps.extend([
                                d.strip().split(">=")[0].split("==")[0]
                                for d in dep_line if d.strip()
                            ])
                            break
                        continue
                    if in_deps:
                        if line.startswith("]"):
                            break
                        dep_name = line.strip().strip('"').strip(",")
                        if dep_name:
                            dep_name = dep_name.split(">=")[0].split("==")[0].split("<=")[0].strip()
                            deps.append(dep_name)
            deps_str = "\n".join(deps) if deps else "No dependencies found."
        except Exception as e:
            deps_str = f"Error reading pyproject.toml: {e}"

        embed = discord.Embed(
            title="ℹ️ Bot Info",
            color=discord.Color.blurple(),
            description="Don's Bot Thingy-ma-jig.",
        )
        embed.add_field(name="Developer", value="Don Corleon", inline=False)
        embed.add_field(name="Library", value=deps_str, inline=False)
        embed.add_field(name="Python", value="3.13+", inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        await ctx.send(embed=embed)

    @commands.command(name="reload", help="Reloads  specified cog/s or all cogs modules")
    @commands.is_owner()
    async def reload(self, ctx, cog_name: str = None):
        """Reloads all cogs, or a specific one (owner only)."""
        EXCLUDED_COGS = ["base_cog.py"]  # Add any files you want to skip

        if cog_name:
            cog_path = f"cogs.{cog_name}"
            try:
                if cog_path in self.bot.extensions:
                    await self.bot.reload_extension(cog_path)  # no await in Pycord
                    action = "reloaded"
                else:
                    await self.bot.load_extension(cog_path)  # no await
                    action = "loaded"

                embed = discord.Embed(
                    title="🔁 Cog Update",
                    description=f"Successfully {action} `{cog_name}`",
                    color=discord.Color.green(),
                )
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Reload Failed",
                    description=f"Failed to load/reload `{cog_name}`\n```\n{e}\n```",
                    color=discord.Color.red(),
                )
                logger.error(f"Failed to load/reload `{cog_name}`\n```\n{e}\n```")
        else:
            reloaded, failed = [], []
            for filename in os.listdir("./cogs"):
                if filename.endswith(".py") and filename not in EXCLUDED_COGS:
                    cog_path = f"cogs.{filename[:-3]}"
                    try:
                        if cog_path in self.bot.extensions:
                            await self.bot.reload_extension(cog_path)
                        else:
                            await self.bot.load_extension(cog_path)
                        reloaded.append(filename)
                    except Exception as e:
                        failed.append(f"{filename} — {e}")

            embed = discord.Embed(
                title="🔁 Cog Reload Report",
                color=discord.Color.gold(),
                description="Reloaded all available cogs.",
            )
            if reloaded:
                embed.add_field(name="✅ Reloaded/Loaded", value="\n".join(reloaded), inline=False)
            if failed:
                embed.add_field(name="❌ Failed", value="\n".join(failed), inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GeneralCog(bot))
