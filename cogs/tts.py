import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import pyttsx3
import asyncio
import tempfile
import os
from base_cog import BaseCog, logger

class TtsCog(BaseCog):
    """Local TTS Cog using pyttsx3 for offline speech in VC."""

    voices = [
        {"name": "James", "country": "Australia", "gender": "male", "voice": "Microsoft James - English (Australia)"},
        {"name": "Catherine", "country": "Australia", "gender": "female", "voice": "Microsoft Catherine - English (Australia)"},
        {"name": "Richard", "country": "Canada", "gender": "male", "voice": "Microsoft Richard - English (Canada)"},
        {"name": "Linda", "country": "Canada", "gender": "female", "voice": "Microsoft Linda - English (Canada)"},
        {"name": "Huihui Desktop", "country": "China (Simplified)", "gender": "male", "voice": "Microsoft Huihui Desktop - Chinese (Simplified)"},
        {"name": "Hedda Desktop", "country": "Germany", "gender": "female", "voice": "Microsoft Hedda Desktop - German"},
        {"name": "Ravi", "country": "India", "gender": "male", "voice": "Microsoft Ravi - English (India)"},
        {"name": "Heera", "country": "India", "gender": "female", "voice": "Microsoft Heera - English (India)"},
        {"name": "Sean", "country": "Ireland", "gender": "male", "voice": "Microsoft Sean - English (Ireland)"},
        {"name": "Irina Desktop", "country": "Russia", "gender": "female", "voice": "Microsoft Irina Desktop - Russian"},
        {"name": "Pavel", "country": "Russia", "gender": "male", "voice": "Microsoft Pavel - Russian (Russia)"},
        {"name": "Lado", "country": "Slovenia", "gender": "male", "voice": "Microsoft Lado - Slovenian (Slovenia)"},
        {"name": "George", "country": "United Kingdom", "gender": "male", "voice": "Microsoft George - English (United Kingdom)"},
        {"name": "Hazel", "country": "United Kingdom", "gender": "female", "voice": "Microsoft Hazel - English (United Kingdom)"},
        {"name": "Susan", "country": "United Kingdom", "gender": "female", "voice": "Microsoft Susan - English (United Kingdom)"},
        {"name": "Hazel Desktop", "country": "United Kingdom", "gender": "female", "voice": "Microsoft Hazel Desktop - English (Great Britain)"},
        {"name": "David", "country": "United States", "gender": "male", "voice": "Microsoft David - English (United States)"},
        {"name": "Mark", "country": "United States", "gender": "male", "voice": "Microsoft Mark - English (United States)"},
        {"name": "David Desktop", "country": "United States", "gender": "male", "voice": "Microsoft David Desktop - English (United States)"},
        {"name": "Zira", "country": "United States", "gender": "female", "voice": "Microsoft Zira - English (United States)"},
        {"name": "Zira Desktop", "country": "United States", "gender": "female", "voice": "Microsoft Zira Desktop - English (United States)"},
    ]

    def __init__(self, bot):
        self.bot = bot
        self.volume = 1.5

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

    async def speak_in_vc(self, vc: discord.VoiceClient, text: str, name=None, gender=None, country=None, rate=150, volume=1.0):
        """Generate TTS, save to temp file, and play in VC asynchronously."""
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

        # Play in VC
        if vc.is_playing():
            await asyncio.sleep(0.1)  # simple wait; can implement queue if needed
        vc.play(FFmpegPCMAudio(temp_file.name), after=lambda e: os.remove(temp_file.name))

    @commands.command(help="Speak text in the voice channel with optional voice settings")
    async def say(self, ctx, *, message: str):
        """Example usage: ~say Hello! --gender male --country Australia --name James"""
        vc: discord.VoiceClient = ctx.voice_client
        if not vc:
            return await ctx.send("⚠️ Join a voice channel first!")

        # Initialize
        gender = None
        country = None
        name = None

        # Split message into words
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
                i += 2  # skip both key and value
            else:
                text_parts.append(words[i])
                i += 1

        text = " ".join(text_parts)
        if not text:
            return await ctx.send("⚠️ No text to speak!")

        await self.speak_in_vc(vc, text, gender=gender, country=country, name=name)
        await ctx.send(f"🎤 Speaking: `{text}`\nOptional args -> gender: {gender}, country: {country}, name: {name}")


async def setup(bot):
    try:
        await bot.add_cog(TtsCog(bot))
        logger.info(f"{__name__} loaded successfully")
    except Exception as e:
        logger.error(f"Failed to load cog {__name__}: {e}")
