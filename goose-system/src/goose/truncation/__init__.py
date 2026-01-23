"""
Context Truncation Management

Token counting, message compaction, and context management.
Reference: goose-rs/crates/goose/src/context_mgmt/mod.rs

Features:
- Token counting with tiktoken support
- Message compaction via LLM summarization
- Context budget tracking
- Automatic and manual compaction

Usage:
    from goose.truncation import TruncationManager, create_token_counter
    
    # Count tokens
    counter = create_token_counter("claude")
    tokens = counter.count_text_tokens("Hello, world!")
    
    # Create truncation manager
    manager = await create_truncation_manager(provider)
    
    # Check and compact if needed
    compacted, usage = await manager.check_and_compact(messages, system_prompt)
"""

from .token_counter import (
    TokenCounter,
    TokenCount,
    create_token_counter,
    count_tokens_for_model,
)

from .compaction import (
    MessageCompactor,
    CompactionConfig,
    CompactionResult,
    DEFAULT_COMPACTION_THRESHOLD,
    CONVERSATION_CONTINUATION_TEXT,
    TOOL_LOOP_CONTINUATION_TEXT,
    MANUAL_COMPACT_CONTINUATION_TEXT,
    format_message_for_compacting,
    create_compactor,
)

from .manager import (
    TruncationManager,
    TruncationConfig,
    TruncationStats,
    ContextBudget,
    create_truncation_manager,
    create_context_budget,
)

__all__ = [
    # Token Counter
    "TokenCounter",
    "TokenCount",
    "create_token_counter",
    "count_tokens_for_model",
    # Compaction
    "MessageCompactor",
    "CompactionConfig",
    "CompactionResult",
    "DEFAULT_COMPACTION_THRESHOLD",
    "CONVERSATION_CONTINUATION_TEXT",
    "TOOL_LOOP_CONTINUATION_TEXT",
    "MANUAL_COMPACT_CONTINUATION_TEXT",
    "format_message_for_compacting",
    "create_compactor",
    # Manager
    "TruncationManager",
    "TruncationConfig",
    "TruncationStats",
    "ContextBudget",
    "create_truncation_manager",
    "create_context_budget",
]
