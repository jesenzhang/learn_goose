"""
Permission Judge

使用 LLM 判断工具是否为只读操作，以及检查工具权限。
参考 goose-rs/crates/goose/src/permission/permission_judge.rs 实现。
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Set, TYPE_CHECKING

from ..conversation.message import (
    Message,
    Role,
    TextContent,
    ToolRequestContent,
)

if TYPE_CHECKING:
    from ..providers.base import BaseLLM
    from .permission_store import ToolPermissionStore
    from ..config.permission_config import PermissionLevel

logger = logging.getLogger("goose.permission.permission_judge")


# Extension management tool name (matches goose-rs)
MANAGE_EXTENSIONS_TOOL_NAME_COMPLETE = "platform__manage_extensions"


@dataclass
class PermissionCheckResult:
    """权限检查结果"""
    approved: List[ToolRequestContent]
    needs_approval: List[ToolRequestContent]
    denied: List[ToolRequestContent]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "approved": [r.to_dict() for r in self.approved],
            "needs_approval": [r.to_dict() for r in self.needs_approval],
            "denied": [r.to_dict() for r in self.denied],
        }


def _create_read_only_tool_schema() -> Dict[str, Any]:
    """创建检测只读工具的工具定义"""
    return {
        "type": "function",
        "function": {
            "name": "platform__tool_by_tool_permission",
            "description": """Analyzez tool requests and determine which ones perform read-only operations.

What constitutes a read-only operation:
- A read-only operation retrieves information without modifying any data or state.
- Examples include:
    - Reading a file without writing to it.
    - Querying a database without making updates.
    - Retrieving information from APIs without performing POST, PUT, or DELETE operations.

Examples of read vs. write operations:
- Read Operations:
    - `SELECT` query in SQL.
    - Reading file metadata or content.
    - Listing directory contents.
- Write Operations:
    - `INSERT`, `UPDATE`, or `DELETE` in SQL.
    - Writing or appending to a file.
    - Modifying system configurations.
    - Sending messages to Slack channel.

How to analyze tool requests:
- Inspect each tool request to identify its purpose based on its name and arguments.
- Categorize operation as read-only if it does not involve any state or data modification.
- Return a list of tool names that are strictly read-only. If you cannot make a decision, then it is not read-only.

Use this analysis to generate a list of tools performing read-only operations from the provided tool requests.
""",
            "parameters": {
                "type": "object",
                "properties": {
                    "read_only_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tool names which has read-only operations."
                    }
                },
                "required": []
            }
        }
    }


def _create_check_messages(tool_requests: List[ToolRequestContent]) -> List[Message]:
    """创建用于检测只读工具的消息"""
    tool_names = []
    for req in tool_requests:
        value = req.tool_call_value
        if value:
            tool_names.append(value.name)

    if not tool_names:
        return []

    messages = [
        Message.user(
            f"""Here are tool requests: {", ".join(tool_names)}

Analyze tool requests and list tools that perform read-only operations.

Guidelines for Read-Only Operations:
- Read-only operations do not modify any data or state.
- Examples include file reading, SELECT queries in SQL, and directory listing.
- Write operations include INSERT, UPDATE, DELETE, and file writing.

