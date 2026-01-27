"""
Token Counter for Assistant

Token counting utilities for context management.
适配 Assistant 的 Message 和 Conversation 类型
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass


@dataclass
class TokenCount:
    """Token count result"""
    text_tokens: int
    messages_tokens: int
    tools_tokens: int
    total_tokens: int


class TokenCounter:
    """
    Token counter for estimating token usage.

    Supports multiple tokenization strategies:
    - tiktoken (OpenAI models)
    - anthropic (Anthropic models)
    - rough estimation (fallback)
    """

    def __init__(self, model_name: str = "claude"):
        self.model_name = model_name
        self._tokenizer = None
        self._initialize_tokenizer()

    def _initialize_tokenizer(self) -> None:
        """Initialize the tokenizer based on model"""
        try:
            import tiktoken
            if "gpt" in self.model_name.lower():
                self._tokenizer = tiktoken.encoding_for_model("gpt-4")
            else:
                self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except (ImportError, Exception):
            self._tokenizer = None

    def count_text_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self._tokenizer:
            return len(self._tokenizer.encode(text))
        else:
            return self._rough_count(text)

    def count_messages_tokens(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None
    ) -> TokenCount:
        """
        Count tokens for a complete message context

        Args:
            system_prompt: System prompt text
            messages: List of messages (each with role and content)
            tools: Optional list of tool definitions

        Returns:
            TokenCount with breakdown
        """
        # Count system prompt
        system_tokens = self.count_text_tokens(system_prompt)

        # Count messages
        messages_text = self._messages_to_text(messages)
        messages_tokens = self.count_text_tokens(messages_text)

        # Count tools
        tools_tokens = 0
        if tools:
            tools_text = self._tools_to_text(tools)
            tools_tokens = self.count_text_tokens(tools_text)

        total = system_tokens + messages_tokens + tools_tokens

        return TokenCount(
            text_tokens=system_tokens,
            messages_tokens=messages_tokens,
            tools_tokens=tools_tokens,
            total_tokens=total
        )

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Convert messages to text for counting"""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if isinstance(content, list):
                content_str = ""
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type", "text")
                        if block_type == "text":
                            content_str += block.get("text", "")
                        elif block_type == "image":
                            content_str += "[image]"
                        elif block_type == "resource":
                            content_str += f"[resource: {block.get('uri', '')}]"
                    else:
                        content_str += str(content)
                content = content_str

            parts.append(f"[{role}]: {content}")

        return "\n".join(parts)

    def _tools_to_text(self, tools: List[Dict[str, Any]]) -> str:
        """Convert tool definitions to text for counting"""
        parts = []
        for tool in tools:
            name = tool.get("name", "unknown")
            description = tool.get("description", "")
            input_schema = tool.get("inputSchema", {})

            schema_text = str(input_schema)
            parts.append(f"Tool: {name}\nDescription: {description}\nSchema: {schema_text}")

        return "\n---\n".join(parts)

    def _rough_count(self, text: str) -> int:
        """
        Rough token estimation (fallback when tiktoken not available)

        Uses a simple heuristic: ~4 characters per token on average
        """
        if not text:
            return 0

        # Basic English text: ~4 chars per token
        # Add overhead for special characters
        text = text.strip()
        if not text:
            return 0

        # Count words
        word_count = len(text.split())

        # Estimate tokens (rough heuristic)
        return int(word_count * 1.33)

    def estimate_context_usage(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        context_limit: int
    ) -> Dict[str, Any]:
        """
        Estimate context usage percentage

        Returns:
            Dict with usage percentage and token breakdown
        """
        token_count = self.count_messages_tokens(system_prompt, messages, tools)
        usage_percent = (token_count.total_tokens / context_limit) * 100

        return {
            "text_tokens": token_count.text_tokens,
            "messages_tokens": token_count.messages_tokens,
            "tools_tokens": token_count.tools_tokens,
            "total_tokens": token_count.total_tokens,
            "context_limit": context_limit,
            "usage_percent": round(usage_percent, 2),
            "needs_compaction": usage_percent > 80,  # 80% threshold
        }

    def get_effective_limit(self, context_limit: int, threshold: float = 0.8) -> int:
        """Get effective limit for context (before triggering compaction)"""
        return int(context_limit * threshold)


def create_token_counter(model_name: str = "claude") -> TokenCounter:
    """Create a token counter instance"""
    return TokenCounter(model_name)


def count_tokens_for_model(text: str, model_name: str) -> int:
    """Quick function to count tokens for a specific model"""
    counter = TokenCounter(model_name)
    return counter.count_text_tokens(text)


__all__ = [
    "TokenCount",
    "TokenCounter",
    "create_token_counter",
    "count_tokens_for_model",
]
