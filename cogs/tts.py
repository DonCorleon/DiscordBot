"""
Updated TTS Cog with ducking support via queue system.
"""

import discord
from discord.ext import commands
import pyttsx3
import asyncio
import tempfile
import os
import re
import json
from pathlib import Path
from base_cog import BaseCog, logger

# Preferences file
PREFERENCES_FILE = "tts_preferences.json"


class TtsCog(BaseCog):
    """Local TTS Cog using pyttsx3 for offline speech in VC with queue integration and ducking support."""

    voices = [
        {"name": "James", "country": "Australia", "gender": "male", "voice": "Microsoft James - English (Australia)"},
        {"name": "Catherine", "country": "Australia", "gender": "female",
         "voice": "Microsoft Catherine - English (Australia)"},
        {"name": "Richard", "country": "Canada", "gender": "male", "voice": "Microsoft Richard - English (Canada)"},
        {"name": "Linda", "country": "Canada", "gender": "female", "voice": "Microsoft Linda - English (Canada)"},
        {"name": "Huihui Desktop", "country": "China (Simplified)", "gender": "male",
         "voice": "Microsoft Huihui Desktop - Chinese (Simplified)"},
        {"name": "Hedda Desktop", "country": "Germany", "gender": "female",
         "voice": "Microsoft Hedda Desktop - German"},
        {"name": "Ravi", "country": "India", "gender": "male", "voice": "Microsoft Ravi - English (India)"},
        {"name": "Heera", "country": "India", "gender": "female", "voice": "Microsoft Heera - English (India)"},
        {"name": "Sean", "country": "Ireland", "gender": "male", "voice": "Microsoft Sean - English (Ireland)"},
        {"name": "Irina Desktop", "country": "Russia", "gender": "female",
         "voice": "Microsoft Irina Desktop - Russian"},
        {"name": "Pavel", "country": "Russia", "gender": "male", "voice": "Microsoft Pavel - Russian (Russia)"},
        {"name": "Lado", "country": "Slovenia", "gender": "male", "voice": "Microsoft Lado - Slovenian (Slovenia)"},
        {"name": "George", "country": "United Kingdom", "gender": "male",
         "voice": "Microsoft George - English (United Kingdom)"},
        {"name": "Hazel", "country": "United Kingdom", "gender": "female",
         "voice": "Microsoft Hazel - English (United Kingdom)"},
        {"name": "Susan", "country": "United Kingdom", "gender": "female",
         "voice": "Microsoft Susan - English (United Kingdom)"},
        {"name": "Hazel Desktop", "country": "United Kingdom", "gender": "female",
         "voice": "Microsoft Hazel Desktop - English (Great Britain)"},
        {"name": "David", "country": "United States", "gender": "male",
         "voice": "Microsoft David - English (United States)"},
        {"name": "Mark", "country": "United States", "gender": "male",
         "voice": "Microsoft Mark - English (United States)"},
        {"name": "David Desktop", "country": "United States", "gender": "male",
         "voice": "Microsoft David Desktop - English (United States)"},
        {"name": "Zira", "country": "United States", "gender": "female",
         "voice": "Microsoft Zira - English (United States)"},
        {"name": "Zira Desktop", "country": "United States", "gender": "female",
         "voice": "Microsoft Zira Desktop - English (United States)"},
    ]

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.volume = 1.5
        self.user_preferences = {}
        self.load_preferences()

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

    def get_user_preferences(self, user_id: int) -> dict:
        """Get preferences for a user, or return defaults."""
        user_id_str = str(user_id)
        if user_id_str in self.user_preferences:
            return self.user_preferences[user_id_str]
        return {"name": None, "gender": None, "country": None, "rate": 150}

    def set_user_preferences(self, user_id: int, **kwargs):
        """Set preferences for a user."""
        user_id_str = str(user_id)
        if user_id_str not in self.user_preferences:
            self.user_preferences[user_id_str] = {"name": None, "gender": None, "country": None, "rate": 150}

        for key, value in kwargs.items():
            if key in self.user_preferences[user_id_str]:
                self.user_preferences[user_id_str][key] = value

        self.save_preferences()

    def _select_voice(self, name=None, gender=None, country=None):
        """Return pyttsx3 voice ID matching criteria."""
        engine = pyttsx3.init()
        voice_list = engine.getProperty("voices")
        selected = None

        for v in self.voices:
            if name and name.lower() != v["name"].lower():
                continue
            if gender and gender.lower() != v["gender"].lower():
                continue
            if country and country.lower() not in v["country"].lower():
                continue
            selected = v
            break

        if selected:
            for py_name, py_id in [(v.name, v.id) for v in voice_list]:
                if selected["voice"] in py_name:
                    engine.stop()
                    return py_id
        engine.stop()
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

    async def generate_tts_file(self, text: str, name=None, gender=None, country=None, rate=150) -> str:
        """Generate TTS and save to temp file. Returns filepath."""
        loop = asyncio.get_running_loop()
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
        temp_file.close()

        def generate_tts():
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            engine.setProperty("volume", self.volume)
            voice_id = self._select_voice(name=name, gender=gender, country=country)
            if voice_id:
                engine.setProperty("voice", voice_id)
            engine.save_to_file(text, temp_file.name)
            engine.runAndWait()
            engine.stop()

        await loop.run_in_executor(None, generate_tts)
        return temp_file.name

    async def queue_tts(self, ctx, text: str, name=None, gender=None, country=None, rate=150):
        """Generate TTS and queue it for playback WITH DUCKING SUPPORT."""
        voice_cog = self.bot.get_cog("VoiceSpeechCog")
        if not voice_cog:
            logger.error("VoiceSpeechCog not found!")
            return await ctx.send("❌ Voice system not available!")

        chunks = self.split_text(text)

        if len(chunks) > 1:
            await ctx.send(f"📝 Splitting message into {len(chunks)} parts...")

        for i, chunk in enumerate(chunks):
            try:
                filepath = await self.generate_tts_file(chunk, name=name, gender=gender, country=country, rate=rate)
                # Use the queue_sound method which supports ducking!
                await voice_cog.queue_sound(ctx.guild.id, filepath, ctx.author, None, 1.0)
                logger.info(f"[{ctx.guild.name}] Queued TTS chunk {i + 1}/{len(chunks)}: '{chunk[:50]}...'")
            except Exception as e:
                logger.error(f"Failed to queue TTS chunk {i + 1}: {e}", exc_info=True)
                await ctx.send(f"❌ Failed to queue part {i + 1}")

    @commands.command(name="say", help="Speak text in voice channel with ducking support")
    async def say(self, ctx, *, message: str):
        """Speak text using TTS with optional voice settings. Now with ducking!"""
        vc = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ I'm not connected to a voice channel! Use ~join first.")

        prefs = self.get_user_preferences(ctx.author.id)
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
                        return await ctx.send("❌ Rate must be a number!")
                i += 2
            else:
                text_parts.append(words[i])
                i += 1

        text = " ".join(text_parts)
        if not text:
            return await ctx.send("⚠️ No text to speak!")

        await self.queue_tts(ctx, text, name=name, gender=gender, country=country, rate=rate)
        await ctx.send(f"💬 Queued TTS message (with ducking support!)")

    @commands.command(name="voices", help="List available TTS voices")
    async def list_voices(self, ctx):
        """List all available TTS voices."""
        voice_list = []
        for v in self.voices:
            voice_list.append(f"**{v['name']}** ({v['gender']}, {v['country']})")

        chunks = [voice_list[i:i + 10] for i in range(0, len(voice_list), 10)]

        for i, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"🎙️ Available TTS Voices (Page {i + 1}/{len(chunks)})",
                description="\n".join(chunk),
                color=discord.Color.blue()
            )
            embed.set_footer(text="Use ~setvoice to configure your preferences")
            await ctx.send(embed=embed)

    @commands.command(name="setvoice", help="Set your TTS voice preferences")
    async def set_voice(self, ctx, *, args: str = None):
        """Set TTS voice preferences. Example: ~setvoice --gender male --country australia --rate 150"""
        if not args:
            prefs = self.get_user_preferences(ctx.author.id)
            embed = discord.Embed(title="🎙️ Your TTS Preferences", color=discord.Color.green())
            embed.add_field(name="Name", value=prefs["name"] or "Auto", inline=True)
            embed.add_field(name="Gender", value=prefs["gender"] or "Auto", inline=True)
            embed.add_field(name="Country", value=prefs["country"] or "Auto", inline=True)
            embed.add_field(name="Rate", value=prefs["rate"], inline=True)
            embed.set_footer(text="Use ~setvoice --gender male --country australia --rate 150")
            return await ctx.send(embed=embed)

        words = args.split()
        updates = {}
        i = 0

        while i < len(words):
            if words[i].startswith("--") and i + 1 < len(words):
                key = words[i][2:].lower()
                value = words[i + 1]
                if key in ["name", "gender", "country"]:
                    updates[key] = value
                elif key == "rate":
                    try:
                        updates["rate"] = int(value)
                    except ValueError:
                        return await ctx.send("❌ Rate must be a number!")
                i += 2
            else:
                i += 1

        if updates:
            self.set_user_preferences(ctx.author.id, **updates)
            await ctx.send(f"✅ Updated your TTS preferences!")
        else:
            await ctx.send("⚠️ No valid preferences found. Use: ~setvoice --gender male --country australia")


async def setup(bot):
    try:
        await bot.add_cog(TtsCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")