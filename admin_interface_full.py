# admin_interface_full.py
"""
Full Featured Multi-View Admin Dashboard
Navigation sidebar with switchable content panels
"""

import pygame
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Optional, Tuple, List, Dict
import hashlib
import io
import urllib.request
from PIL import Image


class ViewType:
    """Available view types."""
    DASHBOARD = "dashboard"
    CHAT = "chat"
    VOICE = "voice"
    SOUNDS = "sounds"
    ERRORS = "errors"
    LOGS = "logs"
    CONFIG = "config"


class FullDashboard:
    """Full dashboard with multi-view navigation."""

    # Colors - Dark theme
    BG_COLOR = (25, 25, 35)
    SIDEBAR_COLOR = (20, 20, 28)
    PANEL_COLOR = (35, 35, 45)
    TEXT_COLOR = (220, 220, 230)
    ACCENT_COLOR = (100, 150, 255)
    SUCCESS_COLOR = (100, 255, 150)
    WARNING_COLOR = (255, 200, 100)
    ERROR_COLOR = (255, 100, 100)
    CRITICAL_COLOR = (255, 50, 50)
    BORDER_COLOR = (60, 60, 70)
    BUTTON_HOVER_COLOR = (45, 45, 55)
    BUTTON_ACTIVE_COLOR = (50, 100, 200)
    TRIGGER_HIGHLIGHT_COLOR = (255, 200, 100)

    # Layout constants
    SIDEBAR_WIDTH = 220
    BUTTON_HEIGHT = 45
    BUTTON_SPACING = 5

    def __init__(self, width=1400, height=900):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        pygame.display.set_caption("Bot Monitor - Admin Dashboard")

        # Fonts
        self.title_font = pygame.font.Font(None, 32)
        self.header_font = pygame.font.Font(None, 24)
        self.text_font = pygame.font.Font(None, 20)
        self.small_font = pygame.font.Font(None, 16)
        self.tiny_font = pygame.font.Font(None, 14)

        # Data paths
        self.data_dir = Path("admin_data")
        self.log_file = Path("logs/discordbot.log")
        self.avatar_cache_dir = Path("admin_data/avatars")
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)

        # Navigation state
        self.current_view = ViewType.DASHBOARD
        self.hovered_button = None
        self.mouse_pos = (0, 0)
        self.button_rects = {}

        # Avatar cache
        self.avatar_cache = {}
        self.user_avatars = {}  # {user_id: avatar_url}
        self.user_id_to_info = {}  # {user_id: full_info}
        self._create_default_avatars()
        self._load_user_info()

        # Data
        self.transcriptions = deque(maxlen=500)  # Increased from 200 to 500
        self.last_log_position = 0
        self.health_data = None
        self.connection_data = None
        self.error_data = None
        self.command_data = None
        self.soundboard_data = None

        # UI state
        self.clock = pygame.time.Clock()
        self.last_update = 0
        self.update_interval = 1000
        self.scroll_offset = 0
        self.max_scroll = 0
        self.auto_scroll = True  # Enable autoscroll by default
        self.last_transcription_count = 0  # Track when new messages arrive

        # Tooltip state
        self.tooltip_text = None
        self.tooltip_pos = None
        self.hovered_trigger = None

        # Error tracking for alerts
        self.unread_errors = 0
        self.unread_critical = 0

        # Sound editing state
        self.selected_sound = None
        self.sound_list_scroll = 0
        self.sound_buttons = {}

    def _create_default_avatars(self):
        """Create default avatar surfaces."""
        size = 32
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(surf, self.ACCENT_COLOR, (size // 2, size // 2), size // 2)
        pygame.draw.circle(surf, self.TEXT_COLOR, (size // 2, size // 2), size // 2 - 2, 2)
        self.default_avatar = surf

    def _load_user_info(self):
        """Load user info including avatar URLs from user_info.json."""
        user_info_file = self.data_dir / "user_info.json"
        if user_info_file.exists():
            try:
                with open(user_info_file, "r") as f:
                    data = json.load(f)
                    # Data is now keyed by user_id
                    users = data.get("users", {})

                    # Build lookup dict by user_id
                    self.user_avatars = {
                        user_id: info["avatar_url"]
                        for user_id, info in users.items()
                    }

                    # Also store full user info for username/display_name lookups
                    self.user_id_to_info = users
            except Exception as e:
                pass  # Silently fail and use fallback avatars

    def _download_avatar(self, username: str, avatar_url: str) -> Optional[pygame.Surface]:
        """Download and cache user avatar."""
        try:
            # Check if already cached on disk
            cache_file = self.avatar_cache_dir / f"{username}.png"

            if not cache_file.exists():
                # Download avatar
                req = urllib.request.Request(
                    avatar_url,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    image_data = response.read()

                # Save to cache
                with open(cache_file, 'wb') as f:
                    f.write(image_data)

            # Load with PIL and convert to pygame
            pil_image = Image.open(cache_file)
            pil_image = pil_image.convert('RGBA')
            pil_image = pil_image.resize((32, 32), Image.Resampling.LANCZOS)

            # Convert PIL to pygame
            mode = pil_image.mode
            size = pil_image.size
            data = pil_image.tobytes()

            py_image = pygame.image.fromstring(data, size, mode)

            # Make circular
            mask = pygame.Surface((32, 32), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (16, 16), 16)

            result = pygame.Surface((32, 32), pygame.SRCALPHA)
            result.blit(py_image, (0, 0))
            result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

            return result

        except Exception as e:
            print(f"Error downloading avatar for {username}: {e}")
            return None

    def get_avatar(self, user_id: str, fallback_name: str = None) -> pygame.Surface:
        """
        Get or create avatar for user by user_id.

        Args:
            user_id: Discord user ID
            fallback_name: Display name to use for initials if avatar not found
        """
        # Use user_id as cache key
        cache_key = user_id if user_id else fallback_name

        if cache_key in self.avatar_cache:
            return self.avatar_cache[cache_key]

        # Try to get real avatar by user_id
        if user_id and user_id in self.user_avatars:
            avatar_url = self.user_avatars[user_id]
            if avatar_url:
                real_avatar = self._download_avatar(user_id, avatar_url)
                if real_avatar:
                    self.avatar_cache[cache_key] = real_avatar
                    return real_avatar

        # Fallback to generated avatar
        display_name = fallback_name or "?"

        size = 32
        surf = pygame.Surface((size, size), pygame.SRCALPHA)

        # Generate color from user_id or name
        hash_str = user_id if user_id else display_name
        hash_val = int(hashlib.md5(hash_str.encode()).hexdigest()[:6], 16)
        color = (
            100 + ((hash_val >> 16) & 0xFF) % 156,
            100 + ((hash_val >> 8) & 0xFF) % 156,
            100 + (hash_val & 0xFF) % 156
        )

        # Draw circle background
        pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2)
        pygame.draw.circle(surf, (255, 255, 255), (size // 2, size // 2), size // 2, 2)

        # Draw initials - handle underscores and special chars
        parts = display_name.replace('_', ' ').split()
        initials = ''.join([word[0].upper() for word in parts[:2] if word])
        if not initials:
            initials = display_name[0].upper() if display_name else "?"

        # Render initials
        font = pygame.font.Font(None, 18)
        text_surf = font.render(initials, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=(size // 2, size // 2))
        surf.blit(text_surf, text_rect)

        self.avatar_cache[cache_key] = surf
        return surf

    def load_data(self):
        """Load all data from JSON files."""
        try:
            health_file = self.data_dir / "health.json"
            if health_file.exists():
                with open(health_file, "r") as f:
                    self.health_data = json.load(f)

            conn_file = self.data_dir / "connections.json"
            if conn_file.exists():
                with open(conn_file, "r") as f:
                    self.connection_data = json.load(f)

            error_file = self.data_dir / "errors.json"
            if error_file.exists():
                with open(error_file, "r") as f:
                    self.error_data = json.load(f)
                    recent = self.error_data.get("recent", [])
                    self.unread_errors = len([e for e in recent if e.get("category") != "user_input"])
                    self.unread_critical = len([e for e in recent if e.get("severity") == "critical"])

            cmd_file = self.data_dir / "commands.json"
            if cmd_file.exists():
                with open(cmd_file, "r") as f:
                    self.command_data = json.load(f)

            sb_file = Path("soundboard.json")
            if sb_file.exists():
                with open(sb_file, "r") as f:
                    self.soundboard_data = json.load(f)

            # Reload user info for new avatars
            self._load_user_info()

        except Exception as e:
            print(f"Error loading data: {e}")

    def load_transcriptions(self):
        """Load new transcriptions from log file."""
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(self.last_log_position)

                for line in f:
                    if "[92m" in line and "] :" in line:
                        try:
                            clean_line = line.replace("\033[92m", "").replace("\033[0m", "")

                            # Try NEW FORMAT first: [timestamp] [guild] [user_id] [display_name] : text
                            # Count brackets to determine format
                            bracket_count = clean_line.count("] [")

                            if bracket_count >= 3 and "] :" in clean_line:
                                # New format with user_id
                                parts = clean_line.split("] [", 3)
                                timestamp = parts[0].strip("[]")
                                guild = parts[1]
                                user_id = parts[2]

                                # Get display_name and text
                                remaining = parts[3]
                                if "] :" in remaining:
                                    display_name, text = remaining.split("] :", 1)
                                    display_name = display_name.strip()
                                    text = text.strip()

                                    triggers = self._find_triggers_in_text(text)

                                    self.transcriptions.append({
                                        "timestamp": timestamp,
                                        "guild": guild,
                                        "user_id": user_id,  # Store user_id (not displayed)
                                        "user": display_name,  # Display name for UI
                                        "text": text,
                                        "triggers": triggers
                                    })
                                    continue

                            # Try OLD FORMAT: [timestamp] [guild] [display_name] : text
                            if bracket_count >= 1 and "] :" in clean_line:
                                parts = clean_line.split("] [", 1)
                                timestamp = parts[0].strip("[]")

                                rest = parts[1].split("] [", 1)
                                guild = rest[0]

                                user_text = rest[1].split("] :", 1)
                                display_name = user_text[0]
                                text = user_text[1].strip()

                                triggers = self._find_triggers_in_text(text)

                                self.transcriptions.append({
                                    "timestamp": timestamp,
                                    "guild": guild,
                                    "user_id": None,  # Old format doesn't have ID
                                    "user": display_name,
                                    "text": text,
                                    "triggers": triggers
                                })

                        except Exception as e:
                            print(f"Error parsing line: {e}")
                            continue

                self.last_log_position = f.tell()

        except Exception as e:
            print(f"Error reading logs: {e}")

    def _find_triggers_in_text(self, text: str) -> List[Dict]:
        """Find trigger words and their positions in text."""
        if not self.soundboard_data:
            return []

        triggers = []
        words = text.lower().split()
        sounds = self.soundboard_data.get("sounds", {})

        for word in words:
            for sound_key, sound_data in sounds.items():
                if word in [t.lower() for t in sound_data.get("triggers", [])]:
                    triggers.append({
                        "word": word,
                        "sound_key": sound_key,
                        "sound_title": sound_data.get("title", "Unknown"),
                        "soundfile": sound_data.get("soundfile", ""),
                        "volume": sound_data.get("audio_metadata", {}).get("volume_adjust", 1.0),
                        "play_count": sound_data.get("play_stats", {}).get("total", 0)
                    })
                    break

        return triggers

    def draw_text(self, text: str, pos: Tuple[int, int], font=None, color=None) -> int:
        """Draw text and return width."""
        if font is None:
            font = self.text_font
        if color is None:
            color = self.TEXT_COLOR

        text_surface = font.render(text, True, color)
        self.screen.blit(text_surface, pos)
        return text_surface.get_width()

    def draw_panel(self, rect: pygame.Rect, title: str = None):
        """Draw a panel background."""
        pygame.draw.rect(self.screen, self.PANEL_COLOR, rect, border_radius=8)
        pygame.draw.rect(self.screen, self.BORDER_COLOR, rect, 2, border_radius=8)

        if title:
            self.draw_text(title, (rect.x + 15, rect.y + 12), self.header_font, self.ACCENT_COLOR)

    def draw_sidebar(self):
        """Draw left sidebar with navigation and bot health."""
        sidebar_rect = pygame.Rect(0, 0, self.SIDEBAR_WIDTH, self.height)
        pygame.draw.rect(self.screen, self.SIDEBAR_COLOR, sidebar_rect)
        pygame.draw.line(self.screen, self.BORDER_COLOR,
                         (self.SIDEBAR_WIDTH, 0),
                         (self.SIDEBAR_WIDTH, self.height), 2)

        # Navigation buttons (no emojis)
        y = 10
        buttons = [
            ("Dashboard", ViewType.DASHBOARD),
            ("Chat", ViewType.CHAT),
            ("Voice", ViewType.VOICE),
            ("Sounds", ViewType.SOUNDS),
            ("Errors", ViewType.ERRORS),
            ("Logs", ViewType.LOGS),
            ("Config", ViewType.CONFIG),
        ]

        for label, view_type in buttons:
            self._draw_nav_button(label, view_type, y)
            y += self.BUTTON_HEIGHT + self.BUTTON_SPACING

        # Bot Health section at bottom
        health_y = self.height - 230
        self._draw_bot_health(health_y)

    def _draw_nav_button(self, label: str, view_type: str, y: int):
        """Draw a navigation button."""
        button_rect = pygame.Rect(10, y, self.SIDEBAR_WIDTH - 20, self.BUTTON_HEIGHT)

        is_active = self.current_view == view_type
        is_hovered = self.hovered_button == view_type

        if is_active:
            color = self.BUTTON_ACTIVE_COLOR
        elif is_hovered:
            color = self.BUTTON_HOVER_COLOR
        else:
            color = self.SIDEBAR_COLOR

        if color != self.SIDEBAR_COLOR:
            pygame.draw.rect(self.screen, color, button_rect, border_radius=6)

        if is_active:
            pygame.draw.rect(self.screen, self.ACCENT_COLOR, button_rect, 2, border_radius=6)

        text_color = self.ACCENT_COLOR if is_active else self.TEXT_COLOR

        label_text = label

        # Add error indicator
        if view_type == ViewType.ERRORS and self.unread_errors > 0:
            if self.unread_critical > 0:
                label_text = f"{label} (!{self.unread_errors})"
                text_color = self.CRITICAL_COLOR
            else:
                label_text = f"{label} ({self.unread_errors})"
                text_color = self.WARNING_COLOR

        # Center text in button
        text_surf = self.text_font.render(label_text, True, text_color)
        text_rect = text_surf.get_rect(center=button_rect.center)
        self.screen.blit(text_surf, text_rect)

        self.button_rects[view_type] = button_rect

    def _draw_bot_health(self, y: int):
        """Draw bot health info at bottom of sidebar."""
        pygame.draw.line(self.screen, self.BORDER_COLOR,
                         (10, y - 10), (self.SIDEBAR_WIDTH - 10, y - 10), 1)

        self.draw_text("Bot Health", (15, y), self.header_font, self.ACCENT_COLOR)
        y += 30

        if not self.health_data or not self.health_data.get("current"):
            self.draw_text("No data", (15, y), self.small_font, self.WARNING_COLOR)
            return

        current = self.health_data["current"]

        cpu = current.get("cpu_percent", 0)
        self.draw_text("CPU:", (15, y), self.small_font)
        self._draw_progress_bar(65, y, 130, 12, cpu / 100, self._get_health_color(cpu, 60, 80))
        self.draw_text(f"{cpu:.1f}%", (200, y), self.tiny_font)
        y += 25

        mem_pct = current.get("memory_percent", 0)
        mem_mb = current.get("memory_mb", 0)
        self.draw_text("MEM:", (15, y), self.small_font)
        self._draw_progress_bar(65, y, 130, 12, mem_pct / 100, self._get_health_color(mem_pct, 60, 80))
        self.draw_text(f"{mem_mb:.0f}MB", (200, y), self.tiny_font)
        y += 25

        vc_count = current.get("active_connections", 0)
        vc_color = self.SUCCESS_COLOR if vc_count > 0 else self.TEXT_COLOR
        self.draw_text(f"Voice: {vc_count}", (15, y), self.small_font, vc_color)
        y += 25

        cmd_rate = current.get("commands_per_minute", 0)
        self.draw_text(f"Cmds/min: {cmd_rate}", (15, y), self.small_font)

    def _draw_progress_bar(self, x: int, y: int, width: int, height: int,
                           progress: float, color: Tuple[int, int, int]):
        """Draw a progress bar."""
        bg_rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (40, 40, 50), bg_rect, border_radius=3)

        fill_width = int(width * min(progress, 1.0))
        if fill_width > 0:
            fill_rect = pygame.Rect(x, y, fill_width, height)
            pygame.draw.rect(self.screen, color, fill_rect, border_radius=3)

        pygame.draw.rect(self.screen, self.BORDER_COLOR, bg_rect, 1, border_radius=3)

    def _get_health_color(self, value: float, warning_threshold: float,
                          critical_threshold: float) -> Tuple[int, int, int]:
        """Get color based on health metric value."""
        if value > critical_threshold:
            return self.ERROR_COLOR
        elif value > warning_threshold:
            return self.WARNING_COLOR
        else:
            return self.SUCCESS_COLOR

    def draw_content(self):
        """Draw main content area based on current view."""
        content_rect = pygame.Rect(
            self.SIDEBAR_WIDTH + 10,
            10,
            self.width - self.SIDEBAR_WIDTH - 20,
            self.height - 20
        )

        if self.current_view == ViewType.DASHBOARD:
            self._draw_dashboard_view(content_rect)
        elif self.current_view == ViewType.CHAT:
            self._draw_chat_view(content_rect)
        elif self.current_view == ViewType.VOICE:
            self._draw_voice_view(content_rect)
        elif self.current_view == ViewType.SOUNDS:
            self._draw_sounds_view(content_rect)
        elif self.current_view == ViewType.ERRORS:
            self._draw_errors_view(content_rect)
        elif self.current_view == ViewType.LOGS:
            self._draw_logs_view(content_rect)
        elif self.current_view == ViewType.CONFIG:
            self._draw_config_view(content_rect)

    def _draw_dashboard_view(self, rect: pygame.Rect):
        """Draw dashboard overview."""
        self.draw_panel(rect, "Dashboard Overview")

        y = rect.y + 50
        x = rect.x + 20

        if self.health_data and self.health_data.get("current"):
            current = self.health_data["current"]

            self.draw_text("System Status", (x, y), self.header_font, self.ACCENT_COLOR)
            y += 30

            stats = [
                ("Active Connections", current.get("active_connections", 0)),
                ("Commands/min", current.get("commands_per_minute", 0)),
                ("CPU Usage", f"{current.get('cpu_percent', 0):.1f}%"),
                ("Memory", f"{current.get('memory_mb', 0):.0f}MB"),
            ]

            for label, value in stats:
                self.draw_text(f"{label}:", (x, y), self.text_font)
                self.draw_text(str(value), (x + 200, y), self.text_font, self.ACCENT_COLOR)
                y += 25

        y += 30
        self.draw_text("Recent Activity", (x, y), self.header_font, self.ACCENT_COLOR)
        y += 30

        if self.transcriptions:
            for trans in list(self.transcriptions)[-5:]:
                time_str = trans["timestamp"].split()[1][:8]
                text = trans["text"][:50] + "..." if len(trans["text"]) > 50 else trans["text"]
                self.draw_text(f"[{time_str}] {trans['user']}: {text}",
                               (x, y), self.small_font)
                y += 22
        else:
            self.draw_text("No recent activity", (x, y), self.text_font, self.WARNING_COLOR)

    def _draw_chat_view(self, rect: pygame.Rect):
        """Draw chat transcriptions with trigger highlighting and real avatars."""
        self.draw_panel(rect, "Live Chat Transcriptions")

        if not self.transcriptions:
            self.draw_text("No transcriptions yet...",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        content_y = rect.y + 50
        visible_height = rect.height - 60
        line_height = 45

        total_content_height = len(self.transcriptions) * line_height
        self.max_scroll = max(0, total_content_height - visible_height)

        y = content_y + visible_height - line_height + self.scroll_offset

        for trans in reversed(self.transcriptions):
            if y + line_height < content_y:
                break
            if y > content_y + visible_height:
                y -= line_height
                continue

            if content_y <= y <= content_y + visible_height:
                x = rect.x + 20

                # Real avatar using user_id
                user_id = trans.get("user_id")
                display_name = trans["user"]
                avatar = self.get_avatar(user_id, display_name)
                self.screen.blit(avatar, (x, y + 6))
                x += 40

                # Timestamp
                timestamp = trans["timestamp"].split()[1][:8]
                self.draw_text(f"[{timestamp}]", (x, y + 10), self.small_font, self.ACCENT_COLOR)
                x += 80

                # Username (display_name only, no user_id shown)
                display_name = trans["user"]
                username_width = self.draw_text(display_name + ":", (x, y + 10), self.text_font)
                x += username_width + 10

                # Text with trigger highlighting
                self._draw_text_with_triggers(trans, x, y + 10, rect.x + rect.width - 30)

            y -= line_height

        if self.max_scroll > 0:
            self._draw_scroll_indicator(rect, content_y, visible_height, total_content_height)

    def _draw_text_with_triggers(self, trans: Dict, x: int, y: int, max_x: int):
        """Draw text with trigger words highlighted."""
        text = trans["text"]
        triggers = trans.get("triggers", [])

        words = text.split()
        current_x = x

        for word in words:
            trigger_info = None
            for trigger in triggers:
                if trigger["word"] == word.lower():
                    trigger_info = trigger
                    break

            if trigger_info:
                color = self.TRIGGER_HIGHLIGHT_COLOR
                word_surf = self.text_font.render(word, True, color)
                word_rect = pygame.Rect(current_x, y, word_surf.get_width(), word_surf.get_height())

                if word_rect.collidepoint(self.mouse_pos):
                    pygame.draw.line(self.screen, color,
                                     (current_x, y + word_surf.get_height()),
                                     (current_x + word_surf.get_width(), y + word_surf.get_height()), 2)

                    self.tooltip_text = (
                        f"Sound: {trigger_info['sound_title']}\n"
                        f"File: {trigger_info['soundfile']}\n"
                        f"Volume: {int(trigger_info['volume'] * 100)}%\n"
                        f"Plays: {trigger_info['play_count']}"
                    )
                    self.tooltip_pos = (self.mouse_pos[0] + 15, self.mouse_pos[1] + 15)

                self.screen.blit(word_surf, (current_x, y))
            else:
                color = self.TEXT_COLOR
                self.draw_text(word, (current_x, y), self.text_font, color)

            word_width = self.text_font.size(word + " ")[0]
            current_x += word_width

            if current_x > max_x:
                break

    def _draw_scroll_indicator(self, rect: pygame.Rect, content_y: int,
                               visible_height: int, total_height: int):
        """Draw scroll indicator bar."""
        indicator_height = max(20, int((visible_height / total_height) * visible_height))
        scroll_percent = abs(self.scroll_offset) / self.max_scroll if self.max_scroll > 0 else 0
        indicator_y = content_y + int(scroll_percent * (visible_height - indicator_height))

        pygame.draw.rect(self.screen, self.ACCENT_COLOR,
                         (rect.x + rect.width - 10, indicator_y, 6, indicator_height),
                         border_radius=3)

    def _draw_voice_view(self, rect: pygame.Rect):
        """Draw voice connections view."""
        self.draw_panel(rect, "Voice Connections")

        if not self.connection_data:
            self.draw_text("No connection data", (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        connections = self.connection_data.get("connections", [])

        if not connections:
            self.draw_text("Not connected to any voice channels",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        y = rect.y + 60
        x = rect.x + 20

        for conn in connections:
            conn_rect = pygame.Rect(x, y, rect.width - 40, 120)
            pygame.draw.rect(self.screen, self.BG_COLOR, conn_rect, border_radius=6)
            pygame.draw.rect(self.screen, self.BORDER_COLOR, conn_rect, 1, border_radius=6)

            status_color = self.SUCCESS_COLOR if conn.get("is_listening") else self.WARNING_COLOR
            pygame.draw.circle(self.screen, status_color, (x + 15, y + 15), 6)

            self.draw_text(conn.get("guild_name", "Unknown"),
                           (x + 30, y + 8), self.text_font, self.ACCENT_COLOR)
            self.draw_text(f"#{conn.get('channel_name', 'Unknown')}",
                           (x + 30, y + 32), self.small_font)

            stats_x = x + 300
            self.draw_text(f"Members: {conn.get('members_count', 0)}",
                           (stats_x, y + 10), self.small_font)
            self.draw_text(f"Queue: {conn.get('queue_size', 0)}",
                           (stats_x, y + 30), self.small_font)

            status_text = "Listening" if conn.get("is_listening") else "Idle"
            self.draw_text(status_text, (stats_x + 150, y + 10),
                           self.small_font, status_color)

            if conn.get("is_playing"):
                self.draw_text("Playing", (stats_x + 150, y + 30),
                               self.small_font, self.SUCCESS_COLOR)

            y += 140

    def _draw_sounds_view(self, rect: pygame.Rect):
        """Draw sounds management view with editing capabilities."""
        self.draw_panel(rect, "Sound Management")

        if not self.soundboard_data:
            self.draw_text("Loading soundboard data...", (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        sounds = self.soundboard_data.get("sounds", {})

        # Split view: Sound list on left, details/edit on right
        list_width = 400

        # Left panel - Sound list
        list_rect = pygame.Rect(rect.x + 10, rect.y + 50, list_width, rect.height - 60)
        pygame.draw.rect(self.screen, self.BG_COLOR, list_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.BORDER_COLOR, list_rect, 1, border_radius=6)

        self.draw_text(f"Total Sounds: {len(sounds)}", (list_rect.x + 10, list_rect.y + 10),
                       self.small_font, self.ACCENT_COLOR)

        # Scrollable sound list
        y = list_rect.y + 40
        self.sound_buttons = {}

        sorted_sounds = sorted(
            sounds.items(),
            key=lambda item: item[1].get("play_stats", {}).get("total", 0),
            reverse=True
        )

        for sound_key, sound_data in sorted_sounds:
            if y > list_rect.y + list_rect.height - 10:
                break

            sound_rect = pygame.Rect(list_rect.x + 5, y, list_width - 10, 50)

            # Highlight if selected
            if self.selected_sound == sound_key:
                pygame.draw.rect(self.screen, self.BUTTON_ACTIVE_COLOR, sound_rect, border_radius=4)
            elif sound_rect.collidepoint(self.mouse_pos):
                pygame.draw.rect(self.screen, self.BUTTON_HOVER_COLOR, sound_rect, border_radius=4)

            # Sound info
            title = sound_data.get("title", "Unknown")
            plays = sound_data.get("play_stats", {}).get("total", 0)

            self.draw_text(title, (sound_rect.x + 10, sound_rect.y + 8), self.text_font)
            self.draw_text(f"{plays} plays", (sound_rect.x + 10, sound_rect.y + 28),
                           self.tiny_font, self.ACCENT_COLOR)

            self.sound_buttons[sound_key] = sound_rect
            y += 55

        # Right panel - Selected sound details
        if self.selected_sound and self.selected_sound in sounds:
            self._draw_sound_editor(rect, list_width + 20, sounds[self.selected_sound], self.selected_sound)
        else:
            detail_x = rect.x + list_width + 30
            self.draw_text("Select a sound to edit", (detail_x, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)

    def _draw_sound_editor(self, parent_rect: pygame.Rect, offset_x: int, sound_data: Dict, sound_key: str):
        """Draw sound editing panel."""
        x = parent_rect.x + offset_x
        y = parent_rect.y + 60

        # Title
        self.draw_text("Edit Sound", (x, y), self.header_font, self.ACCENT_COLOR)
        y += 35

        # Sound title
        title = sound_data.get("title", "Unknown")
        self.draw_text(f"Title: {title}", (x, y), self.text_font)
        y += 30

        # Triggers
        triggers = sound_data.get("triggers", [])
        self.draw_text("Triggers:", (x, y), self.text_font)
        y += 25
        trigger_text = ", ".join(triggers) if triggers else "None"
        self.draw_text(trigger_text, (x + 20, y), self.small_font, self.ACCENT_COLOR)
        y += 30

        # File path
        soundfile = sound_data.get("soundfile", "")
        self.draw_text(f"File: {soundfile}", (x, y), self.small_font)
        y += 30

        # Volume control
        volume = sound_data.get("audio_metadata", {}).get("volume_adjust", 1.0)
        volume_percent = int(volume * 100)

        self.draw_text(f"Volume: {volume_percent}%", (x, y), self.text_font)
        y += 25

        # Volume bar (visual only for now)
        bar_width = 300
        self._draw_progress_bar(x, y, bar_width, 20, volume / 2.0, self.ACCENT_COLOR)
        y += 35

        # Play stats
        stats = sound_data.get("play_stats", {})
        self.draw_text("Statistics:", (x, y), self.text_font)
        y += 25

        stat_items = [
            ("Total plays", stats.get("total", 0)),
            ("This week", stats.get("week", 0)),
            ("This month", stats.get("month", 0)),
        ]

        for label, value in stat_items:
            self.draw_text(f"{label}: {value}", (x + 20, y), self.small_font)
            y += 22

        y += 20

        # Status flags
        is_disabled = sound_data.get("is_disabled", False)
        is_private = sound_data.get("is_private", False)

        status_color = self.ERROR_COLOR if is_disabled else self.SUCCESS_COLOR
        status_text = "Disabled" if is_disabled else "Enabled"
        self.draw_text(f"Status: {status_text}", (x, y), self.text_font, status_color)
        y += 25

        privacy_text = "Private" if is_private else "Public"
        privacy_color = self.WARNING_COLOR if is_private else self.SUCCESS_COLOR
        self.draw_text(f"Privacy: {privacy_text}", (x, y), self.text_font, privacy_color)
        y += 30

        # Added by
        added_by = sound_data.get("added_by", "Unknown")
        added_date = sound_data.get("added_date", "")[:10]
        self.draw_text(f"Added by: {added_by}", (x, y), self.small_font)
        y += 20
        self.draw_text(f"Date: {added_date}", (x, y), self.small_font)
        y += 30

        # Note about editing
        self.draw_text("Editing functionality coming soon!", (x, y), self.small_font, self.WARNING_COLOR)
        self.draw_text("For now, use Discord commands to edit sounds", (x, y + 20), self.tiny_font)

    def _draw_errors_view(self, rect: pygame.Rect):
        """Draw errors view with categorization."""
        self.draw_panel(rect, "Error Log")

        y = rect.y + 60
        x = rect.x + 20

        if not self.error_data:
            self.draw_text("No error data available", (x, y), self.text_font, self.SUCCESS_COLOR)
            return

        recent_errors = self.error_data.get("recent", [])

        if not recent_errors:
            self.draw_text("No errors recorded!", (x, y), self.text_font, self.SUCCESS_COLOR)
            return

        critical = len([e for e in recent_errors if e.get("severity") == "critical"])
        high = len([e for e in recent_errors if e.get("severity") == "high"])
        medium = len([e for e in recent_errors if e.get("severity") == "medium"])

        self.draw_text(f"Total: {len(recent_errors)}", (x, y), self.text_font)
        self.draw_text(f"Critical: {critical}", (x + 150, y), self.text_font,
                       self.CRITICAL_COLOR if critical > 0 else self.TEXT_COLOR)
        self.draw_text(f"High: {high}", (x + 300, y), self.text_font, self.ERROR_COLOR if high > 0 else self.TEXT_COLOR)
        self.draw_text(f"Medium: {medium}", (x + 450, y), self.text_font,
                       self.WARNING_COLOR if medium > 0 else self.TEXT_COLOR)

        y += 40

        for error in recent_errors[-15:]:
            error_rect = pygame.Rect(x, y, rect.width - 40, 70)

            severity = error.get("severity", "medium")
            if severity == "critical":
                border_color = self.CRITICAL_COLOR
            elif severity == "high":
                border_color = self.ERROR_COLOR
            else:
                border_color = self.WARNING_COLOR

            pygame.draw.rect(self.screen, self.BG_COLOR, error_rect, border_radius=6)
            pygame.draw.rect(self.screen, border_color, error_rect, 2, border_radius=6)

            timestamp = error.get("timestamp", "")[:19]
            self.draw_text(timestamp, (x + 10, y + 8), self.tiny_font, self.ACCENT_COLOR)

            category = error.get("category", "unknown")
            error_type = error.get("error_type", "Error")
            self.draw_text(f"[{category}] {error_type}", (x + 10, y + 25), self.small_font, border_color)

            message = error.get("message", "No message")[:80]
            self.draw_text(message, (x + 10, y + 45), self.tiny_font)

            y += 80

            if y > rect.y + rect.height - 100:
                break

    def _draw_logs_view(self, rect: pygame.Rect):
        """Draw system logs view."""
        self.draw_panel(rect, "System Logs")

        y = rect.y + 60
        x = rect.x + 20

        self.draw_text("Recent log entries:", (x, y), self.text_font, self.ACCENT_COLOR)
        y += 30

        if self.log_file.exists():
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-50:]

                for line in lines:
                    if not line.strip():
                        continue

                    color = self.TEXT_COLOR
                    if "ERROR" in line or "CRITICAL" in line:
                        color = self.ERROR_COLOR
                    elif "WARNING" in line:
                        color = self.WARNING_COLOR
                    elif "INFO" in line:
                        color = self.TEXT_COLOR

                    display_line = line.strip()[:120]
                    if len(line.strip()) > 120:
                        display_line += "..."

                    self.draw_text(display_line, (x, y), self.tiny_font, color)
                    y += 16

                    if y > rect.y + rect.height - 30:
                        break

            except Exception as e:
                self.draw_text(f"Error reading logs: {e}", (x, y), self.text_font, self.ERROR_COLOR)
        else:
            self.draw_text("Log file not found", (x, y), self.text_font, self.WARNING_COLOR)

    def _draw_config_view(self, rect: pygame.Rect):
        """Draw configuration view."""
        self.draw_panel(rect, "Configuration")

        y = rect.y + 60
        x = rect.x + 20

        self.draw_text("Bot Configuration", (x, y), self.header_font, self.ACCENT_COLOR)
        y += 40

        configs = [
            ("Command Prefix", "~"),
            ("Admin Dashboard", "Enabled"),
            ("Data Export Interval", "10 seconds"),
            ("Health Collection", "5 seconds"),
            ("Max History", "1000 entries"),
            ("Speech Recognition", "Enabled"),
            ("Auto Disconnect", "Enabled"),
        ]

        for label, value in configs:
            self.draw_text(f"{label}:", (x, y), self.text_font)
            self.draw_text(value, (x + 300, y), self.text_font, self.ACCENT_COLOR)
            y += 30

        y += 20
        self.draw_text("Note: Configuration is read-only in this view",
                       (x, y), self.small_font, self.WARNING_COLOR)
        self.draw_text("Edit config.py to change settings",
                       (x, y + 20), self.small_font, self.WARNING_COLOR)

    def draw_tooltip(self):
        """Draw tooltip if hovering over trigger word."""
        if not self.tooltip_text or not self.tooltip_pos:
            return

        lines = self.tooltip_text.split('\n')

        max_width = max(self.small_font.size(line)[0] for line in lines)
        tooltip_width = max_width + 20
        tooltip_height = len(lines) * 20 + 10

        x, y = self.tooltip_pos

        if x + tooltip_width > self.width:
            x = self.width - tooltip_width - 10
        if y + tooltip_height > self.height:
            y = self.height - tooltip_height - 10

        tooltip_rect = pygame.Rect(x, y, tooltip_width, tooltip_height)
        pygame.draw.rect(self.screen, (40, 40, 50), tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.ACCENT_COLOR, tooltip_rect, 2, border_radius=6)

        text_y = y + 5
        for line in lines:
            self.draw_text(line, (x + 10, text_y), self.small_font)
            text_y += 20

    def handle_input(self):
        """Handle keyboard and mouse input."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_r:
                    self.load_data()
                    self.load_transcriptions()

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Check navigation buttons
                    for view_type, button_rect in self.button_rects.items():
                        if button_rect.collidepoint(event.pos):
                            self.current_view = view_type
                            self.scroll_offset = 0

                            if view_type == ViewType.ERRORS:
                                self.unread_errors = 0
                                self.unread_critical = 0
                            break

                    # Check sound selection buttons
                    if self.current_view == ViewType.SOUNDS:
                        for sound_key, sound_rect in self.sound_buttons.items():
                            if sound_rect.collidepoint(event.pos):
                                self.selected_sound = sound_key
                                break

                elif event.button == 4:  # Scroll up
                    if self.current_view in [ViewType.CHAT, ViewType.LOGS]:
                        self.scroll_offset = min(0, self.scroll_offset + 40)
                        # Disable auto-scroll when user manually scrolls up
                        if self.current_view == ViewType.CHAT:
                            self.auto_scroll = False

                elif event.button == 5:  # Scroll down
                    if self.current_view in [ViewType.CHAT, ViewType.LOGS]:
                        # Clamp to max_scroll
                        new_offset = max(-self.max_scroll, self.scroll_offset - 40)
                        self.scroll_offset = new_offset

                        # Re-enable auto-scroll if scrolled to bottom
                        if self.current_view == ViewType.CHAT:
                            if abs(self.scroll_offset - (-self.max_scroll)) < 10:  # Within 10px of bottom
                                self.auto_scroll = True

            elif event.type == pygame.MOUSEMOTION:
                self.mouse_pos = event.pos

                self.hovered_button = None
                for view_type, button_rect in self.button_rects.items():
                    if button_rect.collidepoint(event.pos):
                        self.hovered_button = view_type
                        break

                if self.tooltip_pos:
                    dist = ((event.pos[0] - self.tooltip_pos[0]) ** 2 +
                            (event.pos[1] - self.tooltip_pos[1]) ** 2) ** 0.5
                    if dist > 50:
                        self.tooltip_text = None
                        self.tooltip_pos = None

            elif event.type == pygame.VIDEORESIZE:
                self.width = event.w
                self.height = event.h
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)

        return True

    def run(self):
        """Main loop."""
        running = True

        print("Full Bot Monitor Dashboard")
        print("==========================")
        print("Controls:")
        print("  Left Click: Navigate between views / Select sounds")
        print("  Mouse Wheel: Scroll in Chat/Logs views")
        print("  Hover: View trigger word details")
        print("  R: Refresh data")
        print("  ESC: Exit")
        print()

        while running:
            current_time = pygame.time.get_ticks()

            if current_time - self.last_update > self.update_interval:
                self.load_data()
                self.load_transcriptions()
                self.last_update = current_time

            running = self.handle_input()

            self.screen.fill(self.BG_COLOR)

            self.draw_sidebar()
            self.draw_content()
            self.draw_tooltip()

            status_text = f"Live | {datetime.now().strftime('%H:%M:%S')} | View: {self.current_view.title()}"
            self.draw_text(status_text, (self.SIDEBAR_WIDTH + 20, self.height - 25),
                           self.small_font, self.ACCENT_COLOR)

            pygame.display.flip()
            self.clock.tick(30)

        pygame.quit()


if __name__ == "__main__":
    data_dir = Path("admin_data")
    if not data_dir.exists():
        print("Error: admin_data directory not found!")
        print("Make sure the bot is running with ENABLE_ADMIN_DASHBOARD=true")
        sys.exit(1)

    dashboard = FullDashboard()
    dashboard.run()