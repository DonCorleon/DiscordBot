import os
from discord.ext import commands
from discord.ui import View, Select
from discord import SelectOption

class TestCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.per_page = 25  # items per page

    @commands.command()
    async def test(self, ctx):
        """Dynamic dropdown test for soundboard."""
        # Example sounds, replace with your real sound file names
        sounds = [f"Sound_{i}" for i in range(1, 101)]
        view = SoundboardDropdown(sounds, ctx)
        await ctx.send("Select a sound:", view=view)


class SoundboardDropdown(View):
    def __init__(self, sounds: list[str], ctx, page: int = 0):
        super().__init__(timeout=300)
        self.sounds = sounds
        self.ctx = ctx
        self.page = page
        self.per_page = 25
        self.update_dropdown()

    def update_dropdown(self):
        self.clear_items()
        total_pages = (len(self.sounds) - 1) // self.per_page + 1
        start = self.page * self.per_page
        end = start + self.per_page
        options = [SelectOption(label=s, value=s) for s in self.sounds[start:end]]

        # Add pagination options
        if self.page > 0:
            options.insert(0, SelectOption(label="◀ Previous Page", value="prev_page"))
        if self.page < total_pages - 1:
            options.append(SelectOption(label="Next Page ▶", value="next_page"))

        select = Select(placeholder=f"Page {self.page + 1}/{total_pages}", options=options)
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction):
        value = interaction.data["values"][0]

        if value == "prev_page":
            self.page -= 1
            self.update_dropdown()
            await interaction.response.edit_message(view=self)
        elif value == "next_page":
            self.page += 1
            self.update_dropdown()
            await interaction.response.edit_message(view=self)
        else:
            # Attempt to play the selected sound if user is in VC
            vc = self.ctx.voice_client
            sound_file = f"sounds/{value}.mp3"  # adjust path as needed

            if vc and os.path.isfile(sound_file):
                from discord import FFmpegPCMAudio
                source = FFmpegPCMAudio(sound_file)
                vc.play(source)
                await interaction.response.send_message(f"▶ Playing: {value}", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"⚠ Cannot play '{value}' (join VC first or file missing)", ephemeral=True
                )


async def setup(bot):
    await bot.add_cog(TestCog(bot))
