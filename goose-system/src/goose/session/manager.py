"""
Session Module

会话管理模块，提供：
- 会话状态持久化
- 会话历史管理
- 会话恢复机制
- 跨会话状态共享

Reference: goose-rs session 模块设计
"""

import json
import uuid
import asyncio
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod


class SessionEventType(str, Enum):
    """会话事件类型"""
    CREATED = "created"
    LOADED = "loaded"
    SAVED = "saved"
    CLOSED = "closed"
    DELETED = "deleted"
    MESSAGE_ADDED = "message_added"
    STATE_CHANGED = "state_changed"


@dataclass
class SessionEvent:
    """会话事件"""
    type: SessionEventType
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionMessage:
    """会话消息"""
    role: str
    content: str
    tool_name: Optional[str] = None
    tool_result: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.tool_name:
            result["tool_name"] = self.tool_name
        if self.tool_result:
            result["tool_result"] = self.tool_result
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionMessage":
        return cls(
            role=data["role"],
            content=data["content"],
            tool_name=data.get("tool_name"),
            tool_result=data.get("tool_result"),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    messages: List[SessionMessage] = field(default_factory=list)
    system_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    max_turns: int = 100
    
    def add_message(self, role: str, content: str, **kwargs) -> SessionMessage:
        """添加消息"""
        msg = SessionMessage(
            role=role,
            content=content,
            tool_name=kwargs.get("tool_name"),
            tool_result=kwargs.get("tool_result"),
            metadata=kwargs.get("metadata", {})
        )
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc).isoformat()
        return msg
    
    def add_tool_result(self, tool_name: str, result: str) -> None:
        """添加工具结果"""
        self.messages.append(SessionMessage(
            role="tool",
            content=result,
            tool_name=tool_name
        ))
    
    def can_continue(self) -> bool:
        """检查是否可以继续"""
        return self.turn_count < self.max_turns
    
    def increment_turn(self) -> None:
        """增加轮次"""
        self.turn_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "messages": [m.to_dict() for m in self.messages],
            "system_prompt": self.system_prompt,
            "metadata": self.metadata,
            "turn_count": self.turn_count,
            "max_turns": self.max_turns,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        messages = [SessionMessage.from_dict(m) for m in data.get("messages", [])]
        return cls(
            session_id=data["session_id"],
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            messages=messages,
            system_prompt=data.get("system_prompt"),
            metadata=data.get("metadata", {}),
            turn_count=data.get("turn_count", 0),
            max_turns=data.get("max_turns", 100)
        )


class SessionBackend(ABC):
    """会话存储后端抽象"""
    
    @abstractmethod
    async def save(self, session: SessionState) -> None:
        """保存会话"""
        pass
    
    @abstractmethod
    async def load(self, session_id: str) -> Optional[SessionState]:
        """加载会话"""
        pass
    
    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """删除会话"""
        pass
    
    @abstractmethod
    async def list_sessions(self) -> List[str]:
        """列出所有会话"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭后端"""
        pass


class MemorySessionBackend(SessionBackend):
    """内存会话存储（用于测试和临时会话）"""
    
    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
    
    async def save(self, session: SessionState) -> None:
        async with self._lock:
            self._sessions[session.session_id] = session
    
    async def load(self, session_id: str) -> Optional[SessionState]:
        async with self._lock:
            return self._sessions.get(session_id)
    
    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    async def list_sessions(self) -> List[str]:
        async with self._lock:
            return list(self._sessions.keys())
    
    async def close(self) -> None:
        self._sessions.clear()


