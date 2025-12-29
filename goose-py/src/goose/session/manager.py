import logging
import json
import datetime
import uuid
from typing import List, Optional, Any, Dict

from ..conversation import Message, Conversation
from .types import Session, SessionType
from .extension_data import ExtensionData
from .repository import SessionRepository, register_session_schemas
from ..model import ModelConfig 

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
            register_session_schemas()
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
            
        now_str = datetime.datetime.now().isoformat()
        
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
        
        # 2. 序列化
        metadata_to_save = cls._session_to_db_metadata(session)
        
        # 3. 持久化
        await repo.create_session(session_id, name, metadata_to_save)
        
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
        data = await repo.get_session_metadata(session_id)
        if not data:
            raise ValueError(f"Session {session_id} not found")
        return cls._db_row_to_session(data)

    @classmethod
    async def list_sessions(cls, limit: int = 20, offset: int = 0) -> List[Session]:
        repo = await cls.get_repo()
        rows = await repo.list_sessions(limit, offset)
        return [cls._db_row_to_session(row) for row in rows]

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
    async def search_history(cls, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        repo = await cls.get_repo()
        # SQL 逻辑下沉到 Repository
        rows = await repo.search_messages(query, limit)
        
        results = []
        for row in rows:
            results.append({
                "id": row["id"],
                "content": row["content"], # 这里可能是 JSON 字符串，前端可能需要解析
                "role": row["role"],
                "created_at": row["created_at"]
            })
        return results

    @classmethod
    async def update_extension_state(cls, session_id: str, ext_name: str, state: Any):
        """
        更新扩展状态。
        流程：Load -> Modify Object -> Serialize -> Save
        """
        repo = await cls.get_repo()
        
        # 1. Load: 获取完整 Session 对象
        session = await cls.get_session(session_id)
        
        # 2. Modify: 更新内存对象
        # ExtensionData 是 Pydantic 模型，data 字段是 Dict[str, Any]
        session.extension_data.data[ext_name] = state
        
        # 3. Serialize: 重新生成包含 _extension_data 的 metadata
        metadata_to_save = cls._session_to_db_metadata(session)
        
        # 4. Save: 更新 DB
        await repo.update_session_metadata(session_id, metadata_to_save)

    # --- 辅助方法 (核心序列化逻辑) ---

    @staticmethod
    def _session_to_db_metadata(session: Session) -> Dict[str, Any]:
        """
        [序列化] 将 Session 对象中的属性打包进 metadata 字典。
        """
        # 1. 复制基础 metadata
        db_meta = session.metadata.copy()
        
        # 2. 注入核心字段 (如果 Session 模型里有这些字段，但 DB 表只有 metadata 列)
        db_meta["working_dir"] = session.working_dir
        db_meta["type"] = session.session_type.value
        
        # 3. 注入 Extension Data (使用下划线前缀防止冲突)
        # model_dump(mode='json') 会把内部对象转为纯 dict/list
        db_meta["_extension_data"] = session.extension_data.model_dump(mode='json')
        
        # 4. 注入 Model Config (如果有)
        if session.current_model_config:
            db_meta["model_config"] = session.current_model_config.model_dump(mode='json')
            
        return db_meta

    @staticmethod
    def _db_row_to_session(row: Dict[str, Any]) -> Session:
        """
        [反序列化] 将 DB 字典转换为 Session Pydantic 对象。
        """
        # 1. 解析 Metadata JSON
        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

        # 2. 提取 ExtensionData
        # pop 出来，这样它不会残留在 session.metadata 属性中
        ext_data_raw = metadata.pop("_extension_data", {})
        extension_data_obj = ExtensionData.model_validate(ext_data_raw)

        # 3. 提取 ModelConfig
        model_config = None
        if "model_config" in metadata:
            mc_raw = metadata.pop("model_config")
            try:
                model_config = ModelConfig.model_validate(mc_raw)
            except Exception:
                pass # 容错

        # 4. 提取基础字段 (优先用 metadata 里的，如果没有则用 defaults)
        working_dir = metadata.get("working_dir", row.get("working_dir", ".")) # 兼容旧数据
        
        # 处理 Session Type
        s_type_str = metadata.get("type", SessionType.USER.value)
        try:
            s_type = SessionType(s_type_str)
        except ValueError:
            s_type = SessionType.USER

        # 处理时间格式 (SQLite 可能返回 str 或 datetime)
        created_at = row.get("created_at")
        if isinstance(created_at, datetime.datetime):
            created_at = created_at.isoformat()
        
        # 构造 Session 对象
        return Session(
            id=row["id"],
            name=row.get("name", ""),
            session_type=s_type,
            working_dir=working_dir,
            created_at=str(created_at),
            updated_at=str(created_at), # DB 没有 updated_at，暂用 created_at
            metadata=metadata,          # 此时 metadata 已移除了 _extension_data 等特殊字段
            extension_data=extension_data_obj,
            current_model_config=model_config
        )