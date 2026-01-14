"""
Database Implementation Module.
Handles SQLite connections, pooling, and queries.

使用通用的字典操作，不依赖具体的状态类型
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Database manager with connection pooling and proper transaction handling.

    操作通用的字典数据，不依赖具体的状态类型
    """

    def __init__(self, db_path: str = "agent_ultra.db", pool_size: int = 5):
        """
        初始化数据库管理器

        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小（预留参数）
        """
        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._initialized = False

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection from pool."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database transaction error: {e}", exc_info=e)
            raise

    def initialize(self):
        """Initialize database schema."""
        if self._initialized:
            return

        with self._transaction() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

            # Sessions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Events Table - 用于事件回放
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, timestamp DESC)")

            # Memories Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id, created_at DESC)")

            self._initialized = True
            logger.info(f"Database initialized at {self.db_path}")

    # ================= Session Ops =================

    def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """
        保存会话状态

        Args:
            session_id: 会话 ID
            state: 状态数据（字典格式）

        Returns:
            是否保存成功
        """
        try:
            # 更新时间戳
            state['updated_at'] = datetime.now().timestamp()
            state['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            state_json = json.dumps(state, ensure_ascii=False)

            with self._transaction() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, state, updated_at) VALUES (?, ?, ?)",
                    (session_id, state_json, state['last_active'])
                )
            logger.debug(f"Saved state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        加载会话状态

        Args:
            session_id: 会话 ID

        Returns:
            状态数据字典，如果不存在则返回 None
        """
        try:
            with self._transaction() as conn:
                row = conn.execute("SELECT state FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if row:
                    state = json.loads(row[0])
                    logger.debug(f"Loaded state for session {session_id}")
                    return state
            return None
        except Exception as e:
            logger.error(f"Load state failed: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话

        Returns:
            会话信息列表
        """
        try:
            with self._transaction() as conn:
                rows = conn.execute("SELECT state FROM sessions").fetchall()
                sessions = []
                for row in rows:
                    try:
                        data = json.loads(row[0])
                        sessions.append({
                            "id": data.get("session_id"),
                            "title": data.get("title", "New Chat"),
                            "updated_at": data.get("updated_at", 0)
                        })
                    except Exception:
                        continue
                return sorted(sessions, key=lambda x: x['updated_at'], reverse=True)
        except Exception as e:
            logger.error(f"List sessions failed: {e}")
            return []

    def delete_state(self, session_id: str) -> bool:
        """
        删除会话状态

        Args:
            session_id: 会话 ID

        Returns:
            是否删除成功
        """
        try:
            with self._transaction() as conn:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM memories WHERE user_id = ?", (session_id,))
            logger.debug(f"Deleted state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Delete state failed: {e}")
            return False

    # ================= Event Ops =================

    def save_event(self, session_id: str, event: Dict[str, Any]) -> bool:
        """
        保存事件

        Args:
            session_id: 会话 ID
            event: 事件数据（字典格式）

        Returns:
            是否保存成功
        """
        try:
            # 添加时间戳（如果没有）
            if 'timestamp' not in event:
                event['timestamp'] = datetime.now().isoformat()

            event_json = json.dumps(event, ensure_ascii=False)

            with self._transaction() as conn:
                conn.execute(
                    "INSERT INTO events (session_id, event, timestamp) VALUES (?, ?, ?)",
                    (session_id, event_json, event['timestamp'])
                )
            logger.debug(f"Saved event for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save event failed: {e}")
            return False

    def load_events(
        self,
        session_id: str,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        加载事件

        Args:
            session_id: 会话 ID
            limit: 返回数量限制
            since: 起始时间（ISO 格式）

        Returns:
            事件列表
        """
        try:
            query = "SELECT event FROM events WHERE session_id = ?"
            params = [session_id]

            if since:
                query += " AND timestamp >= ?"
                params.append(since)

            query += " ORDER BY timestamp ASC"

            if limit:
                query += " LIMIT ?"
                params.append(limit)

            with self._transaction() as conn:
                rows = conn.execute(query, params).fetchall()
                events = [json.loads(row[0]) for row in rows]

            logger.debug(f"Loaded {len(events)} events for session {session_id}")
            return events
        except Exception as e:
            logger.error(f"Load events failed: {e}")
            return []

    def delete_events(self, session_id: str, before: Optional[str] = None) -> int:
        """
        删除事件

        Args:
            session_id: 会话 ID
            before: 删除此时间之前的事件

        Returns:
            删除的事件数量
        """
        try:
            query = "DELETE FROM events WHERE session_id = ?"
            params = [session_id]

            if before:
                query += " AND timestamp < ?"
                params.append(before)

            with self._transaction() as conn:
                cursor = conn.execute(query, params)
                count = cursor.rowcount

            logger.debug(f"Deleted {count} events for session {session_id}")
            return count
        except Exception as e:
            logger.error(f"Delete events failed: {e}")
            return 0

    # ================= Memory Ops =================

    def add_memory(self, user_id: str, content: str) -> bool:
        """
        添加记忆

        Args:
            user_id: 用户/会话 ID
            content: 记忆内容

        Returns:
            是否添加成功
        """
        try:
            with self._transaction() as conn:
                conn.execute("INSERT INTO memories (user_id, content) VALUES (?, ?)", (user_id, content))
            logger.debug(f"Added memory for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Add memory failed: {e}")
            return False

    def get_memories(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        获取记忆

        Args:
            user_id: 用户/会话 ID
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        try:
            with self._transaction() as conn:
                rows = conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"Get memories failed: {e}")
            return []

    def search_memories(self, user_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索记忆

        Args:
            user_id: 用户/会话 ID
            query: 搜索关键词
            limit: 返回数量限制

        Returns:
            记忆列表
        """
        try:
            with self._transaction() as conn:
                like_query = f"%{query}%"
                rows = conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, like_query, limit)
                ).fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception as e:
            logger.error(f"Search memories failed: {e}")
            return []

    def delete_memory(self, memory_id: int) -> bool:
        """
        删除记忆

        Args:
            memory_id: 记忆 ID

        Returns:
            是否删除成功
        """
        try:
            with self._transaction() as conn:
                cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                success = cursor.rowcount > 0
                if success:
                    logger.debug(f"Deleted memory {memory_id}")
                return success
        except Exception as e:
            logger.error(f"Delete memory failed: {e}")
            return False

    # ================= Health Check =================
       
    def health_check(self) -> bool:
        """
        健康检查

        Returns:
            数据库是否可用
        """
        try:
            with self._transaction() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息

        Returns:
            统计信息字典
        """
        try:
            with self._transaction() as conn:
                session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
                memory_count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]

                return {
                    "sessions": session_count,
                    "events": event_count,
                    "memories": memory_count,
                    "db_path": self.db_path
                }
        except Exception as e:
            logger.error(f"Get stats failed: {e}")
            return {}

    # ================= Connection Management =================

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
            logger.debug("Database connection closed")
