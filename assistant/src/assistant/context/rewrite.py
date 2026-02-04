from typing import Any, Dict, List, Optional

from .config import ContextConfig
from .prompts import DEFAULT_QUERY_REWRITE_PROMPT


class QueryRewriter:
    def __init__(
        self,
        config: ContextConfig,
        *,
        message_builder: Optional[Any] = None,
    ) -> None:
        self.config = config
        self.message_builder = message_builder

    async def rewrite(
        self,
        *,
        user_input: str,
        history: List[Dict[str, Any]],
        session_memory: Optional[Dict[str, Any]] = None,
        llm: Any = None,
    ) -> str:
        if not self.config.query_rewrite_enabled or not llm:
            return user_input
        prompt = self.config.query_rewrite_prompt or DEFAULT_QUERY_REWRITE_PROMPT
        snippets = self._build_context_snippets(history, self.config.query_rewrite_max_msgs)
        memory_text = self._format_session_memory(session_memory or {})
        context_parts = []
        if memory_text:
            context_parts.append(f"SessionMemory:\n{memory_text}")
        if snippets:
            context_parts.append("RecentMessages:\n" + "\n".join(snippets))
        context_parts.append(f"UserQuery:\n{user_input}")
        context_blob = "\n\n".join(context_parts)
        max_chars = self.config.query_rewrite_max_chars
        if max_chars and len(context_blob) > max_chars:
            context_blob = context_blob[:max_chars]
        messages = self._build_messages(prompt, context_blob)
        try:
            resp = await llm.agenerate(messages=messages, tools=None)
            rewritten = resp.text.strip() if resp else ""
            rewritten = rewritten.strip('"').strip("'")
            return rewritten or user_input
        except Exception:
            return user_input

    def _build_messages(self, system_prompt: str, user_text: str) -> List[Dict[str, str]]:
        if self.message_builder:
            return self.message_builder(system_prompt, user_text)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

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
