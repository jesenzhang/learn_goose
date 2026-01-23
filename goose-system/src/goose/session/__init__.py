"""
Session Module

Session state management with persistence support.
Reference: goose-rs session module

Features:
- SessionConfig: Session configuration (id, max_turns, retry_config)
- SessionState: Session state with provider/model config, extension state
- SessionManager: Session lifecycle management with persistence
- SessionType: User/SubAgent/Scheduler session types
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
import uuid
import asyncio
import json
import os
from datetime import datetime


class SessionType(str, Enum):
    """Session type for tracking origin and behavior"""
    USER = "user"
    SUBAGENT = "subagent"
    SCHEDULER = "scheduler"


@dataclass
class ModelConfig:
    """Model configuration for LLM provider"""
    model_name: str = "gpt-4"
    context_limit: int = 128000
    max_output_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_name": self.model_name,
            "context_limit": self.context_limit,
            "max_output_tokens": self.max_output_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelConfig":
        return cls(
            model_name=data.get("model_name", "gpt-4"),
            context_limit=data.get("context_limit", 128000),
            max_output_tokens=data.get("max_output_tokens", 4096),
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 1.0)
        )


@dataclass
class SessionConfig:
    """Session configuration"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    schedule_id: Optional[str] = None
    max_turns: Optional[int] = None
    retry_config: Optional[Dict[str, Any]] = None
    session_type: SessionType = SessionType.USER

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "schedule_id": self.schedule_id,
            "max_turns": self.max_turns,
            "retry_config": self.retry_config,
            "session_type": self.session_type.value if isinstance(self.session_type, SessionType) else self.session_type
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionConfig":
        session_type = data.get("session_type", "user")
        if isinstance(session_type, str):
            session_type = SessionType(session_type)
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            schedule_id=data.get("schedule_id"),
            max_turns=data.get("max_turns"),
            retry_config=data.get("retry_config"),
            session_type=session_type
        )


@dataclass
class ExtensionState:
    """State of a single extension"""
    name: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    tool_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "config": self.config,
            "tool_count": self.tool_count
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtensionState":
        return cls(
            name=data.get("name", ""),
            enabled=data.get("enabled", True),
            config=data.get("config", {}),
            tool_count=data.get("tool_count", 0)
        )


@dataclass
class EnabledExtensionsState:
    """State of all enabled extensions"""
    extensions: List[ExtensionState] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "extensions": [ext.to_dict() for ext in self.extensions]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Optional["EnabledExtensionsState"]:
        if not data:
            return None
        extensions = [ExtensionState.from_dict(ext) for ext in data.get("extensions", [])]
        return cls(extensions=extensions)

    def to_extension_data(self) -> Dict[str, Any]:
        """Convert to extension data format for storage"""
        return self.to_dict()

    @staticmethod
    def from_extension_data(data: Dict[str, Any]) -> Optional["EnabledExtensionsState"]:
        """Create from extension data format"""
        return EnabledExtensionsState.from_dict(data)


@dataclass
class SessionData:
    """Complete session data for persistence"""
    id: str
    session_type: str = "user"
    provider_name: Optional[str] = None
    model_config: Optional[Dict[str, Any]] = None
    extension_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_type": self.session_type,
            "provider_name": self.provider_name,
            "model_config": self.model_config,
            "extension_data": self.extension_data,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionData":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            session_type=data.get("session_type", "user"),
            provider_name=data.get("provider_name"),
            model_config=data.get("model_config"),
            extension_data=data.get("extension_data", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            metadata=data.get("metadata", {})
        )


class SessionUpdater:
    """Helper for batch session updates"""

    def __init__(self, manager: "SessionManager", session_id: str):
        self._manager = manager
        self._session_id = session_id
        self._updates: Dict[str, Any] = {}
        self._applied = False

    def provider_name(self, name: str) -> "SessionUpdater":
        """Update provider name"""
        self._updates["provider_name"] = name
        return self

    def model_config(self, config: ModelConfig) -> "SessionUpdater":
        """Update model configuration"""
        self._updates["model_config"] = config.to_dict()
        return self

    def extension_data(self, data: Dict[str, Any]) -> "SessionUpdater":
        """Update extension data"""
        self._updates["extension_data"] = data
        return self

    def metadata(self, key: str, value: Any) -> "SessionUpdater":
        """Update metadata field"""
        if "metadata" not in self._updates:
            self._updates["metadata"] = {}
        self._updates["metadata"][key] = value
        return self

    async def apply(self) -> bool:
        """
        Apply all updates to the session.

        Returns:
            True if successful
        """
        if self._applied:
            return False

        session = await self._manager.get_session(self._session_id, create_if_not_exists=False)
        if session is None:
            return False

        async with self._manager._lock:
            for key, value in self._updates.items():
                setattr(session, key, value)
            session.updated_at = datetime.now().isoformat()
            self._manager._save_sessions()
            self._applied = True
            return True


