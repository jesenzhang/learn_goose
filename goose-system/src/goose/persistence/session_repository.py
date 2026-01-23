"""
Session Persistence

Session storage implementation using the persistence layer.
Integrates SessionManager with PersistenceBackend.
"""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict
import uuid

from .repository import BaseRepository, with_table
from .spec import TableSpec, FieldSpec
from .manager import get_persistence

logger = logging.getLogger("goose.session.persistence")


@dataclass
class PersistedSession:
    """Session data for persistence storage."""
    session_id: str
    user_id: Optional[str] = None
    system_prompt: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: str = "{}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersistedSession":
        return cls(**data)


@dataclass
class PersistedMessage:
    """Message data for persistence storage."""
    id: str
    session_id: str
    role: str
    content: str
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: str = "{}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersistedMessage":
        return cls(**data)


SESSION_TABLE = TableSpec(
    name="sessions",
    fields=[
        FieldSpec(name="session_id", type="TEXT", primary_key=True),
        FieldSpec(name="user_id", type="TEXT"),
        FieldSpec(name="system_prompt", type="TEXT"),
        FieldSpec(name="created_at", type="TEXT"),
        FieldSpec(name="updated_at", type="TEXT"),
        FieldSpec(name="metadata", type="TEXT"),
    ],
    description="Session storage"
)

MESSAGES_TABLE = TableSpec(
    name="messages",
    fields=[
        FieldSpec(name="id", type="TEXT", primary_key=True),
        FieldSpec(name="session_id", type="TEXT", index=True),
        FieldSpec(name="role", type="TEXT"),
        FieldSpec(name="content", type="TEXT"),
        FieldSpec(name="created_at", type="TEXT"),
        FieldSpec(name="metadata", type="TEXT"),
    ],
    description="Message storage"
)


