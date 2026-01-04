# import json
# import asyncio
# from datetime import datetime, timezone
# from pathlib import Path
# from enum import Enum
# from typing import Optional, List, Dict, Any
# from contextlib import asynccontextmanager
# from pydantic import BaseModel, Field
# import aiosqlite

# # --- 核心集成：导入 conversation 模块 ---
# from conversation import (
#     Message, Role, MessageMetadata, Conversation, 
#     MessageContent, TextContent # 用于类型检查
# )
# from goose.providers import ModelConfig
# from extension_data import ExtensionData
# from chat_history_search import ChatHistorySearch
# from diagnostics import generate_diagnostics

# # --- 常量 ---
# CURRENT_SCHEMA_VERSION = 6

# SESSIONS_FOLDER = "sessions"
# DB_NAME = "sessions.db"

# # --- 数据模型 ---

# class SessionType(str, Enum):
#     """对应 Rust: pub enum SessionType"""
#     USER = "user"
#     SCHEDULED = "scheduled"
#     SUB_AGENT = "sub_agent"
#     HIDDEN = "hidden"
#     TERMINAL = "terminal"

# class Session(BaseModel):
#     """
#     对应 Rust: pub struct Session
#     """
#     id: str
#     working_dir: str
#     name: str = ""
#     user_set_name: bool = False
#     session_type: SessionType = SessionType.USER
#     created_at: str
#     updated_at: str
    
#     # 扩展数据 (ExtensionData)
#     extension_data: ExtensionData = Field(default_factory=ExtensionData)
    
#     # Token 统计
#     total_tokens: Optional[int] = None
#     input_tokens: Optional[int] = None
#     output_tokens: Optional[int] = None
#     accumulated_total_tokens: Optional[int] = None
#     accumulated_input_tokens: Optional[int] = None
#     accumulated_output_tokens: Optional[int] = None
    
#     # 上下文相关
#     schedule_id: Optional[str] = None
#     recipe_json: Optional[str] = None
#     user_recipe_values: Optional[Dict[str, str]] = None
    
#     # 运行时状态
#     message_count: int = 0
#     provider_name: Optional[str] = None
    
#     # Pydantic v2 兼容性重命名
#     current_model_config: Optional[ModelConfig] = Field(default=None, alias="model_config")

# # --- 高并发连接池 (保持优化) ---

# class DatabasePool:
#     def __init__(self, db_path: str):
#         self.db_path = db_path
#         self._conn: Optional[aiosqlite.Connection] = None
#         self._lock = asyncio.Lock()

#     async def get_connection(self) -> aiosqlite.Connection:
#         if self._conn is None:
#             async with self._lock:
#                 if self._conn is None:
#                     conn = await aiosqlite.connect(self.db_path)
#                     conn.row_factory = aiosqlite.Row
#                     # 性能优化参数
#                     await conn.execute("PRAGMA journal_mode=WAL;") 
#                     await conn.execute("PRAGMA synchronous=NORMAL;")
#                     await conn.execute("PRAGMA busy_timeout=5000;")
#                     self._conn = conn
#         return self._conn

#     async def close(self):
#         if self._conn:
#             await self._conn.close()
#             self._conn = None

# # --- SessionStorage (持久化层) ---

# class SessionStorage:
#     def __init__(self, db_pool: DatabasePool):
#         self.pool = db_pool

#     @classmethod
#     async def create(cls) -> "SessionStorage":
#         session_dir = Path.cwd() / SESSIONS_FOLDER
#         session_dir.mkdir(exist_ok=True)
#         db_path = str(session_dir / DB_NAME)
#         pool = DatabasePool(db_path)
#         storage = cls(pool)
#         await storage.run_migrations()
#         return storage

#     @asynccontextmanager
#     async def _get_conn(self):
#         conn = await self.pool.get_connection()
#         yield conn

#     async def close(self):
#         await self.pool.close()

