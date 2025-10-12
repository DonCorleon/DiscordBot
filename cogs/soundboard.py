import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import traceback

import discord
from discord.ext import commands
from discord.ui import View, Button, Select

from base_cog import BaseCog, logger

# -----------------------
# soundboard.json format
# -----------------------
# guild id
#       title = ?
#           triggers = []
#           soundfile = filename
#           description = string
#           added by = discord member
#           added date = date
#           number of times played
#               week = int
#               month = int
#               total  = int
# -----------------------

# -----------------------
# To Add:
# load soundboard json ✅
# view sounds and trigger Descriptions ✅
# edit triggers (record transcribed word and text entry plus word removal)
# add triggers  (record transcribed word and text entry)
# upload sound
# remove sounds (admin)
# queue the sound? or return the sound
#   update play stats etc
# -----------------------

SOUNDBOARD_FILE = "soundboard.json"


# -------- Dataclasses --------

@dataclass
class PlayStats:
    week: int = 0
    month: int = 0
    total: int = 0
    guild_play_count: Dict[str, int] = field(default_factory=dict)
    last_played: Optional[str] = None
    played_by: List[str] = field(default_factory=list)


@dataclass
class AudioMetadata:
    duration: Optional[float] = None
    volume_adjust: float = 1.0


@dataclass
class SoundSettings:
    cooldown: int = 0
    autoplay: bool = False


@dataclass
class SoundEntry:
    title: str
    triggers: List[str]
    soundfile: str
    description: str
    added_by: str
    added_by_id: str
    added_date: str
    last_edited_by: Optional[str] = None
    is_private: bool = False
    is_disabled: bool = False
    approved: bool = True
    play_stats: PlayStats = field(default_factory=PlayStats)
    audio_metadata: AudioMetadata = field(default_factory=AudioMetadata)
    settings: SoundSettings = field(default_factory=SoundSettings)


@dataclass
class GuildSoundboard:
    guild_id: str
    sounds: Dict[str, SoundEntry] = field(default_factory=dict)


# -------- Utility Functions --------