class SessionRepository(BaseRepository):
    """Repository for session persistence."""
    
    TABLE_NAME = "sessions"
    SCHEMA = SESSION_TABLE
    
    @classmethod
    async def create_session(
        cls,
        session_id: str,
        user_id: Optional[str] = None,
        system_prompt: str = ""
    ) -> PersistedSession:
        """Create a new session."""
        session = PersistedSession(
            session_id=session_id,
            user_id=user_id,
            system_prompt=system_prompt
        )
        
        pm = get_persistence()
        await pm.backend.insert(cls.TABLE_NAME, session.to_dict())
        
        logger.info(f"Created session: {session_id}")
        return session
    
    @classmethod
    async def get_session(cls, session_id: str) -> Optional[PersistedSession]:
        """Get a session by ID."""
        pm = get_persistence()
        data = await pm.backend.get(cls.TABLE_NAME, session_id)
        
        if data:
            return PersistedSession.from_dict(data)
        return None
    
    @classmethod
    async def update_session(
        cls,
        session_id: str,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update session."""
        pm = get_persistence()
        
        updates = {"updated_at": datetime.now().isoformat()}
        if system_prompt is not None:
            updates["system_prompt"] = system_prompt
        if metadata is not None:
            updates["metadata"] = json.dumps(metadata)
        
        return await pm.backend.update(cls.TABLE_NAME, session_id, updates)
    
    @classmethod
    async def delete_session(cls, session_id: str) -> bool:
        """Delete a session and its messages."""
        pm = get_persistence()
        
        deleted = await pm.backend.delete(cls.TABLE_NAME, session_id)
        
        if deleted:
            await MessageRepository.delete_session_messages(session_id)
            logger.info(f"Deleted session: {session_id}")
        
        return deleted
    
    @classmethod
    async def list_sessions(
        cls,
        user_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersistedSession]:
        """List sessions."""
        pm = get_persistence()
        
        where = {}
        if user_id:
            where["user_id"] = user_id
        
        results = await pm.backend.query(
            cls.TABLE_NAME,
            where=where,
            limit=limit,
            offset=offset,
            order_by="updated_at",
            order_desc=True
        )
        
        return [PersistedSession.from_dict(r) for r in results]


class MessageRepository(BaseRepository):
    """Repository for message persistence."""
    
    TABLE_NAME = "messages"
    SCHEMA = MESSAGES_TABLE
    
    @classmethod
    async def add_message(
        cls,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> PersistedMessage:
        """Add a message to a session."""
        message = PersistedMessage(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            metadata=json.dumps(metadata or {})
        )
        
        pm = get_persistence()
        await pm.backend.insert(cls.TABLE_NAME, message.to_dict())
        
        return message
    
    @classmethod
    async def get_messages(
        cls,
        session_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[PersistedMessage]:
        """Get messages for a session."""
        pm = get_persistence()
        
        results = await pm.backend.query(
            cls.TABLE_NAME,
            where={"session_id": session_id},
            limit=limit,
            offset=offset,
            order_by="created_at",
            order_desc=False
        )
        
        return [PersistedMessage.from_dict(r) for r in results]
    
    @classmethod
    async def delete_session_messages(cls, session_id: str) -> int:
        """Delete all messages for a session."""
        pm = get_persistence()
        return await pm.backend.delete_where(cls.TABLE_NAME, {"session_id": session_id})
    
    @classmethod
    async def count_messages(cls, session_id: str) -> int:
        """Count messages in a session."""
        pm = get_persistence()
        results = await pm.backend.query(
            cls.TABLE_NAME,
            where={"session_id": session_id},
            limit=10000
        )
        return len(results)


class ConversationRepository:
    """Repository for conversation persistence."""
    
    @classmethod
    async def save_conversation(
        cls,
        session_id: str,
        messages: List[Dict[str, Any]]
    ) -> int:
        """Save a conversation (list of messages) to a session."""
        count = 0
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            message_id = msg.get("id", str(uuid.uuid4()))
            
            await MessageRepository.add_message(
                session_id=session_id,
                message_id=message_id,
                role=role,
                content=content
            )
            count += 1
        
        return count
    
    @classmethod
    async def load_conversation(
        cls,
        session_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Load a conversation from a session."""
        messages = await MessageRepository.get_messages(session_id, limit=limit)
        
        return [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            }
            for msg in messages
        ]
    
    @classmethod
    async def search_messages(
        cls,
        session_id: Optional[str] = None,
        query: Optional[str] = None,
        role: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Search messages across sessions."""
        pm = get_persistence()
        
        where: Dict[str, Any] = {}
        if session_id:
            where["session_id"] = session_id
        if role:
            where["role"] = role
        
        results = await pm.backend.query(
            MessageRepository.TABLE_NAME,
            where=where if where else None,
            limit=limit,
            order_by="created_at",
            order_desc=True
        )
        
        if query:
            results = [
                r for r in results
                if query.lower() in r.get("content", "").lower()
            ]
        
        return results


async def init_session_persistence(db_url: str = "file://./sessions") -> None:
    """
    Initialize session persistence.
    
    Args:
        db_url: Database URL (file://./path, sqlite://, postgresql://, etc.)
    """
    pm = init_persistence(db_url)
    await pm.boot()
    
    BaseRepository.register(SessionRepository)
    BaseRepository.register(MessageRepository)
    
    logger.info(f"Session persistence initialized: {db_url}")


async def save_session(
    session_id: str,
    system_prompt: str,
    messages: List[Dict[str, Any]],
    user_id: Optional[str] = None
) -> None:
    """Save a complete session with messages."""
    session = await SessionRepository.create_session(
        session_id=session_id,
        user_id=user_id,
        system_prompt=system_prompt
    )
    
    await ConversationRepository.save_conversation(session_id, messages)
    
    logger.info(f"Saved session {session_id} with {len(messages)} messages")


async def load_session(
    session_id: str,
    include_messages: bool = True
) -> Optional[Dict[str, Any]]:
    """Load a complete session with messages."""
    session = await SessionRepository.get_session(session_id)
    
    if not session:
        return None
    
    result = {
        "session_id": session.session_id,
        "user_id": session.user_id,
        "system_prompt": session.system_prompt,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "metadata": json.loads(session.metadata or "{}"),
    }
    
    if include_messages:
        result["messages"] = await ConversationRepository.load_conversation(session_id)
    
    return result


async def list_user_sessions(
    user_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """List all sessions for a user."""
    sessions = await SessionRepository.list_sessions(user_id=user_id, limit=limit)
    
    return [
        {
            "session_id": s.session_id,
            "system_prompt": s.system_prompt[:100] if s.system_prompt else "",
            "created_at": s.created_at,
            "updated_at": s.updated_at,
            "message_count": await MessageRepository.count_messages(s.session_id)
        }
        for s in sessions
    ]
