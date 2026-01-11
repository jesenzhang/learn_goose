import logging
import json
import datetime
import uuid
import time
from typing import List, Optional, Any, Dict

from ..conversation import Message, Conversation
from .types import Session, SessionType
from .extension_data import ExtensionData
from .repository import SessionRepository
from ..providers import ModelConfig

logger = logging.getLogger(__name__)

class SessionManager:
    """
    业务层 Session 管理器。
    负责协调 Repository 进行数据存取，并进行对象封装（Dict <-> Pydantic）。
    """
    _repo: Optional[SessionRepository] = None

    @classmethod
    async def get_repo(cls) -> SessionRepository:
        if cls._repo is None:
            cls._repo = SessionRepository()
        return cls._repo

    @classmethod
    async def shutdown(cls):
        cls._repo = None

    @classmethod
    async def create_session(
        cls, 
        working_dir: str = ".", 
        name: str = "New Session",
        session_type: SessionType = SessionType.USER, # [修改] 支持指定类型
        metadata: Dict[str, Any] = None,
        session_id: str = None  # [新增参数] 允许外部指定 ID
    ) -> Session:
        """
        通用会话创建方法。
        """
        repo = await cls.get_repo()
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            
        now_str =time.time()
        
        # 合并默认 metadata
        final_metadata = metadata or {}
        
        # 1. 创建内存对象
        session = Session(
            id=session_id,
            name=name,
            session_type=session_type, # 使用传入的类型
            working_dir=working_dir,
            created_at=now_str,
            updated_at=now_str,
            metadata=final_metadata
        )
         
        
        # 3. 持久化
        await repo.create_session(session)
        
        return session

    @classmethod
    async def create_workflow_session(cls, working_dir: str = ".", name: str = "Workflow Run") -> Session:
        """
        [新增] 专门用于创建工作流会话的快捷方法。
        """
        return await cls.create_session(
            working_dir=working_dir,
            name=name,
            session_type=SessionType.WORKFLOW
        )
        
    @classmethod
    async def get_session(cls, session_id: str) -> Session:
        repo = await cls.get_repo()
        data = await repo.get_session(session_id)
        if not data:
            raise ValueError(f"Session {session_id} not found")
        return data

    @classmethod
    async def list_sessions(cls, limit: int = 20, offset: int = 0) -> List[Session]:
        repo = await cls.get_repo()
        data_list = await repo.list_sessions(limit, offset)
        return data_list

    @classmethod
    async def delete_session(cls, session_id: str):
        repo = await cls.get_repo()
        await repo.delete_session(session_id)

    @classmethod
    async def add_message(cls, session_id: str, message: Message):
        repo = await cls.get_repo()
        await repo.add_message(session_id, message)

    @classmethod
    async def get_messages(cls, session_id: str) -> List[Message]:
        repo = await cls.get_repo()
        return await repo.get_messages(session_id)

    @classmethod
    async def get_conversation(cls, session_id: str) -> Conversation:
        msgs = await cls.get_messages(session_id)
        return Conversation(messages=msgs)

    @classmethod
    async def search_history(cls, query: str, limit: int = 10) -> List[Message]:
        repo = await cls.get_repo()
        rows:List[Message] = await repo.search_messages(query, limit)
        return rows

    @classmethod
    async def update_extension_state(cls, session_id: str, ext_name: str, state: Any):
        """
        更新扩展状态。
        流程：Load -> Modify Object -> Serialize -> Save
        """
        repo = await cls.get_repo()
        session = await cls.get_session(session_id)
        session.extension_data.data[ext_name] = state
        await repo.update_session(session_id, extension_data=session.extension_data)
