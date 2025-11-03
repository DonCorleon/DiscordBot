# tts.py
import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import pyttsx3
import asyncio
import tempfile
import os
import re
import json
from dataclasses import dataclass
from pathlib import Path
from bot.base_cog import BaseCog, logger
from bot.core.errors import UserFeedback
from bot.core.config_base import ConfigBase, config_field

# Preferences file
PREFERENCES_FILE = "data/config/tts_preferences.json"


# -------- Configuration Schema --------

def _validate_voice_choice(value: str):
    """Validator for voice choice - extracts voice ID if it contains comma."""
    if not value:
        return True, ""

    # Handle malformed values like "zle/ru,Russian" - extract just the ID part
    if "," in value:
        value_parts = value.split(",")
        cleaned_value = value_parts[0].strip()
        return True, cleaned_value

    return True, ""


@dataclass
class TTSConfig(ConfigBase):
    """TTS (Text-to-Speech) configuration schema."""

    tts_default_voice: str = config_field(
        default="",
        description="Default TTS voice (leave empty for system default)",
        category="Audio/Text-to-Speech",
        guild_override=True,
        choices=[],  # Will be populated dynamically with available voices
        validator=_validate_voice_choice
    )

    tts_default_volume: float = config_field(
        default=1.5,
        description="Default TTS playback volume (0.0 = muted, 1.0 = normal, 2.0 = 200%)",
        category="Audio/Text-to-Speech",
        guild_override=True,
        min_value=0.0,
        max_value=2.0
    )

    tts_default_rate: int = config_field(
        default=150,
        description="Default TTS speech rate in words per minute",
        category="Audio/Text-to-Speech",
        guild_override=True,
        min_value=50,
        max_value=400
    )

    tts_max_text_length: int = config_field(
        default=500,
        description="Maximum text length for TTS messages (prevents spam)",
        category="Audio/Text-to-Speech",
        guild_override=True,
        admin_only=True,
        min_value=50,
        max_value=2000
    )


