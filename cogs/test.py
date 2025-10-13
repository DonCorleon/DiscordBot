import discord
from discord.ext import commands
from discord.ui import View, Select
from datetime import datetime

from cogs.soundboard import Soundboard  # your existing soundboard cog

class TestSoundboardView(discord.ui.View):
    def __init__(self, cog: Soundboard, guild_id: str, sounds: dict, page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.sounds = list(sounds.items())
        self.page = page
        self.sounds_per_page = 4
        self.update_view()

    def update_view(self):
        self.clear_items()
        start = self.page * self.sounds_per_page
        end = start + self.sounds_per_page
        page_sounds = self.sounds[start:end]

        options = []

        # Previous page at top
        if self.page > 0:
            options.append(discord.SelectOption(label="◀ Previous", value="__prev__"))

        # Sound items
        for key, sound in page_sounds:
            triggers_text = ", ".join(sound.triggers[:3])
            if len(sound.triggers) > 3:
                triggers_text += "..."
            options.append(discord.SelectOption(
                label=sound.title[:100],
                value=key,
                description=(f"Triggers: {triggers_text}")[:100] if triggers_text else "No triggers",
                emoji="🔊"
            ))

        # Next page at bottom
        total_pages = (len(self.sounds) - 1) // self.sounds_per_page
        if self.page < total_pages:
            options.append(discord.SelectOption(label="Next ▶", value="__next__"))

        select = Select(placeholder="Select a sound...", options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data["values"][0]

        if selected in ("__prev__", "__next__"):
            if selected == "__prev__":
                self.page -= 1
            else:
                self.page += 1

            self.update_view()
            await interaction.response.edit_message(view=self)  # refresh dropdown
            return

        # Normal sound selected
        sound = dict(self.sounds)[selected]
        embed = discord.Embed(
            title=sound.title,
            description=sound.description or "No description",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Triggers", value=", ".join(sound.triggers) or "None")
        embed.add_field(name="File", value=sound.soundfile)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="test", help="Trial soundboard dropdown")
    async def test(self, ctx):
        soundboard_cog: Soundboard = self.bot.get_cog("Soundboard")
        if not soundboard_cog:
            return await ctx.send("❌ Soundboard cog not loaded!")

        guild_id = str(ctx.guild.id)
        # Filter non-private sounds
        filtered_sounds = {
            k: s for k, s in soundboard_cog.soundboard.sounds.items()
            if not s.is_private or s.guild_id == guild_id
        }

        if not filtered_sounds:
            return await ctx.send("📭 No sounds available!")

        view = TestSoundboardView(soundboard_cog, guild_id, filtered_sounds)
        await ctx.send("🎵 Select a sound:", view=view)


async def setup(bot):
    await bot.add_cog(TestCog(bot))
