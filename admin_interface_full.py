# admin_interface_full.py
"""
Full Featured Multi-View Admin Dashboard with Multi-Guild Support
Navigation sidebar with switchable content panels
"""

import pygame
import json
import sys
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Optional, Tuple, List, Dict
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
    """Full dashboard with multi-view navigation and multi-guild support."""

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
    TAB_ACTIVE_COLOR = (50, 100, 200)
    TAB_HOVER_COLOR = (45, 45, 55)

    # Layout constants
    SIDEBAR_WIDTH = 220
    BUTTON_HEIGHT = 45
    BUTTON_SPACING = 5
    TAB_HEIGHT = 35

    def __init__(self, width=1400, height=900):
        pygame.init()
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        pygame.display.set_caption("Bot Monitor - Multi-Guild Dashboard")

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

        # Multi-guild chat state
        self.guild_transcriptions = {}  # {guild_id: deque([msg, msg, ...])}
        self.available_guilds = {}  # {guild_id: guild_name}
        self.selected_guild = None  # Currently viewing this guild
        self.guild_tab_rects = {}  # {guild_id: pygame.Rect} for click detection

        # Avatar cache
        self.avatar_cache = {}
        self.user_avatars = {}
        self.user_id_to_info = {}
        self._create_default_avatars()
        self._load_user_info()

        # Data
        self.transcriptions = deque(maxlen=500)
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
        self.auto_scroll = True
        self.last_transcription_count = 0

        # Tooltip state
        self.tooltip_text = None
        self.tooltip_pos = None
        self.hovered_trigger = None

        # Error tracking
        self.unread_errors = 0
        self.unread_critical = 0

        # Sound editing state
        self.selected_sound = None
        self.sound_list_scroll = 0
        self.sound_buttons = {}

    def _create_default_avatars(self):
        """Create default avatar surfaces."""
        size = 32
        colors = [
            (100, 150, 255), (255, 100, 150), (100, 255, 150),
            (255, 200, 100), (150, 100, 255), (100, 200, 255)
        ]

        for i, color in enumerate(colors):
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surface, color, (size // 2, size // 2), size // 2)
            self.avatar_cache[f"default_{i}"] = surface

    def _load_user_info(self):
        """Load user information from JSON."""
        try:
            user_file = self.data_dir / "user_info.json"  # FIXED: correct filename
            if user_file.exists():
                with open(user_file, "r") as f:
                    data = json.load(f)
                    users_dict = data.get("users", {})  # FIXED: it's a dict, not list

                    # FIXED: Iterate over dict items
                    for user_id, user_info in users_dict.items():
                        self.user_id_to_info[user_id] = user_info
                        avatar_url = user_info.get("avatar_url")
                        if avatar_url:
                            self.user_avatars[user_id] = avatar_url

                    print(f"Loaded user info for {len(self.user_id_to_info)} users")
        except Exception as e:
            print(f"Error loading user info: {e}")

    def get_avatar(self, user_id: Optional[str], display_name: str) -> pygame.Surface:
        """Get avatar for user - real or default."""
        if not user_id:
            hash_val = hash(display_name) % 6
            return self.avatar_cache.get(f"default_{hash_val}",
                                         list(self.avatar_cache.values())[0])

        cache_key = f"user_{user_id}"
        if cache_key in self.avatar_cache:
            return self.avatar_cache[cache_key]

        avatar_url = self.user_avatars.get(user_id)
        if avatar_url:
            try:
                cache_path = self.avatar_cache_dir / f"{user_id}.png"
                if not cache_path.exists():
                    with urllib.request.urlopen(avatar_url, timeout=5) as response:
                        image_data = response.read()
                    with open(cache_path, 'wb') as f:
                        f.write(image_data)

                pil_image = Image.open(cache_path)
                pil_image = pil_image.resize((32, 32), Image.Resampling.LANCZOS)

                mode = pil_image.mode
                size = pil_image.size
                data = pil_image.tobytes()

                py_image = pygame.image.fromstring(data, size, mode)

                mask_surface = pygame.Surface((32, 32), pygame.SRCALPHA)
                pygame.draw.circle(mask_surface, (255, 255, 255, 255), (16, 16), 16)

                result = pygame.Surface((32, 32), pygame.SRCALPHA)
                result.blit(py_image, (0, 0))
                result.blit(mask_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

                self.avatar_cache[cache_key] = result
                return result

            except Exception as e:
                print(f"Error loading avatar for {user_id}: {e}")

        hash_val = hash(display_name) % 6
        return self.avatar_cache.get(f"default_{hash_val}",
                                     list(self.avatar_cache.values())[0])

    def load_data(self):
        """Load health, connection, error, command, and soundboard data from JSON."""
        try:
            health_file = self.data_dir / "health.json"
            if health_file.exists():
                with open(health_file, "r") as f:
                    self.health_data = json.load(f)

            conn_file = self.data_dir / "connections.json"
            if conn_file.exists():
                with open(conn_file, "r") as f:
                    self.connection_data = json.load(f)
                    # Update available guilds from connections
                    if self.connection_data and "connections" in self.connection_data:
                        for conn in self.connection_data["connections"]:
                            guild_id = str(conn.get("guild_id"))
                            guild_name = conn.get("guild_name", "Unknown")
                            if guild_id not in self.available_guilds:
                                self.available_guilds[guild_id] = guild_name
                                self.guild_transcriptions[guild_id] = deque(maxlen=500)

            error_file = self.data_dir / "errors.json"
            if error_file.exists():
                with open(error_file, "r") as f:
                    self.error_data = json.load(f)
                    if self.error_data:
                        errors = self.error_data.get("errors", [])
                        self.unread_errors = sum(1 for e in errors if not e.get("read", False))
                        self.unread_critical = sum(1 for e in errors
                                                   if not e.get("read", False)
                                                   and e.get("severity") == "CRITICAL")

            command_file = self.data_dir / "commands.json"
            if command_file.exists():
                with open(command_file, "r") as f:
                    self.command_data = json.load(f)

            soundboard_file = self.data_dir / "soundboard_stats.json"
            if soundboard_file.exists():
                with open(soundboard_file, "r") as f:
                    self.soundboard_data = json.load(f)

        except Exception as e:
            print(f"Error loading data: {e}")

    def load_transcriptions(self):
        """Load new transcriptions from log file with guild separation."""
        if not self.log_file.exists():
            return

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                f.seek(self.last_log_position)
                new_lines = f.readlines()
                self.last_log_position = f.tell()

            for line in new_lines:
                if "[TRANSCRIPTION]" in line:
                    try:
                        parts = line.split("[TRANSCRIPTION]", 1)
                        if len(parts) < 2:
                            continue

                        json_str = parts[1].strip()
                        trans_data = json.loads(json_str)

                        guild_id = str(trans_data.get("guild_id", "unknown"))
                        guild_name = trans_data.get("guild", "Unknown Guild")

                        # Ensure guild exists in our tracking
                        if guild_id not in self.available_guilds:
                            self.available_guilds[guild_id] = guild_name
                            self.guild_transcriptions[guild_id] = deque(maxlen=500)

                        # Add to guild-specific transcription queue
                        self.guild_transcriptions[guild_id].append(trans_data)

                        # Also add to general transcriptions for dashboard
                        self.transcriptions.append(trans_data)

                        # Set default selected guild if none selected
                        if self.selected_guild is None and guild_id != "unknown":
                            self.selected_guild = guild_id

                    except json.JSONDecodeError as e:
                        print(f"Failed to parse transcription JSON: {e}")
                        continue

            # Update transcription count for auto-scroll
            current_count = len(self.transcriptions)
            if current_count > self.last_transcription_count:
                if self.auto_scroll:
                    self.scroll_offset = 0
            self.last_transcription_count = current_count

        except Exception as e:
            print(f"Error loading transcriptions: {e}")

    def draw_panel(self, rect: pygame.Rect, title: str):
        """Draw a panel with title."""
        pygame.draw.rect(self.screen, self.PANEL_COLOR, rect, border_radius=8)
        pygame.draw.rect(self.screen, self.BORDER_COLOR, rect, 2, border_radius=8)

        title_surface = self.header_font.render(title, True, self.TEXT_COLOR)
        self.screen.blit(title_surface, (rect.x + 15, rect.y + 12))

    def draw_text(self, text: str, pos: Tuple[int, int], font=None,
                  color=None) -> int:
        """Draw text and return its width."""
        if font is None:
            font = self.text_font
        if color is None:
            color = self.TEXT_COLOR

        surface = font.render(text, True, color)
        self.screen.blit(surface, pos)
        return surface.get_width()

    def draw_sidebar(self):
        """Draw navigation sidebar."""
        sidebar_rect = pygame.Rect(0, 0, self.SIDEBAR_WIDTH, self.height)
        pygame.draw.rect(self.screen, self.SIDEBAR_COLOR, sidebar_rect)

        pygame.draw.line(self.screen, self.BORDER_COLOR,
                         (self.SIDEBAR_WIDTH, 0),
                         (self.SIDEBAR_WIDTH, self.height), 2)

        self.draw_text("Bot Monitor", (15, 15), self.title_font, self.ACCENT_COLOR)

        buttons = [
            (ViewType.DASHBOARD, "📊 Dashboard"),
            (ViewType.CHAT, "💬 Chat"),
            (ViewType.VOICE, "🎤 Voice"),
            (ViewType.SOUNDS, "🔊 Sounds"),
            (ViewType.ERRORS, "⚠️ Errors"),
            (ViewType.LOGS, "📄 Logs"),
            (ViewType.CONFIG, "⚙️ Config"),
        ]

        y = 70
        self.button_rects.clear()

        for view_type, label in buttons:
            rect = pygame.Rect(10, y, self.SIDEBAR_WIDTH - 20, self.BUTTON_HEIGHT)
            self.button_rects[view_type] = rect

            is_active = view_type == self.current_view
            is_hovered = view_type == self.hovered_button

            if is_active:
                color = self.BUTTON_ACTIVE_COLOR
            elif is_hovered:
                color = self.BUTTON_HOVER_COLOR
            else:
                color = self.PANEL_COLOR

            pygame.draw.rect(self.screen, color, rect, border_radius=6)

            if is_active:
                pygame.draw.rect(self.screen, self.ACCENT_COLOR, rect, 2, border_radius=6)

            text_color = self.TEXT_COLOR
            if view_type == ViewType.ERRORS and (self.unread_errors > 0):
                badge_text = f" ({self.unread_critical})" if self.unread_critical > 0 else f" ({self.unread_errors})"
                label_with_badge = label + badge_text
                self.draw_text(label_with_badge, (rect.x + 15, rect.y + 12),
                               self.text_font, self.ERROR_COLOR if self.unread_critical > 0 else self.WARNING_COLOR)
            else:
                self.draw_text(label, (rect.x + 15, rect.y + 12), self.text_font, text_color)

            y += self.BUTTON_HEIGHT + self.BUTTON_SPACING

    def _draw_guild_tabs(self, rect: pygame.Rect) -> int:
        """Draw guild selection tabs at top of chat panel. Returns tab bar height."""
        if not self.available_guilds:
            return 0

        tab_y = rect.y + 50
        tab_x = rect.x + 20
        tab_width = 150
        tab_spacing = 5

        self.guild_tab_rects.clear()

        for guild_id, guild_name in self.available_guilds.items():
            tab_rect = pygame.Rect(tab_x, tab_y, tab_width, self.TAB_HEIGHT)
            self.guild_tab_rects[guild_id] = tab_rect

            is_active = guild_id == self.selected_guild
            is_hovered = tab_rect.collidepoint(self.mouse_pos)

            if is_active:
                color = self.TAB_ACTIVE_COLOR
            elif is_hovered:
                color = self.TAB_HOVER_COLOR
            else:
                color = self.PANEL_COLOR

            pygame.draw.rect(self.screen, color, tab_rect, border_radius=6)

            if is_active:
                pygame.draw.rect(self.screen, self.ACCENT_COLOR, tab_rect, 2, border_radius=6)

            # Truncate guild name if too long
            display_name = guild_name[:18] + "..." if len(guild_name) > 18 else guild_name

            # Center text in tab
            text_surface = self.small_font.render(display_name, True, self.TEXT_COLOR)
            text_x = tab_rect.x + (tab_width - text_surface.get_width()) // 2
            text_y = tab_rect.y + (self.TAB_HEIGHT - text_surface.get_height()) // 2
            self.screen.blit(text_surface, (text_x, text_y))

            tab_x += tab_width + tab_spacing

            # Move to next row if needed
            if tab_x + tab_width > rect.x + rect.width:
                tab_x = rect.x + 20
                tab_y += self.TAB_HEIGHT + tab_spacing

        return tab_y - rect.y + self.TAB_HEIGHT + 10  # Return total height of tab bar

    def _draw_text_with_triggers(self, trans: Dict, x: int, y: int, max_x: int):
        """Draw text with trigger words highlighted."""
        text = trans["text"]
        triggers = trans.get("triggers", [])

        if not triggers:
            self.draw_text(text, (x, y), self.text_font)
            return

        trigger_ranges = []
        for trigger in triggers:
            trigger_word = trigger.get("word", "")
            if not trigger_word:
                continue

            start = 0
            while True:
                pos = text.lower().find(trigger_word.lower(), start)
                if pos == -1:
                    break
                trigger_ranges.append((pos, pos + len(trigger_word), trigger))
                start = pos + len(trigger_word)

        trigger_ranges.sort()

        if not trigger_ranges:
            self.draw_text(text, (x, y), self.text_font)
            return

        current_x = x
        pos = 0

        for start, end, trigger in trigger_ranges:
            if start > pos:
                before_text = text[pos:start]
                width = self.draw_text(before_text, (current_x, y), self.text_font)
                current_x += width

            trigger_text = text[start:end]
            trigger_rect = pygame.Rect(current_x - 2, y - 2,
                                       self.text_font.size(trigger_text)[0] + 4,
                                       self.text_font.get_height() + 4)

            width = self.draw_text(trigger_text, (current_x, y), self.text_font, self.TRIGGER_HIGHLIGHT_COLOR)
            current_x += width

            if trigger_rect.collidepoint(self.mouse_pos):
                self.hovered_trigger = trigger
                self.tooltip_pos = self.mouse_pos
                self.tooltip_text = f"Trigger: {trigger.get('word', '')}\nSound: {trigger.get('sound', 'Unknown')}"

            pos = end

        if pos < len(text):
            remaining = text[pos:]
            self.draw_text(remaining, (current_x, y), self.text_font)

    def _draw_scroll_indicator(self, rect: pygame.Rect, content_y: int,
                               visible_height: int, total_content_height: int):
        """Draw scroll bar indicator."""
        if total_content_height <= visible_height:
            return

        bar_height = max(20, int((visible_height / total_content_height) * visible_height))
        scroll_ratio = abs(self.scroll_offset) / self.max_scroll if self.max_scroll > 0 else 0
        bar_y = content_y + int(scroll_ratio * (visible_height - bar_height))

        bar_rect = pygame.Rect(rect.x + rect.width - 10, bar_y, 6, bar_height)
        pygame.draw.rect(self.screen, self.ACCENT_COLOR, bar_rect, border_radius=3)

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
                # Safely parse timestamp
                timestamp = trans.get("timestamp", "")
                try:
                    if " " in timestamp:
                        time_str = timestamp.split()[1][:8]
                    else:
                        # ISO format like "2025-01-01T12:34:56.789"
                        if "T" in timestamp:
                            time_str = timestamp.split("T")[1][:8]
                        else:
                            time_str = timestamp[:8]
                except:
                    time_str = "00:00:00"

                guild_name = trans.get("guild", "Unknown")
                text = trans.get("text", "")
                text = text[:40] + "..." if len(text) > 40 else text
                user = trans.get("user", "Unknown")

                self.draw_text(f"[{time_str}] [{guild_name}] {user}: {text}",
                               (x, y), self.small_font)
                y += 22
        else:
            self.draw_text("No recent activity", (x, y), self.text_font, self.WARNING_COLOR)

    def _draw_chat_view(self, rect: pygame.Rect):
        """Draw chat transcriptions with guild tabs, trigger highlighting and real avatars."""
        self.draw_panel(rect, "Live Chat Transcriptions")

        # Draw guild tabs
        tab_bar_height = self._draw_guild_tabs(rect)

        # Get transcriptions for selected guild
        current_transcriptions = []
        if self.selected_guild and self.selected_guild in self.guild_transcriptions:
            current_transcriptions = list(self.guild_transcriptions[self.selected_guild])

        if not current_transcriptions:
            no_data_y = rect.y + 60 + tab_bar_height
            self.draw_text("No transcriptions yet...",
                           (rect.x + 20, no_data_y),
                           self.text_font, self.WARNING_COLOR)
            return

        content_y = rect.y + 50 + tab_bar_height
        visible_height = rect.height - 60 - tab_bar_height
        line_height = 45

        total_content_height = len(current_transcriptions) * line_height
        self.max_scroll = max(0, total_content_height - visible_height)

        y = content_y + visible_height - line_height + self.scroll_offset

        for trans in reversed(current_transcriptions):
            if y + line_height < content_y:
                break
            if y > content_y + visible_height:
                y -= line_height
                continue

            if content_y <= y <= content_y + visible_height:
                x = rect.x + 20

                # Real avatar using user_id
                user_id = trans.get("user_id")
                display_name = trans.get("user", "Unknown")
                avatar = self.get_avatar(user_id, display_name)
                self.screen.blit(avatar, (x, y + 6))
                x += 40

                # Timestamp - safely parse
                timestamp = trans.get("timestamp", "")
                try:
                    if " " in timestamp:
                        time_str = timestamp.split()[1][:8]
                    else:
                        # ISO format like "2025-01-01T12:34:56.789"
                        if "T" in timestamp:
                            time_str = timestamp.split("T")[1][:8]
                        else:
                            time_str = timestamp[:8]
                except:
                    time_str = "00:00:00"

                self.draw_text(f"[{time_str}]", (x, y + 10), self.small_font, self.ACCENT_COLOR)
                x += 80

                # Username
                username_width = self.draw_text(display_name + ":", (x, y + 10), self.text_font)
                x += username_width + 10

                # Text with trigger highlighting
                self._draw_text_with_triggers(trans, x, y + 10, rect.x + rect.width - 30)

            y -= line_height

        if self.max_scroll > 0:
            self._draw_scroll_indicator(rect, content_y, visible_height, total_content_height)

    def _draw_voice_view(self, rect: pygame.Rect):
        """Draw voice connections view."""
        self.draw_panel(rect, "Voice Connections")

        if not self.connection_data or not self.connection_data.get("connections"):
            self.draw_text("No active voice connections",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        y = rect.y + 60

        for conn in self.connection_data["connections"]:
            guild_name = conn.get("guild_name", "Unknown")
            channel_name = conn.get("channel_name", "Unknown")
            is_listening = conn.get("is_listening", False)
            is_playing = conn.get("is_playing", False)
            queue_size = conn.get("queue_size", 0)
            members_count = conn.get("members_count", 0)

            status_color = self.SUCCESS_COLOR if is_listening else self.WARNING_COLOR
            status_text = "🎧 Listening" if is_listening else "⏸️ Idle"

            self.draw_text(f"🏠 {guild_name}", (rect.x + 20, y), self.text_font, self.ACCENT_COLOR)
            y += 25

            self.draw_text(f"   Channel: #{channel_name}", (rect.x + 20, y), self.small_font)
            y += 20

            self.draw_text(f"   Status: {status_text}", (rect.x + 20, y), self.small_font, status_color)
            y += 20

            if is_playing:
                self.draw_text(f"   ▶️ Playing audio", (rect.x + 20, y), self.small_font, self.SUCCESS_COLOR)
                y += 20

            if queue_size > 0:
                self.draw_text(f"   Queue: {queue_size} sound(s)", (rect.x + 20, y), self.small_font, self.ACCENT_COLOR)
                y += 20

            self.draw_text(f"   Members: {members_count}", (rect.x + 20, y), self.small_font)
            y += 30

    def _draw_sounds_view(self, rect: pygame.Rect):
        """Draw soundboard stats view."""
        self.draw_panel(rect, "Soundboard Statistics")

        if not self.soundboard_data:
            self.draw_text("No soundboard data available",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        y = rect.y + 60

        stats = self.soundboard_data.get("stats", {})
        total_sounds = stats.get("total_sounds", 0)
        total_triggers = stats.get("total_triggers", 0)
        total_plays = stats.get("total_plays", 0)

        self.draw_text(f"Total Sounds: {total_sounds}", (rect.x + 20, y), self.text_font)
        y += 25
        self.draw_text(f"Total Triggers: {total_triggers}", (rect.x + 20, y), self.text_font)
        y += 25
        self.draw_text(f"Total Plays: {total_plays}", (rect.x + 20, y), self.text_font)
        y += 40

        # Top sounds
        top_sounds = self.soundboard_data.get("top_sounds", [])
        if top_sounds:
            self.draw_text("Top Sounds:", (rect.x + 20, y), self.header_font, self.ACCENT_COLOR)
            y += 30

            for i, sound in enumerate(top_sounds[:10], 1):
                sound_name = sound.get("name", "Unknown")
                play_count = sound.get("play_count", 0)
                self.draw_text(f"{i}. {sound_name}: {play_count} plays",
                               (rect.x + 40, y), self.small_font)
                y += 22

    def _draw_errors_view(self, rect: pygame.Rect):
        """Draw errors view."""
        self.draw_panel(rect, "Error Log")

        if not self.error_data or not self.error_data.get("errors"):
            self.draw_text("No errors logged",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.SUCCESS_COLOR)
            return

        y = rect.y + 60

        for error in self.error_data["errors"][-20:]:
            timestamp = error.get("timestamp", "")[:19]
            severity = error.get("severity", "UNKNOWN")
            message = error.get("message", "No message")

            if severity == "CRITICAL":
                color = self.CRITICAL_COLOR
            elif severity == "HIGH":
                color = self.ERROR_COLOR
            elif severity == "MEDIUM":
                color = self.WARNING_COLOR
            else:
                color = self.TEXT_COLOR

            self.draw_text(f"[{timestamp}] {severity}", (rect.x + 20, y), self.small_font, color)
            y += 20
            self.draw_text(f"   {message[:80]}", (rect.x + 20, y), self.tiny_font)
            y += 25

    def _draw_logs_view(self, rect: pygame.Rect):
        """Draw logs view."""
        self.draw_panel(rect, "Recent Logs")

        if not self.log_file.exists():
            self.draw_text("Log file not found",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.WARNING_COLOR)
            return

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()[-50:]

            y = rect.y + 60

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Truncate long lines
                if len(line) > 120:
                    line = line[:120] + "..."

                # Color code by log level
                color = self.TEXT_COLOR
                if "ERROR" in line:
                    color = self.ERROR_COLOR
                elif "WARNING" in line:
                    color = self.WARNING_COLOR
                elif "INFO" in line:
                    color = self.SUCCESS_COLOR

                self.draw_text(line, (rect.x + 20, y), self.tiny_font, color)
                y += 18

                if y > rect.y + rect.height - 30:
                    break

        except Exception as e:
            self.draw_text(f"Error reading logs: {e}",
                           (rect.x + 20, rect.y + 60),
                           self.text_font, self.ERROR_COLOR)

    def _draw_config_view(self, rect: pygame.Rect):
        """Draw config view."""
        self.draw_panel(rect, "Bot Configuration")

        y = rect.y + 60

        config_items = [
            ("Bot Status", "Online" if self.health_data else "Unknown"),
            ("Command Prefix", "~"),
            ("Voice Quality", "High"),
            ("Auto Disconnect", "Enabled"),
            ("Speech Recognition", "Enabled"),
            ("Admin Dashboard", "Enabled"),
        ]

        for label, value in config_items:
            self.draw_text(f"{label}:", (rect.x + 20, y), self.text_font)
            self.draw_text(value, (rect.x + 250, y), self.text_font, self.ACCENT_COLOR)
            y += 30

        y += 20
        self.draw_text("Note: Configuration is read-only in this interface",
                       (rect.x + 20, y), self.small_font, self.WARNING_COLOR)

    def draw_tooltip(self):
        """Draw tooltip if hovering over trigger."""
        if not self.tooltip_text or not self.tooltip_pos:
            return

        lines = self.tooltip_text.split('\n')
        max_width = max(self.small_font.size(line)[0] for line in lines)
        line_height = self.small_font.get_height()

        padding = 10
        tooltip_width = max_width + padding * 2
        tooltip_height = len(lines) * line_height + padding * 2

        x, y = self.tooltip_pos
        x += 15
        y += 15

        if x + tooltip_width > self.width:
            x = self.width - tooltip_width - 10
        if y + tooltip_height > self.height:
            y = self.height - tooltip_height - 10

        tooltip_rect = pygame.Rect(x, y, tooltip_width, tooltip_height)

        pygame.draw.rect(self.screen, (40, 40, 50), tooltip_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.ACCENT_COLOR, tooltip_rect, 2, border_radius=6)

        text_y = y + padding
        for line in lines:
            self.draw_text(line, (x + padding, text_y), self.small_font)
            text_y += line_height

    def handle_input(self) -> bool:
        """Handle pygame events. Returns False to quit."""
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
                if event.button == 1:  # Left click
                    # Check sidebar buttons
                    for view_type, button_rect in self.button_rects.items():
                        if button_rect.collidepoint(event.pos):
                            self.current_view = view_type
                            self.scroll_offset = 0
                            break

                    # Check guild tabs (only in chat view)
                    if self.current_view == ViewType.CHAT:
                        for guild_id, tab_rect in self.guild_tab_rects.items():
                            if tab_rect.collidepoint(event.pos):
                                self.selected_guild = guild_id
                                self.scroll_offset = 0
                                self.auto_scroll = True
                                break

                elif event.button == 4:  # Scroll up
                    if self.current_view in [ViewType.CHAT, ViewType.LOGS]:
                        self.scroll_offset = min(0, self.scroll_offset + 40)
                        if self.current_view == ViewType.CHAT:
                            self.auto_scroll = False

                elif event.button == 5:  # Scroll down
                    if self.current_view in [ViewType.CHAT, ViewType.LOGS]:
                        new_offset = max(-self.max_scroll, self.scroll_offset - 40)
                        self.scroll_offset = new_offset

                        if self.current_view == ViewType.CHAT:
                            if abs(self.scroll_offset - (-self.max_scroll)) < 10:
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

        print("Full Bot Monitor Dashboard with Multi-Guild Support")
        print("===================================================")
        print("Controls:")
        print("  Left Click: Navigate between views / Select guild tabs")
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
            if self.current_view == ViewType.CHAT and self.selected_guild:
                guild_name = self.available_guilds.get(self.selected_guild, "Unknown")
                status_text += f" | Guild: {guild_name}"

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