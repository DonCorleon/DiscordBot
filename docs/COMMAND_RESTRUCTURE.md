# Command Structure Restructure Proposal

**Date**: 2025-10-28
**Status**: Proposal - Pending Review

## Overview

Restructure all bot commands to use a hierarchical group-based structure for better organization and discoverability.

**Format**: `~<group> <subcommand> [args]`

---

## Proposed Command Groups

### 1. **Voice** - Voice Channel Management
Control voice connections, listening, and auto-join settings.

```
~voice join [channel]              # Join a voice channel
~voice leave                       # Leave the voice channel
~voice start                       # Start speech recognition
~voice stop                        # Stop speech recognition
~voice autojoin list               # List auto-join channels
~voice autojoin add <channel>      # Enable auto-join for channel
~voice autojoin remove <channel>   # Disable auto-join for channel
~voice queue                       # Show current sound queue
~voice clearqueue                  # Clear the sound queue
~voice ducking <enable|disable>    # Configure audio ducking
~voice ducking level <0.0-1.0>     # Set ducking volume level
```

**Current Commands Being Replaced**:
- `~join` → `~voice join`
- `~leave` → `~voice leave`
- `~start` → `~voice start`
- `~stop` → `~voice stop`
- `~autojoin` → `~voice autojoin list`
- `~disableautojoin` → `~voice autojoin remove`
- `~queue` → `~voice queue`
- `~clearqueue` → `~voice clearqueue`
- `~ducking` → `~voice ducking`

---

### 2. **Soundboard** - Sound Management
Manage soundboard sounds, triggers, and playback.

```
~soundboard list                   # View all sounds (interactive UI)
~soundboard play <sound>           # Play a sound by name/trigger
~soundboard add                    # Add new sound (attach file)
~soundboard edit <sound>           # Edit sound properties
~soundboard delete <sound>         # Delete a sound
~soundboard search <query>         # Search sounds
~soundboard random                 # Play a random sound
```

**Current Commands Being Replaced**:
- `~soundboard` → `~soundboard list`
- `~play` → `~soundboard play`
- `~addsound` → `~soundboard add`
- (edit/delete currently done via UI) → explicit commands

---

### 3. **TTS** - Text-to-Speech
Text-to-speech commands for local and Edge TTS.

```
~tts say <text>                    # Speak text (local pyttsx3)
~tts voices                        # List available local voices
~tts setvoice                      # Configure your voice preferences
~tts edge <text>                   # Speak text (Edge TTS)
~tts edge voices                   # List Edge TTS voices
~tts edge stop                     # Stop Edge TTS playback
```

**Current Commands Being Replaced**:
- `~say` → `~tts say`
- `~voices` → `~tts voices`
- `~setvoice` → `~tts setvoice`
- `~edge` → `~tts edge`
- `~edgevoices` → `~tts edge voices`
- `~stopedge` → `~tts edge stop`

---

### 4. **Stats** - User Statistics & Leaderboards
View personal stats and leaderboards.

```
~stats me [actual]                 # Your personal stats
~stats user <@user> [actual]       # View another user's stats
~stats activity [@user]            # Activity stats (messages, reactions, voice)
~stats leaderboard triggers        # Top trigger word users
~stats leaderboard sounds          # Most played sounds
~stats leaderboard members [period] [channel]  # Member trigger leaderboard
~stats leaderboard activity [period] [bots] [actual]  # Activity leaderboard
~stats recap                       # Weekly recap summary (admin)
```

**Current Commands Being Replaced**:
- `~mystats` → `~stats me`
- `~mystats @user` → `~stats user @user`
- `~activityleaderboard` → `~stats leaderboard activity`
- `~leaderboard triggers` → `~stats leaderboard triggers`
- `~leaderboard sounds` → `~stats leaderboard sounds`
- `~leaderboard members` → `~stats leaderboard members`
- `~weeklyrecap` → `~stats recap`

---

### 5. **Admin** - Bot Administration
Administrative commands for bot management.

