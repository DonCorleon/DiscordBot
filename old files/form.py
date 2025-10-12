import discord
from discord.ext import commands
from discord.ui import View, Modal, TextInput
from datetime import datetime

class SoundUploadModal(Modal):
    def __init__(self, attachment: discord.Attachment):
        super().__init__(title="Upload Sound")
        self.attachment = attachment

        # Show file name as plain text (not an input)
        self.filename_display = f"Uploading: `{attachment.filename}`"

        # Inputs
        self.title_input = TextInput(label="Title", placeholder="Sound title")
        self.description_input = TextInput(label="Description", style=discord.TextStyle.paragraph, required=False)
        self.triggers_input = TextInput(label="Triggers (comma separated)", placeholder="e.g., hello, hi, hey", required=False)
        self.flags_input = TextInput(label="Flags (comma separated, optional)", placeholder="private, disabled", required=False)

        self.add_item(self.title_input)
        self.add_item(self.description_input)
        self.add_item(self.triggers_input)
        self.add_item(self.flags_input)

    async def on_submit(self, addsound: discord.Interaction):
        attachment = self.attachment
        title = self.title_input.value
        description = self.description_input.value
        triggers = [t.strip() for t in self.triggers_input.value.split(",") if t.strip()]
        flags = [f.strip().lower() for f in self.flags_input.value.split(",") if f.strip()]

        # Save file
        save_path = f"soundboard/{attachment.filename}"
        await attachment.save(save_path)

        sound_data = {
            "title": title,
            "description": description,
            "soundfile": save_path,
            "added_by": str(addsound.user),
            "added_date": datetime.utcnow().isoformat(),
            "triggers": triggers,
            "private": "private" in flags,
            "disabled": "disabled" in flags,
            "play_count": {"week": 0, "month": 0, "total": 0}
        }

        guild_id = str(addsound.guild_id)
        soundboard = addsound.client.soundboard  # assuming you registered it as bot.soundboard

        guild_data = soundboard.soundboard.setdefault(guild_id, {"sounds": {}})
        guild_data["sounds"][title] = sound_data

        soundboard.save_soundboard()

        await addsound.response.send_message(
            f"✅ Uploaded `{title}` successfully!\nFile: `{attachment.filename}`",
            ephemeral=True
        )

class UploadView(View):
    def __init__(self, attachment: discord.Attachment):
        super().__init__(timeout=180)
        self.attachment = attachment

    @discord.ui.button(label="Upload Sound", style=discord.ButtonStyle.primary, custom_id="upload_sound")
    async def upload_button(self, addsound: discord.Interaction, button: discord.ui.Button):
        await addsound.response.send_modal(SoundUploadModal(self.attachment))

class FormCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="addsound", help="Upload a new sound to the soundboard")
    async def addsound(self, ctx):
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a sound file with the command.")

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".mp3", ".wav", ".ogg")):
            return await ctx.send("❌ Unsupported file type. Use mp3, wav, or ogg.")

        view = UploadView(attachment)

        # Inform the user about the file and instruct them to fill the modal
        await ctx.send(
            f"✅ I have the file `{attachment.filename}` now. Click the button below and tell me its details!",
            view=view
        )

async def setup(bot):
    await bot.add_cog(FormCog(bot))