#     async def run_migrations(self):
#         async with self._get_conn() as db:
#             await db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
#             try:
#                 await db.execute("SELECT 1 FROM sessions LIMIT 1")
#             except aiosqlite.OperationalError:
#                 # 初始化数据库结构 (对应 Rust schema_v6)
#                 await db.execute("BEGIN")
#                 await db.execute("""
#                     CREATE TABLE sessions (
#                         id TEXT PRIMARY KEY,
#                         name TEXT DEFAULT '',
#                         user_set_name BOOLEAN DEFAULT 0,
#                         session_type TEXT DEFAULT 'user',
#                         working_dir TEXT NOT NULL,
#                         created_at TEXT,
#                         updated_at TEXT,
#                         extension_data TEXT DEFAULT '{}',
#                         total_tokens INTEGER,
#                         input_tokens INTEGER,
#                         output_tokens INTEGER,
#                         accumulated_total_tokens INTEGER,
#                         accumulated_input_tokens INTEGER,
#                         accumulated_output_tokens INTEGER,
#                         schedule_id TEXT,
#                         recipe_json TEXT,
#                         user_recipe_values_json TEXT,
#                         provider_name TEXT,
#                         model_config_json TEXT
#                     )
#                 """)
#                 await db.execute("""
#                     CREATE TABLE messages (
#                         id INTEGER PRIMARY KEY AUTOINCREMENT,
#                         session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
#                         role TEXT NOT NULL,
#                         content_json TEXT NOT NULL,
#                         created_timestamp INTEGER NOT NULL,
#                         timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                         metadata_json TEXT
#                     )
#                 """)
#                 await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
#                 await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)")
#                 await db.commit()

#     async def create_session(self, working_dir: str, name: str, session_type: SessionType) -> Session:
#         today = datetime.now(timezone.utc).strftime("%Y%m%d")
#         now_str = datetime.now(timezone.utc).isoformat()
        
#         async with self._get_conn() as db:
#             # 这里的 ID 生成逻辑模拟了 Rust 的 Atomic 行为
#             async with db.execute(f"SELECT MAX(CAST(SUBSTR(id, 10) AS INTEGER)) FROM sessions WHERE id LIKE '{today}_%'") as cursor:
#                 row = await cursor.fetchone()
#                 max_id = row[0] if row and row[0] is not None else 0
#                 new_id = f"{today}_{max_id + 1}"

#             await db.execute(
#                 """
#                 INSERT INTO sessions (id, name, user_set_name, session_type, working_dir, created_at, updated_at, extension_data)
#                 VALUES (?, ?, ?, ?, ?, ?, ?, '{}')
#                 """,
#                 (new_id, name, False, session_type.value, working_dir, now_str, now_str)
#             )
#             await db.commit()
            
#             return Session(
#                 id=new_id, working_dir=working_dir, name=name, session_type=session_type,
#                 created_at=now_str, updated_at=now_str
#             )

#     async def get_session(self, session_id: str) -> Session:
#         async with self._get_conn() as db:
#             async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cursor:
#                 row = await cursor.fetchone()
#                 if not row:
#                     raise ValueError(f"Session {session_id} not found")
#                 return self._row_to_session(row, 0) # 暂时无法获取 count，需二次查询

#     async def get_session_with_count(self, session_id: str) -> Session:
#         """获取 Session 并附带消息计数"""
#         async with self._get_conn() as db:
#             async with db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)) as cursor:
#                 row = await cursor.fetchone()
#                 if not row:
#                     raise ValueError(f"Session {session_id} not found")
                
#                 async with db.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)) as c:
#                     count = (await c.fetchone())[0]
                
#                 return self._row_to_session(row, count)

#     def _row_to_session(self, row, msg_count: int) -> Session:
#         """内部辅助：将 DB Row 转换为 Session 对象"""
#         model_config = None
#         if row['model_config_json']:
#             try:
#                 model_config = ModelConfig.model_validate_json(row['model_config_json'])
#             except: pass

#         ext_data = ExtensionData()
#         if row['extension_data']:
#             try:
#                 raw_dict = json.loads(row['extension_data'])
#                 ext_data = ExtensionData(extension_states=raw_dict)
#             except: pass

#         return Session(
#             id=row['id'],
#             working_dir=row['working_dir'],
#             name=row['name'],
#             user_set_name=bool(row['user_set_name']),
#             session_type=SessionType(row['session_type']),
#             created_at=str(row['created_at']),
#             updated_at=str(row['updated_at']),
#             extension_data=ext_data,
#             total_tokens=row['total_tokens'],
#             provider_name=row['provider_name'],
#             current_model_config=model_config,
#             message_count=msg_count
#         )

