# Linux Deployment Guide

## Quick Migration Plan

### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+ and dependencies
sudo apt install -y python3 python3-pip python3-venv git ffmpeg

# Install system audio dependencies
sudo apt install -y portaudio19-dev python3-pyaudio
```

### Step 1: Clone Repository
```bash
# Clone to your desired location
cd /opt  # or ~/apps or wherever you prefer
git clone <your-repo-url> DiscordBot
cd DiscordBot
```

### Step 2: Python Environment Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### Step 3: Configuration
```bash
# Copy environment template
cp .env.example .env

# Edit with your bot token
nano .env
```

**Required in `.env`:**
```
DISCORD_BOT_TOKEN=your_token_here
```

### Step 4: Download Vosk Model
```bash
# Create models directory
mkdir -p models

# Download Vosk model (small English model ~40MB)
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
cd ..
```

### Step 5: Directory Structure Verification
The bot will auto-create these, but verify permissions:
```bash
# Ensure data directories exist (auto-created by bot)
mkdir -p data/{soundboard,config,stats,admin,logs}

# Set proper permissions if needed
chmod -R 755 data/
```

### Step 6: Test Run
```bash
# Make sure venv is activated
source venv/bin/activate

# Run the bot
python bot/main.py
```

**Expected output:**
```
[INFO] Loaded cog: VoiceSpeechCog
[INFO] Loaded cog: Soundboard
[INFO] Loaded cog: ActivityTrackerCog
...
[INFO] Bot is ready! Logged in as YourBotName#1234
```

---

## Production Deployment with systemd

### Create systemd Service
```bash
sudo nano /etc/systemd/system/discordbot.service
```

**Service file content:**
```ini
[Unit]
Description=Discord Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/DiscordBot
Environment="PATH=/opt/DiscordBot/venv/bin"
ExecStart=/opt/DiscordBot/venv/bin/python bot/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Enable and Start Service
```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable discordbot

# Start service
sudo systemctl start discordbot

# Check status
sudo systemctl status discordbot
```

### Service Management Commands
```bash
# View logs
sudo journalctl -u discordbot -f

# Restart bot
sudo systemctl restart discordbot

# Stop bot
sudo systemctl stop discordbot

# Disable auto-start
sudo systemctl disable discordbot
```

---

## Auto-Update from Git

The bot includes an admin-only `~update` command that:
1. Pulls latest changes from git
2. Restarts the bot automatically (if using systemd)

**Usage:**
```
~update
```

**Requirements:**
- User must be in the admin list (see Configuration below)
- Bot must be running under systemd for auto-restart

---

## Configuration

### Admin Setup
Admins are configured in `bot/config.py` or via environment variables:

```python
# In bot/config.py
ADMIN_USER_IDS = [123456789, 987654321]  # Your Discord user IDs
```

Or in `.env`:
```
ADMIN_USER_IDS=123456789,987654321
```

### Auto-Join Channels
Use `~join` in a voice channel to enable auto-join for that channel.

### Soundboard Setup
Place sound files in `data/soundboard/` and configure triggers in `data/config/soundboard.json`.

---

## Troubleshooting

### Bot won't start
```bash
# Check logs
sudo journalctl -u discordbot -n 50

# Check Python dependencies
source venv/bin/activate
pip list

# Test manually
python bot/main.py
```

### Voice recognition not working
```bash
# Verify Vosk model exists
ls -la models/vosk-model-small-en-us-0.15/

# Check ffmpeg
ffmpeg -version

# Check portaudio
python3 -c "import pyaudio; print('PyAudio OK')"
```

### Permission issues
```bash
# Fix ownership
sudo chown -R your_username:your_username /opt/DiscordBot

# Fix permissions
chmod -R 755 /opt/DiscordBot
chmod 644 .env  # Protect sensitive file
```

### Git update fails
```bash
# Check git status
cd /opt/DiscordBot
git status

# Stash local changes if needed
git stash

# Pull updates
git pull

# Reapply changes
git stash pop
```

---

## Security Notes

1. **Protect your `.env` file:**
   ```bash
   chmod 600 .env
   ```

2. **Don't commit secrets:**
   - `.env` is in `.gitignore` by default
   - Never commit tokens or API keys

3. **Keep system updated:**
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

4. **Limit admin access:**
   - Only add trusted users to `ADMIN_USER_IDS`
   - The `~update` command can execute code changes

---

## Quick Reference

| Task | Command |
|------|---------|
| Start bot | `sudo systemctl start discordbot` |
| Stop bot | `sudo systemctl stop discordbot` |
| Restart bot | `sudo systemctl restart discordbot` |
| View logs | `sudo journalctl -u discordbot -f` |
| Update bot | `~update` (in Discord, admin only) |
| Manual update | `git pull && sudo systemctl restart discordbot` |
| Enter venv | `source venv/bin/activate` |
| Test run | `python bot/main.py` |

---

## Minimal Installation Script

Save this as `setup.sh` for quick setup:

```bash
#!/bin/bash

# Quick setup script for DiscordBot on Linux

set -e

echo "Installing system dependencies..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git ffmpeg portaudio19-dev python3-pyaudio

echo "Setting up Python environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Downloading Vosk model..."
mkdir -p models
cd models
wget -q https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip -q vosk-model-small-en-us-0.15.zip
rm vosk-model-small-en-us-0.15.zip
cd ..

echo "Creating data directories..."
mkdir -p data/{soundboard,config,stats,admin,logs}

echo "Setup complete!"
echo ""
echo "Next steps:"
echo "1. Copy .env.example to .env and add your bot token"
echo "2. Run: source venv/bin/activate"
echo "3. Run: python bot/main.py"
```

Make executable: `chmod +x setup.sh`
