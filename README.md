# Discord Bot

A feature-rich Discord bot with voice recognition, TTS, soundboard, and admin monitoring capabilities.

## Features

- **Voice & Audio**
  - Text-to-Speech (TTS) using Edge TTS
  - Voice recognition with transcription logging
  - Audio playback with queue management
  - Customizable soundboard with trigger words

- **Admin Dashboard**
  - Real-time bot monitoring with Pygame interface
  - Health metrics and connection tracking
  - Command usage statistics
  - Error logging and reporting
  - Live voice transcription display

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
```

4. Run the bot:
```bash
python main.py
```

## Configuration

Edit `.env` file or set environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | Required | Your Discord bot token |
| `COMMAND_PREFIX` | `~` | Bot command prefix |
| `ENABLE_ADMIN_DASHBOARD` | `true` | Enable/disable Pygame dashboard |
| `MAX_HISTORY` | `1000` | Max history entries to track |
| `DEFAULT_VOLUME` | `0.5` | Default audio volume (0.0-1.0) |
| `LOG_LEVEL` | `INFO` | Logging level |

## Commands

**General Commands:**
- `~status` - Show bot status and uptime
- `~help` - Display available commands
- `~info` - Show bot and dependency information
- `~reload [cog]` - Reload cog(s) (owner only)

**Voice Commands:**
- `~join` - Join your voice channel
- `~leave` - Leave voice channel
- `~play <file>` - Play audio file
- `~stop` - Stop current playback

**Soundboard:**
- Trigger words automatically play associated sounds when spoken in voice chat
- Manage sounds through `soundboard.json`

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
├── main.py                 # Bot entry point
├── config.py              # Configuration management
├── cogs/                  # Bot command modules
│   ├── base_commands.py   # General commands
│   ├── soundboard.py      # Soundboard functionality
│   └── ...
├── utils/                 # Utility modules
│   ├── admin_data_collector.py
│   ├── error_handler.py
│   └── ...
├── admin_interface_full.py    # Full admin dashboard
├── admin_interface_minimal.py # Minimal dashboard
├── logs/                  # Bot logs
├── soundboard/           # Audio files
└── admin_data/           # Dashboard data exports
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

## License

This project is open source and available for personal use.

## Author

Don Corleon - [GitHub](https://github.com/DonCorleon)
