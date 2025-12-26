from typing import List, Dict, Any
from ..conversation import Message
from ..utils.token_counter import create_token_counter
from .base import ProviderUsage

async def ensure_usage_tokens(
    provider_usage: ProviderUsage,
    system_prompt: str,
    request_messages: List[Message],
    response: Message,
    tools: List[Dict[str, Any]] = []
) -> ProviderUsage:
    """
    Rust: pub async fn ensure_usage_tokens(...)
    """
    # If usage is already complete, return early
    if provider_usage.usage.input_tokens > 0 and provider_usage.usage.output_tokens > 0:
        return provider_usage

    token_counter = create_token_counter()

    # Estimate Input
    if provider_usage.usage.input_tokens == 0:
        input_count = token_counter.count_chat_tokens(
            system_prompt, request_messages, tools
        )
        provider_usage.usage.input_tokens = input_count

    # Estimate Output
    if provider_usage.usage.output_tokens == 0:
        # Rust logic joins content parts with space
        # .map(|c| format!("{}", c)).collect().join(" ")
        response_text = " ".join([c.text for c in response.content if hasattr(c, 'text') and c.text])
        output_count = token_counter.count_tokens(response_text)
        provider_usage.usage.output_tokens = output_count

    # Calculate Total
    if provider_usage.usage.total_tokens == 0:
        provider_usage.usage.total_tokens = (
            provider_usage.usage.input_tokens + provider_usage.usage.output_tokens
        )

    return provider_usage