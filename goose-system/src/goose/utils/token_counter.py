"""
Token Counter Module

Token counting utilities for LLM context management.
Reference: goose-rs/crates/goose/src/token_counter.rs

Uses tiktoken for tokenization with caching support.
"""

import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from functools import lru_cache
import threading

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

MAX_TOKEN_CACHE_SIZE = 10000

FUNC_INIT = 7
PROP_INIT = 3
PROP_KEY = 3
ENUM_INIT = -3
ENUM_ITEM = 3
FUNC_END = 12
TOKENS_PER_MESSAGE = 4
REPLY_PRIMER = 3


@dataclass
class TokenCountResult:
    """Token count result with breakdown"""
    total: int
    text_tokens: int = 0
    tool_tokens: int = 0
    message_overhead: int = 0


class TokenCounter:
    """
    Token counter with caching support.
    
    Uses tiktoken for accurate token counting with caching
    to improve performance for repeated counting.
    """
    
    _instance: Optional["TokenCounter"] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        if not TIKTOKEN_AVAILABLE:
            raise ImportError("tiktoken is required for token counting. Install with: pip install tiktoken")
        
        self._encoder = tiktoken.get_encoding("cl100k_base")
        self._cache: Dict[str, int] = {}
        self._cache_lock = threading.Lock()
        self._initialized = True
    
    def count_tokens(self, text: str) -> int:
        """Count tokens for a single text string."""
        if not text:
            return 0
            
        cache_key = self._get_cache_key(text)
        
        with self._cache_lock:
            if cache_key in self._cache:
                return self._cache[cache_key]
        
        tokens = self._encoder.encode(text, disallowed_special=[])
        count = len(tokens)
        
        with self._cache_lock:
            if len(self._cache) >= MAX_TOKEN_CACHE_SIZE:
                if self._cache:
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]
            self._cache[cache_key] = count
        
        return count
    
    def count_tokens_for_tools(self, tools: List[Dict[str, Any]]) -> int:
        """Count tokens for a list of tool definitions."""
        if not tools:
            return 0
            
        func_token_count = 0
        
        for tool in tools:
            func_token_count += FUNC_INIT
            
            name = tool.get("name", "")
            description = tool.get("description", "").rstrip('.')
            
            line = f"{name}:{description}"
            func_token_count += self.count_tokens(line)
            
            properties = tool.get("input_schema", {}).get("properties", {})
            
            if properties:
                func_token_count += PROP_INIT
                
                for key, value in properties.items():
                    func_token_count += PROP_KEY
                    
                    p_type = value.get("type", "")
                    p_desc = value.get("description", "").rstrip('.')
                    
                    line = f"{key}:{p_type}:{p_desc}"
                    func_token_count += self.count_tokens(line)
                    
                    enum_values = value.get("enum", [])
                    if enum_values:
                        func_token_count += ENUM_INIT
                        for item in enum_values:
                            if isinstance(item, str):
                                func_token_count += ENUM_ITEM
                                func_token_count += self.count_tokens(item)
            
            if tool.get("required"):
                func_token_count += 1
        
        func_token_count += FUNC_END
        
        return func_token_count
    
    def count_message_tokens(
        self,
        role: str,
        content: str,
        has_tool_call: bool = False
    ) -> int:
        """Count tokens for a single message."""
        tokens = TOKENS_PER_MESSAGE
        
        if content:
            tokens += self.count_tokens(content)
        
        if has_tool_call:
            tokens += 15
        
        return tokens
    
    def count_chat_tokens(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        agent_visible_only: bool = True
    ) -> TokenCountResult:
        """
        Count tokens for a complete chat conversation.
        
        Args:
            system_prompt: System prompt text
            messages: List of message dictionaries
            tools: Optional list of tool definitions
            agent_visible_only: Whether to skip agent-invisible messages
            
        Returns:
            TokenCountResult with total and breakdown
        """
        text_tokens = 0
        tool_tokens = 0
        message_overhead = 0
        
        if system_prompt:
            text_tokens += self.count_tokens(system_prompt)
            message_overhead += TOKENS_PER_MESSAGE
        
        for msg in messages:
            if agent_visible_only:
                metadata = msg.get("metadata", {})
                if not metadata.get("agent_visible", True):
                    continue
            
            role = msg.get("role", "")
            content = msg.get("content", "")
            has_tool_call = False
            
            msg_content = msg.get("content", [])
            if isinstance(msg_content, list):
                for item in msg_content:
                    if isinstance(item, dict):
                        if item.get("type") in ("tool_request", "tool_call"):
                            has_tool_call = True
                            tool_call_text = f"tool_call: {item.get('name', '')}"
                            text_tokens += self.count_tokens(tool_call_text)
                        elif item.get("type") == "tool_response":
                            response_text = item.get("content", "")
                            if isinstance(response_text, list):
                                response_text = str(response_text)
                            text_tokens += self.count_tokens(str(response_text))
            
            message_overhead += TOKENS_PER_MESSAGE
            
            if isinstance(content, str) and content:
                text_tokens += self.count_tokens(content)
            elif isinstance(content, dict):
                text_tokens += self.count_tokens(str(content))
        
        if tools:
            tool_tokens = self.count_tokens_for_tools(tools)
        
        total = text_tokens + tool_tokens + message_overhead + REPLY_PRIMER
        
        return TokenCountResult(
            total=total,
            text_tokens=text_tokens,
            tool_tokens=tool_tokens,
            message_overhead=message_overhead
        )
    
    def count_everything(
        self,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        resources: Optional[List[str]] = None
    ) -> int:
        """Count all tokens including resources."""
        result = self.count_chat_tokens(system_prompt, messages, tools)
        
        total = result.total
        
        if resources:
            for resource in resources:
                total += self.count_tokens(resource)
        
        return total
    
    def clear_cache(self) -> None:
        """Clear the token cache."""
        with self._cache_lock:
            self._cache.clear()
    
    def cache_size(self) -> int:
        """Get current cache size."""
        with self._cache_lock:
            return len(self._cache)
    
    def _get_cache_key(self, text: str) -> str:
        """Generate a cache key for text."""
        return hashlib.md5(text.encode()).hexdigest()


