# src/goose/session/repository.py

import json
import logging
import time
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel,Field
from ..conversation import Message 
from .types import Session,SessionType
from ..persistence import BaseRepository, PersistenceManager,TableSpec,with_table

logger = logging.getLogger("goose.session.repo")

# --- SQL Schemas ---

SESSION_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    -- 1. 核心标识
    id TEXT PRIMARY KEY,
    name TEXT,
    working_dir TEXT NOT NULL,  -- 必须字段
    user_set_name INTEGER,      -- Boolean: 0=False, 1=True
    session_type TEXT,          -- Enum: 存 'user', 'workflow' 等字符串
    
    -- 2. 时间戳 (使用 REAL 存 Unix Timestamp)
    created_at REAL,
    updated_at REAL,
    
    -- 3. 复杂结构 (Repository 会自动序列化为 JSON 字符串)
    metadata TEXT,
    extension_data TEXT,        -- ExtensionData 对象 -> JSON
    stats TEXT,                 -- [变动] TokenStats 对象 -> JSON
    
    -- 4. 上下文与状态
    schedule_id TEXT,
    recipe_json TEXT,
    user_recipe_values TEXT,    -- Dict -> JSON
    
    message_count INTEGER,
    provider_name TEXT,
    
    -- 5. 配置
    -- [注意] 对应字段 current_model_config。
    -- 如果你的 Repository 使用 model.model_dump() (默认 by_alias=False)，
    -- 那么列名必须叫 current_model_config 以匹配 Python 属性名。
    current_model_config TEXT
);
"""

SESSION_INDEX_SCHEMA1 = """
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at);
"""

SESSION_INDEX_SCHEMA2 = """
CREATE INDEX IF NOT EXISTS idx_sessions_type ON sessions(session_type);
"""

MESSAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    role TEXT,
    content TEXT, 
    created_at REAL,
    metadata TEXT,
    FOREIGN KEY(session_id) REFERENCES sessions(id)
);
"""

# [优化] 添加索引以加速查询
MESSAGE_INDEX_SCHEMA = """
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
"""

# def register_session_schemas():
#     """向 PersistenceManager 注册表结构"""
#     pm = persistence_manager
#     # 注册各个 Schema 脚本
#     pm.register_schema(SESSION_SCHEMA)
#     pm.register_schema(MESSAGE_SCHEMA)
#     pm.register_schema(MESSAGE_INDEX_SCHEMA)