class FileSessionBackend(SessionBackend):
    """文件系统会话存储"""
    
    def __init__(self, storage_dir: str = "./sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
    
    def _get_session_path(self, session_id: str) -> Path:
        """获取会话文件路径"""
        return self.storage_dir / f"{session_id}.json"
    
    async def save(self, session: SessionState) -> None:
        async with self._lock:
            path = self._get_session_path(session.session_id)
            data = session.to_dict()
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    
    async def load(self, session_id: str) -> Optional[SessionState]:
        async with self._lock:
            path = self._get_session_path(session_id)
            if not path.exists():
                return None
            try:
                data = json.loads(path.read_text())
                return SessionState.from_dict(data)
            except Exception:
                return None
    
    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            path = self._get_session_path(session_id)
            if path.exists():
                path.unlink()
                return True
            return False
    
    async def list_sessions(self) -> List[str]:
        async with self._lock:
            sessions = []
            for f in self.storage_dir.glob("*.json"):
                sessions.append(f.stem)
            return sessions
    
    async def close(self) -> None:
        pass


class SessionManager:
    """
    会话管理器
    
    职责：
    - 创建和管理会话
    - 会话状态持久化
    - 会话历史压缩
    - 跨会话状态共享
    """
    
    def __init__(
        self,
        backend: Optional[SessionBackend] = None,
        max_history: int = 1000,
        compact_threshold: float = 0.8
    ):
        self.backend = backend or MemorySessionBackend()
        self.max_history = max_history
        self.compact_threshold = compact_threshold
        self._active_sessions: Dict[str, SessionState] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
    
    async def create_session(
        self,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_turns: int = 100,
        **kwargs
    ) -> SessionState:
        """创建新会话"""
        sid = session_id or f"session_{uuid.uuid4().hex[:12]}"
        
        session = SessionState(
            session_id=sid,
            system_prompt=system_prompt,
            max_turns=max_turns,
            metadata=kwargs
        )
        
        async with self._lock:
            self._active_sessions[sid] = session
        
        await self.backend.save(session)
        
        await self._emit_event(SessionEvent(
            type=SessionEventType.CREATED,
            data={"session_id": sid}
        ))
        
        return session
    
    async def get_session(self, session_id: str) -> Optional[SessionState]:
        """获取会话"""
        async with self._lock:
            if session_id in self._active_sessions:
                return self._active_sessions[session_id]
        
        session = await self.backend.load(session_id)
        if session:
            async with self._lock:
                self._active_sessions[session_id] = session
        
        return session
    
    async def save_session(self, session: SessionState) -> None:
        """保存会话"""
        async with self._lock:
            self._active_sessions[session.session_id] = session
        
        await self.backend.save(session)
        
        await self._emit_event(SessionEvent(
            type=SessionEventType.SAVED,
            data={"session_id": session.session_id}
        ))
    
    async def close_session(self, session_id: str) -> None:
        """关闭会话"""
        async with self._lock:
            session = self._active_sessions.pop(session_id, None)
        
        if session:
            await self.backend.save(session)
            
            await self._emit_event(SessionEvent(
                type=SessionEventType.CLOSED,
                data={"session_id": session_id}
            ))
    
    async def delete_session(self, session_id: str) -> bool:
        """删除会话"""
        async with self._lock:
            self._active_sessions.pop(session_id, None)
        
        deleted = await self.backend.delete(session_id)
        if deleted:
            await self._emit_event(SessionEvent(
                type=SessionEventType.DELETED,
                data={"session_id": session_id}
            ))
        
        return deleted
    
    async def list_sessions(self) -> List[str]:
        """列出所有会话"""
        backend_sessions = await self.backend.list_sessions()
        active_sessions = list(self._active_sessions.keys())
        
        all_sessions = set(backend_sessions) | set(active_sessions)
        return sorted(list(all_sessions))
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        **kwargs
    ) -> Optional[SessionMessage]:
        """添加消息"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        message = session.add_message(role, content, **kwargs)
        await self.save_session(session)
        
        await self._emit_event(SessionEvent(
            type=SessionEventType.MESSAGE_ADDED,
            data={"session_id": session_id, "role": role}
        ))
        
        if len(session.messages) > self.max_history * self.compact_threshold:
            await self._compact_session(session)
        
        return message
    
    async def _compact_session(self, session: SessionState) -> None:
        """压缩会话历史"""
        keep_messages = min(10, self.max_history // 10)
        
        system_messages = [
            m for m in session.messages 
            if m.role == "system"
        ]
        
        recent_messages = session.messages[-keep_messages:]
        
        session.messages = system_messages + recent_messages
        
        await self.save_session(session)
        
        await self._emit_event(SessionEvent(
            type=SessionEventType.STATE_CHANGED,
            data={
                "session_id": session.session_id,
                "action": "compacted",
                "message_count": len(session.messages)
            }
        ))
    
    async def clone_session(
        self,
        session_id: str,
        new_session_id: Optional[str] = None
    ) -> Optional[SessionState]:
        """克隆会话"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        new_sid = new_session_id or f"{session_id}_clone_{uuid.uuid4().hex[:6]}"
        
        new_session = SessionState(
            session_id=new_sid,
            system_prompt=session.system_prompt,
            max_turns=session.max_turns,
            metadata={"cloned_from": session_id, **session.metadata}
        )
        
        new_session.messages = session.messages.copy()
        
        await self.save_session(new_session)
        
        return new_session
    
    async def export_session(self, session_id: str) -> Optional[str]:
        """导出会话为 JSON 字符串"""
        session = await self.get_session(session_id)
        if not session:
            return None
        return json.dumps(session.to_dict(), indent=2, ensure_ascii=False)
    
    async def import_session(
        self,
        json_data: str,
        new_session_id: Optional[str] = None
    ) -> Optional[SessionState]:
        """从 JSON 导入会话"""
        try:
            data = json.loads(json_data)
            session = SessionState.from_dict(data)
            
            if new_session_id:
                session.session_id = new_session_id
            
            await self.save_session(session)
            return session
        except Exception:
            return None
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息摘要"""
        session = await self.get_session(session_id)
        if not session:
            return None
        
        return {
            "session_id": session.session_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "message_count": len(session.messages),
            "turn_count": session.turn_count,
            "max_turns": session.max_turns,
            "has_system_prompt": session.system_prompt is not None,
        }
    
    async def close_all(self) -> None:
        """关闭所有活跃会话"""
        for session_id in list(self._active_sessions.keys()):
            await self.close_session(session_id)
        await self.backend.close()
    
    async def _emit_event(self, event: SessionEvent) -> None:
        """发出事件"""
        await self._events.put(event)
    
    async def events(self) -> AsyncIterator[SessionEvent]:
        """事件流"""
        while True:
            try:
                event = await asyncio.wait_for(
                    self._events.get(),
                    timeout=1.0
                )
                yield event
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
    
    def get_active_session_count(self) -> int:
        """获取活跃会话数量"""
        return len(self._active_sessions)


class SharedStateManager:
    """
    跨会话共享状态管理器
    """
    
    def __init__(self):
        self._state: Dict[str, Any] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock = asyncio.Lock()
    
    async def set(self, key: str, value: Any) -> None:
        """设置共享状态"""
        async with self._lock:
            self._state[key] = value
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
    
    async def get(self, key: str, default: Any = None) -> Any:
        """获取共享状态"""
        async with self._lock:
            return self._state.get(key, default)
    
    async def delete(self, key: str) -> bool:
        """删除共享状态"""
        async with self._lock:
            if key in self._state:
                del self._state[key]
                if key in self._locks:
                    del self._locks[key]
                return True
            return False
    
    async def acquire_lock(self, key: str) -> asyncio.Lock:
        """获取状态的锁"""
        async with self._lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]
    
    async def clear(self) -> None:
        """清空所有状态"""
        async with self._lock:
            self._state.clear()
            self._locks.clear()
    
    def keys(self) -> List[str]:
        """获取所有键"""
        return list(self._state.keys())


def create_session_manager(
    storage_dir: Optional[str] = None,
    **kwargs
) -> SessionManager:
    """创建会话管理器工厂函数"""
    if storage_dir:
        backend = FileSessionBackend(storage_dir)
    else:
        backend = MemorySessionBackend()
    
    return SessionManager(backend=backend, **kwargs)