```
~admin health                      # Bot health and resource usage
~admin connections                 # Active voice connections
~admin logs [count]                # Recent log entries
~admin cmdstats                    # Command usage statistics
~admin update                      # Update bot from git and restart
~admin reload [cog]                # Reload cog(s)
~admin users add <@user>           # Add bot admin user
~admin users remove <@user>        # Remove bot admin user
~admin users list                  # List bot admin users
~admin stats reset <week|month> <sounds|members|all>  # Reset statistics
~admin errors stats                # Error statistics
```

**Current Commands Being Replaced**:
- `~health` → `~admin health`
- `~connections` → `~admin connections`
- `~logs` → `~admin logs`
- `~cmdstats` → `~admin cmdstats`
- `~update` → `~admin update`
- `~reload` → `~admin reload`
- `~admincontrol add` → `~admin users add`
- `~admincontrol remove` → `~admin users remove`
- `~admincontrol list` → `~admin users list`
- `~resetstats` → `~admin stats reset`
- `~errorstats` → `~admin errors stats`

---

### 6. **Config** - Configuration Management
Manage guild-specific configuration (alternative to web UI).

```
~config show [category]            # Show current config
~config set <key> <value>          # Set config value
~config reset <key>                # Reset to default
~config guild show                 # Show guild overrides
~config guild set <key> <value>    # Set guild-specific override
~config guild reset <key>          # Remove guild override
```

**Current Commands Being Replaced**:
- `~guildconfig` → `~config guild`
- (new group - provides Discord alternative to web UI)

---

### 7. **Bot** - General Bot Commands
General bot information and utilities.

```
~bot status                        # Bot status and uptime
~bot info                          # Project information
~bot ping                          # Check bot latency
~bot help [command]                # Show help
```

**Current Commands Being Replaced**:
- `~status` → `~bot status`
- `~info` → `~bot info`
- `~ping` → `~bot ping`
- `~help` → `~bot help`

---

## Implementation Strategy

### Phase 1: Create Command Groups (Week 1)
1. Create `@commands.group()` structures for each main group
2. Add subcommands under each group
3. Keep old commands as **aliases** (deprecated, hidden from help)

### Phase 2: Update Documentation (Week 1)
1. Update README.md with new command structure
2. Update help text for all commands
3. Add deprecation warnings to old commands

### Phase 3: User Notification (Week 2-3)
1. Add bot message: "This command is deprecated, use `~new command` instead"
2. Log usage of deprecated commands
3. Announce changes in Discord

### Phase 4: Remove Old Commands (Week 4+)
1. After monitoring period, remove old command aliases
2. Keep only new grouped structure

---

## Help System Design

### `~help` - Show All Command Groups

Shows all main command groups with brief descriptions:

```
🤖 Bot Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~voice       - Voice channel management
~soundboard  - Sound management and playback
~tts         - Text-to-speech commands
~stats       - Statistics and leaderboards
~admin       - Bot administration (Admin only)
~config      - Configuration management
~bot         - General bot information

Use ~help <command> for detailed subcommands
Example: ~help voice
```

### `~help <group>` - Show Subcommands

Shows all subcommands for a specific group:

#### `~help voice`
```
🎤 Voice Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~voice join [channel]              Join a voice channel
~voice leave                       Leave the voice channel
~voice start                       Start speech recognition
~voice stop                        Stop speech recognition
~voice autojoin list               List auto-join channels
~voice autojoin add <channel>      Enable auto-join for channel
~voice autojoin remove <channel>   Disable auto-join for channel
~voice queue                       Show current sound queue
~voice clearqueue                  Clear the sound queue
~voice ducking <enable|disable>    Configure audio ducking
~voice ducking level <0.0-1.0>     Set ducking volume level
```

#### `~help soundboard`
```
🎵 Soundboard Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~soundboard list                   View all sounds (interactive UI)
~soundboard play <sound>           Play a sound by name/trigger
~soundboard add                    Add new sound (attach file)
~soundboard edit <sound>           Edit sound properties
~soundboard delete <sound>         Delete a sound
~soundboard search <query>         Search sounds
~soundboard random                 Play a random sound
```

