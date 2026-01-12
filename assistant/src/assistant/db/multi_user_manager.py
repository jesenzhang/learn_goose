"""
多用户数据库管理器 - 基于 AsyncDatabaseManager 扩展

支持多用户会话管理
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from .async_manager import AsyncDatabaseManager
from .protocol import DatabaseProtocol

logger = logging.getLogger(__name__)


class MultiUserAsyncDatabaseManager(AsyncDatabaseManager):
    """
    多用户异步数据库管理器

    扩展 AsyncDatabaseManager，添加多用户会话管理功能
    """

    async def initialize(self):
        """初始化数据库表结构（含迁移检查）"""
        if self._initialized:
            return

        await super().initialize()

        # 检查并执行迁移
        await self._check_and_migrate()

    async def _check_and_migrate(self):
        """检查并执行数据库迁移"""
        try:
            conn = await self._get_connection()

            # 检查 user_id 列是否存在
            cursor = await conn.execute("PRAGMA table_info(sessions)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'user_id' not in column_names:
                logger.info("Database needs migration for multi-user support")
                await self._add_user_id_column(conn)
            else:
                logger.debug("Multi-user support already enabled")

        except Exception as e:
            logger.error(f"Migration check failed: {e}", exc_info=e)

    async def _add_user_id_column(self, conn):
        """添加 user_id 列"""
        try:
            # 1. 添加 user_id 列
            await conn.execute("ALTER TABLE sessions ADD COLUMN user_id TEXT")

            # 2. 创建索引
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_user "
                "ON sessions(user_id, updated_at DESC)"
            )

            # 3. 为现有数据设置默认用户
            await conn.execute(
                "UPDATE sessions SET user_id = 'default' WHERE user_id IS NULL"
            )

            logger.info("Multi-user support migration completed")

        except Exception as e:
            logger.error(f"Failed to add user_id column: {e}", exc_info=e)
            raise

    # ================= 多用户会话操作 =================

    async def save_state_for_user(
        self,
        user_id: str,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """
        为指定用户保存会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID
            state: 状态数据（字典格式）

        Returns:
            是否保存成功
        """
        try:
            # 更新时间戳
            state['user_id'] = user_id
            state['updated_at'] = datetime.now().timestamp()
            state['last_active'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            state_json = json.dumps(state, ensure_ascii=False)

            async with self._transaction() as conn:
                await conn.execute(
                    "INSERT OR REPLACE INTO sessions (id, user_id, state, updated_at) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, user_id, state_json, state['last_active'])
                )
            logger.debug(f"Saved state for user {user_id}, session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Save state failed: {e}")
            return False

    async def load_state_for_user(
        self,
        user_id: str,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        加载指定用户的会话状态

        Args:
            user_id: 用户 ID
            session_id: 会话 ID

        Returns:
            状态数据字典，如果不存在则返回 None
        """
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

    async def list_sessions_for_user(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        列出指定用户的会话

        Args:
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            会话信息列表
        """
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

    async def delete_user_sessions(self, user_id: str) -> int:
        """
        删除指定用户的所有会话

        Args:
            user_id: 用户 ID

        Returns:
            删除的会话数量
        """
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
                await conn.execute(
                    f"DELETE FROM events WHERE session_id IN ({placeholders})",
                    session_ids
                )

                # 级联删除记忆
                await conn.execute(
                    f"DELETE FROM memories WHERE user_id = ?",
                    (user_id,)
                )

            logger.info(f"Deleted {len(session_ids)} sessions for user {user_id}")
            return len(session_ids)
        except Exception as e:
            logger.error(f"Delete user sessions failed: {e}")
            return 0

    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户统计信息

        Args:
            user_id: 用户 ID

        Returns:
            统计信息字典
        """
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
        """
        列出所有用户（基于 sessions 表）

        Returns:
            用户列表
        """
        try:
            async with self._transaction() as conn:
                cursor = await conn.execute("""
                    SELECT user_id, COUNT(*) as session_count,
                           MAX(updated_at) as last_active
                    FROM sessions
                    WHERE user_id IS NOT NULL AND user_id != 'default'
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

    async def get_global_stats(self) -> Dict[str, Any]:
        """
        获取全局统计信息

        Returns:
            全局统计信息字典
        """
        try:
            async with self._transaction() as conn:
                # 总会话数
                cursor = await conn.execute("SELECT COUNT(*) FROM sessions")
                total_sessions = (await cursor.fetchone())[0]

                # 总用户数
                cursor = await conn.execute(
                    "SELECT COUNT(DISTINCT user_id) FROM sessions WHERE user_id IS NOT NULL"
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
                    "total_memories": total_memories
                }
        except Exception as e:
            logger.error(f"Get global stats failed: {e}")
            return {}

    # ================= 覆盖原有方法以支持 user_id =================

    async def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """
        保存会话状态（向后兼容）

        如果 state 中包含 user_id，则使用用户级别的保存
        """
        user_id = state.get('user_id')
        if user_id:
            return await self.save_state_for_user(user_id, session_id, state)
        return await super().save_state(session_id, state)

    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        列出所有会话（向后兼容）

        返回所有用户的会话
        """
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

                return sessions
        except Exception as e:
            logger.error(f"List sessions failed: {e}")
            return []