def load_soundboard(file_path: str) -> Dict[str, GuildSoundboard]:
    """
    Load the soundboard JSON into structured dataclasses.

    Args:
        file_path: Path to the soundboard JSON file

    Returns:
        Dictionary of guild IDs to GuildSoundboard objects

    Raises:
        FileNotFoundError: If the file doesn't exist
        json.JSONDecodeError: If the JSON is malformed
    """
    logger.info(f"Loading soundboard from '{file_path}'...")

    try:
        if not Path(file_path).exists():
            logger.error(f"Soundboard file not found: {file_path}")
            raise FileNotFoundError(f"Soundboard file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            logger.error(f"Invalid soundboard format: Expected dict, got {type(data)}")
            raise ValueError("Invalid soundboard format: root must be a dictionary")

        guilds = {}
        total_sounds = 0

        for guild_id, sounds in data.items():
            if not isinstance(sounds, dict):
                logger.warning(f"Skipping guild '{guild_id}': Invalid format (expected dict)")
                continue

            entries = {}
            for key, sound_data in sounds.items():
                try:
                    # Manually reconstruct nested dataclasses
                    if 'play_stats' in sound_data and isinstance(sound_data['play_stats'], dict):
                        sound_data['play_stats'] = PlayStats(**sound_data['play_stats'])

                    if 'audio_metadata' in sound_data and isinstance(sound_data['audio_metadata'], dict):
                        sound_data['audio_metadata'] = AudioMetadata(**sound_data['audio_metadata'])

                    if 'settings' in sound_data and isinstance(sound_data['settings'], dict):
                        sound_data['settings'] = SoundSettings(**sound_data['settings'])

                    entries[key] = SoundEntry(**sound_data)
                    total_sounds += 1
                except Exception as e:
                    logger.error(f"Failed to load sound '{key}' in guild '{guild_id}': {e}")
                    continue

            guilds[guild_id] = GuildSoundboard(guild_id, entries)
            logger.info(f"Loaded {len(entries)} sound(s) for guild '{guild_id}'")

        logger.info(f"Successfully loaded {total_sounds} total sound(s) across {len(guilds)} guild(s)")
        return guilds

    except FileNotFoundError:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from '{file_path}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error loading soundboard: {e}", exc_info=True)
        raise


def save_soundboard(file_path: str, soundboard: Dict[str, GuildSoundboard]):
    """
    Save dataclasses back to JSON.

    Args:
        file_path: Path to save the soundboard JSON file
        soundboard: Dictionary of guild IDs to GuildSoundboard objects

    Raises:
        IOError: If unable to write to file
    """
    logger.info(f"Saving soundboard to '{file_path}'...")

    try:
        # Count total sounds for logging
        total_sounds = sum(len(g.sounds) for g in soundboard.values())

        # Create backup of existing file if it exists
        if Path(file_path).exists():
            backup_path = f"{file_path}.backup"
            try:
                import shutil
                shutil.copy2(file_path, backup_path)
                logger.debug(f"Created backup: {backup_path}")
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")

        # Convert to JSON-serializable format
        data = {
            gid: {k: asdict(v) for k, v in g.sounds.items()}
            for gid, g in soundboard.items()
        }

        # Write to file
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully saved {total_sounds} sound(s) across {len(soundboard)} guild(s)")

    except IOError as e:
        logger.error(f"Failed to write soundboard to '{file_path}': {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Unexpected error saving soundboard: {e}", exc_info=True)
        print(soundboard)
        raise


# -------- Discord UI Components --------

class SoundUploadModal(discord.ui.Modal, title="Upload Sound"):
    """
    Modal for uploading a new sound with metadata.

    Collects title, description, triggers, and flags for a sound file.
    """

    def __init__(self, cog, guild_id: str, attachment: discord.Attachment):
        """
        Initialize upload modal.

        Args:
            cog: Reference to Soundboard cog
            guild_id: Discord guild ID
            attachment: The audio file being uploaded
        """
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.attachment = attachment

        # Add text inputs
        self.title_input = discord.ui.TextInput(
            label="Title",
            placeholder="Sound title",
            required=True,
            max_length=100
        )
        self.add_item(self.title_input)

        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Describe this sound...",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500
        )
        self.add_item(self.description_input)

        self.triggers_input = discord.ui.TextInput(
            label="Triggers (comma separated)",
            placeholder="e.g., hello, hi, hey",
            required=True,
            max_length=500
        )
        self.add_item(self.triggers_input)

        self.flags_input = discord.ui.TextInput(
            label="Flags (optional)",
            placeholder="private, disabled",
            required=False,
            max_length=100
        )
        self.add_item(self.flags_input)

    async def on_submit(self, interaction: discord.Interaction):
        """
        Handle sound upload submission.

        Flow:
        1. Extract and validate input values
        2. Save audio file to soundboard directory
        3. Add sound entry to JSON via add_sound()
        4. Send confirmation to user

        Args:
            interaction: Discord interaction from modal submission
        """
        try:
            attachment = self.attachment
            title = self.title_input.value.strip()
            description = self.description_input.value.strip()
            triggers = [t.strip() for t in self.triggers_input.value.split(",") if t.strip()]
            flags = [f.strip().lower() for f in self.flags_input.value.split(",") if f.strip()]

            # Validate triggers
            if not triggers:
                await interaction.response.send_message("❌ At least one trigger is required!", ephemeral=True)
                return

            # Save file to soundboard directory
            Path("soundboard").mkdir(exist_ok=True)
            save_path = f"soundboard/{attachment.filename}"
            await attachment.save(save_path)
            logger.info(f"Saved attachment to {save_path}")

            # Add sound to soundboard
            await self.cog.add_sound(
                guild_id=self.guild_id,
                title=title,
                soundfile=save_path,
                added_by=str(interaction.user),
                added_by_id=str(interaction.user.id),
                description=description,
                triggers=triggers,
                is_private="private" in flags,
                is_disabled="disabled" in flags
            )

            # Build response
            status_text = []
            if "private" in flags:
                status_text.append("🔒 Private")
            if "disabled" in flags:
                status_text.append("⚠️ Disabled")

            response = f"✅ Uploaded `{title}` successfully!\n"
            response += f"**File:** `{attachment.filename}`\n"
            response += f"**Triggers:** {', '.join(f'`{t}`' for t in triggers)}\n"
            if status_text:
                response += f"**Status:** {' • '.join(status_text)}"

            await interaction.response.send_message(response, ephemeral=True)
            logger.info(f"[{self.guild_id}] Sound '{title}' uploaded by {interaction.user}")

        except Exception as e:
            logger.error(f"Failed to upload sound: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to upload sound!", ephemeral=True)