#     async def list_sessions(self, limit: int = 20, offset: int = 0) -> List[Session]:
#         """获取最近的会话列表"""
#         sessions = []
#         async with self._get_conn() as db:
#             sql = "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?"
#             async with db.execute(sql, (limit, offset)) as cursor:
#                 async for row in cursor:
#                     # 列表查询为了性能通常不包含消息计数，设为 0
#                     sessions.append(self._row_to_session(row, 0))
#         return sessions

#     async def delete_session(self, session_id: str):
#         """删除会话及其所有消息 (依赖外键 CASCADE 或手动删除)"""
#         async with self._get_conn() as db:
#             await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
#             await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
#             await db.commit()

#     async def add_message(self, session_id: str, message: Message):
#         """
#         持久化 Message 对象。
#         利用 Pydantic V2 的 model_dump(mode='json') 自动处理 Union 类型的 discriminators
#         """
#         # 1. 序列化 Content List
#         # message.content 是 List[MessageContent]
#         content_json = json.dumps([c.model_dump(mode='json', by_alias=True) for c in message.content])
        
#         # 2. 序列化 Metadata
#         metadata_json = message.metadata.model_dump_json(by_alias=True)
        
#         async with self._get_conn() as db:
#             await db.execute(
#                 """
#                 INSERT INTO messages (session_id, role, content_json, created_timestamp, metadata_json)
#                 VALUES (?, ?, ?, ?, ?)
#                 """,
#                 (session_id, message.role.value, content_json, message.created, metadata_json)
#             )
#             # 更新 session 的 update_time
#             await db.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
#             await db.commit()

#     async def get_messages(self, session_id: str) -> List[Message]:
#         """从数据库恢复 Message 列表"""
#         messages = []
#         async with self._get_conn() as db:
#             async with db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)) as cursor:
#                 async for row in cursor:
#                     try:
#                         # 反序列化
#                         content_list = json.loads(row['content_json'])
#                         # MessageContent 是 Union，Pydantic 会根据 'type' 字段自动推断具体类
                        
#                         metadata = MessageMetadata()
#                         if row['metadata_json']:
#                             metadata = MessageMetadata.model_validate_json(row['metadata_json'])

#                         msg = Message(
#                             id=str(row['id']),
#                             role=Role(row['role']),
#                             created=row['created_timestamp'],
#                             content=content_list, # Pydantic 自动处理 List[Union]
#                             metadata=metadata
#                         )
#                         messages.append(msg)
#                     except Exception as e:
#                         print(f"⚠️ Error parsing message {row['id']} in session {session_id}: {e}")
#         return messages

#     async def update_session_metadata(self, session_id: str, **kwargs):
#         """Builder 模式更新元数据"""
#         valid_fields = {
#             "name", "user_set_name", "session_type", "working_dir", 
#             "total_tokens", "provider_name", "model_config_json",
#             "extension_data"
#         }
        
#         updates = []
#         params = []
        
#         for k, v in kwargs.items():
#             # 字段映射
#             if k == "current_model_config":
#                 k = "model_config_json"
#                 v = v.model_dump_json() if v else None
#             elif k == "extension_data":
#                 v = json.dumps(v.extension_states) if v else '{}'
            
#             if k in valid_fields:
#                 updates.append(f"{k} = ?")
#                 params.append(v)
        
#         if not updates: return

#         params.append(session_id)
#         sql = f"UPDATE sessions SET {', '.join(updates)}, updated_at = datetime('now') WHERE id = ?"
        
#         async with self._get_conn() as db:
#             await db.execute(sql, tuple(params))
#             await db.commit()

# # --- 门面：SessionManager ---

# class SessionManager:
#     _storage: Optional[SessionStorage] = None

#     @classmethod
#     async def get_storage(cls) -> SessionStorage:
#         if cls._storage is None:
#             cls._storage = await SessionStorage.create()
#         return cls._storage

#     @classmethod
#     async def shutdown(cls):
#         if cls._storage:
#             await cls._storage.close()
#             cls._storage = None

#     # --- Session Operations ---

