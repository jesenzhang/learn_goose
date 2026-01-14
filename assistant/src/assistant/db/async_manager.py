"""
异步数据库管理器 - 使用 aiosqlite 实现异步数据库操作

完全异步实现，不阻塞事件循环
支持多用户会话管理
符合 DatabaseProtocol 协议
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, List, Any, Optional

from .protocol import DatabaseProtocol, MemoryProtocol

logger = logging.getLogger(__name__)


class AsyncDatabaseManager:
    """
    异步数据库管理器 - 使用 aiosqlite

    完全异步实现，符合 DatabaseProtocol 协议
    支持多用户会话管理
    """

    def __init__(self, db_path: str = "agent_ultra.db"):
        """
        初始化异步数据库管理器

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._conn = None
        self._lock = asyncio.Lock()
        self._initialized = False

    async def _get_connection(self):
        """获取数据库连接"""
        if self._conn is None:
            import aiosqlite
            self._conn = await aiosqlite.connect(self.db_path)
            await self._conn.execute("PRAGMA journal_mode=WAL")
            await self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    @asynccontextmanager
    async def _transaction(self):
        """异步事务上下文管理器"""
        conn = await self._get_connection()
        try:
            yield conn
            await conn.commit()
        except Exception as e:
            await conn.rollback()
            logger.error(f"Database transaction error: {e}", exc_info=e)
            raise

    async def initialize(self):
        """初始化数据库表结构（含多用户支持）"""
        if self._initialized:
            return

        await self._migrate_to_int_ids()

        async with self._transaction() as conn:
            # Sessions Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at DESC)")

            # Events Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    event TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp DESC)")

            # Memories Table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, created_at DESC)")

        self._initialized = True
        logger.info(f"Database initialized at {self.db_path}")

    async def _migrate_to_int_ids(self):
        """迁移：将 session_id 和 user_id 从 TEXT 改为 INTEGER"""
        try:
            conn = await self._get_connection()

            # 检查表是否存在
            cursor = await conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='sessions'
            """)
            table_exists = await cursor.fetchone()

            if not table_exists:
                logger.debug("Sessions table does not exist yet, skipping migration")
                return

            # 检查表结构
            cursor = await conn.execute("PRAGMA table_info(sessions)")
            columns = await cursor.fetchall()
            column_info = {col[1]: col[2] for col in columns}  # column_name: type

            # 检查 id 和 user_id 是否为 TEXT 类型
            needs_migration = (
                column_info.get('id') == 'TEXT' or
                column_info.get('user_id', '') == 'TEXT'
            )

            if needs_migration:
                logger.info("Migrating database: converting id and user_id to INTEGER")

                # 创建新表
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions_new (
                        id INTEGER PRIMARY KEY,
                        user_id INTEGER,
                        state TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 迁移数据：尝试转换 TEXT id 为 INTEGER
                cursor = await conn.execute("SELECT id, user_id, state, created_at, updated_at FROM sessions")
                rows = await cursor.fetchall()

                for row in rows:
                    old_id, old_user_id, state, created_at, updated_at = row

                    # 尝试将 TEXT id 转换为 INTEGER
                    new_id = None
                    if old_id and str(old_id).isdigit():
                        new_id = int(old_id)
                    elif old_id:
                        # 如果不是纯数字，使用 hash 作为新 id
                        new_id = abs(hash(str(old_id)))

                    # 尝试将 TEXT user_id 转换为 INTEGER
                    new_user_id = None
                    if old_user_id and str(old_user_id).isdigit():
                        new_user_id = int(old_user_id)
                    elif old_user_id:
                        # 如果不是纯数字，使用 hash 作为新 id
                        new_user_id = abs(hash(str(old_user_id)))

                    if new_id is not None:
                        await conn.execute(
                            "INSERT INTO sessions_new (id, user_id, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (new_id, new_user_id, state, created_at, updated_at)
                        )

                # 删除旧表并重命名新表
                await conn.execute("DROP TABLE sessions")
                await conn.execute("ALTER TABLE sessions_new RENAME TO sessions")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, updated_at DESC)")

                # 同样迁移 events 表
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS events_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id INTEGER NOT NULL,
                        event TEXT NOT NULL,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                """)

                cursor = await conn.execute("SELECT id, session_id, event, timestamp FROM events")
                rows = await cursor.fetchall()

                for row in rows:
                    old_ev_id, old_session_id, event, timestamp = row

                    # 尝试将 TEXT session_id 转换为 INTEGER
                    new_session_id = None
                    if old_session_id and str(old_session_id).isdigit():
                        new_session_id = int(old_session_id)
                    elif old_session_id:
                        new_session_id = abs(hash(str(old_session_id)))

                    if new_session_id is not None:
                        await conn.execute(
                            "INSERT INTO events_new (id, session_id, event, timestamp) VALUES (?, ?, ?, ?)",
                            (old_ev_id, new_session_id, event, timestamp)
                        )

                await conn.execute("DROP TABLE events")
                await conn.execute("ALTER TABLE events_new RENAME TO events")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp DESC)")

                # 同样迁移 memories 表
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS memories_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES sessions(id) ON DELETE CASCADE
                    )
                """)

                cursor = await conn.execute("SELECT id, user_id, content, created_at FROM memories")
                rows = await cursor.fetchall()

                for row in rows:
                    old_mem_id, old_user_id, content, created_at = row

                    # 尝试将 TEXT user_id 转换为 INTEGER
                    new_user_id = None
                    if old_user_id and str(old_user_id).isdigit():
                        new_user_id = int(old_user_id)
                    elif old_user_id:
                        new_user_id = abs(hash(str(old_user_id)))

                    if new_user_id is not None:
                        await conn.execute(
                            "INSERT INTO memories_new (id, user_id, content, created_at) VALUES (?, ?, ?, ?)",
                            (old_mem_id, new_user_id, content, created_at)
                        )

                await conn.execute("DROP TABLE memories")
                await conn.execute("ALTER TABLE memories_new RENAME TO memories")
                await conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, created_at DESC)")

                await conn.commit()
                logger.info("ID type migration to INTEGER completed")
            else:
                logger.debug("ID columns already INTEGER type")

        except Exception as e:
            logger.error(f"Migration check failed: {e}", exc_info=e)

    # ================= Session Operations =================
    async def add_message(self, session_id: int, role: str, content: str, metadata: Dict = None, **kwargs) -> bool:
        
        return True
    
    async def save_state(self, session_id: int, state: Dict[str, Any]) -> bool:
        """保存会话状态（向后兼容）"""
        user_id = state.get('user_id')
        if user_id:
            return await self.save_state_for_user(user_id, session_id, state)
        return await self.save_state_legacy(session_id, state)

    async def save_state_legacy(self, session_id: int, state: Dict[str, Any]) -> bool:
        """保存会话状态（原有方式）"""
        try:
            # 更新时间戳
            state['updated_at'] = datetime.now().timestamp()
            state['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            state_json = json.dumps(state, ensure_ascii=False)

            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, state, updated_at) VALUES (?, ?, ?)",
                    (session_id, state_json, state['last_active'])
                )
            logger.debug(f"Saved state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    async def save_state_for_user(
        self,
        user_id: int,
        session_id: int,
        state: Dict[str, Any]
    ) -> bool:
        """为指定用户保存会话状态"""
        try:
            state['user_id'] = user_id
            state['updated_at'] = datetime.now().timestamp()
            state['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            state_json = json.dumps(state, ensure_ascii=False)

            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, user_id, state, updated_at) VALUES (?, ?, ?, ?)",
                    (session_id, user_id, state_json, state['last_active'])
                )
            logger.debug(f"Saved state for user {user_id}, session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    async def load_state(self, session_id: int) -> Optional[Dict[str, Any]]:
        """加载会话状态（向后兼容）"""
        state = await self.load_state_for_user(0, session_id)
        if state:
            return state

        try:
            async with self._transaction() as conn:
                cursor = await conn.execute("SELECT state FROM sessions WHERE id = ?", (session_id,))
                row = await cursor.fetchone()
                if row:
                    state = json.loads(row[0])
                    logger.debug(f"Loaded state for session {session_id}")
                    return state
            return None
        except Exception as e:
            logger.error(f"Load state failed: {e}")
            return None

    async def load_state_for_user(
        self,
        user_id: int,
        session_id: int
    ) -> Optional[Dict[str, Any]]:
        """加载指定用户的会话状态"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT state FROM sessions WHERE id = ? AND user_id = ?",
                    (session_id, user_id)
                )
                row = await cursor.fetchone()
                if row:
                    state = json.loads(row[0])
                    logger.debug(f"Loaded state for user {user_id}, session {session_id}")
                    return state
            return None
        except Exception as e:
            logger.error(f"Load state failed: {e}")
            return None

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """列出所有会话（向后兼容）"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT state FROM sessions ORDER BY updated_at DESC"
                )
                rows = await cursor.fetchall()
                sessions = []
                for row in rows:
                    try:
                        data = json.loads(row[0])
                        sessions.append({
                            "id": data.get("session_id"),
                            "user_id": data.get("user_id"),
                            "title": data.get("title", "New Chat"),
                            "updated_at": data.get("updated_at", 0)
                        })
                    except Exception:
                        continue
                return sorted(sessions, key=lambda x: x['updated_at'], reverse=True)
        except Exception as e:
            logger.error(f"List sessions failed: {e}")
            return []

    async def list_sessions_for_user(
        self,
        user_id: int,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """列出指定用户的会话"""
        try:
            query = "SELECT state FROM sessions WHERE user_id = ? ORDER BY updated_at DESC"
            params = [user_id]

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            async with self._transaction() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()

                sessions = []
                for row in rows:
                    try:
                        data = json.loads(row[0])
                        sessions.append({
                            "id": data.get("session_id"),
                            "user_id": data.get("user_id"),
                            "title": data.get("title", "New Chat"),
                            "updated_at": data.get("updated_at", 0)
                        })
                    except Exception:
                        continue

                return sessions
        except Exception as e:
            logger.error(f"List sessions for user {user_id} failed: {e}")
            return []

    async def delete_state(self, session_id: int) -> bool:
        """删除会话状态"""
        try:
            async with self._transaction() as conn:
                await conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                await conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                await conn.execute("DELETE FROM memories WHERE user_id IN (SELECT user_id FROM sessions WHERE id = ?)", (session_id,))
            logger.debug(f"Deleted state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Delete state failed: {e}")
            return False

    async def delete_user_sessions(self, user_id: int) -> int:
        """删除指定用户的所有会话"""
        try:
            async with self._transaction() as conn:
                # 获取要删除的会话 ID
                cursor = await conn.execute(
                    "SELECT id FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                rows = await cursor.fetchall()
                session_ids = [row[0] for row in rows]

                if not session_ids:
                    return 0

                # 删除会话
                placeholders = ','.join('?' * len(session_ids))
                await conn.execute(
                    f"DELETE FROM sessions WHERE user_id = ? AND id IN ({placeholders})",
                    [user_id] + session_ids
                )

                # 级联删除事件
                if session_ids:
                    placeholders = ','.join('?' * len(session_ids))
                    await conn.execute(
                        f"DELETE FROM events WHERE session_id IN ({placeholders})",
                        session_ids
                    )

                # 级联删除记忆
                await conn.execute("DELETE FROM memories WHERE user_id = ?", (user_id,))

            logger.info(f"Deleted {len(session_ids)} sessions for user {user_id}")
            return len(session_ids)
        except Exception as e:
            logger.error(f"Delete user sessions failed: {e}")
            return 0

    # ================= Event Operations =================

    async def save_event(self, session_id: int, event: Dict[str, Any]) -> bool:
        """保存事件"""
        try:
            if 'timestamp' not in event:
                event['timestamp'] = datetime.now().isoformat()

            event_json = json.dumps(event, ensure_ascii=False)

            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT INTO events (session_id, event, timestamp) VALUES (?, ?, ?)",
                    (session_id, event_json, event['timestamp'])
                )
            logger.debug(f"Saved event for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save event failed: {e}")
            return False

    async def load_events(
        self,
        session_id: int,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """加载事件"""
        try:
            query = "SELECT event FROM events WHERE session_id = ? ORDER BY timestamp ASC"
            params = [session_id]

            if since:
                query += " AND timestamp >= ?"
                params.append(since)

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            async with self._transaction() as conn:
                cursor = await conn.execute(query, params)
                rows = await cursor.fetchall()

                events = [json.loads(row[0]) for row in rows]

            logger.debug(f"Loaded {len(events)} events for session {session_id}")
            return events
        except Exception as e:
            logger.error(f"Load events failed: {e}")
            return []

    async def delete_events(self, session_id: int, before: Optional[str] = None) -> int:
        """删除事件"""
        try:
            query = "DELETE FROM events WHERE session_id = ?"
            params = [session_id]

            if before:
                query += " AND timestamp < ?"
                params.append(before)

            async with self._transaction() as conn:
                cursor = await conn.execute(query, params)
                count = cursor.rowcount

            logger.debug(f"Deleted {count} events for session {session_id}")
            return count
        except Exception as e:
            logger.error(f"Delete events failed: {e}")
            return 0

    # ================= Memory Operations =================

    async def add_memory(self, user_id: int, content: str) -> bool:
        """添加记忆"""
        try:
            async with self._transaction() as conn:
                await conn.execute("INSERT INTO memories (user_id, content) VALUES (?, ?)", (user_id, content))
            logger.debug(f"Added memory for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Add memory failed: {e}")
            return False

    async def get_memories(self, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """获取记忆"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit)
                )
                rows = await cursor.fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"Get memories failed: {e}")
            return []

    async def search_memories(self, user_id: int, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索记忆"""
        try:
            async with self._transaction() as conn:
                like_query = f"%{query}%"
                cursor = await conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, like_query, limit)
                )
                rows = await cursor.fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"Search memories failed: {e}")
            return []

    async def delete_memory(self, memory_id: int) -> bool:
        """删除记忆"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"Deleted memory {memory_id}")
                return success
        except Exception as e:
            logger.error(f"Delete memory failed: {e}")
            return False

    # ================= User Statistics =================

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """获取用户统计信息"""
        try:
            async with self._transaction() as conn:
                # 会话统计
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE user_id = ?",
                    (user_id,)
                )
                session_count = (await cursor.fetchone())[0]

                # 事件统计
                cursor = await conn.execute("""
                    SELECT COUNT(*)
                    FROM events e
                    JOIN sessions s ON e.session_id = s.id
                    WHERE s.user_id = ?
                """, (user_id,))
                event_count = (await cursor.fetchone())[0]

                # 记忆统计
                cursor = await conn.execute(
                    "SELECT COUNT(*) FROM memories WHERE user_id = ?",
                    (user_id,)
                )
                memory_count = (await cursor.fetchone())[0]

                return {
                    "user_id": user_id,
                    "sessions": session_count,
                    "events": event_count,
                    "memories": memory_count
                }
        except Exception as e:
            logger.error(f"Get user stats failed: {e}")
            return {}

    async def list_all_users(self) -> List[Dict[str, Any]]:
        """列出所有用户（基于 sessions 表）"""
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute("""
                    SELECT user_id, COUNT(*) as session_count,
                           MAX(updated_at) as last_active
                    FROM sessions
                    WHERE user_id IS NOT NULL AND user_id != 0
                    GROUP BY user_id
                    ORDER BY last_active DESC
                """)
                rows = await cursor.fetchall()

                users = []
                for row in rows:
                    users.append({
                        "user_id": row[0],
                        "session_count": row[1],
                        "last_active": row[2]
                    })

                return users
        except Exception as e:
            logger.error(f"List users failed: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """获取全局统计信息"""
        try:
            async with self._transaction() as conn:
                # 总会话数
                cursor = await conn.execute("SELECT COUNT(*) FROM sessions")
                total_sessions = (await cursor.fetchone())[0]

                # 总用户数
                cursor = await conn.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE user_id IS NOT NULL AND user_id != 0"
                )
                total_users = (await cursor.fetchone())[0]

                # 总事件数
                cursor = await conn.execute("SELECT COUNT(*) FROM events")
                total_events = (await cursor.fetchone())[0]

                # 总记忆数
                cursor = await conn.execute("SELECT COUNT(*) FROM memories")
                total_memories = (await cursor.fetchone())[0]

                return {
                    "total_sessions": total_sessions,
                    "total_users": total_users,
                    "total_events": total_events,
                    "total_memories": total_memories,
                    "db_path": self.db_path
                }
        except Exception as e:
            logger.error(f"Get stats failed: {e}")
            return {}

    # ================= Health Check =================

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            async with self._transaction() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    # ================= Connection Management =================

    async def close(self):
        """关闭数据库连接"""
        if self._conn:
            await self._conn.close()
            self._conn = None
            logger.debug("Database connection closed")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        await self.close()

    # ================= Protocol Compliance =================

    async def get_db(self) -> "AsyncDatabaseManager":
        """获取数据库实例（向后兼容）"""
        return self

    async def get_db_async(self) -> "AsyncDatabaseManager":
        """获取异步数据库实例"""
        return self

    async def close_db(self):
        """关闭数据库连接（向后兼容）"""
        await self.close()
