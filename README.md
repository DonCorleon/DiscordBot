# Discord Bot

A production-grade Discord bot with voice recognition, TTS, soundboard, comprehensive user statistics, voice time tracking, and web-based admin dashboard.

## Features

- **Voice & Audio**
  - Text-to-Speech (TTS) using Edge TTS and local pyttsx3
  - Voice recognition with real-time transcription (Vosk)
  - Session-based transcript recording with historical viewer
  - Audio playback with per-guild queue management and ducking
  - Customizable soundboard with trigger word detection
  - 20+ voice options with per-user preferences
  - Auto-join and auto-disconnect functionality

- **User Statistics & Tracking**
  - Activity tracking (messages, reactions, replies)
  - Voice time tracking (total, unmuted, speaking)
  - Member leaderboards with guild/channel filtering
  - Personal stats with rankings and progress milestones
  - Trigger word usage statistics
  - Weekly recap summaries
  - Point-based scoring system with ambiguous display

- **Web Admin Dashboard**
  - Modern FastAPI-based web interface
  - Real-time bot monitoring with WebSocket updates
  - Live voice transcription display
  - Historical transcript viewer (browse past voice sessions)
  - Interactive JSON editor for configuration files
  - Unified configuration system with per-guild overrides
  - Health metrics and connection tracking
  - Command usage statistics
  - Error logging and reporting
  - Admin user management system
  - Exact stats viewing mode (admin only)

- **Modular Cog System**
  - Domain-organized architecture (bot/cogs/, bot/core/, bot/ui/)
  - Hot-reload functionality for cogs
  - Centralized error handling via BaseCog
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
uv sync                # Using uv package manager (recommended)
# OR
pip install -e .       # Using pip with pyproject.toml
```

3. Create a `.env` file in the root directory:
```env
DISCORD_TOKEN=your_discord_token_here
COMMAND_PREFIX=~
BOT_OWNER_ID=your_discord_user_id
LOG_LEVEL=INFO

# Web Dashboard
ENABLE_WEB_DASHBOARD=true
WEB_HOST=127.0.0.1
WEB_PORT=8000

# Voice Settings
VOICE_TRACKING_ENABLED=true
VOICE_POINTS_PER_MINUTE=0.0
VOICE_TIME_DISPLAY_MODE=ranges
```

4. Run the bot:
```bash
python bot/main.py
```

## Configuration

The bot uses a unified ConfigManager system with support for:
- Environment variables (`.env` file)
- Global configuration overrides (`data/config/base_config.json`)
- Per-guild configuration overrides (`data/config/guilds/{guild_id}.json`)
- Web-based configuration UI at `http://localhost:8000/config`

### Essential Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DISCORD_TOKEN` | Yes | - | Your Discord bot token |
| `BOT_OWNER_ID` | Yes | - | Your Discord user ID (for admin access) |
| `COMMAND_PREFIX` | No | `~` | Bot command prefix |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

### Web Dashboard Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_WEB_DASHBOARD` | `true` | Enable/disable web dashboard |
| `WEB_HOST` | `127.0.0.1` | Dashboard host address |
| `WEB_PORT` | `8000` | Dashboard port |
| `WEB_RELOAD` | `false` | Enable hot reload (development only) |

### Voice & Audio Settings

Most audio settings can be configured via the web UI at runtime. Key environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_VOLUME` | `0.5` | Default audio volume (0.0-1.0) |
| `DUCKING_ENABLED` | `true` | Enable audio ducking when users speak |
| `DUCKING_LEVEL` | `0.5` | Volume reduction when ducked (0.0-1.0) |
| `VOICE_TRACKING_ENABLED` | `true` | Track voice channel time |
| `VOICE_TIME_DISPLAY_MODE` | `ranges` | Display mode: ranges, descriptions, points_only |

### Transcript Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `TRANSCRIPT_ENABLED` | `true` | Enable session transcript recording |
| `TRANSCRIPT_FLUSH_INTERVAL` | `30` | Seconds between transcript saves (5-300) |
| `TRANSCRIPT_DIR` | `data/transcripts/sessions` | Transcript storage directory |

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

## Web Admin Dashboard

Access the web dashboard at `http://localhost:8000` (requires `ENABLE_WEB_DASHBOARD=true` in `.env`).

**Dashboard Pages:**

- **Home** (`/`) - Bot status overview and health metrics
- **Configuration** (`/config`) - Interactive config editor with per-guild overrides
- **Transcripts** (`/transcripts`) - Live and historical voice session transcripts
- **JSON Editor** (`/json-editor`) - Edit configuration files with table interface
- **Monitoring** - Real-time WebSocket updates for bot metrics

**Key Features:**
- Real-time health monitoring via WebSocket
- Live voice transcription display
- Historical transcript viewer with session browsing
- Interactive configuration management
- Command usage statistics
- Error tracking with severity levels
- Per-guild configuration overrides
- JSON file backup system

