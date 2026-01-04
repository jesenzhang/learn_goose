# import os
# import json
# import asyncio
# from datetime import datetime, timezone
# from pathlib import Path
# from typing import Optional, List, Dict, Any
# from contextlib import asynccontextmanager
# import aiosqlite
# import logging

# from ..conversation import Message, Role, MessageMetadata
# from goose.providers import ModelConfig
# from .types import Session, SessionType
# from .extension_data import ExtensionData

# logger = logging.getLogger(__name__)

# SESSIONS_FOLDER = "sessions"
# DB_NAME = "sessions.db"

# class DatabasePool:
#     def __init__(self, db_path: str):
#         self.db_path = db_path
#         self._conn: Optional[aiosqlite.Connection] = None
#         self._lock = asyncio.Lock()

#     async def get_connection(self) -> aiosqlite.Connection:
#         if self._conn is None:
#             async with self._lock:
#                 if self._conn is None:
#                     # check_same_thread=False 允许在 asyncio 环境中安全使用
#                     conn = await aiosqlite.connect(self.db_path, check_same_thread=False)
#                     conn.row_factory = aiosqlite.Row
#                     await conn.execute("PRAGMA journal_mode=WAL;") 
#                     await conn.execute("PRAGMA synchronous=NORMAL;")
#                     # 增加超时时间防止 database locked
#                     await conn.execute("PRAGMA busy_timeout=10000;") 
#                     self._conn = conn
#         return self._conn

#     async def close(self):
#         if self._conn:
#             await self._conn.close()
#             self._conn = None

# class SessionStorage:
#     def __init__(self, db_pool: DatabasePool):
#         self.pool = db_pool

#     @classmethod
#     async def create(cls) -> "SessionStorage":
#         # [修改] 优先使用环境变量，否则回退到 cwd
#         env_path = os.getenv("GOOSE_SESSIONS_DIR")
#         if env_path:
#             session_dir = Path(env_path)
#         else:
#             session_dir = Path.cwd() / SESSIONS_FOLDER
            
#         # 确保目录存在
#         if not session_dir.exists():
#             session_dir.mkdir(parents=True, exist_ok=True)
            
#         db_path = str(session_dir / DB_NAME)
        
#         # [调试日志] 打印最终决定的 DB 路径，以此判断是否发生漂移
#         print(f"[SessionStorage] Initializing DB at: {db_path}")
        
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
            
#             # 简单的幂等建表
#             await db.execute("""
#                 CREATE TABLE IF NOT EXISTS sessions (
#                     id TEXT PRIMARY KEY,
#                     name TEXT DEFAULT '',
#                     user_set_name BOOLEAN DEFAULT 0,
#                     session_type TEXT DEFAULT 'user',
#                     working_dir TEXT NOT NULL,
#                     created_at TEXT,
#                     updated_at TEXT,
#                     extension_data TEXT DEFAULT '{}',
#                     total_tokens INTEGER,
#                     input_tokens INTEGER,
#                     output_tokens INTEGER,
#                     accumulated_total_tokens INTEGER,
#                     accumulated_input_tokens INTEGER,
#                     accumulated_output_tokens INTEGER,
#                     schedule_id TEXT,
#                     recipe_json TEXT,
#                     user_recipe_values_json TEXT,
#                     provider_name TEXT,
#                     model_config_json TEXT
#                 )
#             """)
#             await db.execute("""
#                 CREATE TABLE IF NOT EXISTS messages (
#                     id INTEGER PRIMARY KEY AUTOINCREMENT,
#                     session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
#                     role TEXT NOT NULL,
#                     content_json TEXT NOT NULL,
#                     created_timestamp INTEGER NOT NULL,
#                     timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#                     metadata_json TEXT
#                 )
#             """)
#             await db.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
#             await db.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at DESC)")
#             await db.commit()

#     async def create_session(self, working_dir: str, name: str, session_type: SessionType) -> Session:
#         today = datetime.now(timezone.utc).strftime("%Y%m%d")
#         now_str = datetime.now(timezone.utc).isoformat()
        
#         async with self._get_conn() as db:
#             # ID 生成逻辑复刻 Rust: YYYYMMDD_Sequence
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
                
#                 async with db.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)) as c:
#                     count = (await c.fetchone())[0]
                
#                 return self._row_to_session(row, count)

#     def _row_to_session(self, row, msg_count: int) -> Session:
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

#     async def list_sessions(self, limit: int, offset: int) -> List[Session]:
#         sessions = []
#         async with self._get_conn() as db:
#             sql = "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ? OFFSET ?"
#             async with db.execute(sql, (limit, offset)) as cursor:
#                 async for row in cursor:
#                     # 列表查询暂不统计 message count 以提高性能，或者用子查询
#                     sessions.append(self._row_to_session(row, 0))
#         return sessions

#     async def delete_session(self, session_id: str):
#         async with self._get_conn() as db:
#             await db.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
#             await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
#             await db.commit()

#     async def add_message(self, session_id: str, message: Message):
#         # 使用 Pydantic 的 dump 确保别名和类型正确
#         content_json = json.dumps([c.model_dump(mode='json', by_alias=True) for c in message.content])
#         metadata_json = message.metadata.model_dump_json(by_alias=True)
        
#         async with self._get_conn() as db:
#             await db.execute(
#                 "INSERT INTO messages (session_id, role, content_json, created_timestamp, metadata_json) VALUES (?, ?, ?, ?, ?)",
#                 (session_id, message.role.value, content_json, message.created, metadata_json)
#             )
#             # Rust 对齐：每次添加消息更新 Session 时间
#             await db.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
#             await db.commit()

#     async def get_messages(self, session_id: str) -> List[Message]:
#         messages = []
#         async with self._get_conn() as db:
#             # 必须按 ID 或 创建时间正序排列
#             async with db.execute("SELECT * FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,)) as cursor:
#                 async for row in cursor:
#                     try:
#                         # 1. 解析原始 JSON
#                         content_data = json.loads(row['content_json'])
#                         metadata_data = json.loads(row['metadata_json']) if row['metadata_json'] else {}
                        
#                         # 2. 构造 Pydantic 验证所需的字典
#                         # 重点：Message 的 id 是 Optional[str]，但 DB 里是 int 自增主键。
#                         # 我们这里暂时不需要把 DB ID 映射回 Message.id (除非需要更新)，或者转为 str
#                         msg_dict = {
#                             "id": str(row['id']),
#                             "role": row['role'],
#                             "created": row['created_timestamp'],
#                             "content": content_data,
#                             "metadata": metadata_data
#                         }
                        
#                         # 3. 使用 Pydantic 自动验证和转换 (处理 Union Types)
#                         msg = Message.model_validate(msg_dict)
#                         messages.append(msg)
#                     except Exception as e:
#                         logger.error(f"Error rehydrating message {row['id']}: {e}")
#                         # 生产环境可能需要跳过或抛出，这里选择记录并跳过
#                         continue
#         return messages

#     async def update_session_metadata(self, session_id: str, **kwargs):
#         valid_fields = {
#             "name", "user_set_name", "session_type", "working_dir", 
#             "total_tokens", "provider_name", "model_config_json",
#             "extension_data"
#         }
        
#         updates = []
#         params = []
        
#         for k, v in kwargs.items():
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