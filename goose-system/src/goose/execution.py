"""
Agent Manager

集中式 Agent 生命周期管理，支持：
- 会话隔离的 Agent 实例
- LRU Cache 缓存管理
- 最大会话数限制
- Scheduler 集成
- SessionManager 集成
- 默认 Provider 设置

Reference: goose-rs/crates/goose/src/execution/manager.rs
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum
import uuid
from datetime import datetime
from collections import OrderedDict
import threading

logger = logging.getLogger("goose.execution")


class SessionExecutionMode(str, Enum):
    """会话执行模式"""
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    SUBTASK = "subtask"
    
    @classmethod
    def chat(cls) -> 'SessionExecutionMode':
        """交互式聊天模式"""
        return cls.INTERACTIVE
    
    @classmethod
    def scheduled(cls) -> 'SessionExecutionMode':
        """后台/计划任务模式"""
        return cls.BACKGROUND
    
    @classmethod
    def task(cls, parent: str) -> 'SessionExecutionMode':
        """子任务模式"""
        return cls.SUBTASK


class AgentInfo:
    """Agent 信息"""
    
    def __init__(
        self,
        agent: Any,
        session_id: str,
        created_at: datetime,
        last_active: datetime,
        execution_mode: SessionExecutionMode,
        parent_session: Optional[str] = None,
    ):
        self.agent = agent
        self.session_id = session_id
        self.created_at = created_at
        self.last_active = last_active
        self.execution_mode = execution_mode
        self.parent_session = parent_session
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "execution_mode": self.execution_mode.value,
            "parent_session": self.parent_session,
        }


class LRUCache:
    """LRU Cache 实现"""
    
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """获取值"""
        with self.lock:
            if key not in self.cache:
                return None
            self.cache.move_to_end(key)
            return self.cache[key]
    
    def put(self, key: str, value: Any) -> None:
        """插入值"""
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            # 超过容量时移除最旧的项
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
    
    def pop(self, key: str) -> Optional[Any]:
        """移除并返回"""
        with self.lock:
            return self.cache.pop(key, None)
    
    def contains(self, key: str) -> bool:
        """检查是否存在"""
        with self.lock:
            return key in self.cache
    
    def keys(self) -> List[str]:
        """获取所有键"""
        with self.lock:
            return list(self.cache.keys())
    
    def len(self) -> int:
        """获取长度"""
        with self.lock:
            return len(self.cache)
    
    def clear(self) -> None:
        """清空"""
        with self.lock:
            self.cache.clear()


class AgentManager:
    """
    Agent 生命周期管理器
    
    功能：
    - 集中管理多个 Agent 实例
    - 会话隔离
    - LRU Cache 缓存
    - 最大会话数限制
    - 默认 Provider 设置
    """
    
    DEFAULT_MAX_SESSIONS = 100
    
    _instance: Optional['AgentManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'AgentManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = AgentManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'AgentManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(
        self,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        session_manager: Optional[Any] = None,
        scheduler: Optional[Any] = None,
    ):
        """
        初始化 AgentManager
        
        Args:
            max_sessions: 最大会话数
            session_manager: SessionManager 实例
            scheduler: Scheduler 实例
        """
        self._max_sessions = max_sessions
        self._session_manager = session_manager
        self._scheduler = scheduler
        self._default_provider = None
        
        # Agent 实例缓存
        self._agents = LRUCache(max_sessions)
        
        # Agent 信息缓存
        self._agent_info: Dict[str, AgentInfo] = {}
        
        # 默认 Provider
        self._default_provider_lock = threading.Lock()
        
        self._lock = threading.Lock()
        
        logger.info(f"AgentManager initialized with max_sessions={max_sessions}")
    
    @property
    def scheduler(self):
        """获取 Scheduler"""
        return self._scheduler
    
    @property
    def session_manager(self):
        """获取 SessionManager"""
        return self._session_manager
    
    def set_default_provider(self, provider: Any) -> None:
        """设置默认 Provider"""
        with self._default_provider_lock:
            self._default_provider = provider
        logger.info("Default provider set on AgentManager")
    
    async def get_or_create_agent(
        self,
        session_id: str,
        execution_mode: SessionExecutionMode = SessionExecutionMode.INTERACTIVE,
        parent_session: Optional[str] = None,
    ) -> Any:
        """
        获取或创建 Agent
        
        Args:
            session_id: 会话 ID
            execution_mode: 执行模式
            parent_session: 父会话 ID (用于子任务)
            
        Returns:
            Agent 实例
        """
        # 检查是否已有缓存的 Agent
        existing_agent = self._agents.get(session_id)
        if existing_agent is not None:
            # 更新最后活跃时间
            if session_id in self._agent_info:
                self._agent_info[session_id].last_active = datetime.utcnow()
            return existing_agent
        
        # 创建新的 Agent
        agent = await self._create_agent(
            session_id=session_id,
            execution_mode=execution_mode,
            parent_session=parent_session,
        )
        
        # 缓存 Agent
        self._agents.put(session_id, agent)
        
        # 记录 Agent 信息
        self._agent_info[session_id] = AgentInfo(
            agent=agent,
            session_id=session_id,
            created_at=datetime.utcnow(),
            last_active=datetime.utcnow(),
            execution_mode=execution_mode,
            parent_session=parent_session,
        )
        
        logger.info(f"Created new agent for session: {session_id}")
        return agent
    
    async def _create_agent(
        self,
        session_id: str,
        execution_mode: SessionExecutionMode,
        parent_session: Optional[str],
    ) -> Any:
        """创建新的 Agent 实例"""
        from ..agent import Agent, AgentConfig
        from ..providers import ProviderFactory
        
        # 获取配置
        max_turns = 100
        if self._session_manager:
            try:
                session = self._session_manager.get_session(session_id)
                if session:
                    max_turns = session.config.max_turns or 100
            except:
                pass
        
        # 获取 Goose Mode
        from ..config import get_config
        config = get_config()
        goose_mode = config.get_goose_mode()
        
        # 创建 Agent 配置
        agent_config = AgentConfig(
            session_id=session_id,
            max_turns=max_turns,
            chat_mode=(execution_mode == SessionExecutionMode.INTERACTIVE),
        )
        
        # 创建 Agent
        agent = Agent(config=agent_config)
        
        # 设置默认 Provider (如果有)
        with self._default_provider_lock:
            if self._default_provider is not None:
                try:
                    await agent.update_provider(self._default_provider)
                except Exception as e:
                    logger.warning(f"Failed to set default provider: {e}")
        
        return agent
    
    async def remove_session(self, session_id: str) -> bool:
        """
        移除会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            是否成功移除
        """
        agent = self._agents.pop(session_id)
        if agent:
            if session_id in self._agent_info:
                del self._agent_info[session_id]
            
            # 清理 Agent 资源
            try:
                if hasattr(agent, 'close'):
                    await agent.close()
            except:
                pass
            
            logger.info(f"Removed session: {session_id}")
            return True
        
        return False
    
    def has_session(self, session_id: str) -> bool:
        """检查会话是否存在"""
        return self._agents.contains(session_id)
    
    def session_count(self) -> int:
        """获取会话数量"""
        return self._agents.len()
    
    def get_session_ids(self) -> List[str]:
        """获取所有会话 ID"""
        return self._agents.keys()
    
    def get_agent_info(self, session_id: str) -> Optional[AgentInfo]:
        """获取 Agent 信息"""
        return self._agent_info.get(session_id)
    
    def get_all_agent_info(self) -> List[AgentInfo]:
        """获取所有 Agent 信息"""
        return list(self._agent_info.values())
    
    def get_active_sessions(self) -> List[str]:
        """获取活跃会话列表 (最近活跃的)"""
        active = []
        for session_id in self._agent_info:
            info = self._agent_info[session_id]
            # 5分钟内活跃的会话
            if (datetime.utcnow() - info.last_active).total_seconds() < 300:
                active.append(session_id)
        return active
    
    def clear_all_sessions(self) -> None:
        """清除所有会话"""
        self._agents.clear()
        self._agent_info.clear()
        logger.info("All sessions cleared")
    
    @property
    def max_sessions(self) -> int:
        """获取最大会话数"""
        return self._max_sessions


class ExecutionContext:
    """执行上下文"""
    
    def __init__(
        self,
        session_id: str,
        execution_mode: SessionExecutionMode = SessionExecutionMode.INTERACTIVE,
        parent_session: Optional[str] = None,
        agent_manager: Optional[AgentManager] = None,
    ):
        self.session_id = session_id
        self.execution_mode = execution_mode
        self.parent_session = parent_session
        self.agent_manager = agent_manager or AgentManager.get_instance()
        self._agent = None
    
    async def get_agent(self) -> Any:
        """获取 Agent"""
        if self._agent is None:
            self._agent = await self.agent_manager.get_or_create_agent(
                session_id=self.session_id,
                execution_mode=self.execution_mode,
                parent_session=self.parent_session,
            )
        return self._agent
    
    async def run(self, message: str) -> str:
        """运行对话"""
        agent = await self.get_agent()
        response = await agent.reply(message)
        return response
    
    async def close(self) -> None:
        """关闭上下文"""
        if self._agent:
            await self.agent_manager.remove_session(self.session_id)
            self._agent = None


# 快捷函数

def get_agent_manager() -> AgentManager:
    """获取 AgentManager 单例"""
    return AgentManager.get_instance()


async def get_or_create_agent(
    session_id: str,
    execution_mode: SessionExecutionMode = SessionExecutionMode.INTERACTIVE,
    parent_session: Optional[str] = None,
) -> Any:
    """获取或创建 Agent"""
    return await get_agent_manager().get_or_create_agent(
        session_id=session_id,
        execution_mode=execution_mode,
        parent_session=parent_session,
    )


def create_execution_context(
    session_id: str,
    execution_mode: SessionExecutionMode = SessionExecutionMode.INTERACTIVE,
    parent_session: Optional[str] = None,
) -> ExecutionContext:
    """创建执行上下文"""
    return ExecutionContext(
        session_id=session_id,
        execution_mode=execution_mode,
        parent_session=parent_session,
    )
