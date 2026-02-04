import json
from typing import Any, Dict, List, Optional

from .interfaces import TokenCounter
from .models import ContextBudget


class ContextBudgeter:
    def __init__(self, token_counter: TokenCounter) -> None:
        self.token_counter = token_counter

    def build(
        self,
        *,
        context_limit: int,
        reserved_tokens: int,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        history_tokens: int = 0,
        input_tokens: int = 0,
    ) -> ContextBudget:
        system_tokens = self.token_counter.count_text_tokens(system_prompt or "")
        tools_tokens = self._estimate_tools_tokens(tools or [])
        return ContextBudget(
            context_limit=context_limit,
            reserved_tokens=reserved_tokens,
            system_tokens=system_tokens,
            tools_tokens=tools_tokens,
            history_tokens=history_tokens,
            input_tokens=input_tokens,
        )

    def _estimate_tools_tokens(self, tools: List[Dict[str, Any]]) -> int:
        if not tools:
            return 0
        try:
            payload = json.dumps(tools, ensure_ascii=False)
        except Exception:
            payload = str(tools)
        return self.token_counter.count_text_tokens(payload)
