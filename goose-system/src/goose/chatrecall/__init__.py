"""
ChatRecall Module

聊天记录回忆功能：
- 搜索历史会话中的消息
- 加载特定会话的摘要（首尾消息）
- 基于日期范围过滤

Reference: goose-rs/crates/goose/src/agents/chatrecall_extension.rs
"""

import asyncio
import re
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from difflib import SequenceMatcher


class SearchMode(Enum):
    """搜索模式"""
    QUERY = "query"
    SESSION = "session"


@dataclass
class ChatRecallResult:
    """聊天记录搜索结果"""
    session_id: str
    messages: List[Dict[str, Any]]
    matched: bool = True
    summary: Optional[str] = None
    score: float = 0.0


@dataclass
class SessionSummary:
    """会话摘要"""
    session_id: str
    first_messages: List[Dict[str, Any]]
    last_messages: List[Dict[str, Any]]
    message_count: int
    created_at: str
    updated_at: str
    system_prompt: Optional[str] = None


@dataclass
class ChatRecallConfig:
    """ChatRecall 配置"""
    max_results: int = 10
    max_session_messages: int = 3
    min_similarity: float = 0.3
    enabled: bool = True


class ChatRecallSearch:
    """聊天记录搜索引擎"""
    
    def __init__(self, config: Optional[ChatRecallConfig] = None):
        self.config = config or ChatRecallConfig()
        self._index: Dict[str, List[str]] = {}
    
    def index_session(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """为会话创建索引"""
        text_parts = []
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")
            if isinstance(content, str):
                text_parts.append(f"[{role}] {content}")
            elif isinstance(content, list):
                for c in content:
                    if isinstance(c, dict):
                        text_parts.append(f"[{role}] {c.get('text', '')}")
        self._index[session_id] = text_parts
    
    def search(
        self,
        query: str,
        sessions: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None,
        limit: int = 10
    ) -> List[ChatRecallResult]:
        """
        搜索聊天记录
        
        Args:
            query: 搜索关键词
            sessions: 会话数据字典
            after_date: 开始日期 (ISO 8601)
            before_date: 结束日期 (ISO 8601)
            limit: 最大结果数
            
        Returns:
            搜索结果列表
        """
        results = []
        query_lower = query.lower()
        query_terms = [t.strip() for t in query_lower.split() if t.strip()]
        
        for session_id, messages in (sessions or {}).items():
            if len(results) >= limit:
                break
            
            filtered = self._filter_by_date(messages, after_date, before_date)
            if not filtered:
                continue
            
            matched_messages = self._search_messages(query_terms, filtered)
            
            if matched_messages:
                score = self._calculate_score(query_terms, matched_messages)
                result = ChatRecallResult(
                    session_id=session_id,
                    messages=matched_messages[:self.config.max_results],
                    score=score
                )
                results.append(result)
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results
    
    def _filter_by_date(
        self,
        messages: List[Dict[str, Any]],
        after_date: Optional[str],
        before_date: Optional[str]
    ) -> List[Dict[str, Any]]:
        """按日期过滤消息"""
        if not after_date and not before_date:
            return messages
        
        filtered = []
        for msg in messages:
            created_at = msg.get("created_at", "")
            if not created_at:
                continue
            
            try:
                msg_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if after_date:
                    after = datetime.fromisoformat(after_date.replace("Z", "+00:00"))
                    if msg_date < after:
                        continue
                if before_date:
                    before = datetime.fromisoformat(before_date.replace("Z", "+00:00"))
                    if msg_date > before:
                        continue
                filtered.append(msg)
            except ValueError:
                filtered.append(msg)
        
        return filtered
    
    def _search_messages(
        self,
        query_terms: List[str],
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """在消息中搜索"""
        matched = []
        
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = str(content)
            
            content_lower = content.lower()
            
            for term in query_terms:
                if term in content_lower:
                    matched.append(msg)
                    break
                else:
                    for word in content_lower.split():
                        similarity = SequenceMatcher(None, term, word).ratio()
                        if similarity >= self.config.min_similarity:
                            matched.append(msg)
                            break
                    else:
                        if self._fuzzy_match(term, content_lower):
                            matched.append(msg)
                            break
        
        return matched
    
    def _fuzzy_match(self, query: str, text: str) -> bool:
        """模糊匹配"""
        words = text.split()
        for word in words:
            if SequenceMatcher(None, query, word).ratio() >= 0.6:
                return True
        return False
    
    def _calculate_score(
        self,
        query_terms: List[str],
        messages: List[Dict[str, Any]]
    ) -> float:
        """计算相关性分数"""
        if not messages:
            return 0.0
        
        total_score = 0.0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                content = str(content)
            content_lower = content.lower()
            
            term_score = 0.0
            for term in query_terms:
                if term in content_lower:
                    term_score += 1.0
                else:
                    for word in content_lower.split():
                        sim = SequenceMatcher(None, term, word).ratio()
                        term_score = max(term_score, sim)
            
            total_score += term_score / len(query_terms)
        
        return min(total_score / len(messages), 1.0)


class ChatRecall:
    """
    ChatRecall 主类
    
    功能：
    - 搜索历史会话
    - 加载会话摘要
    - 管理会话索引
    """
    
    def __init__(
        self,
        session_manager: Optional[Any] = None,
        config: Optional[ChatRecallConfig] = None
    ):
        """
        初始化 ChatRecall
        
        Args:
            session_manager: 会话管理器
            config: 配置
        """
        self.session_manager = session_manager
        self.config = config or ChatRecallConfig()
        self.search_engine = ChatRecallSearch(self.config)
        self._session_cache: Dict[str, SessionSummary] = {}
    
    async def search(
        self,
        query: str,
        limit: int = 10,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None
    ) -> List[ChatRecallResult]:
        """
        搜索聊天记录
        
        Args:
            query: 搜索关键词
            limit: 最大结果数
            after_date: 开始日期
            before_date: 结束日期
            
        Returns:
            搜索结果
        """
        sessions = {}
        
        if self.session_manager:
            try:
                session_ids = await self.session_manager.list_sessions()
                for sid in session_ids:
                    session = await self.session_manager.get_session(sid)
                    if session and hasattr(session, 'messages'):
                        messages = [m.to_dict() if hasattr(m, 'to_dict') else m 
                                   for m in session.messages]
                        sessions[sid] = messages
                        self.search_engine.index_session(sid, messages)
            except Exception as e:
                pass
        
        return self.search_engine.search(
            query=query,
            sessions=sessions,
            after_date=after_date,
            before_date=before_date,
            limit=limit
        )
    
    async def load_session(
        self,
        session_id: str
    ) -> Optional[SessionSummary]:
        """
        加载会话摘要
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话摘要，不存在返回 None
        """
        if session_id in self._session_cache:
            return self._session_cache[session_id]
        
        if not self.session_manager:
            return None
        
        try:
            session = await self.session_manager.get_session(session_id)
            if not session:
                return None
            
            messages = session.messages
            if hasattr(messages[0], 'to_dict'):
                message_dicts = [m.to_dict() for m in messages]
            else:
                message_dicts = messages
            
            max_msgs = self.config.max_session_messages
            first_msgs = message_dicts[:max_msgs]
            last_msgs = message_dicts[-max_msgs:] if len(message_dicts) > max_msgs else []
            
            summary = SessionSummary(
                session_id=session_id,
                first_messages=first_msgs,
                last_messages=last_msgs,
                message_count=len(message_dicts),
                created_at=getattr(session, 'created_at', datetime.now(timezone.utc).isoformat()),
                updated_at=getattr(session, 'updated_at', datetime.now(timezone.utc).isoformat()),
                system_prompt=getattr(session, 'system_prompt', None)
            )
            
            self._session_cache[session_id] = summary
            return summary
            
        except Exception:
            return None
    
    async def recall(
        self,
        query: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 10,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        回忆聊天记录（主入口）
        
        两种模式：
        - 搜索模式：使用 query 关键词搜索
        - 加载模式：使用 session_id 获取摘要
        
        Args:
            query: 搜索关键词
            session_id: 会话 ID
            limit: 最大结果数
            after_date: 开始日期
            before_date: 结束日期
            
        Returns:
            结果字典
        """
        if session_id:
            summary = await self.load_session(session_id)
            if summary:
                return {
                    "mode": "load",
                    "session_id": session_id,
                    "summary": {
                        "message_count": summary.message_count,
                        "first_messages": summary.first_messages,
                        "last_messages": summary.last_messages,
                        "created_at": summary.created_at,
                        "system_prompt": summary.system_prompt
                    }
                }
            return {
                "mode": "load",
                "error": f"Session not found: {session_id}"
            }
        
        if query:
            results = await self.search(
                query=query,
                limit=limit,
                after_date=after_date,
                before_date=before_date
            )
            return {
                "mode": "search",
                "query": query,
                "results": [
                    {
                        "session_id": r.session_id,
                        "messages": r.messages,
                        "score": r.score
                    }
                    for r in results
                ]
            }
        
        return {
            "mode": "error",
            "error": "Either query or session_id is required"
        }
    
    def index_session(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """为会话创建索引"""
        self.search_engine.index_session(session_id, messages)
    
    def clear_cache(self) -> None:
        """清除缓存"""
        self._session_cache.clear()
        self.search_engine._index.clear()
    
    def reindex_all(self, sessions: Dict[str, List[Dict[str, Any]]]) -> int:
        """重新索引所有会话"""
        self.clear_cache()
        count = 0
        for session_id, messages in sessions.items():
            self.index_session(session_id, messages)
            count += 1
        return count


async def create_chat_recall(
    session_manager: Optional[Any] = None,
    config: Optional[ChatRecallConfig] = None
) -> ChatRecall:
    """
    创建 ChatRecall 实例
    
    Args:
        session_manager: 会话管理器
        config: 配置
        
    Returns:
        ChatRecall 实例
    """
    recall = ChatRecall(session_manager=session_manager, config=config)
    return recall
