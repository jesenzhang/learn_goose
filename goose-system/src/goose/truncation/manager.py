"""
Truncation Manager

Central manager for context truncation and compaction.
Reference: goose-rs/crates/goose/src/context_mgmt/mod.rs
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime

from .token_counter import TokenCounter, create_token_counter
from .compaction import (
    MessageCompactor,
    CompactionConfig,
    CompactionResult,
    DEFAULT_COMPACTION_THRESHOLD,
)


logger = logging.getLogger(__name__)


@dataclass
class TruncationConfig:
    """Truncation configuration"""
    enabled: bool = True
    threshold: float = DEFAULT_COMPACTION_THRESHOLD  # 80% of context limit
    auto_compact: bool = True  # Automatically compact when threshold exceeded
    max_messages_before_compact: int = 50  # Hard limit
    keep_recent_messages: int = 5  # Keep N recent messages after compact
    check_interval: int = 5  # Check every N messages


@dataclass
class TruncationStats:
    """Statistics for truncation operations"""
    total_checks: int = 0
    total_compactions: int = 0
    total_tokens_saved: int = 0
    last_check_time: Optional[datetime] = None
    last_compact_time: Optional[datetime] = None
    avg_compaction_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "total_compactions": self.total_compactions,
            "total_tokens_saved": self.total_tokens_saved,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "last_compact_time": self.last_compact_time.isoformat() if self.last_compact_time else None,
            "avg_compaction_time_ms": self.avg_compaction_time_ms,
        }


class TruncationManager:
    """
    Manager for context truncation and compaction.
    
    Responsibilities:
    - Check if truncation is needed
    - Coordinate message compaction
    - Track truncation statistics
    - Provide truncation hooks for agent
    """
    
    def __init__(
        self,
        provider: Any,
        config: Optional[TruncationConfig] = None,
        token_counter: Optional[TokenCounter] = None,
        on_compaction_start: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_compaction_end: Optional[Callable[[CompactionResult], None]] = None,
    ):
        self.provider = provider
        self.config = config or TruncationConfig()
        self.token_counter = token_counter or create_token_counter()
        self.compactor = MessageCompactor(
            provider=provider,
            token_counter=self.token_counter,
            config=CompactionConfig(
                threshold=self.config.threshold,
                keep_recent_messages=self.config.keep_recent_messages,
            ),
        )
        
        self.on_compaction_start = on_compaction_start
        self.on_compaction_end = on_compaction_end
        
        self.stats = TruncationStats()
        self._message_count_since_check = 0
        self._lock = asyncio.Lock()
    
    def get_context_limit(self) -> int:
        """Get the context limit from provider"""
        if hasattr(self.provider, 'get_model_config'):
            config = self.provider.get_model_config()
            return getattr(config, 'context_limit', 128000)
        return 128000  # Default fallback
    
    async def check_and_compact(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if compaction is needed and perform if necessary
        
        Returns:
            Tuple of (compaction_performed, usage_info)
        """
        if not self.config.enabled:
            return False, {"reason": "Truncation disabled"}
        
        async with self._lock:
            self.stats.total_checks += 1
            self.stats.last_check_time = datetime.now()
            
            context_limit = self.get_context_limit()
            
            # Check if we should check
            self._message_count_since_check += 1
            if self._message_count_since_check < self.config.check_interval:
                return False, {"reason": "Not due for check"}
            
            self._message_count_since_check = 0
            
            # Check if compaction is needed
            needs_compaction, usage_info = self.compactor.check_if_compaction_needed(
                messages, context_limit
            )
            
            if not needs_compaction:
                return False, usage_info
            
            # Check hard limit
            if len(messages) >= self.config.max_messages_before_compact:
                logger.warning(
                    f"Message count ({len(messages)}) exceeds hard limit "
                    f"({self.config.max_messages_before_compact}), forcing compaction"
                )
            
            # Perform compaction
            if self.config.auto_compact:
                return await self._perform_compaction(messages, system_prompt), usage_info
            
            return False, usage_info
    
    async def _perform_compaction(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: str,
    ) -> bool:
        """Perform compaction and update stats"""
        start_time = datetime.now()
        
        # Notify start
        if self.on_compaction_start:
            self.on_compaction_start({
                "message_count": len(messages),
                "reason": "context_limit_exceeded",
            })
        
        try:
            result = await self.compactor.compact_messages(
                conversation_messages=messages,
                system_prompt=system_prompt,
                is_manual=False,
            )
            
            # Update stats
            self.stats.total_compactions += 1
            self.stats.total_tokens_saved += result.tokens_saved
            self.stats.last_compact_time = datetime.now()
            
            # Update average compaction time
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            avg = self.stats.avg_compaction_time_ms
            self.stats.avg_compaction_time_ms = (avg + elapsed) / 2
            
            logger.info(
                f"Compaction completed: {result.original_message_count} -> "
                f"{result.compacted_message_count} messages, "
                f"saved ~{result.tokens_saved} tokens"
            )
            
            # Notify end
            if self.on_compaction_end:
                self.on_compaction_end(result)
            
            return result.success
            
        except Exception as e:
            logger.exception(f"Compaction failed: {e}")
            return False
    
    def estimate_context_usage(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str,
    ) -> Dict[str, Any]:
        """Estimate current context usage"""
        context_limit = self.get_context_limit()
        
        return self.token_counter.estimate_context_usage(
            system_prompt=system_prompt,
            messages=messages,
            tools=tools,
            context_limit=context_limit,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get truncation statistics"""
        return self.stats.to_dict()
    
    def reset_stats(self) -> None:
        """Reset statistics"""
        self.stats = TruncationStats()
    
    def update_config(self, **kwargs) -> None:
        """Update configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        
        # Update compactor config
        self.compactor.config.threshold = self.config.threshold
        self.compactor.config.keep_recent_messages = self.config.keep_recent_messages
    
    def get_effective_limit(self) -> int:
        """Get effective context limit (before triggering compaction)"""
        return self.token_counter.get_effective_limit(
            self.get_context_limit(),
            self.config.threshold,
        )


async def create_truncation_manager(
    provider: Any,
    config: Optional[TruncationConfig] = None,
) -> TruncationManager:
    """Create a truncation manager"""
    return TruncationManager(provider, config)


@dataclass
class ContextBudget:
    """Context budget tracking"""
    total_limit: int
    system_prompt_cost: int = 0
    tools_cost: int = 0
    reserved_for_response: int = 4000  # Reserve for response
    
    @property
    def available_for_messages(self) -> int:
        """Available tokens for messages"""
        return max(
            0,
            self.total_limit
            - self.system_prompt_cost
            - self.tools_cost
            - self.reserved_for_response
        )
    
    def check(self, message_cost: int) -> Tuple[bool, int]:
        """Check if we have budget for message cost"""
        available = self.available_for_messages
        return message_cost <= available, available


def create_context_budget(
    provider: Any,
    system_prompt: str,
    tools: List[Dict[str, Any]],
    token_counter: TokenCounter,
) -> ContextBudget:
    """Create a context budget from provider and configuration"""
    context_limit = 128000  # Default
    
    if hasattr(provider, 'get_model_config'):
        config = provider.get_model_config()
        context_limit = getattr(config, 'context_limit', context_limit)
    
    system_cost = token_counter.count_text_tokens(system_prompt)
    tools_cost = 0
    if tools:
        tools_text = token_counter._tools_to_text(tools)
        tools_cost = token_counter.count_text_tokens(tools_text)
    
    return ContextBudget(
        total_limit=context_limit,
        system_prompt_cost=system_cost,
        tools_cost=tools_cost,
    )
