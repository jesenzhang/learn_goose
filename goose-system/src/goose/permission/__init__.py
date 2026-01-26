"""
Permission Module

处理工具权限检查和批准工作流。
参考 goose-rs/crates/goose/src/permission/ 实现。

包含：
- ToolPermissionStore: 工具权限记录存储
- PermissionJudge: 使用 LLM 判断工具是否为只读
- PermissionInspector: 权限检查器
"""

from .permission_store import (
    ToolPermissionStore,
    ToolPermissionRecord,
)

from .permission_judge import (
    PermissionCheckResult,
    detect_read_only_tools,
    check_tool_permissions,
)

from .permission_inspector import (
    PermissionInspector,
)

__all__ = [
    "ToolPermissionStore",
    "ToolPermissionRecord",
    "PermissionCheckResult",
    "detect_read_only_tools",
    "check_tool_permissions",
    "PermissionInspector",
]
