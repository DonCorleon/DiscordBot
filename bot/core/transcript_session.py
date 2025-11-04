"""
Voice channel transcript session manager.

Tracks voice channel sessions from first user join to bot disconnect,
recording all transcriptions for later AI analysis.
"""

import json
import uuid
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("discordbot.transcript_session")


@dataclass
class Participant:
    """Voice channel participant information (summary - just who was present)."""
    user_id: str
    username: str


@dataclass
class ParticipantEvent:
    """Single participant join/leave event."""
    timestamp: str
    user_id: str
    username: str
    event_type: str  # "join" or "leave"


@dataclass
class TranscriptEntry:
    """Single transcription entry."""
    timestamp: str
    user_id: str
    username: str
    text: str
    confidence: float = 1.0


@dataclass
class TranscriptSession:
    """Voice channel session with transcriptions."""
    session_id: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    start_time: str
    end_time: Optional[str] = None
    participants: List[Participant] = field(default_factory=list)
    participant_events: List[ParticipantEvent] = field(default_factory=list)
    transcript: List[TranscriptEntry] = field(default_factory=list)
    file_path: Optional[str] = None  # Track where file is saved
    _dirty: bool = field(default=False, repr=False)  # Has unflushed changes

    @property
    def stats(self) -> Dict:
        """Calculate session statistics."""
        if not self.end_time:
            return {
                "total_messages": len(self.transcript),
                "duration_seconds": None,
                "unique_speakers": len(self.participants)
            }

        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        duration = (end - start).total_seconds()

        return {
            "total_messages": len(self.transcript),
            "duration_seconds": int(duration),
            "unique_speakers": len(self.participants)
        }

    def to_dict(self) -> Dict:
        """Convert session to dictionary for JSON serialization."""
        data = asdict(self)
        # Remove internal fields
        data.pop('_dirty', None)
        # Add computed stats
        data['stats'] = self.stats
        return data


