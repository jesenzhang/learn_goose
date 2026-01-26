"""
Managers Module

六个 Agent 级别的管理器。
参考 goose-rs Agent 架构设计。
"""

from .retry_manager import (
    RetryManager,
    RetryConfig,
    RetryResult,
    SuccessCheck,
    ShellSuccessCheck,
    ExecutionResult,
    execute_shell_command,
    execute_on_failure_command,
    execute_success_checks,
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

from .action_required_manager import (
    ActionRequiredManager,
    PendingRequest,
    request_user_input,
    request_tool_confirmation,
    submit_user_response,
)

__all__ = [
    # Retry Manager
    "RetryManager",
    "RetryConfig",
    "RetryResult",
    "SuccessCheck",
    "ShellSuccessCheck",
    "ExecutionResult",
    "execute_shell_command",
    "execute_on_failure_command",
    "execute_success_checks",
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
    # Action Required Manager
    "ActionRequiredManager",
    "PendingRequest",
    "request_user_input",
    "request_tool_confirmation",
    "submit_user_response",
]
