"""
Permission Manager

Manages tool permissions and approval workflows.
Reference: goose-rs permission module

Features:
- Permission levels per tool
- Approval workflow for sensitive operations
- Always allow / once / deny modes
- Permission caching
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.permission")


class PermissionLevel(str, Enum):
    """Permission levels for tools."""
    ALLOW = "allow"       # Always allow
    ONCE = "once"         # Allow once, then prompt
    DENY = "deny"         # Always deny
    PROMPT = "prompt"     # Always prompt for approval


class ApprovalStatus(str, Enum):
    """Approval request status."""
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


@dataclass
class ApprovalRequest:
    """Tool approval request."""
    tool_name: str
    arguments: Dict[str, Any]
    status: ApprovalStatus = ApprovalStatus.PENDING
    reason: Optional[str] = None
    requested_at: float = field(default_factory=lambda: __import__('time').time())
    approved_by: Optional[str] = None
    expires_in: float = 300.0  # 5 minutes default

    def is_expired(self) -> bool:
        import time
        return time.time() - self.requested_at > self.expires_in


@dataclass
class ToolPermission:
    """Tool permission configuration."""
    tool_name: str
    level: PermissionLevel = PermissionLevel.PROMPT
    requires_approval: bool = False
    approval_category: str = "default"
    allowed_users: List[str] = field(default_factory=list)
    denied_users: List[str] = field(default_factory=list)


class ApprovalCallback(ABC):
    """Abstract approval callback handler."""

    @abstractmethod
    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: Optional[str] = None
    ) -> bool:
        """Request user approval for a tool call."""
        pass


class UserApprovalCallback(ApprovalCallback):
    """Default approval callback using user input."""

    def __init__(self, auto_approve_safe: bool = True):
        self.auto_approve_safe = auto_approve_safe
        self._pending_approvals: Dict[str, ApprovalRequest] = {}
        self._lock = asyncio.Lock()

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: Optional[str] = None
    ) -> bool:
        """Request user approval via console input."""
        from goose.tools.inspection import SecurityInspector

        is_safe = self._check_safety(tool_name, arguments)

        if self.auto_approve_safe and is_safe:
            logger.debug(f"Auto-approved safe tool: {tool_name}")
            return True

        print(f"\n⚠️  Tool approval required: {tool_name}")
        if reason:
            print(f"   Reason: {reason}")
        print(f"   Arguments: {arguments}")
        print(f"   Safe: {is_safe}")

        while True:
            try:
                response = input("\nAllow? [y/n/a/q]: ").lower().strip()
                if response in ('y', 'yes'):
                    return True
                elif response in ('n', 'no'):
                    return False
                elif response in ('a', 'always'):
                    self.auto_approve_safe = True
                    return True
                elif response in ('q', 'quit'):
                    return False
            except (EOFError, KeyboardInterrupt):
                return False

    def _check_safety(self, tool_name: str, arguments: Dict[str, Any]) -> bool:
        """Check if tool call is safe to auto-approve."""
        inspector = SecurityInspector()
        from goose.tools.base import ToolRequest
        request = ToolRequest(name=tool_name, arguments=arguments)
        import asyncio
        result = asyncio.run(inspector.inspect(request, []))
        return result.action.value == "allow"


class PermissionManager:
    """
    Manages tool permissions and approval workflows.

    Reference: goose-rs PermissionManager
    """

    def __init__(self):
        self._permissions: Dict[str, ToolPermission] = {}
        self._approval_callback: ApprovalCallback = UserApprovalCallback()
        self._once_permissions: Dict[str, str] = {}  # session_id -> used_once tools
        self._lock = asyncio.Lock()

    def register_tool_permission(self, permission: ToolPermission) -> None:
        """Register a tool permission configuration."""
        self._permissions[permission.tool_name] = permission
        logger.info(f"Registered permission for tool: {permission.tool_name} -> {permission.level}")

    def set_tool_permission(
        self,
        tool_name: str,
        level: PermissionLevel,
        **kwargs
    ) -> None:
        """Set permission level for a tool."""
        self._permissions[tool_name] = ToolPermission(
            tool_name=tool_name,
            level=level,
            **kwargs
        )

    def get_tool_permission(self, tool_name: str) -> ToolPermission:
        """Get permission for a tool."""
        if tool_name not in self._permissions:
            return ToolPermission(tool_name=tool_name)
        return self._permissions[tool_name]

    def set_approval_callback(self, callback: ApprovalCallback) -> None:
        """Set custom approval callback."""
        self._approval_callback = callback

    async def check_permission(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_id: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a tool call is permitted.

        Returns:
            (is_allowed, reason_if_denied)
        """
        permission = self.get_tool_permission(tool_name)

        if user_id:
            if user_id in permission.denied_users:
                return False, f"User {user_id} is denied access to {tool_name}"

            if permission.allowed_users and user_id not in permission.allowed_users:
                return False, f"User {user_id} not in allowed list for {tool_name}"

        if permission.level == PermissionLevel.ALLOW:
            return True, None

        elif permission.level == PermissionLevel.DENY:
            return False, f"Tool {tool_name} is denied"

        elif permission.level == PermissionLevel.ONCE:
            from goose.conversation import Conversation
            session_id = getattr(Conversation, '_current_session_id', 'default')
            once_key = f"{session_id}:{tool_name}"

            if once_key in self._once_permissions:
                return False, f"Tool {tool_name} already used once"

            self._once_permissions[once_key] = "pending"
            return True, None

        elif permission.level == PermissionLevel.PROMPT:
            if permission.requires_approval:
                reason = permission.approval_category
                approved = await self._approval_callback.request_approval(
                    tool_name, arguments, reason
                )
                if not approved:
                    return False, "User denied approval"
            return True, None

        return True, None

    async def request_approval(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        reason: Optional[str] = None
    ) -> bool:
        """Request explicit approval for a tool call."""
        return await self._approval_callback.request_approval(
            tool_name, arguments, reason
        )

    def clear_once_permissions(self, session_id: str) -> None:
        """Clear once-permission cache for a session."""
        keys_to_remove = [k for k in self._once_permissions if k.startswith(session_id)]
        for k in keys_to_remove:
            del self._once_permissions[k]

    def get_permission_summary(self) -> dict:
        """Get permission summary."""
        return {
            "total_tools": len(self._permissions),
            "allowed": sum(1 for p in self._permissions.values() if p.level == PermissionLevel.ALLOW),
            "denied": sum(1 for p in self._permissions.values() if p.level == PermissionLevel.DENY),
            "prompt": sum(1 for p in self._permissions.values() if p.level == PermissionLevel.PROMPT),
            "once": sum(1 for p in self._permissions.values() if p.level == PermissionLevel.ONCE),
        }
