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

from base_cog import BaseCog, logger

SOUNDBOARD_FILE = "soundboard.json"


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

    @commands.command(name="leaderboard", help="Show sound and trigger word leaderboard")
    async def leaderboard(self, ctx, mode: str = "sounds"):
        """Show top sounds or trigger words by play count."""
        if mode.lower() == "triggers":
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

    @commands.command(name="resetstats", help="Reset play statistics (week or month)")
    @commands.has_permissions(administrator=True)
    async def resetstats(self, ctx, period: str):
        """Reset play statistics for all sounds."""
        period_lower = period.lower()

        if period_lower not in ["week", "month"]:
            return await ctx.send("❌ Period must be either `week` or `month`")

        try:
            count = self.reset_play_stats(period_lower)
            await ctx.send(f"✅ Reset {period_lower} statistics for {count} sound(s)!")
            logger.info(f"[{ctx.guild.name}] {ctx.author} reset {period_lower} stats")
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