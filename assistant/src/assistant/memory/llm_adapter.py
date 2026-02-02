"""
LLM adapter interfaces for memory module.

Keep memory decoupled from concrete message types. Provide a default builder
that uses plain dict messages for LLMs that accept OpenAI-style payloads.
"""

from __future__ import annotations

from typing import Any, Callable, List, Tuple


def default_message_builder(system_prompt: str, user_content: str) -> List[Any]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


MessageBuilder = Callable[[str, str], List[Any]]


async def default_llm_call(llm: Any, messages: List[Any]) -> Tuple[Any, Any]:
    return await llm.agenerate(messages=messages)


LLMCall = Callable[[Any, List[Any]], Any]
