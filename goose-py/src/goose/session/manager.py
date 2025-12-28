import logging
from typing import List, Optional, Any
from ..conversation import Message, Conversation
from .types import Session, SessionType
from .storage import SessionStorage
from .chat_history_search import ChatHistorySearch
from .diagnostics import generate_diagnostics

logger = logging.getLogger(__name__)

class SessionManager:
    _storage: Optional[SessionStorage] = None

    @classmethod
    async def get_storage(cls) -> SessionStorage:
        """单例获取存储"""
        if cls._storage is None:
            # 确保目录存在等初始化工作在 create 中完成
            cls._storage = await SessionStorage.create()
        return cls._storage

    @classmethod
    async def shutdown(cls):
        if cls._storage:
            await cls._storage.close()
            cls._storage = None

    @classmethod
    async def create_session(cls, working_dir: str = ".", name: str = "New Session") -> Session:
        storage = await cls.get_storage()
        # 默认创建 USER 类型的 Session
        return await storage.create_session(working_dir, name, SessionType.USER)

    @classmethod
    async def get_session(cls, session_id: str) -> Session:
        storage = await cls.get_storage()
        return await storage.get_session(session_id)

    @classmethod
    async def list_sessions(cls, limit: int = 20, offset: int = 0) -> List[Session]:
        storage = await cls.get_storage()
        return await storage.list_sessions(limit, offset)

    @classmethod
    async def delete_session(cls, session_id: str):
        storage = await cls.get_storage()
        await storage.delete_session(session_id)

    @classmethod
    async def add_message(cls, session_id: str, message: Message):
        storage = await cls.get_storage()
        await storage.add_message(session_id, message)

    @classmethod
    async def get_messages(cls, session_id: str) -> List[Message]:
        storage = await cls.get_storage()
        return await storage.get_messages(session_id)

    @classmethod
    async def get_conversation(cls, session_id: str) -> Conversation:
        """
        [新增] 获取 Conversation 对象
        Agent 依赖此方法来构造 Conversation 以进行 Context Truncation 检查。
        """
        msgs = await cls.get_messages(session_id)
        return Conversation(messages=msgs)

    @classmethod
    async def search_history(cls, query: str, limit: int = 10) -> Any:
        storage = await cls.get_storage()
        searcher = ChatHistorySearch(storage.pool, query, limit)
        return await searcher.execute()

    @classmethod
    async def create_diagnostics(cls, session_id: str) -> str:
        data = await generate_diagnostics(cls, session_id)
        filename = f"diagnostics_{session_id}.zip"
        with open(filename, "wb") as f:
            f.write(data)
        return filename

    @classmethod
    async def update_extension_state(cls, session_id: str, ext_name: str, state: Any):
        # 1. 获取 Session 读取当前 Extension Data
        session = await cls.get_session(session_id)
        
        # 2. 修改内存状态
        session.extension_data.set_state(ext_name, state)
        
        # 3. 持久化
        storage = await cls.get_storage()
        await storage.update_session_metadata(
            session_id, 
            extension_data=session.extension_data
        )