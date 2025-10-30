"""
Vosk speech recognition engine.

Fast, local speech recognition using voice_recv library's built-in Vosk integration.
Best for low-latency real-time applications.
"""

import json
import discord
from discord.ext import voice_recv
from discord.ext.voice_recv.extras import speechrecognition as dsr
from typing import Optional
from .base import SpeechEngine, logger


class VoskEngine(SpeechEngine):
    """
    Vosk-based speech recognition engine.

    Uses voice_recv's SpeechRecognitionSink with Vosk backend.
    Provides fast, local speech recognition with minimal latency.
    """

    def __init__(
        self,
        bot,
        callback,
        phrase_time_limit: int = 10,
        error_log_threshold: int = 10,
        ducking_callback=None
    ):
        """
        Initialize Vosk engine.

        Args:
            bot: Discord bot instance
            callback: Function called with (member, transcribed_text)
            phrase_time_limit: Max seconds of speech to process
            error_log_threshold: Number of errors before logging warning
            ducking_callback: Optional (guild_id, member, is_speaking) callback for audio ducking
        """
        super().__init__(bot, callback)
        self.phrase_time_limit = phrase_time_limit
        self.error_log_threshold = error_log_threshold
        self.ducking_callback = ducking_callback
        self.sink = None
        self.guild_id = None

    async def start_listening(self, voice_client):
        """Start Vosk speech recognition."""
        self.guild_id = voice_client.guild.id

        def text_callback(user: discord.User, text: str):
            """Process Vosk JSON output and extract transcribed text."""
            try:
                result = json.loads(text)
                transcribed_text = result.get("text", "").strip()

                if not transcribed_text:
                    return

                # Get member object for more context
                member = voice_client.guild.get_member(user.id)
                if not member:
                    return

                # Invoke parent callback with clean text
                self._invoke_callback(member, transcribed_text)

            except json.JSONDecodeError as e:
                logger.warning(f"[Guild {self.guild_id}] Failed to parse Vosk JSON: {e}")
            except Exception as e:
                logger.error(f"[Guild {self.guild_id}] Error in Vosk text_callback: {e}", exc_info=True)

        # Create custom sink with error handling and ducking support
        self.sink = VoskSink(
            self.guild_id,
            text_callback,
            self.phrase_time_limit,
            self.error_log_threshold,
            self.ducking_callback
        )

        # Attach to voice client
        voice_client.listen(self.sink)
        self._is_listening = True

        logger.info(f"[Guild {self.guild_id}] Started Vosk speech recognition")
        return self.sink

    async def stop_listening(self):
        """Stop Vosk speech recognition."""
        if self.sink:
            # voice_recv handles cleanup automatically when voice client disconnects
            self.sink = None
        self._is_listening = False
        logger.info(f"[Guild {self.guild_id}] Stopped Vosk speech recognition")

    def get_sink(self) -> Optional[dsr.SpeechRecognitionSink]:
        """Get the Vosk sink instance."""
        return self.sink


class VoskSink(dsr.SpeechRecognitionSink):
    """
    Custom Vosk sink with error handling and ducking support.

    Extends voice_recv's SpeechRecognitionSink to add:
    - Graceful error handling for corrupted audio
    - Audio ducking integration via callbacks
    - Error count tracking to prevent log spam
    """

    def __init__(
        self,
        guild_id: int,
        text_callback,
        phrase_time_limit: int,
        error_log_threshold: int,
        ducking_callback=None
    ):
        super().__init__(
            default_recognizer="vosk",
            phrase_time_limit=phrase_time_limit,
            text_cb=text_callback
        )
        self.guild_id = guild_id
        self.ducking_callback = ducking_callback
        self.error_count = 0
        self.max_errors = error_log_threshold
        self.error_log_interval = error_log_threshold

    def write(self, user, data):
        """Override write to add error handling for corrupted audio data."""
        try:
            super().write(user, data)
            # Reset error count on successful write
            self.error_count = 0
        except Exception as e:
            self.error_count += 1

            # Log first error and every Nth error to avoid spam
            if self.error_count == 1 or self.error_count % self.error_log_interval == 0:
                logger.warning(
                    f"[Guild {self.guild_id}] Audio write error (count: {self.error_count}): {type(e).__name__}"
                )

            # If too many consecutive errors, log warning
            if self.error_count >= self.max_errors:
                logger.error(
                    f"[Guild {self.guild_id}] Excessive audio errors ({self.error_count}). "
                    "Voice connection may be unstable."
                )
                # Reset counter to avoid spam
                self.error_count = 0

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_start(self, member: discord.Member):
        """Handle member starting to speak - notify ducking callback."""
        try:
            logger.debug(f"[Guild {self.guild_id}] 🎤 {member.display_name} started speaking")
            if self.ducking_callback:
                self.ducking_callback(self.guild_id, member, is_speaking=True)
        except Exception as e:
            logger.error(f"[Guild {self.guild_id}] Error in speaking_start: {e}", exc_info=True)

    @voice_recv.AudioSink.listener()
    def on_voice_member_speaking_stop(self, member: discord.Member):
        """Handle member stopping speaking - notify ducking callback."""
        try:
            logger.debug(f"[Guild {self.guild_id}] 🔇 {member.display_name} stopped speaking")
            if self.ducking_callback:
                self.ducking_callback(self.guild_id, member, is_speaking=False)
        except Exception as e:
            logger.error(f"[Guild {self.guild_id}] Error in speaking_stop: {e}", exc_info=True)
