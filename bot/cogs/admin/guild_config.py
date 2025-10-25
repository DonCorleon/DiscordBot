# guild_config.py
"""
Guild Configuration Commands
Allows guild admins to configure per-guild settings.
"""

import discord
from discord.ext import commands
from bot.base_cog import BaseCog, logger
from bot.core.errors import UserFeedback


class GuildConfigCog(BaseCog):
    """Commands for managing guild-specific configuration."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    async def cog_check(self, ctx):
        """Check if user has permission to use guild config commands."""
        # Allow guild administrators or bot owner
        if ctx.author.id == self.bot.config.bot_owner_id:
            return True

        if ctx.author.guild_permissions.administrator:
            return True

        # Check if user is in admin list
        if hasattr(self.bot.config, 'admin_user_ids') and ctx.author.id in self.bot.config.admin_user_ids:
            return True

        await UserFeedback.error(ctx, "You need administrator permissions to use this command!")
        return False

    @commands.group(name="guildconfig", aliases=["gc"], help="Manage guild-specific configuration")
    async def guildconfig(self, ctx):
        """Guild configuration command group."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @guildconfig.command(name="list", help="List all configurable guild settings")
    async def list_settings(self, ctx):
        """List all settings that can be configured per-guild."""
        if not hasattr(self.bot, 'guild_config'):
            return await UserFeedback.error(ctx, "Guild configuration system not available!")

        settings = self.bot.guild_config.get_overridable_settings()

        embed = discord.Embed(
            title="⚙️ Guild-Configurable Settings",
            description="These settings can be customized for your guild:",
            color=discord.Color.blue()
        )

        # Group by category
        categories = {
            "Audio/Playback": [
                "default_volume", "ducking_enabled", "ducking_level",
                "ducking_transition_ms", "auto_join_enabled", "auto_join_timeout"
            ],
            "TTS": [
                "tts_default_volume", "tts_default_rate", "tts_max_text_length",
                "edge_tts_default_volume", "edge_tts_default_voice"
            ],
            "Playback": [
                "sound_playback_timeout", "sound_queue_warning_size"
            ]
        }

        for category, keys in categories.items():
            category_settings = [s for s in keys if s in settings]
            if category_settings:
                embed.add_field(
                    name=f"📂 {category}",
                    value="\n".join([f"• `{s}`" for s in category_settings]),
                    inline=False
                )

        embed.set_footer(text="Use ~gc show <setting> to view current value • ~gc set <setting> <value> to change")
        await ctx.send(embed=embed)

    @guildconfig.command(name="show", help="Show current value of a guild setting")
    async def show_setting(self, ctx, setting: str = None):
        """Show the current value of a guild setting."""
        if not hasattr(self.bot, 'guild_config'):
            return await UserFeedback.error(ctx, "Guild configuration system not available!")

        if not setting:
            # Show all guild settings
            all_settings = self.bot.guild_config.get_all_guild_config(ctx.guild.id)

            embed = discord.Embed(
                title=f"⚙️ Guild Configuration: {ctx.guild.name}",
                color=discord.Color.blue()
            )

            for key, data in sorted(all_settings.items()):
                is_override = data['is_override']
                value = data['value']
                global_default = data['global_default']

                if is_override:
                    field_value = f"**{value}** ✏️ (Global: {global_default})"
                else:
                    field_value = f"{value} 🌐 (Using global default)"

                embed.add_field(name=key, value=field_value, inline=True)

            embed.set_footer(text="✏️ = Custom guild value • 🌐 = Using global default")
            return await ctx.send(embed=embed)

        # Show specific setting
        try:
            value = self.bot.guild_config.get_guild_config(ctx.guild.id, setting)
            is_override = self.bot.guild_config.is_guild_override(ctx.guild.id, setting)

            embed = discord.Embed(
                title=f"⚙️ Setting: {setting}",
                color=discord.Color.green() if is_override else discord.Color.blue()
            )

            embed.add_field(name="Current Value", value=f"`{value}`", inline=False)

            if is_override:
                global_value = getattr(self.bot.config, setting, "N/A")
                embed.add_field(name="Status", value="✏️ Custom guild override", inline=True)
                embed.add_field(name="Global Default", value=f"`{global_value}`", inline=True)
            else:
                embed.add_field(name="Status", value="🌐 Using global default", inline=True)

            embed.set_footer(text=f"Use ~gc set {setting} <value> to change • ~gc reset {setting} to use global default")
            await ctx.send(embed=embed)

        except Exception as e:
            await UserFeedback.error(ctx, f"Failed to get setting: {str(e)}")

    @guildconfig.command(name="set", help="Set a guild-specific configuration value")
    async def set_setting(self, ctx, setting: str, *, value: str):
        """Set a guild-specific configuration override."""
        if not hasattr(self.bot, 'guild_config'):
            return await UserFeedback.error(ctx, "Guild configuration system not available!")

        # Parse value to correct type
        try:
            # Try to parse as number
            if '.' in value:
                parsed_value = float(value)
            elif value.isdigit():
                parsed_value = int(value)
            elif value.lower() in ['true', 'false']:
                parsed_value = value.lower() == 'true'
            else:
                parsed_value = value  # Keep as string
        except:
            parsed_value = value

        # Validate through config manager if available
        if hasattr(self.bot, 'config_manager'):
            valid, error = self.bot.config_manager.validate_setting(setting, parsed_value)
            if not valid:
                return await UserFeedback.error(ctx, f"Invalid value: {error}")

        # Set the guild config
        success, error = self.bot.guild_config.set_guild_config(ctx.guild.id, setting, parsed_value)

        if success:
            await UserFeedback.success(
                ctx,
                f"✅ Set `{setting}` to `{parsed_value}` for this guild!\n"
                f"This setting will now override the global default."
            )
            logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Admin {ctx.author} set {setting} = {parsed_value}")
        else:
            await UserFeedback.error(ctx, f"Failed to set setting: {error}")

    @guildconfig.command(name="reset", help="Reset a guild setting to global default")
    async def reset_setting(self, ctx, setting: str):
        """Reset a guild setting to use the global default."""
        if not hasattr(self.bot, 'guild_config'):
            return await UserFeedback.error(ctx, "Guild configuration system not available!")

        # Get current value before reset
        old_value = self.bot.guild_config.get_guild_config(ctx.guild.id, setting)

        success, error = self.bot.guild_config.reset_guild_config(ctx.guild.id, setting)

        if success:
            new_value = self.bot.guild_config.get_guild_config(ctx.guild.id, setting)
            await UserFeedback.success(
                ctx,
                f"✅ Reset `{setting}` to global default!\n"
                f"Old value: `{old_value}` → New value: `{new_value}`"
            )
            logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Admin {ctx.author} reset {setting} to global default")
        else:
            await UserFeedback.error(ctx, f"Failed to reset setting: {error}")

    @guildconfig.command(name="reload", help="Reload guild configuration from disk")
    async def reload_config(self, ctx):
        """Reload guild configuration from disk."""
        if not hasattr(self.bot, 'guild_config'):
            return await UserFeedback.error(ctx, "Guild configuration system not available!")

        try:
            # Reload the guild configs
            self.bot.guild_config.guild_configs = self.bot.guild_config._load_guild_configs()
            await UserFeedback.success(ctx, "✅ Reloaded guild configuration from disk!")
            logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Admin {ctx.author} reloaded guild config")
        except Exception as e:
            await UserFeedback.error(ctx, f"Failed to reload: {str(e)}")
            logger.error(f"Failed to reload guild config: {e}", exc_info=True)


async def setup(bot):
    try:
        await bot.add_cog(GuildConfigCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")
