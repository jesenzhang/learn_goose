# src/goose/session/repository.py

import json
import logging
from typing import List, Optional, Dict, Any
from ..persistence import PersistenceManager
from ..conversation import Message, Conversation # 假设你有这些类
# 如果 Message 对象使用了 Pydantic，我们需要用 model_dump 和 model_validate

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
    content TEXT, -- JSON structure
    created_at TIMESTAMP,
    metadata TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
"""

def register_session_schemas():
    """向 PersistenceManager 注册表结构"""
    pm = PersistenceManager.get_instance()
    pm.register_schema(SESSION_SCHEMA)
    pm.register_schema(MESSAGE_SCHEMA)

class SessionRepository:
    def __init__(self):
        # 通过 Manager 获取后端，不需要自己管理连接
        self.backend = PersistenceManager.get_instance().backend

    async def create_session(self, session_id: str, name: str = "New Session", metadata: Dict = None):
        """创建新会话"""
        await self.backend.execute(
            "INSERT INTO sessions (id, name, metadata) VALUES (?, ?, ?)",
            (session_id, name, json.dumps(metadata or {}))
        )
        logger.debug(f"Created session {session_id}")

    async def get_session_metadata(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话元数据"""
        row = await self.backend.fetch_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        if row:
            # 转换 SQLite Row 为 Python Dict
            data = dict(row)
            if isinstance(data.get("metadata"), str):
                data["metadata"] = json.loads(data["metadata"])
            return data
        return None

    async def add_message(self, session_id: str, message: Message):
        """保存单条消息"""
        # 序列化 Logic: Pydantic -> Dict -> JSON String
        # 假设 message 是 Pydantic v2 模型
        msg_dump = message.model_dump(mode='json')
        
        # content 字段可能是复杂的 List[ContentBlock]，存为 JSON 字符串
        content_json = json.dumps(msg_dump.get("content"))
        metadata_json = json.dumps(msg_dump.get("metadata", {}))

        await self.backend.execute(
            """
            INSERT INTO messages (id, session_id, role, content, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                session_id,
                message.role.value, # Enum -> str
                content_json,
                msg_dump.get("created_at"), # ISO format str or timestamp
                metadata_json
            )
        )

    async def get_messages(self, session_id: str) -> List[Message]:
        """加载会话的所有消息"""
        rows = await self.backend.fetch_all(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY created_at ASC", 
            (session_id,)
        )
        
        messages = []
        for row in rows:
            try:
                # 反序列化 Logic
                # 构造符合 Pydantic 初始化的 Dict
                msg_data = {
                    "id": row["id"],
                    "role": row["role"],
                    "created_at": row["created_at"],
                    "content": json.loads(row["content"]), # JSON str -> List[Dict]
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else {}
                }
                # 恢复为 Message 对象
                messages.append(Message.model_validate(msg_data))
            except Exception as e:
                logger.error(f"Failed to load message {row['id']}: {e}")
                
        return messages

    async def list_sessions(self, limit: int, offset: int) -> List[Dict[str, Any]]:
        """列出所有会话 (Dict形式)"""
        sql = "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ? OFFSET ?"
        rows = await self.backend.fetch_all(sql, (limit, offset))
        return [dict(row) for row in rows]

    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]):
        """更新会话元数据"""
        # 注意：这里传入的是字典，Repo 负责 dump 为 JSON 字符串
        sql = "UPDATE sessions SET metadata = ? WHERE id = ?"
        await self.backend.execute(sql, (json.dumps(metadata), session_id))

    async def search_messages(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """搜索消息内容"""
        sql = """
            SELECT * FROM messages 
            WHERE content LIKE ? 
            ORDER BY created_at DESC 
            LIMIT ?
        """
        # 注意：这里简单使用 LIKE，生产环境建议用 FTS
        return await self.backend.fetch_all(sql, (f"%{query}%", limit))

    async def delete_session(self, session_id: str):
        # 事务性删除
        await self.backend.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        await self.backend.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        