# admin_interface_minimal.py
"""
Minimal Pygame Admin Interface
Shows: Connection health + Live voice transcriptions
"""

import pygame
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import deque


class MinimalDashboard:
    """Lightweight dashboard showing health and live transcriptions."""

    # Colors - Dark theme
    BG_COLOR = (25, 25, 35)
    PANEL_COLOR = (35, 35, 45)
    TEXT_COLOR = (220, 220, 230)
    ACCENT_COLOR = (100, 150, 255)
    SUCCESS_COLOR = (100, 255, 150)
    WARNING_COLOR = (255, 200, 100)
    ERROR_COLOR = (255, 100, 100)
    BORDER_COLOR = (60, 60, 70)

    def __init__(self, width=800, height=600):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        pygame.display.set_caption("Bot Monitor - Health & Voice")

        # Fonts
        self.title_font = pygame.font.Font(None, 32)
        self.header_font = pygame.font.Font(None, 24)
        self.text_font = pygame.font.Font(None, 20)
        self.small_font = pygame.font.Font(None, 16)

        # Data
        self.data_dir = Path("data/admin")
        self.log_file = Path("logs/discordbot.log")

        # Transcription buffer - keep last 50 messages
        self.transcriptions = deque(maxlen=50)
        self.last_log_position = 0

        # UI state
        self.clock = pygame.time.Clock()
        self.last_update = 0
        self.update_interval = 1000  # Update every 1 second
        self.scroll_offset = 0
        self.max_scroll = 0

        # Health data cache
        self.health_data = None
        self.connection_data = None

    def load_data(self):
        """Load health and connection data from JSON."""
        try:
            # Load health
            health_file = self.data_dir / "health.json"
            if health_file.exists():
                with open(health_file, "r") as f:
                    self.health_data = json.load(f)

            # Load connections
            conn_file = self.data_dir / "connections.json"
            if conn_file.exists():
                with open(conn_file, "r") as f:
                    self.connection_data = json.load(f)

        except Exception as e:
            print(f"Error loading data: {e}")

    def load_transcriptions(self):
        """Load new transcriptions from log file."""
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                # Seek to last position
                f.seek(self.last_log_position)

                for line in f:
                    # Look for transcription lines (colored output)
                    if "[92m" in line and "] :" in line:
                        # Parse: [timestamp] [guild] [user] : text
                        try:
                            # Remove ANSI codes
                            clean_line = line.replace("\033[92m", "").replace("\033[0m", "")

                            # Extract parts
                            if "] [" in clean_line and "] :" in clean_line:
                                parts = clean_line.split("] [", 1)
                                timestamp = parts[0].strip("[]")

                                rest = parts[1].split("] [", 1)
                                guild = rest[0]

                                user_text = rest[1].split("] :", 1)
                                user = user_text[0]
                                text = user_text[1].strip()

                                # Add to transcriptions
                                self.transcriptions.append({
                                    "timestamp": timestamp,
                                    "guild": guild,
                                    "user": user,
                                    "text": text
                                })
                        except:
                            continue

                # Update position
                self.last_log_position = f.tell()

        except Exception as e:
            print(f"Error reading logs: {e}")

    def draw_text(self, text: str, pos: tuple, font=None, color=None):
        """Helper to draw text."""
        if font is None:
            font = self.text_font
        if color is None:
            color = self.TEXT_COLOR

        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, pos)
        return text_surface.get_height()

    def draw_panel(self, rect: pygame.Rect, title: str = None):
        """Draw a panel background."""
        pygame.draw.rect(self.screen, self.PANEL_COLOR, rect)
        pygame.draw.rect(self.screen, self.BORDER_COLOR, rect, 2)

        if title:
            self.draw_text(title, (rect.x + 10, rect.y + 10), self.header_font, self.ACCENT_COLOR)

    def draw_health_panel(self):
        """Draw compact health status panel."""
        panel_rect = pygame.Rect(10, 10, self.width - 20, 120)
        self.draw_panel(panel_rect, "⚡ Bot Health")

        if not self.health_data or not self.health_data.get("current"):
            self.draw_text("No health data available", (20, 50))
            return

        current = self.health_data["current"]

        y = 45

        # CPU and Memory side by side
        cpu = current.get("cpu_percent", 0)
        memory_mb = current.get("memory_mb", 0)
        memory_pct = current.get("memory_percent", 0)

        # CPU
        self.draw_text(f"CPU: {cpu:.1f}%", (20, y), self.text_font)
        cpu_color = self.ERROR_COLOR if cpu > 80 else (self.WARNING_COLOR if cpu > 60 else self.SUCCESS_COLOR)
        pygame.draw.circle(self.screen, cpu_color, (150, y + 8), 6)

        # Memory
        self.draw_text(f"Memory: {memory_mb:.0f}MB ({memory_pct:.1f}%)", (200, y), self.text_font)
        mem_color = self.ERROR_COLOR if memory_pct > 80 else (
            self.WARNING_COLOR if memory_pct > 60 else self.SUCCESS_COLOR)
        pygame.draw.circle(self.screen, mem_color, (480, y + 8), 6)

        y += 35

        # Connections and Commands
        connections = current.get("active_connections", 0)
        commands_per_min = current.get("commands_per_minute", 0)

        self.draw_text(f"🔊 Connections: {connections}", (20, y), self.text_font)
        self.draw_text(f"📝 Commands/min: {commands_per_min}", (200, y), self.text_font)

        # Timestamp
        timestamp = current.get("timestamp", "")[:19]
        self.draw_text(f"Updated: {timestamp}", (self.width - 220, y), self.small_font, self.ACCENT_COLOR)

    def draw_voice_panel(self):
        """Draw voice connection status."""
        panel_height = self.height - 140 - 10
        panel_rect = pygame.Rect(10, 140, self.width - 20, panel_height)
        self.draw_panel(panel_rect, "🎤 Voice Connections")

        if not self.connection_data:
            self.draw_text("No connection data", (20, 180))
            return

        connections = self.connection_data.get("connections", [])

        if not connections:
            self.draw_text("Not connected to any voice channels", (20, 180), self.text_font, self.WARNING_COLOR)
            return

        y = 180

        for conn in connections:
            guild = conn.get("guild_name", "Unknown")
            channel = conn.get("channel_name", "Unknown")
            listening = conn.get("is_listening", False)
            members = conn.get("members_count", 0)

            # Connection info
            status_color = self.SUCCESS_COLOR if listening else self.WARNING_COLOR
            status_text = "🎧 Listening" if listening else "⏸️  Idle"

            self.draw_text(f"📍 {guild} → #{channel}", (20, y), self.text_font)
            self.draw_text(f"{status_text} • {members} members", (self.width - 250, y), self.text_font, status_color)

            y += 35

            # Show members if listening
            if listening and members > 0:
                # Get active speakers from recent transcriptions
                active_speakers = set()
                cutoff_time = datetime.now().timestamp() - 3  # Active in last 3 seconds

                for trans in reversed(list(self.transcriptions)):
                    try:
                        trans_time = datetime.fromisoformat(trans["timestamp"]).timestamp()
                        if trans_time > cutoff_time and trans["guild"] == guild:
                            active_speakers.add(trans["user"])
                    except:
                        continue

                # Draw member list (from transcriptions to show who's there)
                seen_users = set()
                member_y = y
                col = 0

                # Show recent speakers
                for trans in reversed(list(self.transcriptions)):
                    if trans["guild"] == guild and trans["user"] not in seen_users:
                        user = trans["user"]
                        seen_users.add(user)

                        # Determine if speaking (active)
                        is_speaking = user in active_speakers
                        indicator_color = self.SUCCESS_COLOR if is_speaking else self.ERROR_COLOR

                        # Draw indicator and name
                        x_pos = 40 + (col * 200)
                        pygame.draw.circle(self.screen, indicator_color, (x_pos, member_y + 8), 5)
                        self.draw_text(user, (x_pos + 15, member_y), self.small_font)

                        col += 1
                        if col >= 3:  # 3 columns
                            col = 0
                            member_y += 25

                y = member_y + 30
            else:
                y += 10

    def draw_transcriptions_panel(self):
        """This panel is removed - not needed for minimal version."""
        pass

    def handle_input(self):
        """Handle keyboard and mouse input."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_r:
                    # Manual refresh
                    self.load_data()
                    self.load_transcriptions()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Mouse wheel scrolling
                if event.button == 4:  # Scroll up
                    self.scroll_offset = min(0, self.scroll_offset + 50)
                elif event.button == 5:  # Scroll down
                    self.scroll_offset = max(-self.max_scroll, self.scroll_offset - 50)

            elif event.type == pygame.VIDEORESIZE:
                self.width = event.w
                self.height = event.h
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)

        return True

    def run(self):
        """Main loop."""
        running = True

        print("Minimal Bot Monitor")
        print("===================")
        print("Controls:")
        print("  Mouse Wheel: Scroll transcriptions")
        print("  R: Refresh data")
        print("  ESC: Exit")
        print()

        while running:
            current_time = pygame.time.get_ticks()

            # Auto-refresh data
            if current_time - self.last_update > self.update_interval:
                self.load_data()
                self.load_transcriptions()
                self.last_update = current_time

            # Handle input
            running = self.handle_input()

            # Clear screen
            self.screen.fill(self.BG_COLOR)

            # Draw UI
            self.draw_health_panel()
            self.draw_voice_panel()
            self.draw_transcriptions_panel()

            # Draw status bar
            status_text = f"Live • Updated: {datetime.now().strftime('%H:%M:%S')}"
            self.draw_text(status_text, (10, self.height - 25), self.small_font, self.ACCENT_COLOR)

            pygame.display.flip()
            self.clock.tick(30)  # 30 FPS

        pygame.quit()


if __name__ == "__main__":
    # Check if admin_data directory exists
    data_dir = Path("data/admin")
    if not data_dir.exists():
        print("Error: admin_data directory not found!")
        print("Make sure the bot is running with ENABLE_ADMIN_DASHBOARD=true")
        sys.exit(1)

    # Run dashboard
    dashboard = MinimalDashboard()
    dashboard.run()