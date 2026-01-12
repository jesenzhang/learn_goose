"""
会话管理器 - 支持断线重连和会话状态同步
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum

from ..db import get_db
from ..core.state import AgentStatus

logger = logging.getLogger(__name__)


class SessionState(Enum):
    """会话状态"""
    ACTIVE = "active"
    IDLE = "idle"
    DISCONNECTED = "disconnected"
    RECOVERING = "recovering"
    CLOSED = "closed"


class SessionManager:
    """会话管理器 - 管理会话生命周期、断线重连、状态同步"""

    def __init__(self, db, idle_timeout: int = 300, reconnect_timeout: int = 60):
        """
        初始化会话管理器

        Args:
            db: 数据库管理器实例
            idle_timeout: 空闲超时时间（秒），默认 5 分钟
            reconnect_timeout: 重连超时时间（秒），默认 60 秒
        """
        self.db = db
        self.idle_timeout = idle_timeout
        self.reconnect_timeout = reconnect_timeout

        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_states: Dict[str, SessionState] = {}
        self.session_locks: Dict[str, asyncio.Lock] = {}

        self._monitor_task = None
        self._running = False

    async def start(self):
        """启动会话管理器"""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_sessions())
        logger.info("SessionManager started")

    async def stop(self):
        """停止会话管理器"""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("SessionManager stopped")

    async def _monitor_sessions(self):
        """监控会话状态"""
        while self._running:
            try:
                now = datetime.now()
                expired_sessions = []

                for session_id, session_info in self.sessions.items():
                    last_activity = session_info.get("last_activity")
                    if not last_activity:
                        continue

                    idle_time = (now - last_activity).total_seconds()

                    if idle_time > self.idle_timeout:
                        state = self.session_states.get(session_id)
                        if state == SessionState.DISCONNECTED:
                            expired_sessions.append(session_id)
                        else:
                            await self._handle_idle_session(session_id)

                for session_id in expired_sessions:
                    await self._close_session(session_id)

            except Exception as e:
                logger.error(f"Error monitoring sessions: {e}", exc_info=True)

            await asyncio.sleep(30)

    async def _handle_idle_session(self, session_id: str):
        """处理空闲会话"""
        state = self.session_states.get(session_id)

        if state == SessionState.ACTIVE:
            self.session_states[session_id] = SessionState.IDLE
            logger.info(f"Session {session_id} transitioned to idle")

    async def _close_session(self, session_id: str):
        """关闭会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]

        if session_id in self.session_states:
            del self.session_states[session_id]

        if session_id in self.session_locks:
            del self.session_locks[session_id]

        logger.info(f"Closed session {session_id}")

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """获取会话锁"""
        if session_id not in self.session_locks:
            self.session_locks[session_id] = asyncio.Lock()
        return self.session_locks[session_id]

    async def create_session(
        self,
        session_id: str,
        initial_state: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        创建新会话

        Args:
            session_id: 会话 ID
            initial_state: 初始状态

        Returns:
            会话信息
        """
        async with self._get_lock(session_id):
            if session_id in self.sessions:
                logger.warning(f"Session {session_id} already exists")
                return self.sessions[session_id]

            self.sessions[session_id] = {
                "session_id": session_id,
                "created_at": datetime.now(),
                "last_activity": datetime.now(),
                "reconnect_attempts": 0,
                "last_reconnect": None,
            }

            self.session_states[session_id] = SessionState.ACTIVE

            if initial_state:
                await self.db.save_state(session_id, initial_state)

            logger.info(f"Created session {session_id}")
            return self.sessions[session_id]

    async def update_activity(self, session_id: str):
        """更新会话活动时间"""
        async with self._get_lock(session_id):
            if session_id in self.sessions:
                self.sessions[session_id]["last_activity"] = datetime.now()
                self.session_states[session_id] = SessionState.ACTIVE

    async def handle_disconnect(self, session_id: str):
        """处理断开连接"""
        async with self._get_lock(session_id):
            if session_id not in self.sessions:
                logger.warning(f"Session {session_id} not found")
                return

            self.session_states[session_id] = SessionState.DISCONNECTED
            logger.info(f"Session {session_id} disconnected")

            self.sessions[session_id]["disconnect_time"] = datetime.now()

    async def handle_reconnect(
        self,
        session_id: str,
        client_version: Optional[str] = None
    ) -> bool:
        """
        处理重连

        Args:
            session_id: 会话 ID
            client_version: 客户端版本

        Returns:
            是否重连成功
        """
        async with self._get_lock(session_id):
            if session_id not in self.sessions:
                logger.warning(f"Session {session_id} not found for reconnect")
                return False

            state = self.session_states.get(session_id)
            if state != SessionState.DISCONNECTED:
                logger.warning(f"Session {session_id} is not disconnected")
                return False

            session_info = self.sessions[session_id]
            disconnect_time = session_info.get("disconnect_time")

            if disconnect_time:
                disconnect_duration = (datetime.now() - disconnect_time).total_seconds()
                if disconnect_duration > self.reconnect_timeout:
                    logger.warning(
                        f"Reconnect timeout for session {session_id}: "
                        f"{disconnect_duration:.1f}s > {self.reconnect_timeout}s"
                    )
                    return False

            session_info["reconnect_attempts"] += 1
            session_info["last_reconnect"] = datetime.now()
            session_info["last_activity"] = datetime.now()

            self.session_states[session_id] = SessionState.RECOVERING

            logger.info(
                f"Session {session_id} reconnecting "
                f"(attempt {session_info['reconnect_attempts']})"
            )

            try:
                state = await self.db.load_state(session_id)
                if state:
                    self.session_states[session_id] = SessionState.ACTIVE
                    logger.info(f"Session {session_id} reconnected successfully")
                    return True
                else:
                    logger.warning(f"Could not load state for session {session_id}")
                    return False

            except Exception as e:
                logger.error(f"Error reconnecting session {session_id}: {e}")
                self.session_states[session_id] = SessionState.DISCONNECTED
                return False

    async def get_session_state(self, session_id: str) -> Optional[SessionState]:
        """获取会话状态"""
        return self.session_states.get(session_id)

    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        return self.sessions.get(session_id)

    async def list_active_sessions(self) -> Set[str]:
        """列出所有活跃会话"""
        return {
            sid for sid, state in self.session_states.items()
            if state == SessionState.ACTIVE
        }

    async def cleanup_session(self, session_id: str):
        """清理会话"""
        async with self._get_lock(session_id):
            if session_id in self.sessions:
                await self._close_session(session_id)

    async def sync_session_state(
        self,
        session_id: str,
        state: Dict[str, Any]
    ) -> bool:
        """
        同步会话状态到数据库

        Args:
            session_id: 会话 ID
            state: 会话状态

        Returns:
            是否同步成功
        """
        async with self._get_lock(session_id):
            try:
                success = await self.db.save_state(session_id, state)
                if success:
                    self.sessions[session_id]["last_activity"] = datetime.now()
                return success
            except Exception as e:
                logger.error(f"Error syncing session state: {e}")
                return False