class SoundUploadView(View):
    """
    View for confirming sound upload.

    Displays a button that opens the upload modal when clicked.
    """

    def __init__(self, cog, guild_id: str, attachment: discord.Attachment):
        """
        Initialize upload view.

        Args:
            cog: Reference to Soundboard cog
            guild_id: Discord guild ID
            attachment: The audio file being uploaded
        """
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.attachment = attachment

    @discord.ui.button(label="📤 Upload Sound", style=discord.ButtonStyle.primary, custom_id="upload_sound")
    async def upload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Open modal to upload sound.

        Args:
            interaction: Discord interaction from button click
            button: The button that was clicked
        """
        modal = SoundUploadModal(self.cog, self.guild_id, self.attachment)
        await interaction.response.send_modal(modal)


class SoundEditView(View):
    """View for editing sound properties."""

    def __init__(self, cog, guild_id: str, sound_key: str, sound: SoundEntry):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.sound_key = sound_key
        self.sound = sound

        # Add toggle buttons based on current state
        self._add_buttons()

    def _add_buttons(self):
        """Add buttons based on current sound state."""
        self.clear_items()

        # Edit triggers button
        edit_triggers_btn = Button(
            label="✏️ Edit Triggers",
            style=discord.ButtonStyle.primary,
            custom_id="edit_triggers"
        )
        edit_triggers_btn.callback = self.edit_triggers
        self.add_item(edit_triggers_btn)

        # Edit description button
        edit_desc_btn = Button(
            label="📝 Edit Description",
            style=discord.ButtonStyle.primary,
            custom_id="edit_description"
        )
        edit_desc_btn.callback = self.edit_description
        self.add_item(edit_desc_btn)

        # Status button showing current disabled state (click to toggle)
        if self.sound.is_disabled:
            status_label = "⚠️ Disabled"
            status_style = discord.ButtonStyle.danger
        else:
            status_label = "✅ Available"
            status_style = discord.ButtonStyle.success

        toggle_disabled_btn = Button(
            label=status_label,
            style=status_style,
            custom_id="toggle_disabled"
        )
        toggle_disabled_btn.callback = self.toggle_disabled
        self.add_item(toggle_disabled_btn)

        # Status button showing current private state (click to toggle)
        if self.sound.is_private:
            private_label = "🔒 Private"
            private_style = discord.ButtonStyle.danger
        else:
            private_label = "🔓 Public"
            private_style = discord.ButtonStyle.success

        toggle_private_btn = Button(
            label=private_label,
            style=private_style,
            custom_id="toggle_private"
        )
        toggle_private_btn.callback = self.toggle_private
        self.add_item(toggle_private_btn)

    async def edit_triggers(self, interaction: discord.Interaction):
        """Open modal to edit triggers."""
        modal = TriggersModal(self.cog, self.guild_id, self.sound_key, self.sound)
        await interaction.response.send_modal(modal)

    async def edit_description(self, interaction: discord.Interaction):
        """Open modal to edit description."""
        modal = DescriptionModal(self.cog, self.guild_id, self.sound_key, self.sound)
        await interaction.response.send_modal(modal)

    async def toggle_disabled(self, interaction: discord.Interaction):
        """Toggle the disabled state."""
        try:
            self.sound.is_disabled = not self.sound.is_disabled

            # Save to JSON
            self.cog.soundboard[self.guild_id].sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            status = "disabled" if self.sound.is_disabled else "enabled"
            logger.info(f"[{self.guild_id}] Sound '{self.sound.title}' {status} by {interaction.user}")

            # Update buttons
            self._add_buttons()

            # Update embed
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red() if self.sound.is_disabled else discord.Color.green()

            await interaction.response.edit_message(
                content=f"✅ Sound **{status}** successfully!",
                embed=embed,
                view=self
            )
        except Exception as e:
            logger.error(f"Failed to toggle disabled state: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update sound!", ephemeral=True)

    async def toggle_private(self, interaction: discord.Interaction):
        """
        Toggle the private state.

        Flow:
        1. Flip is_private boolean
        2. Save to JSON
        3. Update button states
        4. Send confirmation

        Args:
            interaction: Discord interaction from button click
        """
        try:
            self.sound.is_private = not self.sound.is_private

            # Save to JSON
            self.cog.soundboard[self.guild_id].sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            status = "private" if self.sound.is_private else "public"
            logger.info(f"[{self.guild_id}] Sound '{self.sound.title}' set to {status} by {interaction.user}")

            # Update buttons
            self._add_buttons()

            await interaction.response.edit_message(
                content=f"✅ Sound set to **{status}** successfully!",
                view=self
            )
        except Exception as e:
            logger.error(f"Failed to toggle private state: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update sound!", ephemeral=True)


class TriggersModal(discord.ui.Modal, title="Edit Triggers"):
    """Modal for editing sound triggers."""

    def __init__(self, cog, guild_id: str, sound_key: str, sound: SoundEntry):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.sound_key = sound_key
        self.sound = sound

        # Add text input with current triggers
        self.triggers_input = discord.ui.TextInput(
            label="Triggers (comma-separated)",
            placeholder="word1, word2, word3",
            default=", ".join(sound.triggers),
            style=discord.TextStyle.short,
            max_length=500,
            required=True
        )
        self.add_item(self.triggers_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle trigger update."""
        try:
            # Parse triggers from input
            new_triggers = [t.strip() for t in self.triggers_input.value.split(",") if t.strip()]

            if not new_triggers:
                await interaction.response.send_message("❌ At least one trigger is required!", ephemeral=True)
                return

            old_triggers = self.sound.triggers.copy()
            self.sound.triggers = new_triggers

            # Save to JSON
            self.cog.soundboard[self.guild_id].sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            logger.info(
                f"[{self.guild_id}] Updated triggers for '{self.sound.title}': {old_triggers} -> {new_triggers}")

            await interaction.response.send_message(
                f"✅ Updated triggers to: {', '.join(f'`{t}`' for t in new_triggers)}",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to update triggers: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update triggers!", ephemeral=True)


class DescriptionModal(discord.ui.Modal, title="Edit Description"):
    """Modal for editing sound description."""

    def __init__(self, cog, guild_id: str, sound_key: str, sound: SoundEntry):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.sound_key = sound_key
        self.sound = sound

        # Add text input with current description
        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Enter a description for this sound...",
            default=sound.description,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle description update."""
        try:
            new_description = self.description_input.value.strip()
            old_description = self.sound.description

            self.sound.description = new_description

            # Save to JSON
            self.cog.soundboard[self.guild_id].sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            logger.info(f"[{self.guild_id}] Updated description for '{self.sound.title}'")

            await interaction.response.send_message(
                f"✅ Description updated successfully!",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Failed to update description: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update description!", ephemeral=True)


class SoundboardView(View):
    """Interactive view for browsing and playing sounds."""

    def __init__(self, cog, guild_id: str, sounds: dict[str, SoundEntry], page: int = 0):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog
        self.guild_id = guild_id
        self.sounds = sounds
        self.page = page
        self.sounds_per_page = 10

        self._update_buttons()

    def _get_page_sounds(self):
        """Get sounds for current page."""
        sound_items = list(self.sounds.items())
        start = self.page * self.sounds_per_page
        end = start + self.sounds_per_page
        return sound_items[start:end]

    def _update_buttons(self):
        """Update button states based on current page."""
        self.clear_items()

        total_pages = (len(self.sounds) - 1) // self.sounds_per_page + 1

        # Add sound selection dropdown
        page_sounds = self._get_page_sounds()
        if page_sounds:
            options = []
            for key, sound in page_sounds:
                # Create description with triggers
                triggers_text = ", ".join(sound.triggers[:3])
                if len(sound.triggers) > 3:
                    triggers_text += "..."

                options.append(discord.SelectOption(
                    label=sound.title[:100],
                    value=key,
                    description=f"Triggers: {triggers_text}"[:100] if triggers_text else "No triggers",
                    emoji="🔊"
                ))

            select = Select(
                placeholder="Select a sound to view details...",
                options=options,
                custom_id="sound_select"
            )
            select.callback = self.sound_selected
            self.add_item(select)

        # Navigation buttons
        if self.page > 0:
            prev_btn = Button(label="◀ Previous", style=discord.ButtonStyle.primary, custom_id="prev")
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)

        if self.page < total_pages - 1:
            next_btn = Button(label="Next ▶", style=discord.ButtonStyle.primary, custom_id="next")
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        # Refresh button
        refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.secondary, custom_id="refresh")
        refresh_btn.callback = self.refresh
        self.add_item(refresh_btn)

    def create_embed(self) -> discord.Embed:
        """
        Create embed showing current page of sounds.

        Returns:
            Discord embed with sound list and page info
        """
        total_sounds = len(self.sounds)
        total_pages = (total_sounds - 1) // self.sounds_per_page + 1

        embed = discord.Embed(
            title="🎵 Soundboard",
            description=f"Browse and play sounds from the soundboard.\nTotal sounds: **{total_sounds}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        page_sounds = self._get_page_sounds()
        if page_sounds:
            for key, sound in page_sounds:
                # Build field value
                triggers = ", ".join(f"`{t}`" for t in sound.triggers) or "None"
                plays = sound.play_stats.total

                value = f"🔊 **Triggers:** {triggers}\n"
                if sound.description:
                    value += f"📝 {sound.description[:100]}\n"
                value += f"▶️ Played: {plays} times\n"
                value += f"👤 Added by: {sound.added_by}"

                if sound.is_disabled:
                    value = "⚠️ **[DISABLED]**\n" + value
                if sound.is_private:
                    value = "🔒 **[PRIVATE]**\n" + value

                embed.add_field(
                    name=sound.title,
                    value=value,
                    inline=False
                )
        else:
            embed.description = "No sounds available."

        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")
        return embed

    async def sound_selected(self, interaction: discord.Interaction):
        """
        Handle sound selection from dropdown.

        Flow:
        1. Get selected sound key from dropdown
        2. Fetch sound entry
        3. Create detailed embed with all sound info
        4. Create edit view with action buttons
        5. Send as ephemeral message (only visible to user)

        Args:
            interaction: Discord interaction from dropdown selection
        """
        sound_key = interaction.data["values"][0]
        sound = self.sounds.get(sound_key)

        if not sound:
            await interaction.response.send_message("❌ Sound not found!", ephemeral=True)
            return

        # Create detailed embed for selected sound
        embed = discord.Embed(
            title=f"🎵 {sound.title}",
            description=sound.description or "No description provided.",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        # Add fields
        embed.add_field(
            name="📋 Triggers",
            value=", ".join(f"`{t}`" for t in sound.triggers) or "None",
            inline=False
        )

        embed.add_field(
            name="📊 Statistics",
            value=f"**Total Plays:** {sound.play_stats.total}\n"
                  f"**This Week:** {sound.play_stats.week}\n"
                  f"**This Month:** {sound.play_stats.month}",
            inline=True
        )

        embed.add_field(
            name="ℹ️ Info",
            value=f"**Added by:** {sound.added_by}\n"
                  f"**Date:** {sound.added_date[:10]}\n"
                  f"**File:** `{sound.soundfile}`",
            inline=True
        )

        # Status indicators
        status = []
        if sound.is_disabled:
            status.append("⚠️ Disabled")
        if sound.is_private:
            status.append("🔒 Private")
        if not sound.approved:
            status.append("⏳ Pending Approval")

        if status:
            embed.add_field(name="Status", value=" • ".join(status), inline=False)

        # Create edit view with buttons
        edit_view = SoundEditView(self.cog, self.guild_id, sound_key, sound)

        await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

    async def previous_page(self, interaction: discord.Interaction):
        """Go to previous page."""
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        """Go to next page."""
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def refresh(self, interaction: discord.Interaction):
        """Refresh the soundboard data."""
        try:
            self.cog.soundboard = load_soundboard(SOUNDBOARD_FILE)
            guild_sounds = self.cog.soundboard.get(self.guild_id)
            if guild_sounds:
                self.sounds = guild_sounds.sounds
            self._update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        except Exception as e:
            logger.error(f"Failed to refresh soundboard: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to refresh soundboard!", ephemeral=True)


# -------- Cog --------

class Soundboard(BaseCog):
    """
    Soundboard cog for managing and playing custom sounds.

    Features:
    - Load/save soundboard from JSON
    - Add new sounds
    - View sounds with interactive UI
    - Track play statistics
    - Manage triggers
    """

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        # Load JSON once on cog load
        self.soundboard: dict[str, GuildSoundboard] = {}
        if Path(SOUNDBOARD_FILE).exists():
            try:
                self.soundboard = load_soundboard(SOUNDBOARD_FILE)
                logger.info(f"Loaded soundboard with {len(self.soundboard)} guilds")
            except Exception as e:
                logger.error(f"Failed to load soundboard: {e}", exc_info=True)
                self.soundboard = {}
        else:
            logger.warning(f"Soundboard file not found: {SOUNDBOARD_FILE}")

    async def cog_unload(self):
        """
        Clean up when cog is unloaded/reloaded.

        Flow:
        1. Save current soundboard state to JSON
        2. Clear in-memory soundboard data

        This ensures no data is lost on reload and memory is freed.
        """
        logger.info("Unloading Soundboard cog, saving data...")

        try:
            # Save any pending changes to JSON
            if self.soundboard:
                save_soundboard(SOUNDBOARD_FILE, self.soundboard)
                logger.info(f"Saved soundboard with {len(self.soundboard)} guilds")
        except Exception as e:
            logger.error(f"Failed to save soundboard during unload: {e}", exc_info=True)

        # Clear data structures
        self.soundboard.clear()
        logger.info("Soundboard cog cleanup complete.")

    def increment_play_stats(self, guild_id: str, soundfile: str, user_id: str):
        """
        Increment the play statistics for a sound.

        Updates:
        - week, month, total
        - guild_play_count[guild_id]
        - last_played timestamp
        - played_by (last user only)

        Args:
            guild_id: Discord guild ID
            soundfile: Path to the sound file being played
            user_id: Discord user ID who played the sound
        """
        # Try the specific guild first
        guild_data = self.soundboard.get(guild_id)

        # If not found, also check default_guild
        if not guild_data or not any(entry.soundfile == soundfile for entry in guild_data.sounds.values()):
            default_data = self.soundboard.get("default_guild")
            if default_data:
                # Check if the sound exists in default_guild
                for entry in default_data.sounds.values():
                    if entry.soundfile == soundfile:
                        guild_data = default_data
                        break

        if not guild_data:
            logger.warning(f"Soundfile '{soundfile}' not found in guild '{guild_id}' or 'default_guild'")
            return

        # Find the sound entry
        sound_entry: SoundEntry | None = None
        for entry in guild_data.sounds.values():
            if entry.soundfile == soundfile:
                sound_entry = entry
                break

        if not sound_entry:
            logger.warning(f"Soundfile '{soundfile}' not found in guild '{guild_id}' or 'default_guild'")
            return

        stats = sound_entry.play_stats
        stats.week += 1
        stats.month += 1
        stats.total += 1
        stats.guild_play_count[guild_id] = stats.guild_play_count.get(guild_id, 0) + 1
        stats.last_played = datetime.utcnow().isoformat()
        stats.played_by = [user_id]  # only last user

        # Save JSON
        try:
            save_soundboard(SOUNDBOARD_FILE, self.soundboard)
            logger.debug(f"[{guild_id}] Updated play stats for '{sound_entry.title}'")
        except Exception as e:
            logger.error(f"Failed to save soundboard after incrementing stats: {e}", exc_info=True)

    def get_soundfiles_for_text(self, guild_id: int, user_id: int, text: str) -> list[str]:
        """
        Return list of soundfile paths for any matching words in the text.
        """
        guild_id_str = str(guild_id)
        words = text.lower().split()
        matched_files = []
        seen_files = set()
        guild_data = self.soundboard.get(guild_id_str)
        default_guild = self.soundboard.get("default_guild")

        for word in words:
            word_lower = word.strip()
            if not word_lower:
                continue
            found = False

            # Check guild-specific sounds first
            if guild_data:
                for entry in guild_data.sounds.values():
                    if word_lower in [t.lower() for t in entry.triggers]:
                        if entry.is_disabled:
                            logger.info(
                                f"Skipped disabled sound '{entry.title}' for word '{word_lower}' in guild {guild_id_str}")
                            continue
                        if entry.is_private and str(user_id) != str(entry.added_by_id):
                            logger.info(
                                f"Skipped private sound '{entry.title}' triggered by user {user_id} (added by {entry.added_by_id})")
                            continue
                        if entry.soundfile not in seen_files:
                            matched_files.append(entry.soundfile)
                            seen_files.add(entry.soundfile)
                            self.increment_play_stats(guild_id_str, entry.soundfile, user_id)
                            found = True
                            break

            # Fallback to default guild
            if not found and default_guild:
                for entry in default_guild.sounds.values():
                    if word_lower in [t.lower() for t in entry.triggers]:
                        if entry.is_disabled:
                            logger.info(f"Skipped disabled default sound '{entry.title}' for word '{word_lower}'")
                            continue
                        if entry.is_private and str(user_id) != str(entry.added_by_id):
                            logger.info(
                                f"Skipped private default sound '{entry.title}' triggered by user {user_id} (added by {entry.added_by_id})")
                            continue
                        if entry.soundfile not in seen_files:
                            matched_files.append(entry.soundfile)
                            seen_files.add(entry.soundfile)
                            self.increment_play_stats("default_guild", entry.soundfile, user_id)
                            break

        return matched_files

    async def add_sound(
            self,
            guild_id: str,
            title: str,
            soundfile: str,
            added_by: str,
            added_by_id: str,
            description: str = "",
            triggers: list[str] = None,
            is_private: bool = False,
            is_disabled: bool = False
    ):
        """
        Add a sound entry to the guild soundboard and save JSON.

        Args:
            guild_id: Discord guild ID
            title: Sound title/name
            soundfile: Path to sound file
            added_by: Username who added the sound
            added_by_id: Discord user ID
            description: Optional description
            triggers: List of trigger words
            is_private: Whether sound is private
            is_disabled: Whether sound is disabled

        Returns:
            SoundEntry: The created sound entry
        """
        if triggers is None:
            triggers = []

        entry = SoundEntry(
            title=title,
            triggers=triggers,
            soundfile=soundfile,
            description=description,
            added_by=added_by,
            added_by_id=added_by_id,
            added_date=datetime.utcnow().isoformat(),
            is_private=is_private,
            is_disabled=is_disabled
        )

        # Ensure guild exists
        if guild_id not in self.soundboard:
            self.soundboard[guild_id] = GuildSoundboard(guild_id)

        # Save by a unique key (title lowercased)
        key = title.lower().replace(" ", "_")
        self.soundboard[guild_id].sounds[key] = entry

        # Save to JSON
        try:
            save_soundboard(SOUNDBOARD_FILE, self.soundboard)
            logger.info(f"Added sound '{title}' to guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to save soundboard after adding '{title}': {e}", exc_info=True)
            raise

        return entry

    @commands.command(help="View all sounds in the soundboard")
    async def sounds(self, ctx):
        """
        Display interactive soundboard browser.

        Shows all available sounds with pagination and details.
        """
        guild_id = str(ctx.guild.id)

        # Check for actual guild ID first, then fall back to "default_guild"
        if guild_id in self.soundboard and self.soundboard[guild_id].sounds:
            sounds = self.soundboard[guild_id].sounds
        elif "default_guild" in self.soundboard and self.soundboard["default_guild"].sounds:
            logger.info(f"Using default_guild soundboard for guild {guild_id}")
            sounds = self.soundboard["default_guild"].sounds
            guild_id = "default_guild"
        else:
            return await ctx.send("📭 No sounds available in this server's soundboard!")

        view = SoundboardView(self, guild_id, sounds)
        embed = view.create_embed()

        await ctx.send(embed=embed, view=view)

    @commands.command(name="addsound", help="Upload a new sound to the soundboard (attach the file before sending this command)")
    async def addsound(self, ctx: commands.Context):
        """Handles uploading a sound file via modal."""
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a sound file with the command.")

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".mp3", ".wav", ".ogg")):
            return await ctx.send("❌ Unsupported file type. Use mp3, wav, or ogg.")

        view = SoundUploadView(self, str(ctx.guild.id), attachment)

        await ctx.send(
            f"✅ I have the file `{attachment.filename}` now. "
            f"Click the button below to add details and upload it!",
            view=view
        )


async def setup(bot):
    """Load the Soundboard cog."""
    try:
        await bot.add_cog(Soundboard(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception:
        logger.error("Failed to load cog %s:\n%s", __name__, traceback.format_exc())