#     @classmethod
#     async def create_session(cls, working_dir: str = ".", name: str = "New Session") -> Session:
#         storage = await cls.get_storage()
#         return await storage.create_session(working_dir, name, SessionType.USER)

#     @classmethod
#     async def get_session(cls, session_id: str) -> Session:
#         """获取单个会话（含消息计数）"""
#         storage = await cls.get_storage()
#         return await storage.get_session_with_count(session_id)

#     @classmethod
#     async def list_sessions(cls, limit: int = 20) -> List[Session]:
#         """列出最近会话"""
#         storage = await cls.get_storage()
#         return await storage.list_sessions(limit=limit)

#     @classmethod
#     async def delete_session(cls, session_id: str):
#         """删除会话"""
#         storage = await cls.get_storage()
#         await storage.delete_session(session_id)

#     # --- Message Operations ---

#     @classmethod
#     async def add_message(cls, session_id: str, message: Message):
#         """添加消息"""
#         storage = await cls.get_storage()
#         await storage.add_message(session_id, message)

#     @classmethod
#     async def get_messages(cls, session_id: str) -> List[Message]:
#         """获取消息列表 (Raw List)"""
#         storage = await cls.get_storage()
#         return await storage.get_messages(session_id)

#     @classmethod
#     async def get_conversation(cls, session_id: str) -> Conversation:
#         """
#         [兼容性关键] 获取 Conversation 对象
#         这允许直接将结果传给 fix_conversation 处理
#         """
#         msgs = await cls.get_messages(session_id)
#         return Conversation(msgs)

#     # --- Advanced Features ---

#     @classmethod
#     async def search_history(cls, query: str, limit: int = 10) -> Any:
#         storage = await cls.get_storage()
#         searcher = ChatHistorySearch(storage.pool, query, limit)
#         return await searcher.execute()

#     @classmethod
#     async def create_diagnostics(cls, session_id: str) -> str:
#         data = await generate_diagnostics(cls, session_id)
#         filename = f"diagnostics_{session_id}.zip"
#         with open(filename, "wb") as f:
#             f.write(data)
#         return filename

#     @classmethod
#     async def update_extension_state(cls, session_id: str, ext_name: str, state: Any):
#         session = await cls.get_session(session_id)
#         session.extension_data.set_state(ext_name, state)
        
#         storage = await cls.get_storage()
#         await storage.update_session_metadata(
#             session_id, 
#             extension_data=session.extension_data
#         )

# # --- 综合测试代码 ---

# async def main():
#     print("--- Session Manager Integration Test ---")
    
#     # 1. 建立会话
#     session = await SessionManager.create_session(name="Integration Test")
#     print(f"✅ Created: {session.id}")
    
#     # 2. 插入复杂消息 (测试 conversation.message 兼容性)
#     from conversation import TextContent
    
#     # User Text
#     msg1 = Message.user("Hello Goose")
#     await SessionManager.add_message(session.id, msg1)
    
#     # Tool Request
#     msg2 = Message.assistant().with_tool_request(
#         "call_1", "get_weather", {"city": "Beijing"}
#     )
#     await SessionManager.add_message(session.id, msg2)
    
#     # Tool Response
#     msg3 = Message.user().with_tool_response(
#         "call_1", "Sunny, 25C"
#     )
#     await SessionManager.add_message(session.id, msg3)
    
#     print("✅ Messages added (Text, ToolRequest, ToolResponse)")
    
#     # 3. 获取 Conversation 对象
#     conv = await SessionManager.get_conversation(session.id)
#     print(f"✅ Loaded Conversation with {len(conv.messages)} messages")
    
#     # 4. 验证多态解析
#     last_msg = conv.messages[-1]
#     if last_msg.content[0].type == 'toolResponse':
#         print(f"✅ Verified Last Message Type: {last_msg.content[0].type}")
#         print(f"   Result: {last_msg.content[0].tool_result.value.content[0].text}")
#     else:
#         print(f"❌ Type mismatch: {last_msg.content[0].type}")

#     # 5. 清理
#     await SessionManager.delete_session(session.id)
#     print("✅ Session deleted")
#     await SessionManager.shutdown()

# if __name__ == "__main__":
#     asyncio.run(main())