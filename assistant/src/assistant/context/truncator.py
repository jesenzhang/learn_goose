from typing import Any, Dict, List, Optional

from .budget import ContextBudgeter
from .interfaces import TruncationProvider, TokenCounter
from .models import ContextBudget, TruncationResult


class ContextTruncator:
    def __init__(
        self,
        truncation_manager: Optional[TruncationProvider] = None,
        *,
        token_counter: Optional[TokenCounter] = None,
        budgeter: Optional[ContextBudgeter] = None,
        context_limit: Optional[int] = None,
        reserved_tokens: int = 0,
    ):
        self.truncation_manager = truncation_manager
        self.token_counter = token_counter
        self.budgeter = budgeter
        self.context_limit = context_limit
        self.reserved_tokens = reserved_tokens

    def build_context_budget(
        self,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> ContextBudget:
        if self.budgeter and self.context_limit:
            return self.budgeter.build(
                context_limit=int(self.context_limit),
                reserved_tokens=int(self.reserved_tokens),
                system_prompt=system_prompt,
                tools=tools or [],
            )
        return ContextBudget(context_limit=0, reserved_tokens=0)

    async def check_and_apply_truncation(
        self,
        conv: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> TruncationResult:
        if self.truncation_manager and hasattr(self.truncation_manager, "check_and_apply_truncation"):
            result = await self.truncation_manager.check_and_apply_truncation(
                conv,
                system_prompt=system_prompt,
                tools=tools,
            )
            if isinstance(result, TruncationResult):
                return result
            if isinstance(result, dict):
                return TruncationResult(
                    truncated=bool(result.get("truncated", False)),
                    summary_text=result.get("summary"),
                    usage=result.get("usage"),
                )
            return TruncationResult(truncated=bool(result))
        return TruncationResult(truncated=False)

    def enforce_budget_on_conversation(
        self,
        conv: Any,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]],
    ) -> TruncationResult:
        if self.budgeter and self.context_limit and self.token_counter and hasattr(conv, "messages_to_dict"):
            budget = self.budgeter.build(
                context_limit=int(self.context_limit),
                reserved_tokens=int(self.reserved_tokens),
                system_prompt=system_prompt,
                tools=tools or [],
            )
            target_limit = int(budget.available_tokens)
            usage = self.token_counter.estimate_context_usage(
                system_prompt=system_prompt,
                messages=conv.messages_to_dict(),
                tools=tools or [],
                context_limit=int(self.context_limit),
            )
            removed = 0
            while usage.get("total_tokens", 0) > target_limit and len(conv.messages) > 1:
                conv.messages.pop(0)
                removed += 1
                usage = self.token_counter.estimate_context_usage(
                    system_prompt=system_prompt,
                    messages=conv.messages_to_dict(),
                    tools=tools or [],
                    context_limit=int(self.context_limit),
                )
            truncated_user = False
            if usage.get("total_tokens", 0) > target_limit and conv.messages:
                from ..conversation import TextContent
                last_msg = conv.messages[-1]
                text_parts = []
                for c in last_msg.content:
                    if isinstance(c, TextContent) and c.text:
                        text_parts.append(c.text)
                text = "\n".join(text_parts)
                if text:
                    total_tokens = max(usage.get("total_tokens", 1), 1)
                    ratio = max(0.1, min(1.0, target_limit / total_tokens))
                    new_len = max(200, int(len(text) * ratio))
                    truncated = text[:new_len].rstrip()
                    if truncated != text:
                        for c in last_msg.content:
                            if isinstance(c, TextContent):
                                c.text = truncated
                                truncated_user = True
                                break
                    usage = self.token_counter.estimate_context_usage(
                        system_prompt=system_prompt,
                        messages=conv.messages_to_dict(),
                        tools=tools or [],
                        context_limit=int(self.context_limit),
                    )
            return TruncationResult(
                truncated=bool(removed or truncated_user),
                usage={
                    "removed": removed,
                    "truncated_user": truncated_user,
                    "usage": usage,
                    "limit": int(self.context_limit),
                    "available": target_limit,
                    "reserved": int(self.reserved_tokens),
                },
            )
        return TruncationResult(truncated=False)
