"""
Voice channel transcript session manager.

Tracks voice channel sessions from first user join to bot disconnect,
recording all transcriptions for later AI analysis.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger("discordbot.transcript_session")

TRANSCRIPTS_DIR = Path("data/transcripts/sessions")


@dataclass
class Participant:
    """Voice channel participant information."""
    user_id: str
    username: str
    join_time: str
    leave_time: Optional[str] = None


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
    transcript: List[TranscriptEntry] = field(default_factory=list)

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
        data['stats'] = self.stats
        return data


class TranscriptSessionManager:
    """Manages voice channel transcript sessions."""

    def __init__(self):
        """Initialize the session manager."""
        self.active_sessions: Dict[str, TranscriptSession] = {}  # {channel_id: session}

        # Ensure transcripts directory exists
        TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("TranscriptSessionManager initialized")

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
            username=first_username,
            join_time=now
        )

        session = TranscriptSession(
            session_id=session_id,
            guild_id=guild_id,
            guild_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
            start_time=now,
            participants=[first_participant]
        )

        self.active_sessions[channel_id] = session

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
        Add a participant to the active session.

        Args:
            channel_id: Voice channel ID
            user_id: User ID
            username: Username
        """
        if channel_id not in self.active_sessions:
            logger.warning(f"No active session for channel {channel_id}")
            return

        session = self.active_sessions[channel_id]

        # Check if participant already exists
        for p in session.participants:
            if p.user_id == user_id:
                return  # Already in session

        participant = Participant(
            user_id=user_id,
            username=username,
            join_time=datetime.utcnow().isoformat()
        )

        session.participants.append(participant)
        logger.debug(f"Added participant {username} to session {session.session_id}")

    def remove_participant(
        self,
        channel_id: str,
        user_id: str
    ):
        """
        Mark a participant as left.

        Args:
            channel_id: Voice channel ID
            user_id: User ID
        """
        if channel_id not in self.active_sessions:
            return

        session = self.active_sessions[channel_id]

        for participant in session.participants:
            if participant.user_id == user_id and participant.leave_time is None:
                participant.leave_time = datetime.utcnow().isoformat()
                logger.debug(f"Marked participant {participant.username} as left")
                break

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
        logger.debug(f"Added transcript to session {session.session_id}: {username}: {text[:50]}")

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

        # Save to file
        self._save_session(session)

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

    def _save_session(self, session: TranscriptSession):
        """
        Save session to JSON file.

        Args:
            session: TranscriptSession to save
        """
        try:
            # Create filename with timestamp and session ID
            start_dt = datetime.fromisoformat(session.start_time)
            filename = f"{start_dt.strftime('%Y%m%d_%H%M%S')}_{session.session_id}.json"
            filepath = TRANSCRIPTS_DIR / filename

            # Save to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Saved transcript session to {filepath}")

        except Exception as e:
            logger.error(f"Failed to save transcript session {session.session_id}: {e}", exc_info=True)

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
