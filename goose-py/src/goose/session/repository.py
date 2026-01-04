# src/goose/session/repository.py

import json
import logging
from typing import List, Optional, Dict, Any
from goose.persistence import persistence_manager
from ..conversation import Message 

logger = logging.getLogger("goose.session.repo")

# --- SQL Schemas ---

SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT
);
"""

MESSAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT, 
    created_at TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
"""

# [优化] 添加索引以加速查询
MESSAGE_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
"""

def register_session_schemas():
    """向 PersistenceManager 注册表结构"""
    pm = persistence_manager
    # 注册各个 Schema 脚本
    pm.register_schema(SESSION_SCHEMA)
    pm.register_schema(MESSAGE_SCHEMA)
    pm.register_schema(MESSAGE_INDEX_SCHEMA)

class SessionRepository:
    def __init__(self):
        # 获取全局单例
        self.pm = persistence_manager
        # 确保 Schema 已注册 (防止用户忘记手动调用 register)
        register_session_schemas()

    async def create_session(self, session_id: str, name: str = "New Session", metadata: Dict = None):
        """创建新会话"""
        await self.pm.execute(
            """
            INSERT INTO sessions (id, name, metadata) 
            VALUES (:id, :name, :metadata)
            """,
            {
                "id": session_id, 
                "name": name, 
                "metadata": json.dumps(metadata or {})
            }
        )
        logger.debug(f"Created session {session_id}")

    async def get_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话元数据"""
        # [优化] 使用 fetch_one
        row = await self.pm.fetch_one(
            "SELECT * FROM sessions WHERE id = :id", 
            {"id": session_id}
        )
        
        if row:
            # SQLAlchemyBackend 返回的 row 已经是 dict (或类 dict 对象)
            # 为了安全起见，做一个浅拷贝再修改
            data = dict(row)
            if isinstance(data.get("metadata"), str):
                try:
                    data["metadata"] = json.loads(data["metadata"])
                except:
                    data["metadata"] = {}
            return data
        return None

    async def add_message(self, session_id: str, message: Message):
        """保存单条消息"""
        # 序列化 Logic: Pydantic -> Dict -> JSON String
        msg_dump = message.model_dump(mode='json')
        
        content_json = json.dumps(msg_dump.get("content"))
        metadata_json = json.dumps(msg_dump.get("metadata", {}))

        await self.pm.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at, metadata)
            VALUES (:id, :session_id, :role, :content, :created_at, :metadata)
            """,
            {
                "id": message.id,
                "session_id": session_id,
                "role": message.role.value if hasattr(message.role, 'value') else str(message.role),
                "content": content_json,
                "created_at": msg_dump.get("created_at"),
                "metadata": metadata_json
            }
        )

    async def get_messages(self, session_id: str) -> List[Message]:
        """加载会话的所有消息"""
        rows = await self.pm.fetch_all(
            "SELECT * FROM messages WHERE session_id = :session_id ORDER BY created_at ASC", 
            {"session_id": session_id}
        )
        
        messages = []
        for row in rows:
            try:
                # 兼容处理: 数据库取出的可能是 None (但在 Schema 中通常 content 不为 null)
                raw_content = row.get("content") or "[]"
                raw_metadata = row.get("metadata") or "{}"
                
                msg_data = {
                    "id": row["id"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "content": json.loads(raw_content),
                    "metadata": json.loads(raw_metadata)
                }
                messages.append(Message.model_validate(msg_data))
            except Exception as e:
                logger.error(f"Failed to load message {row.get('id')}: {e}")
                
        return messages

    async def list_sessions(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        """列出所有会话"""
        sql = "SELECT * FROM sessions ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        rows = await self.pm.fetch_all(sql, {"limit": limit, "offset": offset})
        
        # 简单处理 metadata 反序列化
        results = []
        for row in rows:
            data = dict(row)
            if isinstance(data.get("metadata"), str):
                 try:
                    data["metadata"] = json.loads(data["metadata"])
                 except: pass
            results.append(data)
        return results

    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]):
        """更新会话元数据"""
        sql = "UPDATE sessions SET metadata = :metadata WHERE id = :id"
        await self.pm.execute(
            sql, 
            {
                "metadata": json.dumps(metadata), 
                "id": session_id
            }
        )

    async def search_messages(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索消息内容"""
        # 注意: LIKE 查询的 % 依然是在参数值里处理，而不是 SQL 语句里
        sql = """
            SELECT * FROM messages 
            WHERE content LIKE :query 
            ORDER BY created_at DESC 
            LIMIT :limit
        """
        return await self.pm.fetch_all(
            sql, 
            {
                "query": f"%{query}%", 
                "limit": limit
            }
        )

    async def delete_session(self, session_id: str):
        """
        删除会话及其所有消息。
        [关键改进] 使用 transaction 上下文管理器保证原子性。
        """
        
        async with self.pm.transaction():
            # 先删消息 (外键约束通常要求先删子表，或者配置了 CASCADE)
            await self.pm.execute(
                "DELETE FROM messages WHERE session_id = :session_id", 
                {"session_id": session_id}
            )
            # 再删会话
            await self.pm.execute(
                "DELETE FROM sessions WHERE id = :id", 
                {"id": session_id}
            )