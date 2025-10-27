# guild_config.py
"""
Guild Configuration Commands
Allows guild admins to configure per-guild settings via Discord commands.
Uses the unified ConfigManager system.
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
        if not hasattr(self.bot, 'config_manager'):
            return await UserFeedback.error(ctx, "Configuration system not available!")

        # Get all guild-overridable settings from registered schemas
        categorized = {}

        for cog_name, schema in self.bot.config_manager.schemas.items():
            for field_name, field_meta in schema.fields.items():
                if not field_meta.guild_override:
                    continue

                category = field_meta.category
                if category not in categorized:
                    categorized[category] = []

                categorized[category].append(f"{cog_name}.{field_name}")

        embed = discord.Embed(
            title="⚙️ Guild-Configurable Settings",
            description="These settings can be customized for your guild:",
            color=discord.Color.blue()
        )

        for category in sorted(categorized.keys()):
            settings = sorted(categorized[category])
            embed.add_field(
                name=f"📂 {category}",
                value="\n".join([f"• `{s}`" for s in settings]),
                inline=False
            )

        embed.set_footer(text="Use ~gc show <setting> to view • ~gc set <setting> <value> to change")
        await ctx.send(embed=embed)

    @guildconfig.command(name="show", help="Show current value of a guild setting")
    async def show_setting(self, ctx, *, setting: str = None):
        """Show the current value of a guild setting."""
        if not hasattr(self.bot, 'config_manager'):
            return await UserFeedback.error(ctx, "Configuration system not available!")

        if not setting:
            # Show all guild settings
            categorized = {}

            for cog_name, schema in self.bot.config_manager.schemas.items():
                for field_name, field_meta in schema.fields.items():
                    if not field_meta.guild_override:
                        continue

                    category = field_meta.category
                    if category not in categorized:
                        categorized[category] = {}

                    key = f"{cog_name}.{field_name}"
                    guild_value = self.bot.config_manager.get(cog_name, field_name, ctx.guild.id)
                    global_value = self.bot.config_manager.get(cog_name, field_name)

                    # Check if guild override exists
                    is_override = False
                    if ctx.guild.id in self.bot.config_manager.guild_overrides:
                        if cog_name in self.bot.config_manager.guild_overrides[ctx.guild.id]:
                            if field_name in self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name]:
                                is_override = True

                    categorized[category][key] = {
                        "value": guild_value,
                        "global": global_value,
                        "is_override": is_override
                    }

            embed = discord.Embed(
                title=f"⚙️ Guild Configuration: {ctx.guild.name}",
                color=discord.Color.blue()
            )

            for category in sorted(categorized.keys()):
                lines = []
                for key in sorted(categorized[category].keys()):
                    data = categorized[category][key]
                    value = data['value']
                    is_override = data['is_override']

                    if is_override:
                        lines.append(f"✏️ `{key}`: **{value}**")
                    else:
                        lines.append(f"🌐 `{key}`: {value}")

                if lines:
                    embed.add_field(
                        name=f"📂 {category}",
                        value="\n".join(lines),
                        inline=False
                    )

            embed.set_footer(text="✏️ = Custom guild value • 🌐 = Using global default")
            return await ctx.send(embed=embed)

        # Show specific setting (format: "CogName.field_name")
        try:
            if "." not in setting:
                return await UserFeedback.error(
                    ctx,
                    f"Invalid setting format. Use: `CogName.field_name`\n"
                    f"Example: `TTS.tts_default_volume`\n"
                    f"Use `~gc list` to see all available settings."
                )

            cog_name, field_name = setting.split(".", 1)

            # Validate setting exists
            if cog_name not in self.bot.config_manager.schemas:
                return await UserFeedback.error(ctx, f"Unknown cog: {cog_name}")

            schema = self.bot.config_manager.schemas[cog_name]
            if field_name not in schema.fields:
                return await UserFeedback.error(ctx, f"Unknown setting: {field_name} in {cog_name}")

            field_meta = schema.fields[field_name]

            if not field_meta.guild_override:
                return await UserFeedback.error(ctx, f"Setting `{setting}` cannot be overridden per-guild")

            # Get values
            guild_value = self.bot.config_manager.get(cog_name, field_name, ctx.guild.id)
            global_value = self.bot.config_manager.get(cog_name, field_name)

            # Check if guild override exists
            is_override = False
            if ctx.guild.id in self.bot.config_manager.guild_overrides:
                if cog_name in self.bot.config_manager.guild_overrides[ctx.guild.id]:
                    if field_name in self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name]:
                        is_override = True

            embed = discord.Embed(
                title=f"⚙️ Setting: {setting}",
                description=field_meta.description,
                color=discord.Color.green() if is_override else discord.Color.blue()
            )

            embed.add_field(name="Current Value", value=f"`{guild_value}`", inline=False)

            if is_override:
                embed.add_field(name="Status", value="✏️ Custom guild override", inline=True)
                embed.add_field(name="Global Default", value=f"`{global_value}`", inline=True)
            else:
                embed.add_field(name="Status", value="🌐 Using global default", inline=True)

            # Add constraints if applicable
            constraints = []
            if field_meta.min_value is not None:
                constraints.append(f"Min: {field_meta.min_value}")
            if field_meta.max_value is not None:
                constraints.append(f"Max: {field_meta.max_value}")
            if field_meta.choices:
                constraints.append(f"Choices: {', '.join(str(c) for c in field_meta.choices)}")

            if constraints:
                embed.add_field(name="Constraints", value=" • ".join(constraints), inline=False)

            embed.set_footer(text=f"Use ~gc set {setting} <value> to change • ~gc reset {setting} to use global")
            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to show setting {setting}: {e}", exc_info=True)
            await UserFeedback.error(ctx, f"Failed to get setting: {str(e)}")

    @guildconfig.command(name="set", help="Set a guild-specific configuration value")
    async def set_setting(self, ctx, setting: str, *, value: str):
        """Set a guild-specific configuration override."""
        if not hasattr(self.bot, 'config_manager'):
            return await UserFeedback.error(ctx, "Configuration system not available!")

        try:
            if "." not in setting:
                return await UserFeedback.error(
                    ctx,
                    f"Invalid setting format. Use: `CogName.field_name`\n"
                    f"Example: `TTS.tts_default_volume 1.2`"
                )

            cog_name, field_name = setting.split(".", 1)

            # Validate setting exists
            if cog_name not in self.bot.config_manager.schemas:
                return await UserFeedback.error(ctx, f"Unknown cog: {cog_name}")

            schema = self.bot.config_manager.schemas[cog_name]
            if field_name not in schema.fields:
                return await UserFeedback.error(ctx, f"Unknown setting: {field_name} in {cog_name}")

            field_meta = schema.fields[field_name]

            if not field_meta.guild_override:
                return await UserFeedback.error(ctx, f"Setting `{setting}` cannot be overridden per-guild")

            # Parse value to correct type
            try:
                if field_meta.type == bool:
                    parsed_value = value.lower() in ['true', '1', 'yes', 'on']
                elif field_meta.type == int:
                    parsed_value = int(value)
                elif field_meta.type == float:
                    parsed_value = float(value)
                else:
                    parsed_value = value
            except (ValueError, TypeError):
                return await UserFeedback.error(
                    ctx,
                    f"Invalid value type. Expected {field_meta.type.__name__}, got: {value}"
                )

            # Set the guild config (validation happens automatically)
            success, error = self.bot.config_manager.set(cog_name, field_name, parsed_value, ctx.guild.id)

            if success:
                # Save to disk
                self.bot.config_manager.save()

                await UserFeedback.success(
                    ctx,
                    f"✅ Set `{setting}` to `{parsed_value}` for this guild!\n"
                    f"This setting will now override the global default."
                )
                logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Admin {ctx.author} set {setting} = {parsed_value}")
            else:
                await UserFeedback.error(ctx, f"Validation failed: {error}")

        except Exception as e:
            logger.error(f"Failed to set {setting}: {e}", exc_info=True)
            await UserFeedback.error(ctx, f"Failed to set setting: {str(e)}")

    @guildconfig.command(name="reset", help="Reset a guild setting to global default")
    async def reset_setting(self, ctx, *, setting: str):
        """Reset a guild setting to use the global default."""
        if not hasattr(self.bot, 'config_manager'):
            return await UserFeedback.error(ctx, "Configuration system not available!")

        try:
            if "." not in setting:
                return await UserFeedback.error(
                    ctx,
                    f"Invalid setting format. Use: `CogName.field_name`\n"
                    f"Example: `TTS.tts_default_volume`"
                )

            cog_name, field_name = setting.split(".", 1)

            # Validate setting exists
            if cog_name not in self.bot.config_manager.schemas:
                return await UserFeedback.error(ctx, f"Unknown cog: {cog_name}")

            schema = self.bot.config_manager.schemas[cog_name]
            if field_name not in schema.fields:
                return await UserFeedback.error(ctx, f"Unknown setting: {field_name} in {cog_name}")

            # Get current value before reset
            old_value = self.bot.config_manager.get(cog_name, field_name, ctx.guild.id)

            # Check if guild override exists
            if ctx.guild.id not in self.bot.config_manager.guild_overrides:
                return await UserFeedback.error(ctx, f"No overrides found for this guild")

            if cog_name not in self.bot.config_manager.guild_overrides[ctx.guild.id]:
                return await UserFeedback.error(ctx, f"No overrides for {cog_name} in this guild")

            if field_name not in self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name]:
                return await UserFeedback.error(ctx, f"Setting `{setting}` is not overridden for this guild")

            # Remove the override
            del self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name][field_name]

            # Clean up empty dicts
            if not self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name]:
                del self.bot.config_manager.guild_overrides[ctx.guild.id][cog_name]
            if not self.bot.config_manager.guild_overrides[ctx.guild.id]:
                del self.bot.config_manager.guild_overrides[ctx.guild.id]

            # Invalidate cache
            self.bot.config_manager._invalidate_cache(cog_name, field_name, ctx.guild.id)

            # Save to disk
            self.bot.config_manager.save()

            # Get new value
            new_value = self.bot.config_manager.get(cog_name, field_name, ctx.guild.id)

            await UserFeedback.success(
                ctx,
                f"✅ Reset `{setting}` to global default!\n"
                f"Old value: `{old_value}` → New value: `{new_value}`"
            )
            logger.info(f"[Guild {ctx.guild.id}:{ctx.guild.name}] Admin {ctx.author} reset {setting} to global default")

        except Exception as e:
            logger.error(f"Failed to reset {setting}: {e}", exc_info=True)
            await UserFeedback.error(ctx, f"Failed to reset setting: {str(e)}")

    @guildconfig.command(name="reload", help="Reload guild configuration from disk")
    async def reload_config(self, ctx):
        """Reload guild configuration from disk."""
        if not hasattr(self.bot, 'config_manager'):
            return await UserFeedback.error(ctx, "Configuration system not available!")

        try:
            # Reload the guild configs
            self.bot.config_manager.reload(ctx.guild.id)
            await UserFeedback.success(ctx, f"✅ Reloaded configuration for {ctx.guild.name}!")
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
