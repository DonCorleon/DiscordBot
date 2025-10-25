# Linux Deployment Guide

**Target OS:** Ubuntu Server 24.04.03 LTS
**Python Required:** 3.13+
**Last Updated:** January 2025

> **Note:** This guide is specifically tailored for Ubuntu Server 24.04.03 LTS. Ubuntu 24.04 ships with Python 3.12 by default, so we install Python 3.13 from the deadsnakes PPA.

---

## Table of Contents

1. [Quick Migration Plan](#quick-migration-plan)
2. [Production Deployment with systemd](#production-deployment-with-systemd)
3. [Web Dashboard](#web-dashboard-optional)
4. [Configuration](#configuration)
5. [Troubleshooting](#troubleshooting)
6. [Security Notes](#security-notes)
7. [Quick Reference](#quick-reference)
8. [Automated Installation Script](#automated-installation-script)

---

## Quick Migration Plan

### Prerequisites
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.13+ and dependencies
# Note: Ubuntu 24.04 LTS ships with Python 3.12 by default
# Install Python 3.13 from deadsnakes PPA
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.13 python3.13-venv python3.13-dev

# Install system dependencies
sudo apt install -y git ffmpeg portaudio19-dev

# Install build tools (needed for some Python packages)
sudo apt install -y build-essential libssl-dev libffi-dev
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
# Create virtual environment with Python 3.13
python3.13 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip and install uv (optional but recommended for faster installs)
pip install --upgrade pip
pip install uv

# Option 1: Install with uv (faster, recommended)
uv pip install -e .

# Option 2: Install with pip (traditional)
# pip install -e .

# Verify Python version
python --version  # Should show Python 3.13.x
```

### Step 3: Configuration
```bash
# Copy environment template (if it exists)
# Or create .env manually
nano .env
```

**Required in `.env`:**
```env
DISCORD_TOKEN=your_token_here
COMMAND_PREFIX=~

# Optional settings (with defaults)
ENABLE_ADMIN_DASHBOARD=true
DUCKING_ENABLED=true
DUCKING_LEVEL=0.5
DEFAULT_VOLUME=0.5
AUTO_DISCONNECT_DELAY=300
MAX_HISTORY=1000
LOG_LEVEL=INFO
```

**Get your Discord token:**
1. Go to https://discord.com/developers/applications
2. Select your application (or create one)
3. Go to "Bot" section
4. Click "Reset Token" and copy the new token
5. Enable "Message Content Intent" and "Server Members Intent"

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
The bot will auto-create these, but you can pre-create them:
```bash
# Create data directories (auto-created by bot if missing)
mkdir -p data/soundboard
mkdir -p data/config/guilds
mkdir -p data/stats
mkdir -p data/admin
mkdir -p logs
mkdir -p admin_data

# Set proper permissions if needed
chmod -R 755 data/ logs/ admin_data/
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
INFO - Loaded extension: bot.cogs.audio.voicespeech
INFO - Loaded extension: bot.cogs.audio.soundboard
INFO - Loaded extension: bot.cogs.activity.tracker
INFO - Loaded extension: bot.cogs.audio.tts
INFO - Loaded extension: bot.cogs.audio.edge_tts
INFO - Loaded extension: bot.cogs.admin.monitoring
...
INFO - Logged in as YourBotName#1234
INFO - Connected to X guilds
```

**Press `Ctrl+C` to stop the test run.**

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
# View logs (follow mode)
sudo journalctl -u discordbot -f

# View recent logs
sudo journalctl -u discordbot -n 100

# View logs with timestamps
sudo journalctl -u discordbot -o short-iso

# Restart bot
sudo systemctl restart discordbot

# Stop bot
sudo systemctl stop discordbot

# Disable auto-start
sudo systemctl disable discordbot

# View service status
sudo systemctl status discordbot
```

---

## Web Dashboard (Optional)

The bot includes a web dashboard for configuration and monitoring.

### Running the Dashboard

```bash
# In a separate terminal or screen session
source venv/bin/activate

# Option 1: Full dashboard (all features)
python bot/ui/dashboard_full.py

# Option 2: Minimal dashboard (lightweight)
python bot/ui/dashboard_minimal.py
```

**Default URL:** http://localhost:8000

### Dashboard with systemd

Create a separate service for the dashboard:

```bash
sudo nano /etc/systemd/system/discordbot-dashboard.service
```

```ini
[Unit]
Description=Discord Bot Web Dashboard
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/opt/DiscordBot
Environment="PATH=/opt/DiscordBot/venv/bin"
ExecStart=/opt/DiscordBot/venv/bin/python bot/ui/dashboard_full.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable discordbot-dashboard
sudo systemctl start discordbot-dashboard
```

**Note:** For production, use a reverse proxy (nginx/caddy) with HTTPS.

### Nginx Reverse Proxy (Production)

For secure access to the dashboard over HTTPS:

1. **Install nginx:**
```bash
sudo apt install -y nginx certbot python3-certbot-nginx
```

2. **Create nginx config:**
```bash
sudo nano /etc/nginx/sites-available/discordbot-dashboard
```

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (if using real-time features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

3. **Enable the site:**
```bash
sudo ln -s /etc/nginx/sites-available/discordbot-dashboard /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

4. **Get SSL certificate:**
```bash
sudo certbot --nginx -d your-domain.com
```

---

## Auto-Update from Git

### Manual Update
```bash
cd /opt/DiscordBot
git pull
sudo systemctl restart discordbot
```

### Automatic Update (if admin commands are enabled)
The bot may include admin-only update commands. Check `bot/cogs/admin/` for available admin commands.

---

## Configuration

### Admin Setup
Configure admin users in `.env`:

```env
ADMIN_USER_IDS=123456789,987654321
```

**To get your Discord user ID:**
1. Enable Developer Mode in Discord (Settings → Advanced → Developer Mode)
2. Right-click your username and select "Copy ID"

### Voice Channel Auto-Join
Use `~join` in a voice channel to make the bot auto-join that channel when users connect.

### Soundboard Setup
1. Place sound files in `data/soundboard/`
2. Configure via web dashboard (recommended) or edit `data/config/soundboard.json`
3. Supported formats: MP3, WAV, OGG, FLAC, M4A

**Example soundboard.json:**
```json
{
  "sounds": {
    "hello": {
      "title": "Hello Sound",
      "triggers": ["hello", "hi"],
      "soundfile": "data/soundboard/hello.mp3",
      "volume_adjust": 1.0,
      "guilds": null,
      "is_private": false,
      "is_disabled": false
    }
  }
}
```

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

# Check if opus library is available (required for Discord voice)
python3.13 -c "import discord; print(discord.opus.is_loaded())"

# Test audio libraries
source venv/bin/activate
python -c "import pyaudio; print('PyAudio OK')"
python -c "from vosk import Model; print('Vosk OK')"
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
   - Admin commands have elevated privileges

5. **Firewall configuration (if using web dashboard):**
   ```bash
   # Enable UFW firewall
   sudo ufw enable

   # Allow SSH (important!)
   sudo ufw allow 22/tcp

   # Allow HTTP/HTTPS (if using nginx)
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp

   # Dashboard is on localhost only by default (secure)
   # Don't expose port 8000 directly to the internet

   # Check status
   sudo ufw status
   ```

---

## Quick Reference

| Task | Command |
|------|---------|
| **Bot Management** | |
| Start bot | `sudo systemctl start discordbot` |
| Stop bot | `sudo systemctl stop discordbot` |
| Restart bot | `sudo systemctl restart discordbot` |
| View logs (follow) | `sudo journalctl -u discordbot -f` |
| View recent logs | `sudo journalctl -u discordbot -n 100` |
| Check status | `sudo systemctl status discordbot` |
| **Dashboard** | |
| Start dashboard | `sudo systemctl start discordbot-dashboard` |
| Stop dashboard | `sudo systemctl stop discordbot-dashboard` |
| View dashboard logs | `sudo journalctl -u discordbot-dashboard -f` |
| **Updates** | |
| Manual update | `cd /opt/DiscordBot && git pull && sudo systemctl restart discordbot` |
| Check git status | `git status` |
| **Development** | |
| Enter venv | `source venv/bin/activate` |
| Test run bot | `python bot/main.py` |
| Test run dashboard | `python bot/ui/dashboard_full.py` |
| Check Python version | `python --version` (should be 3.13.x) |
| **Troubleshooting** | |
| View all services | `sudo systemctl list-units --type=service \| grep discord` |
| Check file permissions | `ls -la /opt/DiscordBot` |
| Check .env exists | `cat /opt/DiscordBot/.env` |

---

## Automated Installation Script

Save this as `setup.sh` for quick setup on Ubuntu 24.04 LTS:

```bash
#!/bin/bash

# Quick setup script for DiscordBot on Ubuntu 24.04 LTS
# Requires: Ubuntu 24.04.03 LTS

set -e

echo "======================================"
echo "DiscordBot Setup for Ubuntu 24.04 LTS"
echo "======================================"

echo ""
echo "Step 1: Installing system dependencies..."
sudo apt update
sudo apt install -y software-properties-common

echo ""
echo "Step 2: Adding deadsnakes PPA for Python 3.13..."
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update

echo ""
echo "Step 3: Installing Python 3.13 and build tools..."
sudo apt install -y python3.13 python3.13-venv python3.13-dev
sudo apt install -y git ffmpeg portaudio19-dev
sudo apt install -y build-essential libssl-dev libffi-dev

echo ""
echo "Step 4: Setting up Python virtual environment..."
python3.13 -m venv venv
source venv/bin/activate

echo ""
echo "Step 5: Installing Python dependencies..."
pip install --upgrade pip
pip install uv
uv pip install -e .

echo ""
echo "Step 6: Downloading Vosk speech recognition model..."
mkdir -p models
cd models
if [ ! -d "vosk-model-small-en-us-0.15" ]; then
    echo "Downloading Vosk model (~40MB)..."
    wget -q --show-progress https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
    unzip -q vosk-model-small-en-us-0.15.zip
    rm vosk-model-small-en-us-0.15.zip
    echo "Vosk model downloaded successfully"
else
    echo "Vosk model already exists, skipping download"
fi
cd ..

echo ""
echo "Step 7: Creating data directories..."
mkdir -p data/soundboard
mkdir -p data/config/guilds
mkdir -p data/stats
mkdir -p data/admin
mkdir -p logs
mkdir -p admin_data

echo ""
echo "======================================"
echo "Setup complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Create .env file with your Discord bot token:"
echo "   nano .env"
echo ""
echo "2. Add the following to .env:"
echo "   DISCORD_TOKEN=your_token_here"
echo "   COMMAND_PREFIX=~"
echo ""
echo "3. Activate virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "4. Start the bot:"
echo "   python bot/main.py"
echo ""
echo "5. (Optional) Set up systemd service for production:"
echo "   See 'Production Deployment with systemd' section in docs"
echo ""
```

**Make executable and run:**
```bash
chmod +x setup.sh
./setup.sh
```
