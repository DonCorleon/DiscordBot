# Discord Bot

A feature-rich Discord bot with voice recognition, TTS, soundboard, comprehensive user statistics, and voice time tracking.

## Features

- **Voice & Audio**
  - Text-to-Speech (TTS) using Edge TTS and local pyttsx3
  - Voice recognition with transcription logging
  - Audio playback with queue management and ducking
  - Customizable soundboard with trigger word detection
  - 20+ voice options with per-user preferences

- **User Statistics & Tracking**
  - Activity tracking (messages, reactions, replies)
  - Voice time tracking (total, unmuted, speaking)
  - Member leaderboards with guild/channel filtering
  - Personal stats with rankings and progress milestones
  - Trigger word usage statistics
  - Weekly recap summaries
  - Point-based scoring system with ambiguous display

- **Admin Dashboard**
  - Real-time bot monitoring with Pygame interface
  - Health metrics and connection tracking
  - Command usage statistics
  - Error logging and reporting
  - Live voice transcription display
  - Admin user management system
  - Exact stats viewing mode (admin only)

- **Modular Cog System**
  - Hot-reload functionality for cogs
  - Centralized error handling
  - Command execution tracking
  - Easy extensibility

## Requirements

- Python 3.13+
- Discord Bot Token

## Installation

1. Clone the repository:
```bash
git clone https://github.com/DonCorleon/DiscordBot.git
cd DiscordBot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file in the root directory:
```env
DISCORD_TOKEN=your_discord_token_here
COMMAND_PREFIX=~
ENABLE_ADMIN_DASHBOARD=true
VOICE_TRACKING_ENABLED=true
VOICE_POINTS_PER_MINUTE=0.0
VOICE_TIME_DISPLAY_MODE=ranges
```

4. Run the bot:
```bash
python main.py
```

## Configuration

Edit `.env` file or set environment variables:

### Core Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | Required | Your Discord bot token |
| `COMMAND_PREFIX` | `~` | Bot command prefix |
| `ENABLE_ADMIN_DASHBOARD` | `true` | Enable/disable Pygame dashboard |
| `LOG_LEVEL` | `INFO` | Logging level |

### Audio Settings
| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_VOLUME` | `0.5` | Default audio volume (0.0-1.0) |
| `DUCKING_ENABLED` | `true` | Enable audio ducking when users speak |
| `DUCKING_LEVEL` | `0.5` | Volume reduction when ducked (0.0-1.0) |