## Project Structure

```
DiscordBot/
├── bot/                              # Main bot package (domain-organized)
│   ├── main.py                       # Bot entry point
│   ├── config.py                     # Legacy config (deprecated)
│   ├── base_cog.py                   # Base cog with error handling
│   │
│   ├── cogs/                         # Discord command modules (UI layer)
│   │   ├── admin/
│   │   │   └── monitoring.py         # Bot monitoring commands
│   │   ├── activity/
│   │   │   └── tracker.py            # Activity & voice time tracking
│   │   ├── audio/
│   │   │   ├── soundboard.py         # Soundboard commands
│   │   │   ├── voice_speech.py       # Voice recognition
│   │   │   ├── tts.py                # Text-to-speech
│   │   │   └── edge_tts.py           # Edge TTS integration
│   │   ├── errors.py                 # Error handling cog
│   │   └── utility/
│   │       ├── base_commands.py      # General commands
│   │       └── test.py               # Test commands
│   │
│   ├── core/                         # Business logic (reusable)
│   │   ├── config_system.py          # Unified ConfigManager
│   │   ├── system_config.py          # System-level config schema
│   │   ├── errors.py                 # Custom exceptions
│   │   ├── transcript_session.py     # Transcript recording manager
│   │   ├── admin/
│   │   │   ├── manager.py            # Admin user management
│   │   │   └── data_collector.py     # Metrics collection
│   │   ├── audio/
│   │   │   ├── sources.py            # Discord audio source
│   │   │   ├── player.py             # PyAudio player
│   │   │   └── auto_join.py          # Auto-join logic
│   │   └── stats/
│   │       ├── activity.py           # Activity statistics
│   │       └── user_triggers.py      # User trigger statistics
│   │
│   └── ui/                           # UI components
│       └── (Discord views/modals)
│
├── web/                              # FastAPI web dashboard
│   ├── app.py                        # FastAPI app entry point
│   ├── routes/                       # API endpoints
│   │   ├── index.py                  # Home page
│   │   ├── config.py                 # Config management API
│   │   ├── transcripts.py            # Transcript API
│   │   ├── json_editor.py            # JSON editor API
│   │   └── websocket.py              # WebSocket endpoints
│   ├── templates/                    # Jinja2 HTML templates
│   └── static/                       # CSS, JS, assets
│       ├── css/
│       └── js/
│
├── data/                             # Runtime data files
│   ├── config/                       # Configuration files
│   │   ├── base_config.json          # Global overrides
│   │   ├── soundboard.json           # Sound definitions
│   │   └── guilds/                   # Per-guild config overrides
│   ├── soundboard/                   # Audio files (MP3, OGG)
│   ├── transcripts/                  # Voice session transcripts
│   │   └── sessions/
│   │       └── {guild_id}/
│   │           └── {channel_id}/
│   ├── activity_stats.json           # Activity statistics (runtime)
│   ├── user_stats.json               # User trigger stats (runtime)
│   └── tts_preferences.json          # TTS user preferences
│
├── logs/                             # Rotating log files
├── admin_data/                       # Dashboard data exports
├── model/                            # Vosk speech recognition model
├── docs/                             # Project documentation
│   ├── CLAUDE.md                     # AI assistant guidance
│   ├── SUGGESTIONS_28-10.md          # Refactoring roadmap
│   └── backups/                      # Config file backups
│
├── .env                              # Environment variables
├── pyproject.toml                    # Python dependencies (uv)
└── README.md                         # This file
```

## Development

**Adding New Cogs:**
1. Create a new Python file in `bot/cogs/` directory (organized by domain: audio, activity, admin, utility)
2. Inherit from `BaseCog` for automatic error handling
3. Use `@track_command` decorator for command tracking
4. Register any config fields in `__init__` using `config_manager.register_schema()`
5. Add `async def setup(bot)` function

**Example:**
```python
from bot.base_cog import BaseCog
from discord.ext import commands
from bot.core.config_system import ConfigSchema, config_field

class MyCog(BaseCog):
    def __init__(self, bot):
        super().__init__(bot)
        # Register config schema
        self.config_manager.register_schema("MyCog", ConfigSchema(
            my_setting=config_field(
                default="default_value",
                description="Description of my setting",
                guild_override=True
            )
        ))

    @track_command
    @commands.command(name="mycommand")
    async def my_command(self, ctx):
        # Get config (with guild override support)
        cfg = self.config_manager.for_guild("MyCog", ctx.guild.id)
        await ctx.send(f"Setting value: {cfg.my_setting}")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

**Configuration System:**
- All config should use `ConfigManager` (accessible via `self.config_manager` in cogs)
- Register config schemas in cog `__init__` method
- Use `config_field()` to define config metadata (defaults, descriptions, guild overrides, etc.)
- Test config changes via web UI at `http://localhost:8000/config`
- See `bot/core/config_system.py` for full API details

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
