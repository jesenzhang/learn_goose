"""
Session Manager

业务层 Session 管理器。
负责协调 Repository 进行数据存取，并进行对象封装（Dict <-> Pydantic）。

Reference: goose-rs session 模块
"""

import logging
import time
import uuid
from typing import List, Optional, Dict, Any

from ..conversation import Message, Conversation
from .types import Session, SessionType, ExtensionData
from .repository import SessionRepository

logger = logging.getLogger(__name__)


class SessionManager:
    """
    业务层 Session 管理器。

    负责：
    - 创建和管理会话
    - 消息管理
    - 扩展状态管理
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize SessionManager with optional storage path.

        Args:
            storage_path: Directory for session storage (optional)
        """
        self._repo: Optional[SessionRepository] = None
        self._storage_path = storage_path

    @classmethod
    def _get_class_repo(cls) -> SessionRepository:
        """Get class-level repository instance"""
        if cls._class_repo is None:
            cls._class_repo = SessionRepository()
        return cls._class_repo

    # Class-level repository for classmethod usage
    _class_repo: Optional[SessionRepository] = None

    def get_repo(self) -> SessionRepository:
        """Get repository instance (instance or class-level)"""
        if self._repo is None:
            if self._storage_path:
                self._repo = SessionRepository(storage_dir=self._storage_path)
            else:
                self._repo = SessionRepository()
        return self._repo

    async def initialize(self):
        """Initialize the session manager"""
        logger.info(f"SessionManager initialized with storage_path: {self._storage_path}")

    async def close_all(self):
        """Close all sessions and cleanup resources"""
        if self._repo:
            self._repo = None
        logger.info("SessionManager closed")

    @classmethod
    def shutdown(cls):
        """Cleanup class-level resources"""
        cls._class_repo = None

    def create_session(
        self,
        working_dir: str = ".",
        name: str = "New Session",
        session_type: SessionType = SessionType.USER,
        metadata: Dict[str, Any] = None,
        session_id: str = None,
    ) -> Session:
        """
        通用会话创建方法。
        """
        repo = self.get_repo()
        if not session_id:
            session_id = str(uuid.uuid4())

        now = time.time()

        # 合并默认 metadata
        final_metadata = metadata or {}

        # 1. 创建内存对象
        session = Session(
            id=session_id,
            name=name,
            session_type=session_type,
            working_dir=working_dir,
            created_at=now,
            updated_at=now,
            metadata=final_metadata
        )

        # 2. 持久化
        repo.create_session(session)

        return session

    def create_workflow_session(self, working_dir: str = ".", name: str = "Workflow Run") -> Session:
        """
        专门用于创建工作流会话的快捷方法。
        """
        return self.create_session(
            working_dir=working_dir,
            name=name,
            session_type=SessionType.WORKFLOW
        )

    def get_session(self, session_id: str) -> Session:
        repo = self.get_repo()
        data = repo.get_session(session_id)
        if not data:
            raise ValueError(f"Session {session_id} not found")
        return data

    def list_sessions(self, limit: int = 20, offset: int = 0) -> List[Session]:
        repo = self.get_repo()
        data_list = repo.list_sessions(limit, offset)
        return data_list

    def delete_session(self, session_id: str):
        repo = self.get_repo()
        repo.delete_session(session_id)

    def add_message(self, session_id: str, message: Message):
        repo = self.get_repo()
        repo.add_message(session_id, message)

    def get_messages(self, session_id: str) -> List[Message]:
        repo = self.get_repo()
        return repo.get_messages(session_id)

    def get_conversation(self, session_id: str) -> Conversation:
        msgs = self.get_messages(session_id)
        return Conversation(messages=msgs)

    def search_history(self, query: str, limit: int = 10) -> List[Message]:
        repo = self.get_repo()
        rows = repo.search_messages(query, limit)
        return rows

    def update_extension_state(self, session_id: str, ext_name: str, version: str, state: Any):
        """
        更新扩展状态。
        流程：Load -> Modify Object -> Serialize -> Save
        """
        repo = self.get_repo()
        session = self.get_session(session_id)
        session.extension_data.set_extension_state(ext_name, version, state)
        session.updated_at = time.time()
        repo.update_session(session_id, session)