### Voice Time Tracking
| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_TRACKING_ENABLED` | `true` | Track voice channel time |
| `VOICE_POINTS_PER_MINUTE` | `0.0` | Points awarded per minute in voice |
| `VOICE_TIME_DISPLAY_MODE` | `ranges` | Display mode: ranges, descriptions, points_only |
| `VOICE_TRACKING_TYPE` | `total` | Type to track: total, unmuted, speaking |

### Admin System
| Variable | Default | Description |
|----------|---------|-------------|
| `WEEKLY_RECAP_ENABLED` | `false` | Enable weekly recap posting |
| `WEEKLY_RECAP_CHANNEL_ID` | None | Channel ID for weekly recaps |

## Commands

### General Commands
- `~status` - Show bot status and uptime
- `~help` - Display available commands
- `~info` - Show bot and dependency information
- `~reload [cog]` - Reload cog(s) (owner only)

### Voice & Audio Commands
- `~join` - Join your voice channel
- `~leave` - Leave voice channel
- `~start` - Start voice recognition
- `~stop` - Stop voice recognition
- `~play <sound>` - Play soundboard sound by trigger or title
- `~tts <text>` - Text-to-speech in voice channel
- `~setvoice` - Set your TTS voice preferences

### Soundboard Commands
- `~soundboard` - Interactive soundboard UI with pagination
- `~add` - Add new sound to soundboard
- `~edit <sound>` - Edit sound properties
- `~delete <sound>` - Delete sound from soundboard
- `~search <query>` - Search sounds by trigger or title
- `~random` - Play a random sound
- Trigger words automatically play sounds when spoken in voice chat

### Statistics & Leaderboards
- `~mystats [@user] [actual]` - View personal stats (triggers, activity, voice time)
- `~leaderboard triggers` - Top trigger words leaderboard
- `~leaderboard sounds` - Most played sounds leaderboard
- `~leaderboard members [period] [channel]` - Member trigger leaderboard
  - Periods: `week`, `month`, `total` (default)
  - Filter by voice channel name
- `~activityleaderboard [period] [bots] [actual]` - Activity leaderboard
  - Shows message, reaction, reply, and voice time stats
  - Periods: `daily`, `weekly`, `monthly`, `total` (default)
  - Add `actual` for exact stats (admin only)

### Admin Commands
- `~resetstats <week|month> <sounds|members|all>` - Reset statistics
- `~weeklyrecap` - Generate weekly stats summary (admin only)
- `~admincontrol <add|remove|list> [@user]` - Manage bot admins (owner only)

## Admin Dashboard

Run the admin dashboard (requires `ENABLE_ADMIN_DASHBOARD=true`):

```bash
python admin_interface_full.py
```

**Dashboard Features:**
- Real-time health monitoring
- Active connections display
- Command usage statistics
- Error tracking with severity levels
- Live voice transcription feed
- Soundboard management

**Controls:**
- Left Click: Navigate views
- Mouse Wheel: Scroll
- R: Refresh data
- ESC: Exit

## Project Structure

```
DiscordBot/
├── main.py                      # Bot entry point
├── config.py                    # Configuration management
├── base_cog.py                  # Base cog with error handling
│
├── cogs/                        # Bot command modules
│   ├── activity_tracker.py      # Activity & voice time tracking
│   ├── soundboard.py            # Soundboard + stats/leaderboards
│   ├── voicespeech.py           # Voice recognition
│   ├── tts.py                   # Text-to-speech
│   ├── monitoring.py            # Bot monitoring
│   └── base_commands.py         # General commands
│
├── utils/                       # Utility modules
│   ├── activity_stats.py        # Activity statistics data layer
│   ├── user_stats.py            # User trigger statistics
│   ├── admin_manager.py         # Admin user management
│   ├── admin_data_collector.py  # Metrics collection
│   ├── error_handler.py         # Error handling utilities
│   ├── discord_audio_source.py  # Audio source implementation
│   └── pyaudio_player.py        # Audio player
│
├── admin_interface_full.py      # Full admin dashboard
├── admin_interface_minimal.py   # Minimal dashboard
│
├── soundboard/                  # Audio files (MP3, OGG)
├── model/                       # Vosk speech model
├── logs/                        # Bot logs
├── admin_data/                  # Dashboard data exports
│
├── soundboard.json              # Sound definitions
├── activity_stats.json          # Activity statistics (runtime)
├── user_stats.json              # User trigger stats (runtime)
└── tts_preferences.json         # TTS user preferences
```

## Development

**Adding New Cogs:**
1. Create a new Python file in `cogs/` directory
2. Inherit from `BaseCog` for automatic error handling
3. Use `@track_command` decorator for command tracking
4. Add `async def setup(bot)` function

**Example:**
```python
from base_cog import BaseCog
from discord.ext import commands

class MyCog(BaseCog):
    @commands.command(name="mycommand")
    async def my_command(self, ctx):
        await ctx.send("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

## Key Features Explained

### Activity Tracking
The bot tracks three types of user activity:
- **Messages**: Sent messages, replies, reactions (given/received)
- **Voice Time**: Total time, unmuted time, speaking time
- **Triggers**: Soundboard trigger word usage

Statistics are stored in JSON files and can be displayed in:
- **Ambiguous mode** (default): Shows ranges/tiers to keep exact counts private
- **Exact mode** (admin only): Shows precise numbers for moderation

### Voice Time Tracking
Voice time is tracked in three ways:
- **Total**: All time spent in any voice channel
- **Unmuted**: Time when not muted or deafened
- **Speaking**: Time when actively speaking (detected by Discord)

A background task runs every minute to update voice time for all active sessions. Users earn configurable points per minute (default: 0).

### Leaderboards
Multiple leaderboard types available:
- **Trigger Words**: Most-used soundboard triggers
- **Sounds**: Most-played sounds
- **Members**: Top trigger users (filterable by time period and channel)
- **Activity**: Top active members (messages + reactions + voice time)

All leaderboards are guild-isolated to prevent cross-server data mixing.

## License

This project is open source and available for personal use.

## Author

Don Corleon - [GitHub](https://github.com/DonCorleon)
