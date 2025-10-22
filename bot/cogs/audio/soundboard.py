import json
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict
from datetime import datetime
from pathlib import Path
import traceback
import random

import discord
from discord.ext import commands
from discord.ui import View, Button, Select

from bot.base_cog import BaseCog, logger

SOUNDBOARD_FILE = "data/config/soundboard.json"


# -------- Dataclasses --------

@dataclass
class PlayStats:
    week: int = 0
    month: int = 0
    total: int = 0
    guild_play_count: Dict[str, int] = field(default_factory=dict)
    trigger_word_stats: Dict[str, int] = field(default_factory=dict)  # {trigger_word: count}
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
    guild_id: str  # Guild where this sound was added
    last_edited_by: Optional[str] = None
    last_edited_date: Optional[str] = None
    is_private: bool = False
    is_disabled: bool = False
    approved: bool = True
    play_stats: PlayStats = field(default_factory=PlayStats)
    audio_metadata: AudioMetadata = field(default_factory=AudioMetadata)
    settings: SoundSettings = field(default_factory=SoundSettings)


@dataclass
class SoundboardData:
    """Flat structure containing all sounds."""
    sounds: Dict[str, SoundEntry] = field(default_factory=dict)


# -------- Utility Functions --------

def load_soundboard(file_path: str) -> SoundboardData:
    """Load the soundboard JSON into flat structure with auto-migration from old format."""
    logger.info(f"Loading soundboard from '{file_path}'...")

    try:
        if not Path(file_path).exists():
            logger.error(f"Soundboard file not found: {file_path}")
            raise FileNotFoundError(f"Soundboard file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        all_sounds = {}
        total_sounds = 0
        skipped_sounds = 0

        # Check if old format (guild_id as keys) or new format (flat structure)
        if "sounds" in data:
            # New flat format
            logger.info("Loading soundboard in new flat format")
            for key, sound_data in data["sounds"].items():
                try:
                    soundfile = sound_data.get('soundfile', '')
                    if not soundfile or not Path(soundfile).exists():
                        logger.error(f"Sound file missing for '{key}': {soundfile}")
                        skipped_sounds += 1
                        continue

                    if 'play_stats' in sound_data and isinstance(sound_data['play_stats'], dict):
                        sound_data['play_stats'] = PlayStats(**sound_data['play_stats'])
                    if 'audio_metadata' in sound_data and isinstance(sound_data['audio_metadata'], dict):
                        sound_data['audio_metadata'] = AudioMetadata(**sound_data['audio_metadata'])
                    if 'settings' in sound_data and isinstance(sound_data['settings'], dict):
                        sound_data['settings'] = SoundSettings(**sound_data['settings'])

                    all_sounds[key] = SoundEntry(**sound_data)
                    total_sounds += 1
                except Exception as e:
                    logger.error(f"Failed to load sound '{key}': {e}")
                    skipped_sounds += 1
        else:
            # Old format - migrate
            logger.info("Migrating soundboard from old format to new flat format")
            for guild_id, sounds in data.items():
                if not isinstance(sounds, dict):
                    continue

                for key, sound_data in sounds.items():
                    try:
                        soundfile = sound_data.get('soundfile', '')
                        if not soundfile or not Path(soundfile).exists():
                            logger.error(f"Sound file missing for '{key}': {soundfile}")
                            skipped_sounds += 1
                            continue

                        if 'guild_id' not in sound_data:
                            sound_data['guild_id'] = guild_id

                        if 'play_stats' in sound_data and isinstance(sound_data['play_stats'], dict):
                            sound_data['play_stats'] = PlayStats(**sound_data['play_stats'])
                        if 'audio_metadata' in sound_data and isinstance(sound_data['audio_metadata'], dict):
                            sound_data['audio_metadata'] = AudioMetadata(**sound_data['audio_metadata'])
                        if 'settings' in sound_data and isinstance(sound_data['settings'], dict):
                            sound_data['settings'] = SoundSettings(**sound_data['settings'])

                        unique_key = f"{guild_id}_{key}" if guild_id != "default_guild" else key
                        all_sounds[unique_key] = SoundEntry(**sound_data)
                        total_sounds += 1
                    except Exception as e:
                        logger.error(f"Failed to load sound '{key}': {e}")
                        skipped_sounds += 1

        if skipped_sounds > 0:
            logger.warning(f"Skipped {skipped_sounds} sound(s)")
        logger.info(f"Successfully loaded {total_sounds} sound(s)")

        return SoundboardData(sounds=all_sounds)

    except Exception as e:
        logger.error(f"Error loading soundboard: {e}", exc_info=True)
        raise


def save_soundboard(file_path: str, soundboard: SoundboardData):
    """Save soundboard to JSON in flat structure."""
    logger.info(f"Saving soundboard to '{file_path}'...")

    try:
        validated_sounds = {}
        skipped = 0

        for key, sound in soundboard.sounds.items():
            if not Path(sound.soundfile).exists():
                logger.error(f"Sound file missing for '{sound.title}': {sound.soundfile}")
                skipped += 1
                continue
            validated_sounds[key] = sound

        if Path(file_path).exists():
            import shutil
            shutil.copy2(file_path, f"{file_path}.backup")

        data = {"sounds": {k: asdict(v) for k, v in validated_sounds.items()}}

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved {len(validated_sounds)} sound(s)" + (f" (skipped {skipped})" if skipped else ""))

    except Exception as e:
        logger.error(f"Error saving soundboard: {e}", exc_info=True)
        raise


# -------- Discord UI Components --------

class SoundUploadModal(discord.ui.Modal, title="Upload Sound"):
    def __init__(self, cog, guild_id: str, attachment: discord.Attachment):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.attachment = attachment

        self.title_input = discord.ui.TextInput(label="Title", required=True, max_length=100)
        self.add_item(self.title_input)

        self.description_input = discord.ui.TextInput(
            label="Description", style=discord.TextStyle.paragraph, required=False, max_length=500
        )
        self.add_item(self.description_input)

        self.triggers_input = discord.ui.TextInput(
            label="Triggers (comma separated)", placeholder="e.g., hello, hi, hey", required=True, max_length=500
        )
        self.add_item(self.triggers_input)

        self.flags_input = discord.ui.TextInput(
            label="Flags (optional)", placeholder="private, disabled", required=False, max_length=100
        )
        self.add_item(self.flags_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            title = self.title_input.value.strip()
            triggers = [t.strip() for t in self.triggers_input.value.split(",") if t.strip()]
            flags = [f.strip().lower() for f in self.flags_input.value.split(",") if f.strip()]

            if not triggers:
                return await interaction.response.send_message("❌ At least one trigger required!", ephemeral=True)

            Path("soundboard").mkdir(exist_ok=True)
            save_path = f"soundboard/{self.attachment.filename}"
            await self.attachment.save(save_path)

            await self.cog.add_sound(
                guild_id=self.guild_id,
                title=title,
                soundfile=save_path,
                added_by=str(interaction.user),
                added_by_id=str(interaction.user.id),
                description=self.description_input.value.strip(),
                triggers=triggers,
                is_private="private" in flags,
                is_disabled="disabled" in flags
            )

            status = []
            if "private" in flags:
                status.append("🔒 Private")
            if "disabled" in flags:
                status.append("⚠️ Disabled")

            response = f"✅ Uploaded `{title}`!\n**Triggers:** {', '.join(f'`{t}`' for t in triggers)}"
            if status:
                response += f"\n**Status:** {' • '.join(status)}"

            await interaction.response.send_message(response, ephemeral=True)
            logger.info(f"[{self.guild_id}] Sound '{title}' uploaded by {interaction.user}")

        except Exception as e:
            logger.error(f"Upload failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to upload sound!", ephemeral=True)


class SoundUploadView(View):
    def __init__(self, cog, guild_id: str, attachment: discord.Attachment):
        super().__init__(timeout=180)
        self.cog = cog
        self.guild_id = guild_id
        self.attachment = attachment

    @discord.ui.button(label="📤 Upload Sound", style=discord.ButtonStyle.primary)
    async def upload_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SoundUploadModal(self.cog, self.guild_id, self.attachment))


class SoundEditView(View):
    def __init__(self, cog, sound_key: str, sound: SoundEntry, message: discord.Message = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.sound_key = sound_key
        self.sound = sound
        self.message = message
        self._add_buttons()

    def _add_buttons(self):
        self.clear_items()

        edit_triggers = Button(label="✏️ Edit Triggers", style=discord.ButtonStyle.primary)
        edit_triggers.callback = self.edit_triggers
        self.add_item(edit_triggers)

        edit_desc = Button(label="📝 Edit Description", style=discord.ButtonStyle.primary)
        edit_desc.callback = self.edit_description
        self.add_item(edit_desc)

        edit_volume = Button(label="🔊 Edit Volume", style=discord.ButtonStyle.primary)
        edit_volume.callback = self.edit_volume
        self.add_item(edit_volume)

        status_label = "⚠️ Disabled" if self.sound.is_disabled else "✅ Available"
        status_style = discord.ButtonStyle.danger if self.sound.is_disabled else discord.ButtonStyle.success
        toggle_disabled = Button(label=status_label, style=status_style)
        toggle_disabled.callback = self.toggle_disabled
        self.add_item(toggle_disabled)

        private_label = "🔒 Private" if self.sound.is_private else "🔓 Public"
        private_style = discord.ButtonStyle.danger if self.sound.is_private else discord.ButtonStyle.success
        toggle_private = Button(label=private_label, style=private_style)
        toggle_private.callback = self.toggle_private
        self.add_item(toggle_private)

    def create_updated_embed(self) -> discord.Embed:
        """Create an updated embed with current sound data."""
        # Use last_edited_date for timestamp if available, otherwise added_date
        timestamp_str = self.sound.last_edited_date if self.sound.last_edited_date else self.sound.added_date
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            timestamp = datetime.utcnow()

        embed = discord.Embed(
            title=f"🎵 {self.sound.title}",
            description=self.sound.description or "No description provided.",
            color=discord.Color.green(),
            timestamp=timestamp
        )

        embed.add_field(
            name="📋 Triggers",
            value=", ".join(f"`{t}`" for t in self.sound.triggers) or "None",
            inline=False
        )

        embed.add_field(
            name="📊 Statistics",
            value=f"**Total:** {self.sound.play_stats.total}\n**Week:** {self.sound.play_stats.week}\n**Month:** {self.sound.play_stats.month}",
            inline=True
        )

        # Create volume bar (0-200% scale)
        volume = self.sound.audio_metadata.volume_adjust
        volume_percent = int(volume * 100)
        bars = int((volume / 2.0) * 10)
        volume_bar = "█" * bars + "░" * (10 - bars)

        # Format added date as Discord timestamp for local conversion
        try:
            added_dt = datetime.fromisoformat(self.sound.added_date.replace('Z', '+00:00'))
            added_timestamp = int(added_dt.timestamp())
            added_display = f"<t:{added_timestamp}:d>"
        except:
            added_display = self.sound.added_date[:10]

        info_value = f"**Added by:** {self.sound.added_by}\n**Added:** {added_display}"

        if self.sound.last_edited_by:
            try:
                edited_dt = datetime.fromisoformat(self.sound.last_edited_date.replace('Z', '+00:00'))
                edited_timestamp = int(edited_dt.timestamp())
                edited_display = f"<t:{edited_timestamp}:R>"
                info_value += f"\n**Last edited:** {edited_display}\n**Edited by:** {self.sound.last_edited_by}"
            except:
                info_value += f"\n**Last edited by:** {self.sound.last_edited_by}"

        info_value += f"\n**File:** `{self.sound.soundfile}`"

        embed.add_field(
            name="ℹ️ Info",
            value=info_value,
            inline=True
        )

        embed.add_field(
            name="🔊 Volume",
            value=f"`{volume_bar}` **{volume_percent}%**",
            inline=False
        )

        status = []
        if self.sound.is_disabled:
            status.append("⚠️ Disabled")
        if self.sound.is_private:
            status.append("🔒 Private")
        if status:
            embed.add_field(name="Status", value=" • ".join(status), inline=False)

        return embed

    async def edit_triggers(self, interaction: discord.Interaction):
        modal = TriggersModal(self.cog, self.sound_key, self.sound, self)
        await interaction.response.send_modal(modal)

    async def edit_description(self, interaction: discord.Interaction):
        modal = DescriptionModal(self.cog, self.sound_key, self.sound, self)
        await interaction.response.send_modal(modal)

    async def edit_volume(self, interaction: discord.Interaction):
        modal = VolumeModal(self.cog, self.sound_key, self.sound, self)
        await interaction.response.send_modal(modal)

    async def toggle_disabled(self, interaction: discord.Interaction):
        try:
            self.sound.is_disabled = not self.sound.is_disabled
            self.sound.last_edited_by = str(interaction.user)
            self.cog.soundboard.sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            status = "disabled" if self.sound.is_disabled else "enabled"
            logger.info(f"Sound '{self.sound.title}' {status} by {interaction.user}")

            self._add_buttons()
            embed = interaction.message.embeds[0]
            embed.color = discord.Color.red() if self.sound.is_disabled else discord.Color.green()

            # Update last edited info in embed
            for i, field in enumerate(embed.fields):
                if field.name == "ℹ️ Info":
                    embed.set_field_at(i, name="ℹ️ Info",
                                       value=f"**Added by:** {self.sound.added_by}\n**Date:** {self.sound.added_date[:10]}\n**File:** `{self.sound.soundfile}`\n**Last edited by:** {self.sound.last_edited_by}",
                                       inline=True)
                    break

            await interaction.response.edit_message(content=f"✅ Sound **{status}**!", embed=embed, view=self)
        except Exception as e:
            logger.error(f"Toggle disabled failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update!", ephemeral=True)

    async def toggle_private(self, interaction: discord.Interaction):
        try:
            self.sound.is_private = not self.sound.is_private
            self.sound.last_edited_by = str(interaction.user)
            self.cog.soundboard.sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            status = "private" if self.sound.is_private else "public"
            logger.info(f"Sound '{self.sound.title}' set to {status} by {interaction.user}")

            self._add_buttons()

            # Update last edited info in embed
            embed = interaction.message.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "ℹ️ Info":
                    embed.set_field_at(i, name="ℹ️ Info",
                                       value=f"**Added by:** {self.sound.added_by}\n**Date:** {self.sound.added_date[:10]}\n**File:** `{self.sound.soundfile}`\n**Last edited by:** {self.sound.last_edited_by}",
                                       inline=True)
                    break

            await interaction.response.edit_message(content=f"✅ Sound set to **{status}**!", embed=embed, view=self)
        except Exception as e:
            logger.error(f"Toggle private failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update!", ephemeral=True)


class TriggersModal(discord.ui.Modal, title="Edit Triggers"):
    def __init__(self, cog, sound_key: str, sound: SoundEntry, parent_view: 'SoundEditView'):
        super().__init__()
        self.cog = cog
        self.sound_key = sound_key
        self.sound = sound
        self.parent_view = parent_view

        self.triggers_input = discord.ui.TextInput(
            label="Triggers (comma-separated)",
            default=", ".join(sound.triggers),
            style=discord.TextStyle.short,
            max_length=500,
            required=True
        )
        self.add_item(self.triggers_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_triggers = [t.strip() for t in self.triggers_input.value.split(",") if t.strip()]
            if not new_triggers:
                return await interaction.response.send_message("❌ At least one trigger required!", ephemeral=True)

            self.sound.triggers = new_triggers
            self.sound.last_edited_by = str(interaction.user)
            self.sound.last_edited_date = datetime.utcnow().isoformat()
            self.cog.soundboard.sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            logger.info(f"Updated triggers for '{self.sound.title}' by {interaction.user}")

            # Update the parent view's sound reference
            self.parent_view.sound = self.sound

            # Update the embed with new data
            updated_embed = self.parent_view.create_updated_embed()

            # Edit the original message with updated embed
            await self.parent_view.message.edit(embed=updated_embed, view=self.parent_view)

            await interaction.response.send_message(
                f"✅ Updated triggers: {', '.join(f'`{t}`' for t in new_triggers)}", ephemeral=True
            )
        except Exception as e:
            logger.error(f"Update triggers failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update!", ephemeral=True)


class DescriptionModal(discord.ui.Modal, title="Edit Description"):
    def __init__(self, cog, sound_key: str, sound: SoundEntry, parent_view: 'SoundEditView'):
        super().__init__()
        self.cog = cog
        self.sound_key = sound_key
        self.sound = sound
        self.parent_view = parent_view

        self.description_input = discord.ui.TextInput(
            label="Description",
            default=sound.description,
            style=discord.TextStyle.paragraph,
            max_length=1000,
            required=False
        )
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.sound.description = self.description_input.value.strip()
            self.sound.last_edited_by = str(interaction.user)
            self.sound.last_edited_date = datetime.utcnow().isoformat()
            self.cog.soundboard.sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            logger.info(f"Updated description for '{self.sound.title}' by {interaction.user}")

            # Update the parent view's sound reference
            self.parent_view.sound = self.sound

            # Update the embed with new data
            updated_embed = self.parent_view.create_updated_embed()

            # Edit the original message with updated embed
            await self.parent_view.message.edit(embed=updated_embed, view=self.parent_view)

            await interaction.response.send_message("✅ Description updated!", ephemeral=True)
        except Exception as e:
            logger.error(f"Update description failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update!", ephemeral=True)


class VolumeModal(discord.ui.Modal, title="Edit Volume"):
    def __init__(self, cog, sound_key: str, sound: SoundEntry, parent_view: 'SoundEditView'):
        super().__init__()
        self.cog = cog
        self.sound_key = sound_key
        self.sound = sound
        self.parent_view = parent_view

        # Convert current volume to percentage for display
        current_percent = int(sound.audio_metadata.volume_adjust * 100)

        self.volume_input = discord.ui.TextInput(
            label="Volume (0 to 200)",
            default=str(current_percent),
            style=discord.TextStyle.short,
            placeholder="100 = normal, 50 = half, 200 = double",
            max_length=3,
            required=True
        )
        self.add_item(self.volume_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            volume_str = self.volume_input.value.strip()

            # Parse and validate volume percentage
            try:
                volume_percent = int(volume_str)
            except ValueError:
                return await interaction.response.send_message("❌ Volume must be a whole number!", ephemeral=True)

            if volume_percent < 0 or volume_percent > 200:
                return await interaction.response.send_message("❌ Volume must be between 0 and 200!", ephemeral=True)

            # Convert percentage to decimal (50 -> 0.5, 100 -> 1.0, 200 -> 2.0)
            volume_decimal = volume_percent / 100.0

            self.sound.audio_metadata.volume_adjust = volume_decimal
            self.sound.last_edited_by = str(interaction.user)
            self.sound.last_edited_date = datetime.utcnow().isoformat()
            self.cog.soundboard.sounds[self.sound_key] = self.sound
            save_soundboard(SOUNDBOARD_FILE, self.cog.soundboard)

            logger.info(
                f"Updated volume for '{self.sound.title}' to {volume_decimal} ({volume_percent}%) by {interaction.user}")

            # Update the parent view's sound reference
            self.parent_view.sound = self.sound

            # Update the embed with new data
            updated_embed = self.parent_view.create_updated_embed()

            # Edit the original message with updated embed
            await self.parent_view.message.edit(embed=updated_embed, view=self.parent_view)

            # Create visual volume bar
            bars = int((volume_percent / 200.0) * 10)
            volume_bar = "█" * bars + "░" * (10 - bars)

            await interaction.response.send_message(
                f"✅ Volume updated to **{volume_percent}%**\n`{volume_bar}`",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Update volume failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to update!", ephemeral=True)


class SoundboardView(View):
    def __init__(self, cog, guild_id: str, sounds: dict[str, SoundEntry], page: int = 0):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild_id = guild_id
        self.sounds = sounds
        self.page = page
        self.sounds_per_page = 10
        self._update_buttons()

    def _get_page_sounds(self):
        sound_items = list(self.sounds.items())
        start = self.page * self.sounds_per_page
        end = start + self.sounds_per_page
        return sound_items[start:end]

    def _update_buttons(self):
        self.clear_items()
        total_pages = (len(self.sounds) - 1) // self.sounds_per_page + 1

        page_sounds = self._get_page_sounds()
        if page_sounds:
            options = []
            for key, sound in page_sounds:
                triggers_text = ", ".join(sound.triggers[:3])
                if len(sound.triggers) > 3:
                    triggers_text += "..."

                options.append(discord.SelectOption(
                    label=sound.title[:100],
                    value=key,
                    description=f"Triggers: {triggers_text}"[:100] if triggers_text else "No triggers",
                    emoji="🔊"
                ))

            select = Select(placeholder="Select a sound to view details...", options=options)
            select.callback = self.sound_selected
            self.add_item(select)

        if self.page > 0:
            prev_btn = Button(label="◀ Previous", style=discord.ButtonStyle.primary)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)

        if self.page < total_pages - 1:
            next_btn = Button(label="Next ▶", style=discord.ButtonStyle.primary)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        refresh_btn = Button(label="🔄 Refresh", style=discord.ButtonStyle.secondary)
        refresh_btn.callback = self.refresh
        self.add_item(refresh_btn)

    def create_embed(self) -> discord.Embed:
        total_sounds = len(self.sounds)
        total_pages = (total_sounds - 1) // self.sounds_per_page + 1

        embed = discord.Embed(
            title="🎵 Soundboard",
            description=f"Total sounds: **{total_sounds}**",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        page_sounds = self._get_page_sounds()
        if page_sounds:
            for key, sound in page_sounds:
                triggers = ", ".join(f"`{t}`" for t in sound.triggers) or "None"
                plays = sound.play_stats.total

                value = f"🔊 **Triggers:** {triggers}\n"
                if sound.description:
                    value += f"📝 {sound.description[:100]}\n"
                value += f"▶️ Played: {plays} times"

                if sound.is_disabled:
                    value = "⚠️ **[DISABLED]**\n" + value
                if sound.is_private:
                    value = "🔒 **[PRIVATE]**\n" + value

                embed.add_field(name=sound.title, value=value, inline=False)
        else:
            embed.description = "No sounds available."

        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")
        return embed

    async def sound_selected(self, interaction: discord.Interaction):
        sound_key = interaction.data["values"][0]
        sound = self.sounds.get(sound_key)

        if not sound:
            return await interaction.response.send_message("❌ Sound not found!", ephemeral=True)

        # Use last_edited_date for timestamp if available, otherwise added_date
        timestamp_str = sound.last_edited_date if sound.last_edited_date else sound.added_date
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except:
            timestamp = datetime.utcnow()

        embed = discord.Embed(
            title=f"🎵 {sound.title}",
            description=sound.description or "No description provided.",
            color=discord.Color.green(),
            timestamp=timestamp  # This will show in user's local time at the bottom
        )

        embed.add_field(
            name="📋 Triggers",
            value=", ".join(f"`{t}`" for t in sound.triggers) or "None",
            inline=False
        )

        embed.add_field(
            name="📊 Statistics",
            value=f"**Total:** {sound.play_stats.total}\n**Week:** {sound.play_stats.week}\n**Month:** {sound.play_stats.month}",
            inline=True
        )

        # Create volume bar (0-200% scale)
        volume = sound.audio_metadata.volume_adjust
        volume_percent = int(volume * 100)
        bars = int((volume / 2.0) * 10)
        volume_bar = "█" * bars + "░" * (10 - bars)

        # Format added date as Discord timestamp for local conversion
        try:
            added_dt = datetime.fromisoformat(sound.added_date.replace('Z', '+00:00'))
            added_timestamp = int(added_dt.timestamp())
            added_display = f"<t:{added_timestamp}:d>"  # Short date format
        except:
            added_display = sound.added_date[:10]

        info_value = f"**Added by:** {sound.added_by}\n**Added:** {added_display}"

        if sound.last_edited_by:
            try:
                edited_dt = datetime.fromisoformat(sound.last_edited_date.replace('Z', '+00:00'))
                edited_timestamp = int(edited_dt.timestamp())
                edited_display = f"<t:{edited_timestamp}:R>"  # Relative time (e.g., "5 minutes ago")
                info_value += f"\n**Last edited:** {edited_display}\n**Edited by:** {sound.last_edited_by}"
            except:
                info_value += f"\n**Last edited by:** {sound.last_edited_by}"

        info_value += f"\n**File:** `{sound.soundfile}`"

        embed.add_field(
            name="ℹ️ Info",
            value=info_value,
            inline=True
        )

        embed.add_field(
            name="🔊 Volume",
            value=f"`{volume_bar}` **{volume_percent}%**",
            inline=False
        )

        status = []
        if sound.is_disabled:
            status.append("⚠️ Disabled")
        if sound.is_private:
            status.append("🔒 Private")
        if status:
            embed.add_field(name="Status", value=" • ".join(status), inline=False)

        edit_view = SoundEditView(self.cog, sound_key, sound)
        message = await interaction.response.send_message(embed=embed, view=edit_view, ephemeral=True)

        # Store the message reference in the view for later updates
        edit_view.message = await interaction.original_response()

    async def previous_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def refresh(self, interaction: discord.Interaction):
        try:
            self.cog.soundboard = load_soundboard(SOUNDBOARD_FILE)
            guild_id = str(interaction.guild.id)

            # Filter sounds by privacy
            filtered_sounds = {
                k: s for k, s in self.cog.soundboard.sounds.items()
                if not s.is_private or s.guild_id == guild_id
            }
            self.sounds = filtered_sounds
            self._update_buttons()
            await interaction.response.edit_message(embed=self.create_embed(), view=self)
        except Exception as e:
            logger.error(f"Refresh failed: {e}", exc_info=True)
            await interaction.response.send_message("❌ Failed to refresh!", ephemeral=True)


# -------- Cog --------

class Soundboard(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.soundboard: SoundboardData = SoundboardData()
        if Path(SOUNDBOARD_FILE).exists():
            try:
                self.soundboard = load_soundboard(SOUNDBOARD_FILE)
                logger.info(f"Loaded soundboard with {len(self.soundboard.sounds)} sounds")
            except Exception as e:
                logger.error(f"Failed to load soundboard: {e}", exc_info=True)
                self.soundboard = SoundboardData()
        else:
            logger.warning(f"Soundboard file not found: {SOUNDBOARD_FILE}")

    async def cog_unload(self):
        logger.info("Unloading Soundboard cog...")
        try:
            if self.soundboard.sounds:
                save_soundboard(SOUNDBOARD_FILE, self.soundboard)
                logger.info(f"Saved {len(self.soundboard.sounds)} sounds")
        except Exception as e:
            logger.error(f"Save during unload failed: {e}", exc_info=True)
        self.soundboard.sounds.clear()
        logger.info("Soundboard cog cleanup complete")

    def increment_play_stats(self, guild_id: int, soundfile: str, user_id: str, trigger_word: str = None):
        """Increment play statistics for a sound and track trigger word usage."""
        guild_id_str = str(guild_id)
        user_id_str = str(user_id)

        # Find sound by soundfile
        sound_entry = None
        sound_key = None
        for key, entry in self.soundboard.sounds.items():
            if entry.soundfile == soundfile:
                sound_entry = entry
                sound_key = key
                break

        if not sound_entry:
            logger.warning(f"Soundfile '{soundfile}' not found")
            return

        stats = sound_entry.play_stats
        stats.week += 1
        stats.month += 1
        stats.total += 1
        stats.guild_play_count[guild_id_str] = stats.guild_play_count.get(guild_id_str, 0) + 1
        stats.last_played = datetime.utcnow().isoformat()
        stats.played_by = [user_id_str]

        # Track trigger word usage
        if trigger_word:
            stats.trigger_word_stats[trigger_word] = stats.trigger_word_stats.get(trigger_word, 0) + 1

        try:
            save_soundboard(SOUNDBOARD_FILE, self.soundboard)
            logger.debug(f"Updated stats for '{sound_entry.title}'" + (f" (trigger: '{trigger_word}')" if trigger_word else ""))
        except Exception as e:
            logger.error(f"Failed to save stats: {e}", exc_info=True)

    def reset_play_stats(self, period: str) -> int:
        """Reset play statistics for a given period."""
        if period not in ["week", "month"]:
            raise ValueError(f"Period must be 'week' or 'month', got '{period}'")

        count = 0
        for entry in self.soundboard.sounds.values():
            if period == "week":
                entry.play_stats.week = 0
            elif period == "month":
                entry.play_stats.month = 0
            count += 1

        try:
            save_soundboard(SOUNDBOARD_FILE, self.soundboard)
            logger.info(f"Reset {period} stats for {count} sounds")
        except Exception as e:
            logger.error(f"Failed to save after reset: {e}", exc_info=True)
            raise

        return count

    def get_soundfiles_for_text(self, guild_id: int, user_id: int, text: str) -> list[tuple[str, str, float, str]]:
        """Return list of (soundfile, sound_key, volume, trigger_word) tuples for matching words in text.

        If multiple sounds share the same trigger, randomly selects one.
        Returns the sound_key, volume, and trigger_word along with soundfile so stats can be tracked properly.
        """
        guild_id_str = str(guild_id)
        words = text.lower().split()
        matched_files = []
        seen_triggers = set()

        for word in words:
            word_lower = word.strip()
            if not word_lower:
                continue

            # Skip if we've already matched this trigger
            if word_lower in seen_triggers:
                continue

            # Find all sounds that match this trigger
            candidates = []
            for key, entry in self.soundboard.sounds.items():
                if word_lower not in [t.lower() for t in entry.triggers]:
                    continue

                if entry.is_disabled:
                    continue

                # Privacy check
                if entry.is_private and entry.guild_id != guild_id_str:
                    continue

                candidates.append((key, entry))

            # If we have candidates, randomly choose one
            if candidates:
                chosen_key, chosen_entry = random.choice(candidates)
                volume = chosen_entry.audio_metadata.volume_adjust
                matched_files.append((chosen_entry.soundfile, chosen_key, volume, word_lower))
                seen_triggers.add(word_lower)

                if len(candidates) > 1:
                    logger.info(
                        f"[{guild_id}] Randomly selected '{chosen_entry.title}' from {len(candidates)} sounds for trigger '{word_lower}'")

        if matched_files:
            logger.info(f"[{guild_id}] Found {len(matched_files)} sound(s) for: '{text}'")

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
        """Add a sound entry to the soundboard."""
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
            guild_id=guild_id,
            is_private=is_private,
            is_disabled=is_disabled
        )

        key = title.lower().replace(" ", "_")
        # Ensure unique key
        if key in self.soundboard.sounds:
            key = f"{guild_id}_{key}"

        self.soundboard.sounds[key] = entry

        try:
            save_soundboard(SOUNDBOARD_FILE, self.soundboard)
            logger.info(f"Added sound '{title}' to guild {guild_id}")
        except Exception as e:
            logger.error(f"Failed to save after adding '{title}': {e}", exc_info=True)
            raise

        return entry

    @commands.command(help="View all sounds in the soundboard")
    async def sounds(self, ctx):
        """Display interactive soundboard browser."""
        guild_id = str(ctx.guild.id)

        # Filter sounds by privacy
        filtered_sounds = {
            k: s for k, s in self.soundboard.sounds.items()
            if not s.is_private or s.guild_id == guild_id
        }

        if not filtered_sounds:
            return await ctx.send("🔭 No sounds available!")

        view = SoundboardView(self, guild_id, filtered_sounds)
        embed = view.create_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(name="addsound", help="Upload a sound (attach file)")
    async def addsound(self, ctx):
        """Upload a new sound with attached file."""
        if not ctx.message.attachments:
            return await ctx.send("❌ Please attach a sound file with the command.")

        attachment = ctx.message.attachments[0]
        if not attachment.filename.lower().endswith((".mp3", ".wav", ".ogg")):
            return await ctx.send("❌ Unsupported file type. Use mp3, wav, or ogg.")

        view = SoundUploadView(self, str(ctx.guild.id), attachment)
        await ctx.send(
            f"✅ I have the file `{attachment.filename}`. Click the button to add details!",
            view=view
        )

    @commands.command(name="leaderboard", help="Show sound, trigger word, or member leaderboard")
    async def leaderboard(self, ctx, mode: str = "triggers", *args):
        """
        Show top sounds, trigger words, or members by play count (guild-isolated).

        Usage:
            ~leaderboard triggers - Show top trigger words
            ~leaderboard sounds - Show top sounds
            ~leaderboard members - Show all-time top members in this guild
            ~leaderboard members week - Show weekly top members
            ~leaderboard members month - Show monthly top members
            ~leaderboard members pubg - Show all-time stats for "pubg" channel
            ~leaderboard members pubg week - Show weekly stats for "pubg" channel
            ~leaderboard members actual - Show with admin indicator (admin only)
        """
        if mode.lower() == "members":
            # Import user stats utilities
            from bot.core.stats.user_triggers import load_user_stats, get_leaderboard, render_bar_chart, USER_STATS_FILE
            from bot.core.admin.manager import is_admin

            try:
                user_stats = load_user_stats(USER_STATS_FILE)
                guild_id_str = str(ctx.guild.id)

                # Parse arguments: could be [period], [channel], [channel period], or [... actual]
                period = "total"  # default
                channel_name = None
                show_exact = False

                # Check for "actual" keyword
                args_list = list(args)
                if args_list and args_list[-1].lower() == "actual":
                    # Check if user is admin
                    user_roles = [role.id for role in ctx.author.roles]
                    if is_admin(ctx.author.id, user_roles):
                        show_exact = True
                    # Remove "actual" from args either way
                    args_list = args_list[:-1]

                # Check arguments
                if args_list:
                    # Check if last arg is a period
                    if args_list[-1].lower() in ["week", "month", "total"]:
                        period = args_list[-1].lower()
                        # Everything before is channel name
                        if len(args_list) > 1:
                            channel_name = " ".join(args_list[:-1])
                    else:
                        # All args are channel name
                        channel_name = " ".join(args_list)

                # Determine channel if specified
                voice_channel = None
                channel_id_str = None
                if channel_name:
                    for channel in ctx.guild.voice_channels:
                        if channel.name.lower() == channel_name.lower():
                            voice_channel = channel
                            channel_id_str = str(voice_channel.id)
                            break

                    if not voice_channel:
                        return await ctx.send(f"❌ Voice channel `{channel_name}` not found in this guild!")

                # Get leaderboard data
                leaderboard_data = get_leaderboard(
                    user_stats,
                    guild_id=guild_id_str,
                    period=period,
                    channel_id=channel_id_str,
                    limit=10
                )

                # Build title
                period_text = {"week": "Weekly", "month": "Monthly", "total": "All-Time"}[period]
                if voice_channel:
                    title = f"🏆 {period_text} Top Members in #{voice_channel.name}"
                else:
                    title = f"🏆 {period_text} Top Members in {ctx.guild.name}"

                # Add admin indicator if showing exact stats
                if show_exact:
                    title += " (Admin View)"

                embed = discord.Embed(title=title, color=discord.Color.gold())

                # Set guild icon as thumbnail
                if ctx.guild.icon:
                    embed.set_thumbnail(url=ctx.guild.icon.url)

                if leaderboard_data:
                    max_count = leaderboard_data[0][2]  # Highest count for bar scaling

                    for i, (user_id, username, count) in enumerate(leaderboard_data, 1):
                        # Get member info
                        try:
                            member = ctx.guild.get_member(int(user_id))
                            display_name = member.display_name if member else username
                            avatar_url = member.avatar.url if member and member.avatar else None
                        except:
                            display_name = username
                            avatar_url = None

                        # Add medal for top 3
                        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                        medal = medals.get(i, "")

                        # Render bar chart
                        bar = render_bar_chart(count, max_count, bar_length=15)

                        # Format value
                        value_text = f"{bar} **{count}** trigger{'s' if count != 1 else ''}"

                        # Add avatar as field thumbnail for #1
                        field_name = f"{medal} {i}. {display_name}"

                        embed.add_field(
                            name=field_name,
                            value=value_text,
                            inline=False
                        )

                        # Set #1 user's avatar as embed author icon
                        if i == 1 and avatar_url:
                            embed.set_author(name=f"👑 {display_name} is leading!", icon_url=avatar_url)

                else:
                    embed.description = "No member stats yet!"

                await ctx.send(embed=embed)

            except Exception as e:
                logger.error(f"Failed to load member leaderboard: {e}", exc_info=True)
                await ctx.send("❌ Failed to load member leaderboard!")

        elif mode.lower() == "triggers":
            # Collect all trigger word stats
            trigger_counts = {}
            for sound_entry in self.soundboard.sounds.values():
                for trigger_word, count in sound_entry.play_stats.trigger_word_stats.items():
                    trigger_counts[trigger_word] = trigger_counts.get(trigger_word, 0) + count

            # Sort and get top 10
            top_triggers = sorted(trigger_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            embed = discord.Embed(title="🏆 Top Trigger Words", color=discord.Color.gold())
            if top_triggers:
                for i, (trigger, count) in enumerate(top_triggers, 1):
                    embed.add_field(name=f"{i}. {trigger}", value=f"{count} plays", inline=False)
            else:
                embed.description = "No trigger word stats yet!"

            await ctx.send(embed=embed)
        else:
            # Show top sounds
            sounds_with_counts = [(key, entry, entry.play_stats.total)
                                  for key, entry in self.soundboard.sounds.items()]
            top_sounds = sorted(sounds_with_counts, key=lambda x: x[2], reverse=True)[:10]

            embed = discord.Embed(title="🏆 Top Sounds", color=discord.Color.gold())
            if top_sounds:
                for i, (key, entry, count) in enumerate(top_sounds, 1):
                    embed.add_field(name=f"{i}. {entry.title}", value=f"{count} plays", inline=False)
            else:
                embed.description = "No sounds played yet!"

            await ctx.send(embed=embed)

    @commands.command(name="mystats", help="Show your personal trigger statistics")
    async def mystats(self, ctx, member: discord.Member = None, show_actual: str = None):
        """
        Show personal trigger and activity statistics for yourself or another user.

        Usage:
            ~mystats - Show your own stats (ambiguous)
            ~mystats @User - Show another user's stats (ambiguous)
            ~mystats actual - Show your exact stats (admin only)
            ~mystats @User actual - Show exact stats for user (admin only)
        """
        from bot.core.stats.user_triggers import (
            load_user_stats, get_user_rank, get_user_channel_breakdown,
            get_user_top_triggers, render_progress_bar, USER_STATS_FILE
        )
        from bot.core.stats.activity import (
            load_activity_stats, get_user_activity_rank, get_activity_tier,
            ACTIVITY_STATS_FILE
        )
        from bot.core.admin.manager import is_admin

        try:
            # Check for "actual" keyword in arguments
            show_exact = False
            target_member = member if member else ctx.author

            # Handle "actual" keyword
            if show_actual and show_actual.lower() == "actual":
                # Check if user is admin
                user_roles = [role.id for role in ctx.author.roles]
                if not is_admin(ctx.author.id, user_roles):
                    return await ctx.send("❌ Only admins can view exact stats!")
                show_exact = True
            elif member and not isinstance(member, discord.Member):
                # If member parameter is actually the "actual" keyword
                if isinstance(member, str) and member.lower() == "actual":
                    user_roles = [role.id for role in ctx.author.roles]
                    if not is_admin(ctx.author.id, user_roles):
                        return await ctx.send("❌ Only admins can view exact stats!")
                    show_exact = True
                    target_member = ctx.author

            # Load stats
            user_stats = load_user_stats(USER_STATS_FILE)
            activity_stats = load_activity_stats(ACTIVITY_STATS_FILE)
            guild_id_str = str(ctx.guild.id)
            user_id_str = str(target_member.id)

            # Check if guild and user exist in trigger stats
            has_trigger_stats = (
                guild_id_str in user_stats.guilds and
                user_id_str in user_stats.guilds[guild_id_str].users
            )

            # Check if guild and user exist in activity stats
            has_activity_stats = (
                guild_id_str in activity_stats.guilds and
                user_id_str in activity_stats.guilds[guild_id_str].users
            )

            # Must have at least one type of stats
            if not has_trigger_stats and not has_activity_stats:
                return await ctx.send(f"❌ {target_member.display_name} has no stats yet!")

            user_stat = user_stats.guilds[guild_id_str].users[user_id_str] if has_trigger_stats else None

            # Create embed
            embed = discord.Embed(
                title=f"📊 Stats for {target_member.display_name}",
                color=discord.Color.blue()
            )

            # Set user's avatar
            if target_member.avatar:
                embed.set_thumbnail(url=target_member.avatar.url)

            # Add trigger stats if available
            if has_trigger_stats:
                # Get rank for different periods
                rank_total, count_total, total_users = get_user_rank(user_stats, guild_id_str, user_id_str, "total")
                rank_week, count_week, _ = get_user_rank(user_stats, guild_id_str, user_id_str, "week")
                rank_month, count_month, _ = get_user_rank(user_stats, guild_id_str, user_id_str, "month")

                # Add rank information
                rank_value = (
                    f"**All-Time:** #{rank_total} of {total_users} ({count_total} triggers)\n"
                    f"**This Week:** #{rank_week} ({count_week} triggers)\n"
                    f"**This Month:** #{rank_month} ({count_month} triggers)"
                )
                embed.add_field(name="🏆 Trigger Rankings", value=rank_value, inline=False)

                # Add progress to next milestone
                milestones = [10, 25, 50, 100, 250, 500, 1000, 2500, 5000]
                next_milestone = None
                for milestone in milestones:
                    if count_total < milestone:
                        next_milestone = milestone
                        break

                if next_milestone:
                    progress_bar = render_progress_bar(count_total, next_milestone)
                    embed.add_field(
                        name=f"📈 Progress to {next_milestone} Triggers",
                        value=f"{progress_bar} ({count_total}/{next_milestone})",
                        inline=False
                    )

                # Get channel breakdown
                channel_breakdown = get_user_channel_breakdown(user_stats, guild_id_str, user_id_str, limit=5)
                if channel_breakdown:
                    channel_lines = []
                    for ch_id, ch_count in channel_breakdown:
                        ch_obj = ctx.guild.get_channel(int(ch_id))
                        ch_name = ch_obj.name if ch_obj else f"Unknown"
                        channel_lines.append(f"**#{ch_name}:** {ch_count}")

                    channel_value = "\n".join(channel_lines)
                    embed.add_field(name="📍 Most Active Channels (Triggers)", value=channel_value, inline=False)

                # Add most used trigger words
                top_triggers = get_user_top_triggers(user_stats, guild_id_str, user_id_str, limit=5)
                if top_triggers:
                    trigger_lines = []
                    for trigger_word, trig_count in top_triggers:
                        trigger_lines.append(f"**`{trigger_word}`:** {trig_count}")

                    trigger_value = "\n".join(trigger_lines)
                    embed.add_field(name="🎯 Favorite Triggers", value=trigger_value, inline=False)

            # Add activity stats if available
            if has_activity_stats:
                activity_guild_stats = activity_stats.guilds[guild_id_str]
                user_activity_stat = activity_guild_stats.users[user_id_str]

                # Get activity rank
                activity_rank, activity_score, total_activity_users = get_user_activity_rank(
                    activity_stats, guild_id_str, user_id_str, "total", target_member.bot
                )

                if show_exact:
                    # Show exact stats for admins
                    activity_value = (
                        f"**Rank:** #{activity_rank} of {total_activity_users}\n"
                        f"**Activity Score:** {activity_score:.1f}\n\n"
                        f"**📝 Messages:** {user_activity_stat.activity_stats._message_count}\n"
                        f"**👍 Reactions Given:** {user_activity_stat.activity_stats._reaction_given} | "
                        f"**Received:** {user_activity_stat.activity_stats._reaction_received}\n"
                        f"**💬 Replies Given:** {user_activity_stat.activity_stats._replies_given} | "
                        f"**Received:** {user_activity_stat.activity_stats._replies_received}\n\n"
                        f"**🎤 Voice (Total):** {user_activity_stat.activity_stats._voice_total_minutes} min\n"
                        f"**🔊 Voice (Unmuted):** {user_activity_stat.activity_stats._voice_unmuted_minutes} min\n"
                        f"**🗣️ Voice (Speaking):** {user_activity_stat.activity_stats._voice_speaking_minutes} min"
                    )
                    embed.add_field(name="⚡ Activity Stats (Exact)", value=activity_value, inline=False)
                else:
                    # Show ambiguous stats for regular users
                    tier_name, tier_emoji, tier_desc = get_activity_tier(activity_score)
                    from bot.core.stats.activity import render_bar_chart, get_voice_time_display
                    from bot.config import config

                    # Find max score for bar chart
                    max_score = 0
                    for u_id, u_stat in activity_guild_stats.users.items():
                        if u_stat.is_bot == target_member.bot:
                            if u_stat.activity_stats.activity_score > max_score:
                                max_score = u_stat.activity_stats.activity_score

                    bar = render_bar_chart(int(activity_score), int(max_score))

                    # Get voice time based on configured tracking type
                    voice_minutes = 0
                    if config.voice_tracking_type == "total":
                        voice_minutes = user_activity_stat.activity_stats._voice_total_minutes
                    elif config.voice_tracking_type == "unmuted":
                        voice_minutes = user_activity_stat.activity_stats._voice_unmuted_minutes
                    elif config.voice_tracking_type == "speaking":
                        voice_minutes = user_activity_stat.activity_stats._voice_speaking_minutes

                    voice_display = get_voice_time_display(
                        voice_minutes,
                        display_mode=config.voice_time_display_mode,
                        tracking_type=config.voice_tracking_type
                    )

                    activity_value = (
                        f"**Rank:** #{activity_rank} of {total_activity_users}\n"
                        f"**Activity Score:** {activity_score:.1f}\n"
                        f"{bar} {tier_emoji}\n"
                        f"**{tier_name}** - {tier_desc}"
                    )

                    # Add voice time if not in points_only mode
                    if voice_display:
                        activity_value += f"\n\n{voice_display}"

                    embed.add_field(name="⚡ Activity Stats", value=activity_value, inline=False)

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to load personal stats: {e}", exc_info=True)
            await ctx.send("❌ Failed to load personal stats!")

    @commands.command(name="weeklyrecap", help="Show weekly recap of trigger usage (admin only)")
    @commands.has_permissions(administrator=True)
    async def weeklyrecap(self, ctx):
        """
        Display a weekly recap of trigger usage in the guild.

        Shows:
        - Top user of the week
        - Most active channel
        - Total triggers used
        - Average triggers per user
        """
        from bot.core.stats.user_triggers import load_user_stats, get_weekly_recap_data, USER_STATS_FILE

        try:
            user_stats = load_user_stats(USER_STATS_FILE)
            guild_id_str = str(ctx.guild.id)

            recap_data = get_weekly_recap_data(user_stats, guild_id_str)

            embed = discord.Embed(
                title=f"📅 Weekly Recap for {ctx.guild.name}",
                description="Here's what happened this week!",
                color=discord.Color.purple()
            )

            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            # Top user
            if recap_data["top_user"]:
                user_id, username, count = recap_data["top_user"]
                try:
                    member = ctx.guild.get_member(int(user_id))
                    display_name = member.display_name if member else username
                    avatar_url = member.avatar.url if member and member.avatar else None
                except:
                    display_name = username
                    avatar_url = None

                top_user_text = f"🥇 **{display_name}** with **{count}** triggers!"
                embed.add_field(name="👑 Top User", value=top_user_text, inline=False)

                if avatar_url:
                    embed.set_author(name=f"{display_name} dominated this week!", icon_url=avatar_url)
            else:
                embed.add_field(name="👑 Top User", value="No activity this week", inline=False)

            # Most active channel
            if recap_data["most_active_channel"]:
                channel_id, count = recap_data["most_active_channel"]
                channel_obj = ctx.guild.get_channel(int(channel_id))
                channel_name = channel_obj.name if channel_obj else "Unknown"

                channel_text = f"📍 **#{channel_name}** with **{count}** triggers"
                embed.add_field(name="🔥 Hottest Channel", value=channel_text, inline=False)
            else:
                embed.add_field(name="🔥 Hottest Channel", value="No activity", inline=False)

            # Stats summary
            stats_text = (
                f"**Total Triggers:** {recap_data['total_triggers']}\n"
                f"**Active Users:** {recap_data['total_users']}\n"
                f"**Avg Per User:** {recap_data['avg_per_user']:.1f}"
            )
            embed.add_field(name="📊 Week Summary", value=stats_text, inline=False)

            embed.set_footer(text="Use ~resetstats week members to reset weekly stats")

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to generate weekly recap: {e}", exc_info=True)
            await ctx.send("❌ Failed to generate weekly recap!")

    @commands.command(name="activityleaderboard", help="Show activity leaderboard")
    async def activityleaderboard(self, ctx, *args):
        """
        Show activity leaderboard (ambiguous by default, exact for admins with 'actual').

        Usage:
            ~activityleaderboard               # All-time human activity (ambiguous)
            ~activityleaderboard week          # Weekly human activity
            ~activityleaderboard bots          # Bot leaderboard
            ~activityleaderboard actual        # All-time with exact counts (admin only)
            ~activityleaderboard week actual   # Weekly exact counts (admin only)
            ~activityleaderboard bots actual   # Bot exact counts (admin only)
        """
        from bot.core.stats.activity import (
            load_activity_stats, get_activity_leaderboard, get_activity_tier,
            render_bar_chart, ACTIVITY_STATS_FILE
        )
        from bot.core.admin.manager import is_admin

        try:
            activity_stats = load_activity_stats(ACTIVITY_STATS_FILE)
            guild_id_str = str(ctx.guild.id)

            # Parse arguments
            period = "total"
            show_bots = False
            show_actual = False

            for arg in args:
                arg_lower = arg.lower()
                if arg_lower in ["daily", "weekly", "monthly", "total"]:
                    period = arg_lower
                elif arg_lower == "bots":
                    show_bots = True
                elif arg_lower == "actual":
                    # Check if user is admin
                    user_roles = [role.id for role in ctx.author.roles] if hasattr(ctx.author, 'roles') else []
                    if not is_admin(ctx.author.id, user_roles):
                        return await ctx.send("❌ Only admins can view actual stats!", delete_after=5)
                    show_actual = True

            # Get leaderboard data
            leaderboard_data = get_activity_leaderboard(
                activity_stats,
                guild_id=guild_id_str,
                period=period,
                include_bots=show_bots,
                limit=10
            )

            # Build title
            period_text = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly", "total": "All-Time"}[period]
            bot_text = " (Bots)" if show_bots else ""
            actual_text = " - Exact Data" if show_actual else ""
            title = f"📊 {period_text} Activity Leaderboard{bot_text}{actual_text}"

            embed = discord.Embed(title=title, color=discord.Color.green())

            # Set guild icon
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

            if leaderboard_data:
                max_score = leaderboard_data[0][2]  # Highest score for bar scaling

                for i, (user_id, username, score, is_bot) in enumerate(leaderboard_data, 1):
                    # Get member info
                    try:
                        member = ctx.guild.get_member(int(user_id))
                        display_name = member.display_name if member else username
                        avatar_url = member.avatar.url if member and member.avatar else None
                    except:
                        display_name = username
                        avatar_url = None

                    # Add medal for top 3
                    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
                    medal = medals.get(i, "")

                    if show_actual:
                        # Show exact internal stats (admin only)
                        user_stat = activity_stats.guilds[guild_id_str].users.get(str(user_id))
                        if user_stat:
                            stats = user_stat.activity_stats
                            value_text = (
                                f"**Messages:** {stats._message_count}\n"
                                f"**Reactions Given:** {stats._reaction_given} | **Received:** {stats._reaction_received}\n"
                                f"**Replies Given:** {stats._replies_given} | **Received:** {stats._replies_received}\n"
                                f"**Voice (Total/Unmuted/Speaking):** {stats._voice_total_minutes}/{stats._voice_unmuted_minutes}/{stats._voice_speaking_minutes} min\n"
                                f"**Activity Score:** {score:.1f}"
                            )
                        else:
                            value_text = f"Score: {score:.1f}"
                    else:
                        # Show ambiguous data
                        from bot.core.stats.activity import get_voice_time_display
                        from bot.config import config

                        tier_name, tier_emoji, tier_desc = get_activity_tier(score)
                        bar = render_bar_chart(int(score), int(max_score), bar_length=15)
                        value_text = f"{bar} {tier_emoji} **{tier_name}**\n{tier_desc} (Score: {int(score)})"

                        # Add voice time if enabled
                        user_stat = activity_stats.guilds[guild_id_str].users.get(str(user_id))
                        if user_stat:
                            voice_minutes = 0
                            if config.voice_tracking_type == "total":
                                voice_minutes = user_stat.activity_stats._voice_total_minutes
                            elif config.voice_tracking_type == "unmuted":
                                voice_minutes = user_stat.activity_stats._voice_unmuted_minutes
                            elif config.voice_tracking_type == "speaking":
                                voice_minutes = user_stat.activity_stats._voice_speaking_minutes

                            if voice_minutes > 0:
                                voice_display = get_voice_time_display(
                                    voice_minutes,
                                    display_mode=config.voice_time_display_mode,
                                    tracking_type=config.voice_tracking_type
                                )
                                if voice_display:
                                    value_text += f"\n{voice_display}"

                    field_name = f"{medal} {i}. {display_name}"
                    embed.add_field(name=field_name, value=value_text, inline=False)

                    # Set #1 user's avatar
                    if i == 1 and avatar_url:
                        embed.set_author(name=f"👑 {display_name} is most active!", icon_url=avatar_url)

            else:
                embed.description = "No activity stats yet!"

            await ctx.send(embed=embed)

        except Exception as e:
            logger.error(f"Failed to load activity leaderboard: {e}", exc_info=True)
            await ctx.send("❌ Failed to load activity leaderboard!")

    @commands.command(name="admincontrol", hidden=True)
    async def admincontrol(self, ctx, action: str = None, target: discord.Member = None):
        """
        Hidden command to manage bot admins (owner only).
        Not listed in help.

        Usage:
            ~admincontrol add @User       - Add user as admin
            ~admincontrol remove @User    - Remove user from admins
            ~admincontrol list            - List current admins
        """
        from bot.core.admin.manager import (
            is_owner, add_admin_user, remove_admin_user,
            get_admin_users, get_admin_roles
        )

        # Only owner can use this command
        if not is_owner(ctx.author.id):
            return  # Silently ignore non-owners

        if not action:
            return await ctx.send("❌ Usage: `~admincontrol [add|remove|list] [@User]`", delete_after=10)

        action = action.lower()

        if action == "list":
            admin_users = get_admin_users()
            admin_roles = get_admin_roles()

            embed = discord.Embed(
                title="🔐 Bot Admins",
                color=discord.Color.blue()
            )

            # List admin users
            if admin_users:
                user_lines = []
                for user_id in admin_users:
                    user = self.bot.get_user(user_id)
                    if user:
                        user_lines.append(f"• {user.mention} ({user.name})")
                    else:
                        user_lines.append(f"• Unknown User (ID: {user_id})")

                embed.add_field(
                    name="👥 Admin Users",
                    value="\n".join(user_lines),
                    inline=False
                )
            else:
                embed.add_field(name="👥 Admin Users", value="None", inline=False)

            # List admin roles
            if admin_roles:
                role_lines = []
                for role_id in admin_roles:
                    role = ctx.guild.get_role(role_id) if ctx.guild else None
                    if role:
                        role_lines.append(f"• {role.mention} ({role.name})")
                    else:
                        role_lines.append(f"• Unknown Role (ID: {role_id})")

                embed.add_field(
                    name="🎭 Admin Roles",
                    value="\n".join(role_lines),
                    inline=False
                )
            else:
                embed.add_field(name="🎭 Admin Roles", value="None", inline=False)

            await ctx.send(embed=embed, delete_after=30)

        elif action == "add":
            if not target:
                return await ctx.send("❌ Please mention a user to add as admin.", delete_after=10)

            if add_admin_user(target.id):
                await ctx.send(f"✅ Added {target.mention} as an admin.", delete_after=10)
                logger.info(f"[Admin] {ctx.author} added {target} as admin")
            else:
                await ctx.send(f"ℹ️ {target.mention} is already an admin.", delete_after=10)

        elif action == "remove":
            if not target:
                return await ctx.send("❌ Please mention a user to remove from admins.", delete_after=10)

            if remove_admin_user(target.id):
                await ctx.send(f"✅ Removed {target.mention} from admins.", delete_after=10)
                logger.info(f"[Admin] {ctx.author} removed {target} from admins")
            else:
                await ctx.send(f"❌ {target.mention} is not an admin or is the bot owner (cannot be removed).", delete_after=10)

        else:
            await ctx.send("❌ Invalid action. Use: `add`, `remove`, or `list`", delete_after=10)

    @commands.command(name="resetstats", help="Reset play statistics (week or month) [sounds|members|all]")
    @commands.has_permissions(administrator=True)
    async def resetstats(self, ctx, period: str, stat_type: str = "all"):
        """
        Reset play statistics for sounds and/or members.

        Usage:
            ~resetstats week sounds - Reset weekly sound stats
            ~resetstats month members - Reset monthly member trigger stats
            ~resetstats week all - Reset both sound and member stats
        """
        period_lower = period.lower()
        stat_type_lower = stat_type.lower()

        if period_lower not in ["week", "month"]:
            return await ctx.send("❌ Period must be either `week` or `month`")

        if stat_type_lower not in ["sounds", "members", "all"]:
            return await ctx.send("❌ Type must be either `sounds`, `members`, or `all`")

        results = []

        try:
            # Reset sound stats
            if stat_type_lower in ["sounds", "all"]:
                count = self.reset_play_stats(period_lower)
                results.append(f"sound(s): {count}")
                logger.info(f"[{ctx.guild.name}] {ctx.author} reset {period_lower} sound stats")

            # Reset member stats (guild-specific)
            if stat_type_lower in ["members", "all"]:
                from bot.core.stats.user_triggers import load_user_stats, save_user_stats, reset_user_stats, USER_STATS_FILE
                user_stats = load_user_stats(USER_STATS_FILE)
                count = reset_user_stats(user_stats, period_lower, guild_id=str(ctx.guild.id))
                save_user_stats(USER_STATS_FILE, user_stats)
                results.append(f"member(s): {count}")
                logger.info(f"[{ctx.guild.name}] {ctx.author} reset {period_lower} member stats")

            result_text = ", ".join(results)
            await ctx.send(f"✅ Reset {period_lower} statistics for {result_text}!")

        except Exception as e:
            logger.error(f"Reset stats failed: {e}", exc_info=True)
            await ctx.send(f"❌ Failed to reset {period_lower} statistics!")


async def setup(bot):
    """Load the Soundboard cog."""
    try:
        await bot.add_cog(Soundboard(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception:
        logger.error("Failed to load cog %s:\n%s", __name__, traceback.format_exc())