class TtsCog(BaseCog):
    """Local TTS Cog using pyttsx3 for offline speech in VC with queue integration."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

        # Discover available voices from the system
        self.available_voices = self._discover_voices()
        logger.info(f"Discovered {len(self.available_voices)} TTS voices on this system")

        # Register config schema with dynamic voice choices
        from bot.core.config_system import CogConfigSchema
        schema = CogConfigSchema.from_dataclass("TTS", TTSConfig)

        # Populate voice choices dynamically
        voice_choices = [("", "System Default")] + [(v["id"], v["name"]) for v in self.available_voices]
        if hasattr(schema.fields["tts_default_voice"], "choices"):
            schema.fields["tts_default_voice"].choices = voice_choices

        bot.config_manager.register_schema("TTS", schema)
        logger.info("Registered TTS config schema")

        self.user_preferences = {}
        self.load_preferences()

    def _discover_voices(self):
        """Discover all available TTS voices on the system."""
        try:
            engine = pyttsx3.init()
            system_voices = engine.getProperty("voices")
            discovered = []

            for voice in system_voices:
                # On Linux (espeak), voice.id might be like 'gmw/en' or 'zle/ru'
                # On Windows, voice.id is a full path or GUID
                # We'll store the full ID for proper voice selection
                voice_id = voice.id

                # Create a display name for the dropdown
                # For espeak voices, the name is typically the language name
                display_name = voice.name if hasattr(voice, 'name') else voice_id

                # Parse voice metadata
                voice_info = {
                    "id": voice_id,
                    "name": display_name,
                    "languages": voice.languages if hasattr(voice, "languages") else [],
                    "gender": voice.gender if hasattr(voice, "gender") else "unknown",
                    "age": voice.age if hasattr(voice, "age") else None
                }

                # Try to extract country/language info from name or languages
                country = "Unknown"
                if voice_info["languages"]:
                    # Languages are typically in format like ['en_US', 'en-US']
                    lang = str(voice_info["languages"][0]) if voice_info["languages"] else ""
                    if "_" in lang or "-" in lang:
                        country_code = lang.split("_")[-1].split("-")[-1]
                        country_map = {
                            "US": "United States",
                            "GB": "United Kingdom",
                            "AU": "Australia",
                            "CA": "Canada",
                            "IN": "India",
                            "IE": "Ireland",
                            "DE": "Germany",
                            "FR": "France",
                            "ES": "Spain",
                            "IT": "Italy",
                            "RU": "Russia",
                            "CN": "China",
                            "JP": "Japan"
                        }
                        country = country_map.get(country_code.upper(), country_code)

                # Extract country from name if present (e.g., "English (United States)")
                if "(" in display_name and ")" in display_name:
                    country_from_name = display_name.split("(")[-1].split(")")[0]
                    if country_from_name:
                        country = country_from_name

                voice_info["country"] = country
                discovered.append(voice_info)

            engine.stop()
            logger.debug(f"Discovered {len(discovered)} voices: {[v['id'] for v in discovered[:5]]}")
            return discovered

        except Exception as e:
            logger.error(f"Failed to discover TTS voices: {e}", exc_info=True)
            return []

    def load_preferences(self):
        """Load user preferences from JSON file."""
        try:
            if Path(PREFERENCES_FILE).exists():
                with open(PREFERENCES_FILE, "r", encoding="utf-8") as f:
                    self.user_preferences = json.load(f)
                logger.info(f"Loaded TTS preferences for {len(self.user_preferences)} users")
            else:
                logger.info("No TTS preferences file found, starting fresh")
        except Exception as e:
            logger.error(f"Failed to load TTS preferences: {e}", exc_info=True)
            self.user_preferences = {}

    def save_preferences(self):
        """Save user preferences to JSON file."""
        try:
            with open(PREFERENCES_FILE, "w", encoding="utf-8") as f:
                json.dump(self.user_preferences, f, indent=2)
            logger.debug("Saved TTS preferences")
        except Exception as e:
            logger.error(f"Failed to save TTS preferences: {e}", exc_info=True)

    def get_user_preferences(self, user_id: int, guild_id: int = None) -> dict:
        """Get preferences for a user, or return guild/global defaults."""
        user_id_str = str(user_id)
        if user_id_str in self.user_preferences:
            return self.user_preferences[user_id_str]

        # Get default rate from unified config manager
        default_rate = 150
        if guild_id and hasattr(self.bot, 'config_manager'):
            default_rate = self.bot.config_manager.get("TTS", "tts_default_rate", guild_id)

        return {"name": None, "gender": None, "country": None, "rate": default_rate}

    def set_user_preferences(self, user_id: int, **kwargs):
        """Set preferences for a user."""
        user_id_str = str(user_id)
        if user_id_str not in self.user_preferences:
            self.user_preferences[user_id_str] = {"name": None, "gender": None, "country": None, "rate": 150}

        for key, value in kwargs.items():
            if key in self.user_preferences[user_id_str]:
                self.user_preferences[user_id_str][key] = value

        self.save_preferences()

    def _select_voice(self, name=None, gender=None, country=None, guild_id=None):
        """Return pyttsx3 voice ID matching criteria or configured default voice."""
        # If no criteria provided, use the configured default voice
        if not name and not gender and not country and guild_id:
            default_voice = self.bot.config_manager.get("TTS", "tts_default_voice", guild_id)
            if default_voice:
                return default_voice

        # Search for matching voice in discovered voices
        for voice in self.available_voices:
            # Match by exact voice ID if name matches the full voice ID
            if name and name == voice["id"]:
                return voice["id"]

            # Match by name (partial or full)
            if name and name.lower() in voice["name"].lower():
                # Check gender and country if specified
                if gender and str(voice.get("gender", "")).lower() != gender.lower():
                    continue
                if country and country.lower() not in voice.get("country", "").lower():
                    continue
                return voice["id"]

            # Match by gender and/or country only
            if not name:
                gender_match = (not gender or str(voice.get("gender", "")).lower() == gender.lower())
                country_match = (not country or country.lower() in voice.get("country", "").lower())
                if gender_match and country_match:
                    return voice["id"]

        # No match found, return None (will use system default)
        return None

    def split_text(self, text: str, max_length: int = 500) -> list:
        """Split text into chunks at sentence boundaries."""
        if len(text) <= max_length:
            return [text]

        sentence_pattern = r'([.!?]+[\s]+)'
        parts = re.split(sentence_pattern, text)

        sentences = []
        for i in range(0, len(parts), 2):
            if i + 1 < len(parts):
                sentences.append(parts[i] + parts[i + 1])
            else:
                sentences.append(parts[i])

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            if len(current_chunk) + len(sentence) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    if len(sentence) > max_length:
                        words = sentence.split()
                        temp_chunk = ""
                        for word in words:
                            if len(temp_chunk) + len(word) + 1 > max_length:
                                if temp_chunk:
                                    chunks.append(temp_chunk.strip())
                                temp_chunk = word
                            else:
                                temp_chunk += " " + word if temp_chunk else word
                        if temp_chunk:
                            current_chunk = temp_chunk
                    else:
                        current_chunk = sentence
            else:
                current_chunk += " " + sentence if current_chunk else sentence

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text]

    async def generate_tts_file(self, text: str, name=None, gender=None, country=None, rate=150, volume=1.5, guild_id=None) -> str:
        """Generate TTS and save to temp file. Returns filepath."""
        loop = asyncio.get_running_loop()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.close()

        def generate_tts():
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.setProperty("volume", volume)
            voice_id = self._select_voice(name=name, gender=gender, country=country, guild_id=guild_id)
            if voice_id:
                engine.setProperty("voice", voice_id)
            engine.save_to_file(text, temp_file.name)
            engine.runAndWait()
            engine.stop()

        await loop.run_in_executor(None, generate_tts)
        return temp_file.name

    async def queue_tts(self, ctx, text: str, name=None, gender=None, country=None, rate=150):
        """Generate TTS and queue it for playback."""
        voice_cog = self.bot.get_cog("VoiceSpeechCog")
        if not voice_cog:
            logger.error("VoiceSpeechCog not found!")
            return await UserFeedback.error(ctx, "Voice system not available!")

        # Get guild config for volume and max text length from unified config manager
        volume = 1.5  # default
        max_length = 500  # default
        if hasattr(self.bot, 'config_manager'):
            volume = self.bot.config_manager.get("TTS", "tts_default_volume", ctx.guild.id)
            max_length = self.bot.config_manager.get("TTS", "tts_max_text_length", ctx.guild.id)

        chunks = self.split_text(text, max_length=max_length)

        if len(chunks) > 1:
            await UserFeedback.info(ctx, f"Splitting message into {len(chunks)} parts...")

        for i, chunk in enumerate(chunks):
            try:
                filepath = await self.generate_tts_file(chunk, name=name, gender=gender, country=country, rate=rate, volume=volume, guild_id=ctx.guild.id)

                # CRITICAL FIX: Pass ctx.guild.id to queue_sound for guild isolation
                await voice_cog.queue_sound(ctx.guild.id, filepath, ctx.author, None, 1.0)

                # Add to transcript
                if ctx.voice_client and ctx.voice_client.channel:
                    voice_cog.transcript_manager.add_bot_message(
                        channel_id=str(ctx.voice_client.channel.id),
                        bot_id=str(self.bot.user.id),
                        bot_name=self.bot.user.name,
                        message_type="TTS",
                        content=f"[{ctx.author.display_name}] {chunk}"
                    )

                logger.info(
                    f"[Guild {ctx.guild.id}:{ctx.guild.name}] Queued TTS chunk {i + 1}/{len(chunks)}: '{chunk[:50]}...'")
            except Exception as e:
                logger.error(f"[Guild {ctx.guild.id}] Failed to queue TTS chunk {i + 1}: {e}", exc_info=True)
                await UserFeedback.error(ctx, f"Failed to queue part {i + 1}")

    @commands.command(name="say", help="Speak text in voice channel")
    async def say(self, ctx, *, message: str):
        """Speak text using TTS with optional voice settings."""
        vc = ctx.voice_client
        if not vc:
            return await UserFeedback.warning(ctx, "I'm not connected to a voice channel! Use ~join first.")

        prefs = self.get_user_preferences(ctx.author.id, guild_id=ctx.guild.id)
        gender = prefs["gender"]
        country = prefs["country"]
        name = prefs["name"]
        rate = prefs["rate"]

        words = message.split()
        text_parts = []
        i = 0

        while i < len(words):
            if words[i].startswith("--") and i + 1 < len(words):
                key = words[i][2:].lower()
                value = words[i + 1]
                if key == "gender":
                    gender = value
                elif key == "country":
                    country = value
                elif key == "name":
                    name = value
                elif key == "rate":
                    try:
                        rate = int(value)
                    except ValueError:
                        return await UserFeedback.error(ctx, "Rate must be a number!")
                i += 2
            else:
                text_parts.append(words[i])
                i += 1

        text = " ".join(text_parts)
        if not text:
            return await UserFeedback.error(ctx, "No text to speak!")

        voice_info = []
        if name:
            voice_info.append(f"Name: {name}")
        if gender:
            voice_info.append(f"Gender: {gender}")
        if country:
            voice_info.append(f"Country: {country}")
        if rate != 150:
            voice_info.append(f"Rate: {rate}")

        status_msg = f"Speaking: `{text[:100]}{'...' if len(text) > 100 else ''}`"
        if voice_info:
            status_msg += f"\nSettings: {' - '.join(voice_info)}"

        await ctx.send(status_msg)
        await self.queue_tts(ctx, text, name=name, gender=gender, country=country, rate=rate)

    @commands.command(name="setvoice", help="Set your default TTS voice preferences")
    async def setvoice(self, ctx, *, settings: str = None):
        """Set your default TTS voice preferences."""
        if settings and settings.lower() == "reset":
            user_id_str = str(ctx.author.id)
            if user_id_str in self.user_preferences:
                del self.user_preferences[user_id_str]
                self.save_preferences()
                await UserFeedback.success(ctx, "Voice preferences reset to defaults!")
            else:
                await UserFeedback.info(ctx, "You don't have any saved preferences.")
            return

        if not settings:
            prefs = self.get_user_preferences(ctx.author.id, guild_id=ctx.guild.id)
            embed = discord.Embed(title="Your TTS Voice Preferences", color=discord.Color.blue())
            embed.add_field(name="Name", value=prefs["name"] or "Not set", inline=True)
            embed.add_field(name="Gender", value=prefs["gender"] or "Not set", inline=True)
            embed.add_field(name="Country", value=prefs["country"] or "Not set", inline=True)
            embed.add_field(name="Rate", value=str(prefs["rate"]), inline=True)
            embed.set_footer(text="Use ~setvoice --name <n> --gender <g> --country <c> --rate <r> to update")
            return await ctx.send(embed=embed)

        words = settings.split()
        updates = {}
        i = 0

        while i < len(words):
            if words[i].startswith("--") and i + 1 < len(words):
                key = words[i][2:].lower()
                value = words[i + 1]
                if key == "gender":
                    updates["gender"] = value
                elif key == "country":
                    updates["country"] = value
                elif key == "name":
                    updates["name"] = value
                elif key == "rate":
                    try:
                        updates["rate"] = int(value)
                    except ValueError:
                        return await UserFeedback.error(ctx, "Rate must be a number!")
                i += 2
            else:
                i += 1

        if not updates:
            return await UserFeedback.error(ctx, "No valid settings provided! Use --name, --gender, --country, or --rate")

        self.set_user_preferences(ctx.author.id, **updates)
        prefs = self.get_user_preferences(ctx.author.id, guild_id=ctx.guild.id)

        embed = discord.Embed(title="Voice Preferences Updated", color=discord.Color.green())
        embed.add_field(name="Name", value=prefs["name"] or "Not set", inline=True)
        embed.add_field(name="Gender", value=prefs["gender"] or "Not set", inline=True)
        embed.add_field(name="Country", value=prefs["country"] or "Not set", inline=True)
        embed.add_field(name="Rate", value=str(prefs["rate"]), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="voices", help="List available TTS voices")
    async def list_voices(self, ctx):
        """Show all available TTS voices grouped by country."""
        if not self.available_voices:
            return await UserFeedback.error(ctx, "No TTS voices available on this system!")

        embed = discord.Embed(
            title=f"Available TTS Voices ({len(self.available_voices)} total)",
            description="Use ~setvoice --name <voice_name> or configure default in web UI",
            color=discord.Color.blue()
        )

        # Group voices by country
        by_country = {}
        for voice in self.available_voices:
            country = voice.get("country", "Unknown")
            if country not in by_country:
                by_country[country] = []

            # Extract short name from full voice name
            short_name = voice["name"]
            if " - " in short_name:
                short_name = short_name.split(" - ")[0].replace("Microsoft ", "")

            gender = voice.get("gender", "unknown")
            gender_emoji = "♂️" if str(gender).lower() == "male" else "♀️" if str(gender).lower() == "female" else "⚧"

            by_country[country].append(f"{gender_emoji} **{short_name}**")

        # Add fields to embed (Discord limit: 25 fields, 1024 chars per field)
        field_count = 0
        for country, voices_list in sorted(by_country.items()):
            if field_count >= 25:
                break

            # Split long voice lists into multiple fields if needed
            voices_text = "\n".join(voices_list)
            if len(voices_text) > 1024:
                # Split into chunks
                chunks = []
                current_chunk = []
                current_length = 0

                for voice_entry in voices_list:
                    entry_length = len(voice_entry) + 1  # +1 for newline
                    if current_length + entry_length > 1024:
                        chunks.append("\n".join(current_chunk))
                        current_chunk = [voice_entry]
                        current_length = entry_length
                    else:
                        current_chunk.append(voice_entry)
                        current_length += entry_length

                if current_chunk:
                    chunks.append("\n".join(current_chunk))

                for i, chunk in enumerate(chunks):
                    field_name = f"{country}" if i == 0 else f"{country} (cont.)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
                    field_count += 1
                    if field_count >= 25:
                        break
            else:
                embed.add_field(name=country, value=voices_text, inline=False)
                field_count += 1

        embed.set_footer(text="💡 Tip: Set default voice in web UI or use --rate to adjust speech speed")
        await ctx.send(embed=embed)


async def setup(bot):
    try:
        await bot.add_cog(TtsCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")