class TranscriptSessionManager:
    """Manages voice channel transcript sessions with incremental file writing."""

    def __init__(self, bot):
        """Initialize the session manager.

        Args:
            bot: Discord bot instance (for accessing ConfigManager)
        """
        self.bot = bot
        self.active_sessions: Dict[str, TranscriptSession] = {}  # {channel_id: session}
        self._flush_task: Optional[asyncio.Task] = None

        # Get transcript directory from config (will use Voice config)
        # Note: We'll read this dynamically in methods to support hot-reload

        logger.info("TranscriptSessionManager initialized")

    def _get_transcripts_dir(self) -> Path:
        """Get transcripts directory from config."""
        try:
            voice_cfg = self.bot.config_manager.for_guild("Voice", "System")
            return Path(voice_cfg.transcript_dir)
        except:
            # Fallback to default if config not available
            return Path("data/transcripts/sessions")

    def _get_flush_interval(self) -> int:
        """Get flush interval from config."""
        try:
            voice_cfg = self.bot.config_manager.for_guild("Voice", "System")
            return voice_cfg.transcript_flush_interval
        except:
            return 30  # Default fallback

    def start_flush_task(self):
        """Start background task to periodically flush active sessions."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._flush_loop())
            logger.info("Started transcript flush task")

    def stop_flush_task(self):
        """Stop the background flush task."""
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            logger.info("Stopped transcript flush task")

    async def _flush_loop(self):
        """Background loop that periodically flushes dirty sessions."""
        try:
            while True:
                interval = self._get_flush_interval()
                await asyncio.sleep(interval)

                # Flush all dirty sessions
                flushed_count = 0
                for channel_id, session in self.active_sessions.items():
                    if session._dirty:
                        await asyncio.to_thread(self._update_session_file, session)
                        session._dirty = False
                        flushed_count += 1

                if flushed_count > 0:
                    logger.debug(f"Flushed {flushed_count} transcript session(s)")

        except asyncio.CancelledError:
            logger.info("Transcript flush loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in transcript flush loop: {e}", exc_info=True)

    def _create_session_file(self, session: TranscriptSession):
        """
        Create initial session file immediately when session starts.
        Uses nested directory structure: {transcripts_dir}/{guild_id}/{channel_id}/

        Args:
            session: TranscriptSession to create file for
        """
        logger.info(f"_create_session_file called for session {session.session_id}")
        try:
            # Create nested directory structure: guild_id/channel_id/
            base_dir = self._get_transcripts_dir()
            logger.info(f"Base dir: {base_dir}")
            session_dir = base_dir / session.guild_id / session.channel_id
            logger.info(f"Creating session dir: {session_dir}")
            session_dir.mkdir(parents=True, exist_ok=True)

            # Create filename with timestamp and session ID
            start_dt = datetime.fromisoformat(session.start_time)
            filename = f"{start_dt.strftime('%Y%m%d_%H%M%S')}_{session.session_id}.json"
            filepath = session_dir / filename
            logger.info(f"Writing to filepath: {filepath}")

            # Store filepath in session
            session.file_path = str(filepath)

            # Write initial session data
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Created transcript session file: {filepath}")

        except Exception as e:
            logger.error(f"Failed to create transcript session file for {session.session_id}: {e}", exc_info=True)

    def _update_session_file(self, session: TranscriptSession):
        """
        Update existing session file with new data (incremental write).
        Uses atomic write (write to temp file, then rename).

        Args:
            session: TranscriptSession to update
        """
        if not session.file_path:
            logger.warning(f"Cannot update session {session.session_id}: no file_path set")
            return

        try:
            filepath = Path(session.file_path)
            temp_filepath = filepath.with_suffix('.tmp')

            # Write to temp file
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

            # Atomic replace
            temp_filepath.replace(filepath)

            logger.debug(f"Updated transcript session file: {filepath}")

        except Exception as e:
            logger.error(f"Failed to update transcript session file for {session.session_id}: {e}", exc_info=True)

    def resume_or_start_session(
        self,
        channel_id: str,
        guild_id: str,
        guild_name: str,
        channel_name: str,
        first_user_id: str,
        first_username: str,
        existing_session_id: str = None
    ) -> str:
        """
        Resume an existing session or start a new one.

        Args:
            channel_id: Voice channel ID
            guild_id: Guild ID
            guild_name: Guild name
            channel_name: Voice channel name
            first_user_id: ID of first user who joined
            first_username: Username of first user
            existing_session_id: Optional session ID to resume (from voice state)

        Returns:
            session_id: UUID of the resumed or created session
        """
        # Check if session already active in memory
        if channel_id in self.active_sessions:
            logger.info(f"Session already active in memory for channel {channel_id}")
            return self.active_sessions[channel_id].session_id

        # Try to resume existing session from disk
        if existing_session_id:
            try:
                session = self._load_session_from_disk(existing_session_id)
                if session:
                    # Add session to active sessions
                    self.active_sessions[channel_id] = session

                    # Add a resume event
                    now = datetime.utcnow().isoformat()
                    resume_event = ParticipantEvent(
                        timestamp=now,
                        user_id=first_user_id,
                        username=first_username,
                        event_type="bot_resumed"
                    )
                    session.participant_events.append(resume_event)
                    session._dirty = True

                    # Start flush task if not already running
                    self.start_flush_task()

                    logger.info(f"Resumed transcript session {session.session_id} for channel '{channel_name}'")
                    return session.session_id
            except Exception as e:
                logger.error(f"Failed to resume session {existing_session_id}: {e}", exc_info=True)
                # Fall through to create new session

        # Create new session if resume failed or no existing session
        return self.start_session(
            channel_id=channel_id,
            guild_id=guild_id,
            guild_name=guild_name,
            channel_name=channel_name,
            first_user_id=first_user_id,
            first_username=first_username
        )

    def _load_session_from_disk(self, session_id: str) -> Optional[TranscriptSession]:
        """
        Load a session from disk by session ID.

        Args:
            session_id: Session UUID

        Returns:
            TranscriptSession or None if not found
        """
        try:
            base_dir = self._get_transcripts_dir()

            # Search recursively for file containing this session ID
            for filepath in base_dir.glob(f"**/*_{session_id}.json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Convert lists back to dataclass instances
                participants = [Participant(**p) for p in data.get('participants', [])]
                participant_events = [ParticipantEvent(**pe) for pe in data.get('participant_events', [])]
                transcript = [TranscriptEntry(**t) for t in data.get('transcript', [])]

                session = TranscriptSession(
                    session_id=data['session_id'],
                    guild_id=data['guild_id'],
                    guild_name=data['guild_name'],
                    channel_id=data['channel_id'],
                    channel_name=data['channel_name'],
                    start_time=data['start_time'],
                    end_time=data.get('end_time'),
                    participants=participants,
                    participant_events=participant_events,
                    transcript=transcript,
                    file_path=str(filepath)
                )

                logger.info(f"Loaded session {session_id} from disk: {filepath}")
                return session

            logger.warning(f"Session file not found for {session_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to load session {session_id} from disk: {e}", exc_info=True)
            return None

    def start_session(
        self,
        channel_id: str,
        guild_id: str,
        guild_name: str,
        channel_name: str,
        first_user_id: str,
        first_username: str
    ) -> str:
        """
        Start a new transcript session for a voice channel.

        Args:
            channel_id: Voice channel ID
            guild_id: Guild ID
            guild_name: Guild name
            channel_name: Voice channel name
            first_user_id: ID of first user who joined
            first_username: Username of first user

        Returns:
            session_id: UUID of the created session
        """
        # Check if session already exists
        if channel_id in self.active_sessions:
            logger.warning(f"Session already exists for channel {channel_id}")
            return self.active_sessions[channel_id].session_id

        session_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        first_participant = Participant(
            user_id=first_user_id,
            username=first_username
        )

        # Create first participant join event
        first_join_event = ParticipantEvent(
            timestamp=now,
            user_id=first_user_id,
            username=first_username,
            event_type="join"
        )

        session = TranscriptSession(
            session_id=session_id,
            guild_id=guild_id,
            guild_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
            start_time=now,
            participants=[first_participant],
            participant_events=[first_join_event]
        )

        self.active_sessions[channel_id] = session

        # Create session file immediately
        self._create_session_file(session)

        # Start flush task if not already running
        self.start_flush_task()

        logger.info(
            f"Started transcript session {session_id} for channel '{channel_name}' "
            f"in guild '{guild_name}' (first user: {first_username})"
        )

        return session_id

    def add_participant(
        self,
        channel_id: str,
        user_id: str,
        username: str
    ):
        """
        Add a participant join event to the active session.

        Args:
            channel_id: Voice channel ID
            user_id: User ID
            username: Username
        """
        if channel_id not in self.active_sessions:
            logger.warning(f"No active session for channel {channel_id}")
            return

        session = self.active_sessions[channel_id]
        now = datetime.utcnow().isoformat()

        # Add join event to chronological log
        join_event = ParticipantEvent(
            timestamp=now,
            user_id=user_id,
            username=username,
            event_type="join"
        )
        session.participant_events.append(join_event)

        # Check if participant already exists in summary list
        participant_exists = any(p.user_id == user_id for p in session.participants)
        if not participant_exists:
            participant = Participant(
                user_id=user_id,
                username=username
            )
            session.participants.append(participant)

        # Mark session as dirty for next flush
        session._dirty = True
        logger.debug(f"Added participant join event: {username} to session {session.session_id}")

    def remove_participant(
        self,
        channel_id: str,
        user_id: str
    ):
        """
        Add a participant leave event to the active session.

        Args:
            channel_id: Voice channel ID
            user_id: User ID
        """
        if channel_id not in self.active_sessions:
            return

        session = self.active_sessions[channel_id]
        now = datetime.utcnow().isoformat()

        # Find username from participants list
        username = "Unknown"
        for p in session.participants:
            if p.user_id == user_id:
                username = p.username
                break

        # Add leave event to chronological log
        leave_event = ParticipantEvent(
            timestamp=now,
            user_id=user_id,
            username=username,
            event_type="leave"
        )
        session.participant_events.append(leave_event)

        # Mark session as dirty for next flush
        session._dirty = True
        logger.debug(f"Added participant leave event: {username} from session {session.session_id}")

    def add_transcript(
        self,
        channel_id: str,
        user_id: str,
        username: str,
        text: str,
        confidence: float = 1.0
    ):
        """
        Add a transcription to the active session.

        Args:
            channel_id: Voice channel ID
            user_id: User ID
            username: Username
            text: Transcribed text
            confidence: Recognition confidence (0.0-1.0)
        """
        if channel_id not in self.active_sessions:
            logger.warning(f"No active session for channel {channel_id} when adding transcript")
            return

        session = self.active_sessions[channel_id]

        entry = TranscriptEntry(
            timestamp=datetime.utcnow().isoformat(),
            user_id=user_id,
            username=username,
            text=text,
            confidence=confidence
        )

        session.transcript.append(entry)

        # Mark session as dirty for next flush
        session._dirty = True

        logger.debug(f"Added transcript to session {session.session_id}: {username}: {text[:50]}")

    def add_bot_message(
        self,
        channel_id: str,
        bot_id: str,
        bot_name: str,
        message_type: str,
        content: str
    ):
        """
        Add a bot action/message to the transcript.

        Args:
            channel_id: Voice channel ID
            bot_id: Bot user ID
            bot_name: Bot username
            message_type: Type of message (e.g., "TTS", "SOUND", "COMMAND")
            content: Message content
        """
        self.add_transcript(
            channel_id=channel_id,
            user_id=bot_id,
            username=f"{bot_name} [{message_type}]",
            text=content,
            confidence=1.0
        )

    def end_session(self, channel_id: str) -> Optional[str]:
        """
        End a transcript session and save to file.

        Args:
            channel_id: Voice channel ID

        Returns:
            session_id: UUID of the ended session, or None if no session exists
        """
        if channel_id not in self.active_sessions:
            logger.warning(f"No active session to end for channel {channel_id}")
            return None

        session = self.active_sessions[channel_id]
        session.end_time = datetime.utcnow().isoformat()

        # Final flush to ensure all data written
        self._update_session_file(session)

        # Remove from active sessions
        del self.active_sessions[channel_id]

        logger.info(
            f"Ended transcript session {session.session_id} - "
            f"{session.stats['total_messages']} messages, "
            f"{session.stats['duration_seconds']}s duration"
        )

        return session.session_id

    def get_active_session(self, channel_id: str) -> Optional[TranscriptSession]:
        """
        Get the active session for a channel.

        Args:
            channel_id: Voice channel ID

        Returns:
            TranscriptSession or None
        """
        return self.active_sessions.get(channel_id)


    def load_session(self, session_id: str) -> Optional[TranscriptSession]:
        """
        Load a session from file by ID.

        Args:
            session_id: Session UUID

        Returns:
            TranscriptSession or None if not found
        """
        try:
            # Search for file containing this session ID
            for filepath in TRANSCRIPTS_DIR.glob(f"*_{session_id}.json"):
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Convert lists back to dataclass instances
                participants = [Participant(**p) for p in data['participants']]
                transcript = [TranscriptEntry(**t) for t in data['transcript']]

                return TranscriptSession(
                    session_id=data['session_id'],
                    guild_id=data['guild_id'],
                    guild_name=data['guild_name'],
                    channel_id=data['channel_id'],
                    channel_name=data['channel_name'],
                    start_time=data['start_time'],
                    end_time=data.get('end_time'),
                    participants=participants,
                    transcript=transcript
                )

            logger.warning(f"Session {session_id} not found")
            return None

        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}", exc_info=True)
            return None