#### `~help tts`
```
🗣️ Text-to-Speech Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~tts say <text>                    Speak text (local pyttsx3)
~tts voices                        List available local voices
~tts setvoice                      Configure your voice preferences
~tts edge <text>                   Speak text (Edge TTS)
~tts edge voices                   List Edge TTS voices
~tts edge stop                     Stop Edge TTS playback
```

#### `~help stats`
```
📊 Statistics Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~stats me [actual]                 Your personal stats
~stats user <@user> [actual]       View another user's stats
~stats activity [@user]            Activity stats (messages, reactions, voice)
~stats leaderboard triggers        Top trigger word users
~stats leaderboard sounds          Most played sounds
~stats leaderboard members [period] [channel]
                                   Member trigger leaderboard
~stats leaderboard activity [period] [bots] [actual]
                                   Activity leaderboard
~stats recap                       Weekly recap summary (admin)
```

#### `~help admin`
```
⚙️ Admin Commands (Admin Only)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~admin health                      Bot health and resource usage
~admin connections                 Active voice connections
~admin logs [count]                Recent log entries
~admin cmdstats                    Command usage statistics
~admin update                      Update bot from git and restart
~admin reload [cog]                Reload cog(s)
~admin users add <@user>           Add bot admin user
~admin users remove <@user>        Remove bot admin user
~admin users list                  List bot admin users
~admin stats reset <week|month> <sounds|members|all>
                                   Reset statistics
~admin errors stats                Error statistics
```

#### `~help config`
```
⚙️ Configuration Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~config show [category]            Show current config
~config set <key> <value>          Set config value
~config reset <key>                Reset to default
~config guild show                 Show guild overrides
~config guild set <key> <value>    Set guild-specific override
~config guild reset <key>          Remove guild override
```

#### `~help bot`
```
ℹ️ Bot Information Commands
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

~bot status                        Bot status and uptime
~bot info                          Project information
~bot ping                          Check bot latency
~bot help [command]                Show this help message
```

### Implementation Notes

1. **Custom Help Command**: Override default discord.py help command
2. **Group Detection**: If argument matches a group name, show group help
3. **Error Handling**: If invalid group name, suggest similar groups
4. **Permissions**: Hide admin-only groups for non-admin users
5. **Aliases**: Old deprecated commands should not appear in help

### Help Command Code Structure

```python
@commands.command(name="help")
async def help_command(self, ctx, command_group: str = None):
    """Show help for commands"""
    if command_group is None:
        # Show all command groups
        await self.show_main_help(ctx)
    else:
        # Show specific group help
        group = self.bot.get_command(command_group)
        if group and isinstance(group, commands.Group):
            await self.show_group_help(ctx, group)
        else:
            await ctx.send(f"Unknown command group: {command_group}")
```

## Benefits

1. **Better Organization**: Commands grouped by functionality
2. **Discoverability**: Easier to find related commands with hierarchical help
3. **Consistency**: Uniform command structure across the bot
4. **Scalability**: Easy to add new commands to existing groups
5. **Help System**: Two-level help system (groups → subcommands)

---

## Example Usage Comparison

### Before:
```
~join
~start
~play shrek
~mystats
~leaderboard members week
~admincontrol add @user
~health
```

### After:
```
~voice join
~voice start
~soundboard play shrek
~stats me
~stats leaderboard members week
~admin users add @user
~admin health
```

---

## Migration Notes

- **Backward Compatibility**: Old commands will work during transition period (hidden aliases)
- **User Education**: Add deprecation messages to guide users to new commands
- **Documentation**: Update all docs, README, and in-bot help
- **Web Dashboard**: No changes needed (uses direct cog methods, not commands)

---

## Questions for Review

1. Should we keep `~help` at root level or move to `~bot help`?
2. Should `~soundboard list` be just `~soundboard` (group default action)?
3. Should `~voice autojoin` be its own command or nested subgroup?
4. Any commands missing from this reorganization?
5. Any groups that should be split or merged?

---

**Next Steps**: Review and approve structure, then implement Phase 1.
