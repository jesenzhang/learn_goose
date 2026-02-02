"""
Query rewrite module for memory.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from .llm_adapter import default_message_builder, default_llm_call

DEFAULT_QUERY_REWRITE_PROMPT = (
    "You are a query rewriting assistant. Rewrite the user query to be explicit and "
    "self-contained using the provided conversation context and session memory. "
    "Keep it short and focused. Output ONLY the rewritten query text, no quotes, no extra text."
)


class QueryRewriter:
    def __init__(
        self,
        config: Any,
        *,
        message_builder: Optional[Callable[[str, str], List[Any]]] = None,
        llm_call: Optional[Callable[[Any, List[Any]], Any]] = None,
    ):
        self.config = config
        self._message_builder = message_builder or default_message_builder
        self._llm_call = llm_call or default_llm_call

    async def rewrite(
        self,
        *,
        user_input: str,
        history: List[Dict[str, Any]],
        session_memory: Dict[str, Any],
        llm: Any,
    ) -> str:
        if not getattr(self.config, "query_rewrite_enabled", False) or not llm:
            return user_input
        prompt = getattr(self.config, "query_rewrite_prompt", None) or DEFAULT_QUERY_REWRITE_PROMPT
        snippets = self._build_context_snippets(history, getattr(self.config, "query_rewrite_max_msgs", 6))
        memory_text = self._format_session_memory(session_memory)
        context_parts = []
        if memory_text:
            context_parts.append(f"SessionMemory:\n{memory_text}")
        if snippets:
            context_parts.append("RecentMessages:\n" + "\n".join(snippets))
        context_parts.append(f"UserQuery:\n{user_input}")
        context_blob = "\n\n".join(context_parts)
        max_chars = getattr(self.config, "query_rewrite_max_chars", 800)
        if max_chars and len(context_blob) > max_chars:
            context_blob = context_blob[:max_chars]
        try:
            messages = self._message_builder(prompt, context_blob)
            resp, _usage = await self._llm_call(llm, messages)
            payload = resp if isinstance(resp, dict) else resp.model_dump()
            rewritten = self._extract_message_text(payload)
            rewritten = rewritten.strip().strip('"').strip("'")
            return rewritten or user_input
        except Exception:
            return user_input

    @staticmethod
    def _build_context_snippets(history: List[Dict[str, Any]], max_msgs: int) -> List[str]:
        snippets = []
        for msg in reversed(history):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            text = QueryRewriter._extract_message_text(msg).strip()
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
            parts.append(f"facts: {session_memory.get('facts')}")
        if session_memory.get("entities"):
            parts.append(f"entities: {session_memory.get('entities')}")
        if session_memory.get("topics"):
            parts.append(f"topics: {session_memory.get('topics')}")
        return "\n".join(parts)

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