Please provide a list of tool names that qualify as read-only:"""
        )
    ]

    return messages


def _extract_read_only_tools(response: Message) -> Optional[List[str]]:
    """从响应中提取只读工具列表"""
    for content in response.content:
        if isinstance(content, ToolRequestContent):
            value = content.tool_call_value
            if value and value.name == "platform__tool_by_tool_permission":
                if value.arguments:
                    read_only_tools = value.arguments.get("read_only_tools")
                    if isinstance(read_only_tools, list):
                        return [t for t in read_only_tools if isinstance(t, str)]
    return None


async def detect_read_only_tools(
    provider: "BaseLLM",
    tool_requests: List[ToolRequestContent],
    system_prompt: Optional[str] = None
) -> List[str]:
    """
    使用 LLM 检测只读工具

    Args:
        provider: LLM 提供者
        tool_requests: 工具请求列表
        system_prompt: 系统提示词

    Returns:
        只读工具名称列表
    """
    if not tool_requests:
        return []

    tool = _create_read_only_tool_schema()
    messages = _create_check_messages(tool_requests)

    if not messages:
        return []

    try:
        response_msg, _ = await provider.agenerate(
            messages=messages,
            tools=[tool],
        )

        result = _extract_read_only_tools(response_msg)
        return result if result else []

    except Exception as e:
        logger.error(f"Error detecting read-only tools: {e}")
        return []


async def check_tool_permissions(
    candidate_requests: List[ToolRequestContent],
    mode: str,
    tools_with_readonly_annotation: Set[str],
    tools_without_annotation: Set[str],
    permission_manager: "PermissionManager",
    provider: Optional["BaseLLM"] = None,
) -> tuple[PermissionCheckResult, List[str]]:
    """
    检查工具权限

    Args:
        candidate_requests: 候选工具请求列表
        mode: 运行模式
        tools_with_readonly_annotation: 标记为只读的工具集
        tools_without_annotation: 未标记的工具集
        permission_manager: 权限管理器
        provider: LLM 提供者（用于智能模式）

    Returns:
        (PermissionCheckResult, extension_request_ids) 元组
    """
    approved = []
    needs_approval = []
    denied = []
    llm_detect_candidates = []
    extension_request_ids = []

    for request in candidate_requests:
        value = request.tool_call_value
        if not value:
            continue

        tool_name = value.name

        # Handle extension management tool
        if tool_name == MANAGE_EXTENSIONS_TOOL_NAME_COMPLETE:
            extension_request_ids.append(request.id)

        if mode == "chat":
            # Chat mode - no auto-approval
            needs_approval.append(request)
            continue

        elif mode == "auto":
            # Auto mode - approve everything
            approved.append(request)
            continue

        else:  # approve or smart_approve modes
            # 1. Check user-defined permission
            user_permission = _get_user_permission(permission_manager, tool_name)
            if user_permission:
                if user_permission == PermissionLevel.ALLOW:
                    approved.append(request)
                elif user_permission == PermissionLevel.ASK_BEFORE:
                    needs_approval.append(request)
                elif user_permission == PermissionLevel.DENY:
                    denied.append(request)
                continue

            # 2. Fallback based on mode and annotations
            if mode == "approve":
                needs_approval.append(request)

            elif mode == "smart_approve":
                # Check smart approve permission
                smart_permission = _get_smart_approve_permission(permission_manager, tool_name)
                if smart_permission:
                    if smart_permission == PermissionLevel.ALLOW:
                        approved.append(request)
                    elif smart_permission == PermissionLevel.ASK_BEFORE:
                        needs_approval.append(request)
                    elif smart_permission == PermissionLevel.DENY:
                        denied.append(request)
                    continue

                # Use annotations
                if tool_name in tools_with_readonly_annotation:
                    approved.append(request)
                elif tool_name in tools_without_annotation:
                    llm_detect_candidates.append(request)
                else:
                    needs_approval.append(request)

    # 3. LLM detection for smart_approve mode
    if llm_detect_candidates and mode == "smart_approve" and provider:
        detected_readonly_tools = await detect_read_only_tools(
            provider, llm_detect_candidates
        )

        for request in llm_detect_candidates:
            value = request.tool_call_value
            if value:
                tool_name = value.name

                if tool_name in detected_readonly_tools:
                    approved.append(request)
                    # Cache the decision
                    _update_smart_approve_permission(
                        permission_manager, tool_name, PermissionLevel.ALLOW
                    )
                else:
                    needs_approval.append(request)
                    # Cache the decision
                    _update_smart_approve_permission(
                        permission_manager, tool_name, PermissionLevel.ASK_BEFORE
                    )

    result = PermissionCheckResult(
        approved=approved,
        needs_approval=needs_approval,
        denied=denied,
    )

    return result, extension_request_ids


# Helper functions for permission manager interaction

def _get_user_permission(
    permission_manager: "PermissionManager",
    tool_name: str
) -> Optional["PermissionLevel"]:
    """获取用户定义的权限"""
    if hasattr(permission_manager, "get_user_permission"):
        return permission_manager.get_user_permission(tool_name)
    return None


def _get_smart_approve_permission(
    permission_manager: "PermissionManager",
    tool_name: str
) -> Optional["PermissionLevel"]:
    """获取智能的自动批准权限"""
    if hasattr(permission_manager, "get_smart_approve_permission"):
        return permission_manager.get_smart_approve_permission(tool_name)
    return None


def _update_smart_approve_permission(
    permission_manager: "PermissionManager",
    tool_name: str,
    level: "PermissionLevel"
) -> None:
    """更新智能自动批准权限"""
    if hasattr(permission_manager, "update_smart_approve_permission"):
        permission_manager.update_smart_approve_permission(tool_name, level)
