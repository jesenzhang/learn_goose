"""
Managers Module

六个 Agent 级别的管理器。
参考 goose-rs Agent 架构设计。
"""

from .retry_manager import (
    RetryManager,
    RetryConfig,
    RetryState,
    with_retry,
)

from .inspection_manager import (
    ToolInspectionManager,
    ToolInspector,
    SecurityInspector,
    PermissionInspector,
    RepetitionInspector,
    InspectionResult,
    InspectionAction,
    ToolRequest,
)

from .prompt_manager import (
    PromptManager,
    PromptTemplate,
    PromptCategory,
    PromptContext,
)

from .subagent_handler import (
    SubagentHandler,
    SubagentConfig,
    SubagentResult,
)

from .permission_manager import (
    PermissionManager,
    PermissionLevel,
)

__all__ = [
    # Retry Manager
    "RetryManager",
    "RetryConfig",
    "RetryState",
    "with_retry",
    # Inspection Manager
    "ToolInspectionManager",
    "ToolInspector",
    "SecurityInspector",
    "PermissionInspector",
    "RepetitionInspector",
    "InspectionResult",
    "InspectionAction",
    "ToolRequest",
    # Prompt Manager
    "PromptManager",
    "PromptTemplate",
    "PromptCategory",
    "PromptContext",
    # Subagent Handler
    "SubagentHandler",
    "SubagentConfig",
    "SubagentResult",
    # Permission Manager
    "PermissionManager",
    "PermissionLevel",
]
