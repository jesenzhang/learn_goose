"""
Context Truncation Management for Assistant

Token counting, message compaction, and context management.
适配 Assistant 项目的体系结构
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
