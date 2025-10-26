# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Note:** This project was restructured in October 2024 to use a domain-organized architecture. All code now lives in the `bot/` package with clear separation between cogs, core utilities, and UI components.

## Development Commands

**Running the bot:**
```bash
python bot/main.py
```

**Installing dependencies:**
```bash
uv sync                            # Using uv package manager
# OR
pip install -e .                   # Using pip with pyproject.toml
```

**Python version:** Requires Python 3.13+

## High-Level Architecture

### Core Bot Structure

This is a production-grade Discord bot using **discord.py** with a modular cog-based architecture:

1. **Entry Point:** `main.py` initializes the bot, loads all cogs from `cogs/`, sets up logging with rotating file handlers, and applies monkey patches for voice_recv compatibility.

2. **Configuration:** `config.py` uses dataclass-based config loaded from `.env` file with support for environment variable overrides. All bot settings (audio, ducking, monitoring) are centralized here.

3. **Modular Cogs:** All command modules in `cogs/` inherit from `BaseCog` which provides:
   - Automatic command tracking via `@track_command` decorator
   - Centralized error handling via `cog_command_error`
   - Integrated logging and metrics collection

### Voice & Audio Pipeline

The bot implements a sophisticated voice processing system:

**Voice Connection Flow:**
```
~join → VoiceRecvClient created
  ↓
~start → SpeechRecognitionSink attached
  ↓
User speaks → Vosk recognizes speech → JSON transcription
  ↓
Transcription checked against soundboard triggers
  ↓
Sound queued → Async queue processor → Plays via Discord
```

**Audio Ducking System:**
- `cogs/voicespeech.py` tracks speaking users per guild
- When user speaks: `DuckedAudioSource.duck()` reduces volume smoothly
- When user stops: `DuckedAudioSource.unduck()` restores volume
- Prevents audio from drowning out users

**Queue Architecture:**
- Per-guild `asyncio.Queue` for sound playback
- Singleton async task `_process_sound_queue()` per guild
- Prevents blocking main event loop
- 30-second timeout per sound with error recovery

### Key Files and Their Purposes

**`cogs/voicespeech.py`** - Voice reception and speech recognition hub
- Manages voice connections and audio playback queues
- Implements audio ducking when users speak
- Sends silence packets every 30s to keep connection alive
- Creates `SpeechRecognitionSink` for Vosk speech-to-text
- **Critical:** Uses `guild_id` isolation to prevent cross-guild interference

**`cogs/soundboard.py`** - Sound management and trigger system
- Flat JSON structure in `soundboard.json` with sound metadata
- Interactive UI with pagination (`SoundboardView`, `SoundEditView`)
- Auto-migration from old format to new flat structure
- Play statistics tracking: week/month/total/guild-specific counts
- Privacy controls and random selection for multi-trigger sounds

**`cogs/tts.py`** - Local text-to-speech using pyttsx3
- 20+ voice options with per-user preferences in `tts_preferences.json`
- Splits long text at sentence boundaries
- Integrates with VoiceSpeechCog queue system

**`utils/discord_audio_source.py`** & **`utils/pyaudio_player.py`**
- Implements Discord's `AudioSource` interface
- Reads audio in 20ms chunks (960 samples @ 48kHz)
- Smooth volume transitions and ducking control
- Handles multiple audio formats (MP3, WAV, OGG, etc.)

**`utils/admin_data_collector.py`** - Real-time metrics collection
- Time-series data in deques (auto-discard old data via `maxlen`)
- Exports JSON to `admin_data/` for dashboard consumption
- Background tasks for collection and export
- Singleton pattern via `get_data_collector()`

**`utils/error_handler.py`** - Centralized error management
- Error severity levels and categories
- Custom exceptions: `BotError`, `VoiceError`, `AudioError`
- Decorators: `@handle_errors()`, `@safe_operation()`
- Helper classes: `UserFeedback`, `Validator`, `ProgressTracker`

### Critical Implementation Details

**Monkey Patching (main.py:47-56):**
- Patches `discord-ext-voice-recv` `_remove_ssrc()` method
- Handles missing reader gracefully to prevent crashes
- Required for voice_recv library compatibility

**Guild Isolation:**
- All voice/audio operations pass `guild_id` to prevent cross-guild interference
- Each guild has separate sound queue and speaking user tracking

**Thread Safety:**
- All async operations from sync contexts use `asyncio.run_coroutine_threadsafe()`
- Proper event loop handling for cross-thread calls

**Memory Efficiency:**
- Deques use `maxlen` to auto-discard old data
- Rotating file handlers for logs with size limits

### Data Files

**`soundboard.json`** - Sound definitions with flat structure:
```json
{
  "sounds": {
    "trigger_name": {
      "title": "Sound Name",
      "triggers": ["hello", "hi"],
      "soundfile": "soundboard/sound.mp3",
      "volume_adjust": 1.0,
      "is_private": false,
      "is_disabled": false,
      "play_stats": {
        "week": 0, "month": 0, "total": 0,
        "last_played": null,
        "guild_stats": {}
      }
    }
  }
}
```

**`tts_preferences.json`** - Per-user TTS settings:
```json
{
  "user_id": {
    "name": "James",
    "gender": "male",
    "country": "Australia",
    "rate": 150
  }
}
```

**`.env`** - Required configuration:
```env
DISCORD_TOKEN=<bot-token>
COMMAND_PREFIX=~
ENABLE_ADMIN_DASHBOARD=true
DUCKING_ENABLED=true
DUCKING_LEVEL=0.5           # 0.0-1.0
DEFAULT_VOLUME=0.5
AUTO_DISCONNECT_DELAY=300   # seconds
MAX_HISTORY=1000
LOG_LEVEL=INFO
```

## Adding New Cogs

1. Create file in `cogs/` directory
2. Inherit from `BaseCog` for automatic error handling
3. Use `@track_command` decorator on command methods
4. Implement `async def setup(bot)` function

Example:
```python
from base_cog import BaseCog
from discord.ext import commands

class MyCog(BaseCog):
    @track_command
    @commands.command(name="mycommand")
    async def my_command(self, ctx):
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

The cog will be loaded automatically on bot startup.

## Important Notes

- **Voice Keepalive:** Bot sends silence packets every 30s to prevent disconnection
- **Error Recovery:** Individual sounds fail gracefully without stopping queue
- **Auto-backup:** Soundboard JSON automatically backed up before modifications
- **Ducking Transitions:** 50ms smooth transitions to prevent audio pops
- **Command Prefix:** Default is `~`, configurable via `.env`
- **Logs Location:** `logs/` directory with timestamp rotation
- **Admin Data:** Exported to `admin_data/` directory for dashboard