async def create_token_counter() -> TokenCounter:
    """Create a token counter instance."""
    return TokenCounter()


def estimate_tokens_for_model(
    text: str,
    model: str = "gpt-4"
) -> int:
    """
    Quick estimate of tokens for a given model.
    
    Note: This is an approximation. For accurate counts,
    use TokenCounter with the actual encoder.
    """
    if not text:
        return 0
    
    if model in ("gpt-4", "gpt-4-turbo", "gpt-4o"):
        return len(text) // 4 + 1
    elif model in ("gpt-3.5-turbo", "gpt-35-turbo"):
        return len(text) // 4 + 1
    elif model in ("claude-3-5-sonnet-20241022", "claude-3-opus-20240229"):
        return len(text) // 4 + 1
    else:
        return len(text) // 4 + 1


class TokenBudget:
    """Token budget manager for context management."""
    
    def __init__(
        self,
        max_tokens: int,
        system_prompt_tokens: int = 0,
        reserve_tokens: int = 100
    ):
        self.max_tokens = max_tokens
        self.reserve_tokens = reserve_tokens
        self.available_for_messages = max_tokens - system_prompt_tokens - reserve_tokens
    
    def can_fit(self, token_count: int) -> bool:
        """Check if tokens can fit in budget."""
        return token_count <= self.available_for_messages
    
    def remaining(self) -> int:
        """Get remaining token budget."""
        return self.available_for_messages
    
    def check_and_update(
        self,
        current_tokens: int,
        additional_tokens: int
    ) -> tuple[bool, int]:
        """
        Check if additional tokens fit and return new total.
        
        Returns:
            (can_fit, new_total)
        """
        new_total = current_tokens + additional_tokens
        return new_total <= self.max_tokens, new_total


def count_tokens_for_provider_format(
    messages: List[Dict[str, Any]],
    system_prompt: Optional[str] = None
) -> int:
    """
    Count tokens in provider message format.
    
    This is a simplified version for quick estimates.
    """
    counter = TokenCounter()
    
    tools = None
    
    return counter.count_chat_tokens(
        system_prompt or "",
        messages,
        tools
    ).total
