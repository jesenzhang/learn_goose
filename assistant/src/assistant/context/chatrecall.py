"""
ChatRecall Module for Assistant (Context layer)

聊天记录回忆功能：
- 搜索历史会话中的消息
- 加载特定会话的摘要（首尾消息）
- 基于日期范围过滤

适配 Assistant 项目的 Conversation 和 Message 类型
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from difflib import SequenceMatcher
import math
import json
import logging

from ..memory.session_memory import SessionMemoryUpdater

logger = logging.getLogger(__name__)


class SearchMode(Enum):
    """搜索模式"""
    QUERY = "query"
    SESSION = "session"


@dataclass
class ChatRecallResultConfig:
    """聊天记录搜索结果配置"""
    session_id: str
    messages: List[Dict[str, Any]]
    matched: bool = True
    summary: Optional[str] = None
    score: float = 0.0


@dataclass
class SessionSummaryConfig:
    """会话摘要配置"""
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
    max_session_messages: int = 20
    min_similarity: float = 0.3
    enabled: bool = True
    query_expand_max_msgs: int = 4
    query_max_chars: int = 800
    use_semantic: bool = False
    semantic_top_k: int = 20
    semantic_query_max_chars: int = 800
    semantic_doc_max_chars: int = 2000
    semantic_batch_size: int = 4
    use_rerank: bool = False
    rerank_top_k: int = 10
    rerank_threshold: float = 0.0
    session_memory_enabled: bool = True
    session_memory_use_llm: bool = False
    session_memory_recent_msgs: int = 6
    session_memory_max_chars: int = 800
    session_summary_max_chars: int = 400
    session_facts_max_items: int = 20
    session_entities_max_items: int = 30
    session_topics_max_items: int = 20


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
    ) -> List[ChatRecallResultConfig]:
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
        query_terms = [t.strip() for t in query_lower.split() if t.strip().strip()]

        for session_id, messages in (sessions or {}).items():
            if len(results) >= limit:
                break

            filtered = self._filter_by_date(messages, after_date, before_date)
            if not filtered:
                continue

            matched_messages = self._search_messages(query_terms, filtered)

            if matched_messages:
                score = self._calculate_score(query_terms, matched_messages)
                result = ChatRecallResultConfig(
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
        session_query_func=None,
        config: Optional[ChatRecallConfig] = None,
        embedding_client=None,
        reranker_client=None,
        message_builder=None,
        llm_call=None,
    ):
        """
        初始化 ChatRecall

        Args:
            session_query_func: 会话查询函数，接收查询参数返回会话数据
            config: 配置
        """
        self.session_query_func = session_query_func
        self.config = config or ChatRecallConfig()
        self.search_engine = ChatRecallSearch(self.config)
        self._session_cache: Dict[str, SessionSummaryConfig] = {}
        self.embedding_client = embedding_client
        self.reranker_client = reranker_client
        self.session_memory_updater = SessionMemoryUpdater(
            self.config, message_builder=message_builder, llm_call=llm_call
        )

    async def search(
        self,
        query: str,
        session_id: Optional[str] = None,
        limit: int = 10,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None
    ) -> List[ChatRecallResultConfig]:
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

        if self.session_query_func:
            try:
                if session_id:
                    session = await self.session_query_func(session_id=session_id)
                    if session and isinstance(session, dict):
                        sessions = {session_id: session.get("messages", [])}
                else:
                    sessions = await self.session_query_func()
                for session_id, messages in sessions.items():
                    self.search_engine.index_session(session_id, messages)
            except Exception:
                pass

        return self.search_engine.search(
            query=query,
            sessions=sessions,
            after_date=after_date,
            before_date=before_date,
            limit=limit
        )

    def build_query_from_history(
        self,
        history: List[Dict[str, Any]],
        user_input: str,
        max_msgs: int = 4,
        max_chars: int = 800
    ) -> str:
        """Expand query with recent conversation context to handle elliptical follow-ups."""
        if not history:
            return user_input
        snippets = []
        for msg in reversed(history):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            text = self._extract_message_text(msg).strip()
            if text:
                snippets.append(text)
            if len(snippets) >= max_msgs:
                break
        if not snippets:
            return user_input
        snippets.reverse()
        context = " | ".join(snippets)
        expanded = f"{user_input} | {context}"
        if max_chars and len(expanded) > max_chars:
            return expanded[:max_chars]
        return expanded

    def search_from_messages(
        self,
        query: str,
        messages: List[Dict[str, Any]],
        *,
        session_id: str,
        limit: int = 10,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None
    ) -> List[ChatRecallResultConfig]:
        """Direct search using in-memory messages without DB/session lookup."""
        sessions = {session_id: messages or []}
        self.search_engine.index_session(session_id, sessions[session_id])
        return self.search_engine.search(
            query=query,
            sessions=sessions,
            after_date=after_date,
            before_date=before_date,
            limit=limit
        )

    async def search_with_history(
        self,
        user_input: str,
        history: List[Dict[str, Any]],
        *,
        session_id: str,
        limit: int = 10,
        max_msgs: Optional[int] = None,
        max_chars: Optional[int] = None,
        after_date: Optional[str] = None,
        before_date: Optional[str] = None,
        llm: Any = None,
        session_memory: Optional[Dict[str, Any]] = None
    ) -> List[ChatRecallResultConfig]:
        """Search using expanded query built from history + current input."""
        expanded_query = self.build_query_from_history(
            history,
            user_input,
            max_msgs=max_msgs or self.config.query_expand_max_msgs,
            max_chars=max_chars or self.config.query_max_chars
        )
        query_for_search = expanded_query
        # query rewrite has moved to Context; keep expanded query only
        query_for_search = self._truncate_text(
            query_for_search,
            self.config.semantic_query_max_chars or self.config.query_max_chars,
        )
        if self.config.use_semantic and self.embedding_client:
            try:
                return await self._semantic_search_from_history(
                    query_for_search,
                    history,
                    session_id=session_id,
                    limit=limit,
                )
            except Exception as e:
                logger.warning("ChatRecall semantic search failed, fallback to lexical: %s", e)
        results = self.search_from_messages(
            query=query_for_search,
            messages=history,
            session_id=session_id,
            limit=limit,
            after_date=after_date,
            before_date=before_date,
        )
        if self.config.use_rerank and self.reranker_client and results:
            return await self._rerank_results(query_for_search, results)
        return results

    @staticmethod
    def _extract_message_text(msg: Dict[str, Any]) -> str:
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") in ("tool", "tool_response", "tool_result"):
                        continue
                    if item.get("toolResult") or item.get("tool_call_id"):
                        continue
                    if item.get("text"):
                        parts.append(str(item.get("text")))
                else:
                    parts.append(str(item))
            return " ".join(p for p in parts if p)
        return str(content)

    async def _semantic_search_from_history(
        self,
        query: str,
        history: List[Dict[str, Any]],
        *,
        session_id: str,
        limit: int = 10
    ) -> List[ChatRecallResultConfig]:
        if self.config.max_session_messages:
            history = history[-self.config.max_session_messages:]
        texts = [
            self._truncate_text(self._extract_message_text(m), self.config.semantic_doc_max_chars)
            for m in history
        ]
        if not texts:
            return []

        query_vec = await self.embedding_client.aembed_query(query)
        doc_vecs: List[List[float]] = []
        batch_size = max(1, int(self.config.semantic_batch_size))
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                doc_vecs.extend(await self.embedding_client.aembed_documents(batch))
            except Exception as e:
                logger.warning("ChatRecall embedding batch failed (size=%s): %s", len(batch), e)
                doc_vecs.extend([[] for _ in batch])

        scored = []
        for msg, vec in zip(history, doc_vecs):
            score = self._cosine_similarity(query_vec, vec)
            scored.append((score, msg))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_k = min(self.config.semantic_top_k, len(scored))
        top_scored = scored[:top_k]
        messages = [m for _, m in top_scored][:limit]
        score = top_scored[0][0] if top_scored else 0.0

        results = [
            ChatRecallResultConfig(
                session_id=session_id,
                messages=messages,
                score=score
            )
        ]

        if self.config.use_rerank and self.reranker_client:
            return await self._rerank_results(query, results)
        return results

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if not text:
            return ""
        if max_chars and len(text) > max_chars:
            return text[:max_chars]
        return text

    async def _rerank_results(
        self,
        query: str,
        results: List[ChatRecallResultConfig]
    ) -> List[ChatRecallResultConfig]:
        if not results:
            return results
        # Rerank messages within each session result.
        for res in results:
            items = res.messages
            if not items:
                continue
            reranked = await self.reranker_client.rank_objects(
                query=query,
                items=items,
                key_func=self._extract_message_text,
                top_k=min(self.config.rerank_top_k, len(items)),
                threshold=self.config.rerank_threshold,
            )
            res.messages = reranked
        return results

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    async def load_session(
        self,
        session_id: str
    ) -> Optional[SessionSummaryConfig]:
        """
        加载会话摘要

        Args:
            session_id: 会话 ID

        Returns:
            会话摘要，不存在返回 None
        """
        if session_id in self._session_cache:
            return self._session_cache[session_id]

        if not self.session_query_func:
            return None

        try:
            session = await self.session_query_func(session_id=session_id)
            if not session:
                return None

            messages = session.get("messages", [])

            max_msgs = self.config.max_session_messages
            first_msgs = messages[:max_msgs]
            last_msgs = messages[-max_msgs:] if len(messages) > max_msgs else []

            summary = SessionSummaryConfig(
                session_id=session_id,
                first_messages=first_msgs,
                last_messages=last_msgs,
                message_count=len(messages),
                created_at=session.get("created_at", datetime.now(timezone.utc).isoformat()),
                updated_at=session.get("updated_at", datetime.now(timezone.utc).isoformat()),
                system_prompt=session.get("system_prompt", None)
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

    async def update_session_memory(
        self,
        *,
        user_input: str,
        assistant_output: str,
        history: List[Dict[str, Any]],
        session_summary: Optional[str],
        session_facts: Dict[str, Any],
        session_entities: List[str],
        session_topics: List[str],
        llm: Any = None,
    ) -> Dict[str, Any]:
        """Update session memory fields after a turn."""
        return await self.session_memory_updater.update(
            user_input=user_input,
            assistant_output=assistant_output,
            history=history,
            session_summary=session_summary,
            session_facts=session_facts,
            session_entities=session_entities,
            session_topics=session_topics,
            llm=llm,
        )

    def _build_context_snippets(self, history: List[Dict[str, Any]], max_msgs: int) -> List[str]:
        snippets = []
        for msg in reversed(history):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            text = self._extract_message_text(msg).strip()
            if text:
                snippets.append(f"[{role}] {text}")
            if len(snippets) >= max_msgs:
                break
        snippets.reverse()
        return snippets

    @staticmethod
    def _format_session_memory(session_memory: Dict[str, Any]) -> str:
        if not session_memory:
            return ""
        parts = []
        if session_memory.get("summary"):
            parts.append(f"summary: {session_memory.get('summary')}")
        if session_memory.get("facts"):
            parts.append(f"facts: {json.dumps(session_memory.get('facts'), ensure_ascii=False)}")
        if session_memory.get("entities"):
            parts.append(f"entities: {session_memory.get('entities')}")
        if session_memory.get("topics"):
            parts.append(f"topics: {session_memory.get('topics')}")
        return "\n".join(parts)

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
    session_query_func=None,
    config: Optional[ChatRecallConfig] = None,
    message_builder=None,
    llm_call=None,
) -> ChatRecall:
    """
    创建 ChatRecall 实例

    Args:
        session_query_func: 会话查询函数
        config: 配置

    Returns:
        ChatRecall 实例
    """
    recall = ChatRecall(
        session_query_func=session_query_func,
        config=config,
        message_builder=message_builder,
        llm_call=llm_call,
    )
    return recall


__all__ = [
    "SearchMode",
    "ChatRecallResultConfig",
    "SessionSummaryConfig",
    "ChatRecallConfig",
    "ChatRecallSearch",
    "ChatRecall",
    "create_chat_recall",
]