class SessionManager:
    """
    Session manager with persistence support.

    Features:
    - Session creation and retrieval
    - Provider/model configuration persistence
    - Extension state storage
    - Message history management
    """

    _instance: Optional["SessionManager"] = None

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize session manager.

        Args:
            storage_path: Optional path to JSON file for persistence
        """
        self.storage_path = storage_path
        self._sessions: Dict[str, SessionData] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

        if storage_path and os.path.exists(storage_path):
            self._load_sessions()

    @classmethod
    def get_instance(cls, storage_path: Optional[str] = None) -> "SessionManager":
        """Get or create the singleton instance"""
        if cls._instance is None:
            cls._instance = cls(storage_path)
        return cls._instance

    async def initialize(self) -> None:
        """Initialize the session manager"""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            if self.storage_path and os.path.exists(self.storage_path):
                self._load_sessions()

            self._initialized = True

    def _load_sessions(self) -> None:
        """Load sessions from storage"""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for session_dict in data.get("sessions", []):
                    session = SessionData.from_dict(session_dict)
                    self._sessions[session.id] = session
        except Exception:
            pass

    def _save_sessions(self) -> None:
        """Save sessions to storage"""
        if not self.storage_path:
            return

        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = {
                "sessions": [session.to_dict() for session in self._sessions.values()],
                "updated_at": datetime.now().isoformat()
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    async def create_session(
        self,
        session_type: SessionType = SessionType.USER,
        provider_name: Optional[str] = None,
        model_config: Optional[ModelConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        working_dir: Optional[str] = None,
        name: Optional[str] = None
    ) -> SessionData:
        """
        Create a new session.

        Args:
            session_type: Type of session (user/subagent/scheduler)
            provider_name: Name of the LLM provider
            model_config: Model configuration
            metadata: Optional metadata
            working_dir: Working directory for the session
            name: Session name

        Returns:
            Created session data
        """
        async with self._lock:
            session_metadata = metadata or {}
            if working_dir:
                session_metadata["working_dir"] = working_dir
            if name:
                session_metadata["name"] = name

            session = SessionData(
                id=str(uuid.uuid4()),
                session_type=session_type.value if isinstance(session_type, SessionType) else session_type,
                provider_name=provider_name,
                model_config=model_config.to_dict() if model_config else None,
                metadata=session_metadata
            )
            self._sessions[session.id] = session
            self._save_sessions()
            return session

    async def get_session(self, session_id: str, create_if_not_exists: bool = True, include_messages: bool = True) -> Optional[SessionData]:
        """
        Get a session by ID.

        Args:
            session_id: Session ID
            create_if_not_exists: Create session if it doesn't exist
            include_messages: Include messages in the response

        Returns:
            Session data or None
        """
        await self.initialize()

        if session_id in self._sessions:
            return self._sessions[session_id]

        if create_if_not_exists:
            return await self.create_session()

        return None

    async def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """
        Add a message to session history.

        Args:
            session_id: Session ID
            message: Message data

        Returns:
            True if successful
        """
        await self.initialize()

        session = await self.get_session(session_id, create_if_not_exists=False)
        if session is None:
            return False

        if "messages" not in session.metadata:
            session.metadata["messages"] = []

        session.metadata["messages"].append(message)
        session.updated_at = datetime.now().isoformat()
        self._save_sessions()
        return True

    async def update(
        self,
        session_id: str
    ) -> SessionUpdater:
        """
        Get a session updater for batch updates.

        Args:
            session_id: Session ID

        Returns:
            SessionUpdater for chaining updates
        """
        await self.initialize()
        return SessionUpdater(self, session_id)

    async def list_sessions(self) -> List[SessionData]:
        """List all sessions"""
        await self.initialize()
        return list(self._sessions.values())

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted
        """
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                self._save_sessions()
                return True
            return False


class InMemorySessionManager:
    """Simple in-memory session manager for testing"""

    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = asyncio.Lock()

    async def create_session(
        self,
        session_type: SessionType = SessionType.USER,
        provider_name: Optional[str] = None,
        model_config: Optional[ModelConfig] = None
    ) -> SessionData:
        async with self._lock:
            session = SessionData(
                id=str(uuid.uuid4()),
                session_type=session_type.value if isinstance(session_type, SessionType) else session_type,
                provider_name=provider_name,
                model_config=model_config.to_dict() if model_config else None
            )
            self._sessions[session.id] = session
            return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def update(
        self,
        session_id: str
    ) -> SessionUpdater:
        return SessionUpdater(self, session_id)

    async def list_sessions(self) -> List[SessionData]:
        async with self._lock:
            return list(self._sessions.values())

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False


__all__ = [
    "SessionType",
    "ModelConfig",
    "SessionConfig",
    "ExtensionState",
    "EnabledExtensionsState",
    "SessionData",
    "Session",
    "SessionManager",
    "SessionUpdater",
    "InMemorySessionManager",
]

Session = SessionData