@with_table(name='sessions',model=Session,sql=[SESSION_SCHEMA,SESSION_INDEX_SCHEMA1,SESSION_INDEX_SCHEMA2],pk='id',priority=0,attr_name='session_spec')
@with_table(name='messages',model=Message,sql=[MESSAGE_SCHEMA,MESSAGE_INDEX_SCHEMA],pk='id',priority=1,attr_name='message_spec')
class SessionRepository(BaseRepository):
    
    async def create_session(self, session:Session):
        """创建新会话"""
        await self._upsert(Session,session)
        
        # (
        #     """
        #     INSERT INTO sessions (id, name, metadata) 
        #     VALUES (:id, :name, :metadata)
        #     """,
        #     {
        #         "id": session_id, 
        #         "name": name, 
        #         "metadata": json.dumps(metadata or {})
        #     }
        # )
        logger.debug(f"Created session {session.id}")

    async def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话元数据"""
        try:
            entity:Session = await self._get(Session, session_id)
            return entity
        except Exception as e:
            logger.error(f"Failed to get session metadata {session_id}: {e}")
            return None
    
        # row = await self.pm.fetch_one(
        #     "SELECT * FROM sessions WHERE id = :id", 
        #     {"id": session_id}
        # )
        
        # if row:
        #     # SQLAlchemyBackend 返回的 row 已经是 dict (或类 dict 对象)
        #     # 为了安全起见，做一个浅拷贝再修改
        #     data = dict(row)
        #     if isinstance(data.get("metadata"), str):
        #         try:
        #             data["metadata"] = json.loads(data["metadata"])
        #         except:
        #             data["metadata"] = {}
        #     return data
        # return None

    async def add_message(self, session_id: str, message: Message):
        """保存单条消息"""
        try:
            message.session_id = session_id
            await self._insert(Message,message)
        except Exception as e:
            logger.error(f"Failed to add message {message.id}: {e}")
        
        # # 序列化 Logic: Pydantic -> Dict -> JSON String
        # msg_dump = message.model_dump(mode='json')
        
        # content_json = json.dumps(msg_dump.get("content"))
        # metadata_json = json.dumps(msg_dump.get("metadata", {}))

        # await self.pm.execute(
        #     """
        #     INSERT INTO messages (id, session_id, role, content, created_at, metadata)
        #     VALUES (:id, :session_id, :role, :content, :created_at, :metadata)
        #     """,
        #     {
        #         "id": message.id,
        #         "session_id": session_id,
        #         "role": message.role.value if hasattr(message.role, 'value') else str(message.role),
        #         "content": content_json,
        #         "created_at": msg_dump.get("created_at"),
        #         "metadata": metadata_json
        #     }
        # )

    async def get_messages(self, session_id: str) -> List[Message]:
        """加载会话的所有消息"""
        try:
            entities: List[Message] = await self._find(Message, {"session_id": session_id})
            entities.sort(key=lambda x: x.created_at)
            return entities
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            return []
        
        # rows = await self.pm.fetch_all(
        #     "SELECT * FROM messages WHERE session_id = :session_id ORDER BY created_at ASC", 
        #     {"session_id": session_id}
        # )
        
        # messages = []
        # for row in rows:
        #     try:
        #         # 兼容处理: 数据库取出的可能是 None (但在 Schema 中通常 content 不为 null)
        #         raw_content = row.get("content") or "[]"
        #         raw_metadata = row.get("metadata") or "{}"
                
        #         msg_data = {
        #             "id": row["id"],
        #             "role": row["role"],
        #             "created_at": row["created_at"],
        #             "content": json.loads(raw_content),
        #             "metadata": json.loads(raw_metadata)
        #         }
        #         messages.append(Message.model_validate(msg_data))
        #     except Exception as e:
        #         logger.error(f"Failed to load message {row.get('id')}: {e}")
                
        # return messages

    async def list_sessions(self, limit: int=-1, offset: int=0) -> List[Dict[str, Any]]:
        """列出所有会话"""
        try:
            entities = await self._find(Session, {}, limit, offset)
            return entities
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
            return []
        
        # sql = "SELECT * FROM sessions ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
        # rows = await self.pm.fetch_all(sql, {"limit": limit, "offset": offset})
        
        # # 简单处理 metadata 反序列化
        # results = []
        # for row in rows:
        #     data = dict(row)
        #     if isinstance(data.get("metadata"), str):
        #          try:
        #             data["metadata"] = json.loads(data["metadata"])
        #          except: pass
        #     results.append(data)
        # return results

    async def update_session(self, session_id: str, **kwargs):
        """更新会话元数据"""
        try:
            await self._update_by(Session,filters={"id": session_id},**kwargs)
        except Exception as e:
            logger.error(f"Failed to update session metadata {session_id}: {e}")
        
        # sql = "UPDATE sessions SET metadata = :metadata WHERE id = :id"
        # await self.pm.execute(
        #     sql, 
        #     {
        #         "metadata": json.dumps(metadata), 
        #         "id": session_id
        #     }
        # )

    async def search_messages(self, query: str, limit: int =-1) -> List[Message]:
        """搜索消息内容"""
        
        try:
            entities = await self._find(Message, filters={"content": {"$like": f"%{query}%"}},limit=limit)
            return [
                Message.model_validate(entity.model_dump()) for entity in entities
            ]
        except Exception as e:
            logger.error(f"Failed to search messages: {e}")
            return []
        
        # # 注意: LIKE 查询的 % 依然是在参数值里处理，而不是 SQL 语句里
        # from goose.persistence.backends.sql_backend import SQLBackend
        # from goose.persistence.backends.jsonl_backend import JsonlBackend
        # spec = self.message_spec
        # # ==================================================
        # # 分支 A: 生产环境 (SQL Backend)
        # # ==================================================
        # if isinstance(self.backend, SQLBackend):
        #     # 1. 直接编写原生 SQL
        #     # 注意：SQLite/PG 中对 JSON 类型的列做 LIKE 查询，其实就是对 JSON 字符串做匹配，
        #     # 这对于简单的文本搜索是有效的。
        #     sql = f"""
        #         SELECT * FROM {spec.table_name} 
        #         WHERE content LIKE :query 
        #         ORDER BY created_at DESC 
        #     """
            
        #     # 处理 limit (-1 表示不限制)
        #     params = {"query": f"%{query}%"}
        #     if limit > 0:
        #         sql += " LIMIT :limit"
        #         params["limit"] = limit

        #     # 2. 调用 Driver 执行 (绕过 Backend 的通用接口)
        #     rows = await self.backend.driver.fetch_all(sql, params)
            
        #     # 3. 转换回对象
        #     return [self._from_db(r, spec) for r in rows]

        # # ==================================================
        # # 分支 B: 开发环境 (JSONL Backend)
        # # ==================================================
        # elif isinstance(self.backend, JsonlBackend):
        #     # 1. 获取所有数据 (JSONL 没有索引，只能全扫)
        #     # 传入 limit=-1 获取全部
        #     all_rows = await self.backend.find(spec,{}, limit=-1, offset=0)
            
        #     # 2. 内存过滤 (模拟 LIKE)
        #     # content 在 JSONL 里可能是字符串，也可能是复杂的 dict/list 结构
        #     # 最简单的方法是转成字符串再搜
        #     matched_rows = []
        #     for row in all_rows:
        #         content_val = row.get("content", "")
        #         # 无论 content 是 list 还是 str，转成 str 之后进行包含判断
        #         if query in str(content_val):
        #             matched_rows.append(row)
            
        #     # 3. 内存排序 (模拟 ORDER BY created_at DESC)
        #     # 假设 created_at 存的是 timestamp (int/float) 或 ISO string
        #     matched_rows.sort(key=lambda x: x.get("created_at", 0), reverse=True)
            
        #     # 4. 内存分页 (模拟 LIMIT)
        #     if limit > 0:
        #         matched_rows = matched_rows[:limit]
                
        #     return [self._from_db(r, spec) for r in matched_rows]
            
        # else:
        #     return []
        # sql = """
        #     SELECT * FROM messages 
        #     WHERE content LIKE :query 
        #     ORDER BY created_at DESC 
        #     LIMIT :limit
        # """
        # return await self.pm.fetch_all(
        #     sql, 
        #     {
        #         "query": f"%{query}%", 
        #         "limit": limit
        #     }
        # )

    async def delete_session(self, session_id: str):
        """
        删除会话及其所有消息。
        [关键改进] 使用 transaction 上下文管理器保证原子性。
        """
        try:
            # 👇 这一行是必须的！
            # 对于 SQL 后端，它开启真正的 DB 事务；
            # 对于 JSONL 后端，它获取文件锁防止并发写入冲突。
            async with self.transaction():
                
                # 1. 先删消息 (使用 session_id 筛选)
                await self._delete_by(Message, filters={"session_id": session_id})
                
                # 2. 再删会话 (使用 id 筛选)
                await self._delete_by(Session, filters={"id": session_id})
                
            logger.info(f"🗑️ Deleted session {session_id}")

        except Exception as e:
            logger.error(f"❌ Failed to delete session {session_id}: {e}")
            # 👇 强烈建议：不要吞掉异常！
            # 如果这里捕获了不抛出，上层调用者会以为删除成功了，导致 UI 状态错误。
            # 在 transaction 块中抛出异常会自动触发 SQL 回滚。
            raise e