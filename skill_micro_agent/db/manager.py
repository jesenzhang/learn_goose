"""
Database Implementation Module.
Handles SQLite connections, pooling, and queries.
"""

import sqlite3
import json
import logging
import threading
from datetime import datetime
from typing import Dict, List, Any, Optional
from contextlib import contextmanager

# 引入 Core 中的 State 定义
from skill_micro_agent.core.state import AgentState

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Database manager with connection pooling and proper transaction handling.
    """

    def __init__(self, db_path: str = "agent_ultra.db", pool_size: int = 5):
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

    def save_state(self, state: AgentState) -> bool:
        try:
            state.updated_at = datetime.now().timestamp()
            state.last_active = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._transaction() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, state, updated_at) VALUES (?, ?, ?)",
                    (state.session_id, state.to_json(), state.last_active)
                )
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    def load_state(self, session_id: str) -> Optional[AgentState]:
        try:
            with self._transaction() as conn:
                row = conn.execute("SELECT state FROM sessions WHERE id = ?", (session_id,)).fetchone()
                if row:
                    return AgentState.from_json(row[0])
            return None
        except Exception as e:
            logger.error(f"Load state failed: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
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
                    except: continue
                return sorted(sessions, key=lambda x: x['updated_at'], reverse=True)
        except Exception:
            return []

    def delete_session(self, session_id: str) -> bool:
        try:
            with self._transaction() as conn:
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
                conn.execute("DELETE FROM memories WHERE user_id = ?", (session_id,))
            return True
        except Exception:
            return False

    # ================= Memory Ops =================

    def add_memory(self, user_id: str, content: str) -> bool:
        try:
            with self._transaction() as conn:
                conn.execute("INSERT INTO memories (user_id, content) VALUES (?, ?)", (user_id, content))
            return True
        except Exception as e:
            logger.error(f"Add memory failed: {e}")
            return False

    def get_memories(self, user_id: str, limit: int = 100) -> List[Dict]:
        try:
            with self._transaction() as conn:
                rows = conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, limit)
                ).fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception:
            return []

    def search_memories(self, user_id: str, query: str, limit: int = 20) -> List[Dict]:
        try:
            with self._transaction() as conn:
                like_query = f"%{query}%"
                rows = conn.execute(
                    "SELECT id, content, created_at FROM memories WHERE user_id = ? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (user_id, like_query, limit)
                ).fetchall()
                return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in rows]
        except Exception:
            return []

    def delete_memory(self, memory_id: int) -> bool:
        try:
            with self._transaction() as conn:
                cursor = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                return cursor.rowcount > 0
        except Exception:
            return False

    def close(self):
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None