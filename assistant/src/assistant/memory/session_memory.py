"""
Session memory updater.

Maintains session_summary / session_facts / session_entities / session_topics.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from .llm_adapter import default_message_builder, default_llm_call

DEFAULT_SESSION_MEMORY_PROMPT = (
    "You update session memory for a conversation. "
    "Given the existing memory and the latest user+assistant exchange, output a JSON object ONLY. "
    "Keys: session_summary (string), session_facts (object), session_entities (array of strings), "
    "session_topics (array of strings). Keep it concise. Do not include any extra text."
)


class SessionMemoryUpdater:
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

    async def update(
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
        if not getattr(self.config, "session_memory_enabled", True):
            return {
                "session_summary": session_summary,
                "session_facts": session_facts,
                "session_entities": session_entities,
                "session_topics": session_topics,
            }

        use_llm = getattr(self.config, "session_memory_use_llm", False)
        if use_llm and llm:
            return await self._update_with_llm(
                user_input=user_input,
                assistant_output=assistant_output,
                history=history,
                session_summary=session_summary,
                session_facts=session_facts,
                session_entities=session_entities,
                session_topics=session_topics,
                llm=llm,
            )

        return self._update_heuristic(
            user_input=user_input,
            assistant_output=assistant_output,
            session_summary=session_summary,
            session_facts=session_facts,
            session_entities=session_entities,
            session_topics=session_topics,
        )

    async def _update_with_llm(
        self,
        *,
        user_input: str,
        assistant_output: str,
        history: List[Dict[str, Any]],
        session_summary: Optional[str],
        session_facts: Dict[str, Any],
        session_entities: List[str],
        session_topics: List[str],
        llm: Any,
    ) -> Dict[str, Any]:
        prompt = DEFAULT_SESSION_MEMORY_PROMPT
        memory_text = self._format_session_memory(
            {
                "summary": session_summary,
                "facts": session_facts,
                "entities": session_entities,
                "topics": session_topics,
            }
        )
        snippets = self._build_context_snippets(
            history,
            max(2, getattr(self.config, "session_memory_recent_msgs", 6)),
        )
        content_parts = []
        if memory_text:
            content_parts.append(f"ExistingMemory:\n{memory_text}")
        if snippets:
            content_parts.append("RecentMessages:\n" + "\n".join(snippets))
        content_parts.append(f"User:\n{user_input}")
        content_parts.append(f"Assistant:\n{assistant_output}")
        content = "\n\n".join(content_parts)
        max_chars = getattr(self.config, "session_memory_max_chars", 800)
        if max_chars and len(content) > max_chars:
            content = content[:max_chars]
        try:
            messages = self._message_builder(prompt, content)
            resp, _usage = await self._llm_call(llm, messages)
            payload = resp if isinstance(resp, dict) else resp.model_dump()
            text = self._extract_message_text(payload)
            data = self._safe_json_load(text)
            return self._merge_session_memory(
                session_summary=session_summary,
                session_facts=session_facts,
                session_entities=session_entities,
                session_topics=session_topics,
                new_summary=data.get("session_summary"),
                new_facts=data.get("session_facts"),
                new_entities=data.get("session_entities"),
                new_topics=data.get("session_topics"),
            )
        except Exception:
            return self._update_heuristic(
                user_input=user_input,
                assistant_output=assistant_output,
                session_summary=session_summary,
                session_facts=session_facts,
                session_entities=session_entities,
                session_topics=session_topics,
            )

    def _update_heuristic(
        self,
        *,
        user_input: str,
        assistant_output: str,
        session_summary: Optional[str],
        session_facts: Dict[str, Any],
        session_entities: List[str],
        session_topics: List[str],
    ) -> Dict[str, Any]:
        summary = session_summary
        if not summary:
            summary = self._truncate_text(
                f"{user_input} / {assistant_output}",
                getattr(self.config, "session_summary_max_chars", 400),
            )
        facts = dict(session_facts or {})
        facts.setdefault("last_user", self._truncate_text(user_input, 200))
        facts.setdefault("last_assistant", self._truncate_text(assistant_output, 200))
        entities = self._merge_unique(
            session_entities,
            self._simple_keywords(user_input),
            getattr(self.config, "session_entities_max_items", 30),
        )
        topics = self._merge_unique(
            session_topics,
            self._simple_keywords(user_input),
            getattr(self.config, "session_topics_max_items", 20),
        )
        return {
            "session_summary": summary,
            "session_facts": facts,
            "session_entities": entities,
            "session_topics": topics,
        }

    def _merge_session_memory(
        self,
        *,
        session_summary: Optional[str],
        session_facts: Dict[str, Any],
        session_entities: List[str],
        session_topics: List[str],
        new_summary: Any,
        new_facts: Any,
        new_entities: Any,
        new_topics: Any,
    ) -> Dict[str, Any]:
        summary = session_summary
        if isinstance(new_summary, str) and new_summary.strip():
            summary = self._truncate_text(
                new_summary.strip(),
                getattr(self.config, "session_summary_max_chars", 400),
            )
        facts = dict(session_facts or {})
        if isinstance(new_facts, dict):
            facts.update(new_facts)
        entities = self._merge_unique(
            session_entities,
            new_entities or [],
            getattr(self.config, "session_entities_max_items", 30),
        )
        topics = self._merge_unique(
            session_topics,
            new_topics or [],
            getattr(self.config, "session_topics_max_items", 20),
        )
        return {
            "session_summary": summary,
            "session_facts": facts,
            "session_entities": entities,
            "session_topics": topics,
        }

    @staticmethod
    def _merge_unique(existing: List[str], incoming: List[Any], max_items: int) -> List[str]:
        merged = []
        seen = set()
        for item in (existing or []) + [str(i) for i in (incoming or []) if i]:
            if item not in seen:
                merged.append(item)
                seen.add(item)
            if max_items and len(merged) >= max_items:
                break
        return merged

    @staticmethod
    def _truncate_text(text: str, max_chars: int) -> str:
        if not text:
            return ""
        if max_chars and len(text) > max_chars:
            return text[:max_chars]
        return text

    @staticmethod
    def _simple_keywords(text: str) -> List[str]:
        if not text:
            return []
        parts = re.split(r"[\\s,.;:!?()\\[\\]{}<>\"'，。！？；：]", text)
        keywords = [p for p in parts if len(p) >= 2]
        return keywords[:10]

    @staticmethod
    def _safe_json_load(text: str) -> Dict[str, Any]:
        if not text:
            return {}
        try:
            return json.loads(text)
        except Exception:
            match = re.search(r"\\{.*\\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    return {}
        return {}

    @staticmethod
    def _build_context_snippets(history: List[Dict[str, Any]], max_msgs: int) -> List[str]:
        snippets = []
        for msg in reversed(history):
            role = msg.get("role")
            if role not in ("user", "assistant"):
                continue
            text = SessionMemoryUpdater._extract_message_text(msg).strip()
            if text:
                snippets.append(f"[{role}] {text}")
            if len(snippets) >= max_msgs:
                break
        snippets.reverse()
        return snippets

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
