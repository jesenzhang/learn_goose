import json
from typing import List, Any,Optional
from ..conversation import Message, Conversation
from .types import Session, SessionType
from .storage import SessionStorage
from .chat_history_search import ChatHistorySearch
from .diagnostics import generate_diagnostics

class SessionManager:
    _storage: Optional[SessionStorage] = None

    @classmethod
    async def get_storage(cls) -> SessionStorage:
        if cls._storage is None:
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
        msgs = await cls.get_messages(session_id)
        return Conversation(msgs)

    @classmethod
    async def search_history(cls, query: str, limit: int = 10) -> Any:
        storage = await cls.get_storage()
        searcher = ChatHistorySearch(storage.pool, query, limit)
        return await searcher.execute()

    @classmethod
    async def create_diagnostics(cls, session_id: str) -> str:
        # 注意：generate_diagnostics 现在需要接收 cls (SessionManager 类本身)
        data = await generate_diagnostics(cls, session_id)
        filename = f"diagnostics_{session_id}.zip"
        with open(filename, "wb") as f:
            f.write(data)
        return filename

    @classmethod
    async def update_extension_state(cls, session_id: str, ext_name: str, state: Any):
        session = await cls.get_session(session_id)
        session.extension_data.set_state(ext_name, state)
        
        storage = await cls.get_storage()
        await storage.update_session_metadata(
            session_id, 
            extension_data=session.extension_data
        )