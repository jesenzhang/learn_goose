"""
Permission Inspector

权限检查器，处理工具权限检查。
参考 goose-rs/crates/goose/src/permission/permission_inspector.rs 实现。
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Set, TYPE_CHECKING, Optional

from ..conversation.message import Message, Role

if TYPE_CHECKING:
    from .permission_judge import PermissionCheckResult
    from .permission_store import ToolPermissionStore
    from ..managers.inspection_manager import InspectionResult, InspectionAction
    from ..config.permission_config import PermissionManager, PermissionLevel

logger = logging.getLogger("goose.permission.permission_inspector")


# Extension management tool name (matches goose-rs)
MANAGE_EXTENSIONS_TOOL_NAME_COMPLETE = "platform__manage_extensions"


@dataclass
class PermissionInspector:
    """
    权限检查器

    功能：
    - 检查用户定义的权限
    - 检查标记为只读的工具
    - 处理扩展管理工具的特殊权限

    参考 goose-rs PermissionInspector
    """

    readonly_tools: Set[str]
    regular_tools: Set[str]
    permission_manager: Optional["PermissionManager"] = None

    def __init__(
        self,
        readonly_tools: Set[str],
        regular_tools: Set[str],
        permission_manager: Optional["PermissionManager"] = None
    ):
        self.readonly_tools = readonly_tools
        self.regular_tools = regular_tools
        self.permission_manager = permission_manager

    @property
    def name(self) -> str:
        """检查器名称"""
        return "permission"

    def process_inspection_results(
        self,
        remaining_requests: List["ToolRequestContent"],
        inspection_results: List["InspectionResult"]
    ) -> "PermissionCheckResult":
        """
        将检查结果处理为权限决策

        Args:
            remaining_requests: 剩余的工具请求
            inspection_results: 检查结果列表

        Returns:
            权限检查结果
        """
        from .permission_judge import PermissionCheckResult

        # 以权限检查器的决策为基准
        permission_check_result = PermissionCheckResult(
            approved=[],
            needs_approval=[],
            denied=[]
        )

        # 应用权限检查器结果（基准行为）
        permission_results = [
            r for r in inspection_results if r.inspector_name == "permission"
        ]

        for request in remaining_requests:
            # 查找此请求的权限决策
            permission_result = None
            for result in permission_results:
                if result.tool_request_id == request.id:
                    permission_result = result
                    break

            if permission_result:
                if permission_result.action == InspectionAction.ALLOW:
                    permission_check_result.approved.append(request)
                elif permission_result.action == InspectionAction.DENY:
                    permission_check_result.denied.append(request)
                elif permission_result.action == InspectionAction.CONFIRM:
                    permission_check_result.needs_approval.append(request)
                else:
                    # 默认需要确认（安全优先）
                    permission_check_result.needs_approval.append(request)
            else:
                # 如果没有找到权限结果，默认需要确认（安全优先）
                permission_check_result.needs_approval.append(request)

        # 应用其他检查器结果作为覆盖
        non_permission_results = [
            r for r in inspection_results if r.inspector_name != "permission"
        ]

        if non_permission_results:
            permission_check_result = self._apply_inspection_results_to_permissions(
                permission_check_result,
                non_permission_results
            )

        return permission_check_result

    def _apply_inspection_results_to_permissions(
        self,
        permission_check_result: "PermissionCheckResult",
        inspection_results: List["InspectionResult"]
    ) -> "PermissionCheckResult":
        """应用检查结果到权限检查结果"""
        from .permission_judge import PermissionCheckResult

        # 创建映射以便快速查找
        result_map = {r.tool_request_id: r for r in inspection_results}

        # 处理批准的请求 - 可能被其他检查器拒绝
        approved = []
        for req in permission_check_result.approved:
            result = result_map.get(req.id)
            if not result:
                approved.append(req)
            elif result.action == InspectionAction.ALLOW:
                approved.append(req)
            elif result.action == InspectionAction.DENY:
                # 被安全检查器拒绝
                permission_check_result.denied.append(req)
            else:
                # 需要确认
                permission_check_result.needs_approval.append(req)

        # 处理需要批准的请求
        needs_approval = []
        for req in permission_check_result.needs_approval:
            result = result_map.get(req.id)
            if not result:
                needs_approval.append(req)
            elif result.action == InspectionAction.ALLOW:
                # 被其他检查器批准
                approved.append(req)
            elif result.action == InspectionAction.DENY:
                # 被拒绝
                permission_check_result.denied.append(req)
            else:
                needs_approval.append(req)

        permission_check_result.approved = approved
        permission_check_result.needs_approval = needs_approval

        return permission_check_result

    async def inspect(
        self,
        tool_requests: List["ToolRequestContent"],
        messages: List[Message],
        goose_mode: str
    ) -> List["InspectionResult"]:
        """
        检查工具请求的权限

        Args:
            tool_requests: 工具请求列表
            messages: 消息历史
            goose_mode: goose 模式

        Returns:
            检查结果列表
        """
        from ..managers.inspection_manager import InspectionResult, InspectionAction

        results = []
        permission_manager = self.permission_manager

        for request in tool_requests:
            value = request.tool_call_value
            if not value:
                continue

            tool_name = value.name

            # 根据模式决定操作
            action, reason = self._get_action_for_mode(
                tool_name,
                goose_mode,
                permission_manager
            )

            results.append(InspectionResult(
                allowed=(action != InspectionAction.DENY),
                action=action,
                reason=reason,
                details={},
                inspector_name=self.name,
                tool_request_id=request.id,
            ))

        return results

    def _get_action_for_mode(
        self,
        tool_name: str,
        goose_mode: str,
        permission_manager: Optional["PermissionManager"]
    ) -> tuple["InspectionAction", str]:
        """根据模式获取操作和原因"""
        from ..managers.inspection_manager import InspectionAction

        if goose_mode == "chat":
            # Chat 模式 - 跳过所有工具
            continue  # type: ignore

        elif goose_mode == "auto":
            # Auto 模式 - 批准所有工具
            return (
                InspectionAction.ALLOW,
                "Auto mode - all tools approved"
            )

        elif goose_mode in ("approve", "smart_approve"):
            # 1. 检查用户定义的权限
            if permission_manager:
                user_level = self._get_user_permission(permission_manager, tool_name)
                if user_level:
                    return self._action_from_permission_level(user_level, user_reason=True)

            # 2. 检查是否为只读或常规工具（两者都预批准）
            if tool_name in self.readonly_tools:
                return (
                    InspectionAction.ALLOW,
                    "Tool marked as read-only"
                )
            elif tool_name in self.regular_tools:
                return (
                    InspectionAction.ALLOW,
                    "Tool pre-approved"
                )

            # 4. 扩展管理特殊处理
            if tool_name == MANAGE_EXTENSIONS_TOOL_NAME_COMPLETE:
                return (
                    InspectionAction.CONFIRM,
                    "Extension management requires approval for security"
                )

            # 5. 默认：未知工具需要批准
            return (
                InspectionAction.CONFIRM,
                "Tool requires user approval"
            )

        # 默认：需要批准
        return (
            InspectionAction.CONFIRM,
            "Tool requires user approval"
        )

    def _get_user_permission(
        self,
        permission_manager: "PermissionManager",
        tool_name: str
    ) -> Optional["PermissionLevel"]:
        """获取用户定义的权限"""
        if hasattr(permission_manager, "get_user_permission"):
            return permission_manager.get_user_permission(tool_name)
        return None

    def _action_from_permission_level(
        self,
        level: "PermissionLevel",
        user_reason: bool = False
    ) -> tuple["InspectionAction", str]:
        """从权限级别获取操作"""
        from ..managers.inspection_manager import InspectionAction

        if level == PermissionLevel.ALLOW:
            reason = "User permission allows this tool" if user_reason else "Always allow"
            return (InspectionAction.ALLOW, reason)
        elif level == PermissionLevel.DENY:
            reason = "User permission denies this tool" if user_reason else "Never allow"
            return (InspectionAction.DENY, reason)
        else:  # ASK_BEFORE
            return (
                InspectionAction.CONFIRM,
                "User permission requires asking before"
            )
