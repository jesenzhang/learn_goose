"""
Session Repository

Session data persistence layer.
Reference: goose-rs session persistence patterns (SQLite/JSONL)
"""

import json
import os
import uuid
import time
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from .types import Session

logger = logging.getLogger(__name__)


class SessionRepository:
    """
    Session repository for data persistence.

    Supports JSONL format storage (one session per file or combined JSONL).
    Matches goose-rs session management patterns.
    """

    def __init__(self, storage_dir: str = "./sessions"):
        """
        Initialize repository.

        Args:
            storage_dir: Directory for session storage
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, Dict[str, Any]] = {}
        self._lock: None  # Will be set to asyncio.Lock in async context
        self._load_index()

    def _load_index(self) -> None:
        """Load session index from .index.jsonl"""
        index_file = self.storage_dir / ".index.jsonl"
        if index_file.exists():
            with open(index_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            session_data = json.loads(line)
                            self._index[session_data.get("id", "")] = session_data
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse index line: {line}")
                            continue

    def _save_index(self) -> None:
        """Save session index to .index.jsonl"""
        index_file = self.storage_dir / ".index.jsonl"
        with open(index_file, 'w', encoding='utf-8') as f:
            for session_id, session_data in self._index.items():
                f.write(json.dumps(session_data) + "\n")
                f.flush()
        logger.debug(f"Saved index with {len(self._index)} sessions")

    def _get_session_path(self, session_id: str) -> Path:
        """Get session file path"""
        return self.storage_dir / f"{session_id}.jsonl"

    def create_session(self, session: Session) -> None:
        """
        Create a new session.

        Args:
            session: Session object
        """
        self._index[session.id] = session.to_dict()
        self._save_index()
        logger.info(f"Created session: {session.id}")

    def get_session(self, session_id: str) -> Optional[Session]:
        """
        Get session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session object or None
        """
        session_data = self._index.get(session_id)
        if session_data:
            return Session.from_dict(session_data)
        return None

    def update_session(self, session_id: str, session: Session) -> None:
        """
        Update session data.

        Args:
            session_id: Session ID
            session: Updated session object
        """
        self._index[session_id] = session.to_dict()
        self._save_index()
        logger.info(f"Updated session: {session_id}")

    def delete_session(self, session_id: str) -> bool:
        """
        Delete session by ID.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False otherwise
        """
        if session_id in self._index:
            del self._index[session_id]

            # Delete session file if exists
            session_path = self._get_session_path(session_id)
            if session_path.exists():
                session_path.unlink()

            self._save_index()
            logger.info(f"Deleted session: {session_id}")
            return True
        return False

    def list_sessions(self, limit: int = 20, offset: int = 0) -> List[Session]:
        """
        List all sessions with pagination.

        Args:
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of Session objects
        """
        session_ids = sorted(self._index.keys())
        sessions = [Session.from_dict(self._index[sid]) for sid in session_ids[offset:offset + limit]]
        return sessions

    def add_message(self, session_id: str, message: Any) -> None:
        """
        Add message to session.

        Args:
            session_id: Session ID
            message: Message object
        """
        session = self.get_session(session_id)
        if session:
            session.message_count += 1
            session.updated_at = time.time()
            self.update_session(session_id, session)
            logger.info(f"Added message to session {session_id}")

    def get_messages(self, session_id: str, limit: int = 100) -> List[Any]:
        """
        Get messages for a session.

        Args:
            session_id: Session ID
            limit: Maximum number of messages

        Returns:
            List of messages
        """
        # Messages will be stored in separate message files
        # This is a placeholder - will need integration with conversation module
        return []

    def search_messages(self, query: str, limit: int = 10) -> List[Any]:
        """
        Search messages across all sessions.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching messages
        """
        # This is a placeholder - will need full-text search implementation
        return []
