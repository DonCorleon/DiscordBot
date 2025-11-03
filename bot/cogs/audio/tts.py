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

@dataclass
class TTSConfig(ConfigBase):
    """TTS (Text-to-Speech) configuration schema."""

    tts_engine: str = config_field(
        default="pyttsx3",
        description="TTS engine to use",
        category="Audio/Text-to-Speech",
        guild_override=True,
        choices=[
            ("pyttsx3", "Pyttsx3 (Local - espeak/SAPI)"),
            ("edge", "Edge TTS (Cloud - Microsoft Neural)"),
            ("piper", "Piper (Local Neural - High Quality)")
        ]
    )

    tts_default_voice: str = config_field(
        default="",
        description="Default TTS voice ID (use ~voices command to see available voices, leave empty for engine default)",
        category="Audio/Text-to-Speech",
        guild_override=True
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
    """TTS Cog with support for multiple engines (pyttsx3, Edge TTS, Piper)."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

        # TTS engines (per-guild caching)
        self.engines = {}  # {guild_id: TTSEngine}

        # Register config schema first (before creating engines)
        from bot.core.config_system import CogConfigSchema
        schema = CogConfigSchema.from_dataclass("TTS", TTSConfig)
        bot.config_manager.register_schema("TTS", schema)
        logger.info("Registered TTS config schema")

        # User preferences (voice customization)
        self.user_preferences = {}
        self.load_preferences()

    async def get_engine(self, guild_id: int):
        """Get or create TTS engine for this guild based on config."""
        from bot.core.tts_engines import create_tts_engine

        # Get configured engine type
        engine_type = self.bot.config_manager.get("TTS", "tts_engine", guild_id)

        # Check if we have a cached engine of the right type
        if guild_id in self.engines:
            cached_engine = self.engines[guild_id]
            cached_type = type(cached_engine).__name__.replace("Engine", "").lower()
            if cached_type == engine_type:
                return cached_engine
            else:
                # Engine type changed, clean up old engine
                logger.info(f"[Guild {guild_id}] TTS engine changed from {cached_type} to {engine_type}")
                if hasattr(cached_engine, 'cleanup'):
                    cached_engine.cleanup()
                del self.engines[guild_id]

        # Create new engine
        try:
            engine = create_tts_engine(self.bot, engine_type)
            self.engines[guild_id] = engine
            logger.info(f"[Guild {guild_id}] Created TTS engine: {engine_type}")
            return engine
        except ImportError as e:
            logger.error(f"[Guild {guild_id}] Failed to create {engine_type} engine: {e}")
            # Fallback to pyttsx3
            if engine_type != "pyttsx3":
                logger.info(f"[Guild {guild_id}] Falling back to pyttsx3")
                engine = create_tts_engine(self.bot, "pyttsx3")
                self.engines[guild_id] = engine
                return engine
            raise

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
        # Get the appropriate engine for this guild
        engine = await self.get_engine(guild_id)

        # Determine voice to use
        # For pyttsx3: name/gender/country can be used for voice selection (legacy support)
        # For other engines: name is the voice ID
        voice = None
        if name:
            voice = name
        elif not name and not gender and not country:
            # No preferences specified, use engine's default voice
            voice = engine.get_default_voice(guild_id)

        # Generate audio using the engine
        try:
            filepath = await engine.generate_audio(
                text=text,
                voice=voice,
                rate=rate,
                volume=volume,
                guild_id=guild_id
            )
            return filepath
        except Exception as e:
            logger.error(f"[Guild {guild_id}] TTS generation failed: {e}", exc_info=True)
            raise

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
        # Only use user prefs if they're actually set (not None)
        # This allows guild default voice to be used when user hasn't set preferences
        gender = prefs["gender"] if prefs["gender"] else None
        country = prefs["country"] if prefs["country"] else None
        name = prefs["name"] if prefs["name"] else None
        rate = prefs["rate"]

        logger.info(f"[Guild {ctx.guild.id}] User {ctx.author.id} TTS prefs: name={name}, gender={gender}, country={country}, rate={rate}")

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
        """Show all available TTS voices for current engine."""
        # Get engine for this guild
        try:
            engine = await self.get_engine(ctx.guild.id)
            engine_type = self.bot.config_manager.get("TTS", "tts_engine", ctx.guild.id)
        except Exception as e:
            return await UserFeedback.error(ctx, f"Failed to get TTS engine: {e}")

        # Get available voices from engine
        try:
            available_voices = await engine.list_voices()
        except Exception as e:
            logger.error(f"Failed to list voices: {e}", exc_info=True)
            return await UserFeedback.error(ctx, f"Failed to list voices: {e}")

        if not available_voices:
            return await UserFeedback.error(ctx, f"No TTS voices available for {engine_type} engine!")

        embed = discord.Embed(
            title=f"Available TTS Voices ({len(available_voices)} total)",
            description=f"Engine: **{engine_type}**\nUse ~setvoice --name <voice_id> or configure in web UI",
            color=discord.Color.blue()
        )

        # Group voices by language
        by_language = {}
        for voice in available_voices:
            language = voice.get("language", "Unknown")
            if language not in by_language:
                by_language[language] = []

            # Extract info
            voice_id = voice["id"]
            voice_name = voice["name"]
            gender = voice.get("gender", "unknown")
            gender_emoji = "♂️" if str(gender).lower() == "male" else "♀️" if str(gender).lower() == "female" else "⚧"

            by_language[language].append(f"{gender_emoji} `{voice_id}`\n  {voice_name}")

        # Add fields to embed (Discord limit: 25 fields, 1024 chars per field)
        field_count = 0
        for language, voices_list in sorted(by_language.items()):
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
                    field_name = f"{language}" if i == 0 else f"{language} (cont.)"
                    embed.add_field(name=field_name, value=chunk, inline=False)
                    field_count += 1
                    if field_count >= 25:
                        break
            else:
                embed.add_field(name=language, value=voices_text, inline=False)
                field_count += 1

        embed.set_footer(text="💡 Tip: Switch engine in web UI (pyttsx3/edge/piper)")
        await ctx.send(embed=embed)

    def cog_unload(self):
        """Cleanup when cog is unloaded."""
        for guild_id, engine in self.engines.items():
            if hasattr(engine, 'cleanup'):
                try:
                    engine.cleanup()
                    logger.info(f"[Guild {guild_id}] Cleaned up TTS engine")
                except Exception as e:
                    logger.error(f"[Guild {guild_id}] Failed to cleanup TTS engine: {e}")


async def setup(bot):
    try:
        await bot.add_cog(TtsCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")