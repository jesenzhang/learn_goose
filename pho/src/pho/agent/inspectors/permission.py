"""
PermissionInspector - Check user permissions for tool access.

This inspector implements permission checks based on:
- User roles
- Session context
- Tool-specific permissions
- Resource ownership
"""

import logging
from typing import Dict, Any, Optional, Set, List, Callable
from enum import Enum
from .base import ToolInspector, InspectorResult, InspectorAction

logger = logging.getLogger(__name__)


class Permission(str, Enum):
    """Permission levels"""
    NONE = "none"           # No access
    READ = "read"           # Read-only access
    WRITE = "write"         # Write access
    EXECUTE = "execute"     # Execute access
    ADMIN = "admin"         # Full administrative access


class Role(str, Enum):
    """User roles"""
    GUEST = "guest"         # Unauthenticated user
    USER = "user"           # Regular authenticated user
    POWER_USER = "power_user"  # User with elevated permissions
    ADMIN = "admin"         # Administrator

    @classmethod
    def from_str(cls, value: str) -> "Role":
        """Parse role from string, default to GUEST"""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.GUEST


class PermissionInspector(ToolInspector):
    """
    Inspector that checks user permissions for tool access.

    Uses a role-based access control (RBAC) system.
    """

    # Default role permissions
    DEFAULT_ROLE_PERMISSIONS = {
        Role.GUEST: {
            "read_only_tools": Permission.READ,
        },
        Role.USER: {
            "read_only_tools": Permission.READ,
            "write_tools": Permission.WRITE,
            "analysis_tools": Permission.READ,
        },
        Role.POWER_USER: {
            "read_only_tools": Permission.READ,
            "write_tools": Permission.WRITE,
            "analysis_tools": Permission.EXECUTE,
            "execute_tools": Permission.EXECUTE,
        },
        Role.ADMIN: {
            "*": Permission.ADMIN,  # All tools
        }
    }

    # Tool categories
    TOOL_CATEGORIES = {
        # Read tools
        "read_file": "read_only_tools",
        "list_files": "read_only_tools",
        "search": "read_only_tools",
        "grep": "read_only_tools",

        # Write tools
        "write_file": "write_tools",
        "create_file": "write_tools",
        "delete_file": "write_tools",
        "edit_file": "write_tools",

        # Analysis tools
        "analyze": "analysis_tools",
        "summarize": "analysis_tools",
        "extract": "analysis_tools",

        # Execute tools
        "execute_command": "execute_tools",
        "run_script": "execute_tools",
        "bash": "execute_tools",
    }

    def __init__(
        self,
        priority: int = 20,
        enabled: bool = True,
        role_permissions: Optional[Dict[Role, Dict[str, Permission]]] = None,
        custom_tool_mapping: Optional[Dict[str, str]] = None,
        default_role: Role = Role.GUEST,
        permission_callback: Optional[Callable[[str, str, Dict[str, Any]], bool]] = None
    ):
        """
        Initialize PermissionInspector.

        Args:
            priority: Inspector priority (default 20)
            enabled: Whether inspector is enabled
            role_permissions: Custom role-to-permissions mapping
            custom_tool_mapping: Custom tool-to-category mapping
            default_role: Default role if not specified in context
            permission_callback: Optional async callback for custom permission checks
        """
        super().__init__(priority=priority)
        if not enabled:
            self.disable()

        self.role_permissions = role_permissions or self.DEFAULT_ROLE_PERMISSIONS
        self.tool_categories = {**self.TOOL_CATEGORIES}
        if custom_tool_mapping:
            self.tool_categories.update(custom_tool_mapping)
        self.default_role = default_role
        self.permission_callback = permission_callback

    async def inspect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> InspectorResult:
        """Inspect tool call for proper permissions"""

        context = context or {}

        # Get user role from context
        role_str = context.get("user_role", context.get("role", self.default_role.value))
        role = Role.from_str(role_str)

        # Get user_id for logging
        user_id = context.get("user_id", context.get("user", "unknown"))

        # Check admin bypass
        if role == Role.ADMIN:
            logger.debug(f"Admin user '{user_id}' granted access to '{tool_name}'")
            return InspectorResult.allow(reason="Admin access granted")

        # Get tool category
        category = self.tool_categories.get(tool_name, "read_only_tools")

        # Check role permissions
        role_perms = self.role_permissions.get(role, {})

        # Check wildcard permission
        if "*" in role_perms:
            required_perm = role_perms["*"]
        else:
            required_perm = role_perms.get(category)

        if required_perm is None:
            # No permission defined for this category
            return InspectorResult.deny(
                reason=f"Role '{role.value}' has no permissions for category '{category}'",
                error_message=f"You don't have permission to use this tool"
            )

        # Check if permission level is sufficient
        if required_perm == Permission.NONE:
            return InspectorResult.deny(
                reason=f"Role '{role.value}' has no access to tool '{tool_name}'",
                error_message=f"You don't have permission to use this tool"
            )

        # Call custom permission callback if provided
        if self.permission_callback:
            try:
                has_permission = await self._call_permission_callback(
                    self.permission_callback, user_id, tool_name, tool_args, context
                )
                if not has_permission:
                    return InspectorResult.deny(
                        reason=f"Custom permission check failed for '{tool_name}'",
                        error_message=f"Permission denied for this tool"
                    )
            except Exception as e:
                logger.error(f"Permission callback error: {e}")
                return InspectorResult.deny(
                    reason=f"Permission check failed: {e}",
                    error_message=f"Unable to verify permissions"
                )

        logger.debug(
            f"User '{user_id}' (role: {role.value}) granted {required_perm.value} "
            f"access to '{tool_name}'"
        )
        return InspectorResult.allow(
            reason=f"Permission granted: {required_perm.value} access"
        )

    async def _call_permission_callback(
        self,
        callback: Callable,
        user_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Dict[str, Any]
    ) -> bool:
        """Call the permission callback (sync or async)"""
        if asyncio.iscoroutinefunction(callback):
            return await callback(user_id, tool_name, tool_args, context)
        else:
            return callback(user_id, tool_name, tool_args, context)

    def add_tool_permission(self, tool_name: str, category: str) -> None:
        """Add a tool to a permission category"""
        self.tool_categories[tool_name] = category

    def set_role_permission(
        self,
        role: Role,
        category: str,
        permission: Permission
    ) -> None:
        """Set permission for a specific role and category"""
        if role not in self.role_permissions:
            self.role_permissions[role] = {}
        self.role_permissions[role][category] = permission

    def grant_wildcard_permission(self, role: Role, permission: Permission) -> None:
        """Grant wildcard permission to a role"""
        if role not in self.role_permissions:
            self.role_permissions[role] = {}
        self.role_permissions[role]["*"] = permission


# Need to import asyncio
import asyncio


__all__ = ["PermissionInspector", "Permission", "Role"]
