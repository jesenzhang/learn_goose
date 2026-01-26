"""
Tool Inspection Manager

工具检查管理器 (责任链模式)。
检查器链：SecurityInspector → PermissionInspector → RepetitionInspector
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from enum import Enum
import asyncio


class InspectionAction(str, Enum):
    """检查动作"""
    ALLOW = "allow"
    DENY = "deny"
    CONFIRM = "confirm"
    SKIP = "skip"
    REQUIRE_APPROVAL = "require_approval"

    @classmethod
    def require_approval(cls, reason: Optional[str] = None) -> "InspectionAction":
        """创建需要批准操作"""
        return cls.REQUIRE_APPROVAL


@dataclass
class InspectionResult:
    """检查结果"""
    allowed: bool
    action: InspectionAction = InspectionAction.ALLOW
    reason: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0  # 置信度，0.0-1.0
    inspector_name: str = ""  # 检查器名称
    tool_request_id: str = ""  # 工具请求 ID
    finding_id: Optional[str] = None  # 发现 ID


@dataclass
class ToolRequest:
    """工具请求"""
    id: str
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolInspector(ABC):
    """工具检查器基类"""
    
    @abstractmethod
    async def inspect(
        self,
        request: ToolRequest
    ) -> InspectionResult:
        """检查工具请求"""
        pass
    
    @property
    def name(self) -> str:
        """检查器名称"""
        return self.__class__.__name__


class SecurityInspector(ToolInspector):
    """安全检查器"""
    
    def __init__(
        self,
        blocked_patterns: Optional[List[str]] = None,
        allowed_tools: Optional[List[str]] = None
    ):
        self.blocked_patterns = blocked_patterns or [
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\(",
            r"open\s*\(",
            r"os\.system",
            r"subprocess",
        ]
        self.allowed_tools = allowed_tools or []
    
    async def inspect(
        self,
        request: ToolRequest
    ) -> InspectionResult:
        """安全扫描"""
        import re
        
        # 检查工具名称是否在允许列表中
        if self.allowed_tools and request.name not in self.allowed_tools:
            return InspectionResult(
                allowed=False,
                action=InspectionAction.DENY,
                reason=f"Tool '{request.name}' is not in the allowed list"
            )
        
        # 检查参数中的危险模式
        args_str = str(request.arguments)
        for pattern in self.blocked_patterns:
            if re.search(pattern, args_str, re.IGNORECASE):
                return InspectionResult(
                    allowed=False,
                    action=InspectionAction.DENY,
                    reason=f"Potentially dangerous pattern detected: {pattern}",
                    details={"pattern": pattern}
                )
        
        return InspectionResult(
            allowed=True,
            action=InspectionAction.ALLOW,
            reason="Security check passed"
        )


class LegacyPermissionInspector(ToolInspector):
    """旧的权限检查器（已弃用，请使用 permission.PermissionInspector）"""

    def __init__(self):
        self.permission_levels: Dict[str, str] = {}  # tool_name -> level
        self._approval_callbacks: Dict[str, asyncio.Future] = {}

    async def inspect(
        self,
        request: ToolRequest
    ) -> InspectionResult:
        """权限检查"""
        level = self.permission_levels.get(request.name, "unknown")

        if level == "always_allow":
            return InspectionResult(
                allowed=True,
                action=InspectionAction.ALLOW,
                reason="Tool has always allow permission"
            )
        elif level == "deny":
            return InspectionResult(
                allowed=False,
                action=InspectionAction.DENY,
                reason="Tool has deny permission"
            )
        elif level == "once":
            return InspectionResult(
                allowed=True,
                action=InspectionAction.ALLOW,
                reason="Tool has once permission"
            )
        elif level == "confirm":
            return InspectionResult(
                allowed=False,
                action=InspectionAction.CONFIRM,
                reason="Tool requires user confirmation",
                details={"tool_name": request.name}
            )

        # 默认需要确认
        return InspectionResult(
            allowed=False,
            action=InspectionAction.CONFIRM,
            reason="Tool permission not set",
            details={"tool_name": request.name}
        )

    def set_permission(self, tool_name: str, level: str) -> None:
        """设置工具权限"""
        self.permission_levels[tool_name] = level

# 保持向后兼容
PermissionInspector = LegacyPermissionInspector


class RepetitionInspector(ToolInspector):
    """重复检测器"""
    
    def __init__(self, max_repeat_count: int = 3):
        self.max_repeat_count = max_repeat_count
        self._tool_history: Dict[str, List[ToolRequest]] = {}
    
    async def inspect(
        self,
        request: ToolRequest
    ) -> InspectionResult:
        """重复检测"""
        history = self._tool_history.get(request.name, [])
        
        # 清理过期记录 (只保留最近 N 次)
        if len(history) > self.max_repeat_count * 2:
            self._tool_history[request.name] = history[-self.max_repeat_count * 2:]
        
        # 检查是否重复调用
        repeat_count = 0
        for prev in reversed(history):
            if self._is_similar(prev, request):
                repeat_count += 1
        
        if repeat_count >= self.max_repeat_count:
            return InspectionResult(
                allowed=False,
                action=InspectionAction.CONFIRM,
                reason=f"Tool '{request.name}' has been called {repeat_count + 1} times similarly",
                details={"repeat_count": repeat_count}
            )
        
        # 记录调用
        history.append(request)
        self._tool_history[request.name] = history
        
        return InspectionResult(
            allowed=True,
            action=InspectionAction.ALLOW,
            reason="No repetition detected"
        )
    
    def _is_similar(self, prev: ToolRequest, current: ToolRequest) -> bool:
        """判断两次调用是否相似"""
        return prev.name == current.name and prev.arguments == current.arguments
    
    def clear_history(self, tool_name: Optional[str] = None) -> None:
        """清除历史记录"""
        if tool_name:
            self._tool_history.pop(tool_name, None)
        else:
            self._tool_history.clear()


class ToolInspectionManager:
    """
    工具检查管理器 (责任链模式)
    
    检查器链：
    1. SecurityInspector - 安全扫描
    2. PermissionInspector - 权限检查
    3. RepetitionInspector - 重复检测
    """
    
    def __init__(self):
        self.inspectors: List[ToolInspector] = []
        self._enabled = True
    
    def add_inspector(self, inspector: ToolInspector) -> None:
        """添加检查器"""
        self.inspectors.append(inspector)
    
    def remove_inspector(self, name: str) -> bool:
        """移除检查器"""
        for i, inspector in enumerate(self.inspectors):
            if inspector.name == name:
                self.inspectors.pop(i)
                return True
        return False
    
    async def inspect(
        self,
        request: ToolRequest
    ) -> InspectionResult:
        """执行所有检查 (责任链)"""
        if not self._enabled:
            return InspectionResult(
                allowed=True,
                action=InspectionAction.ALLOW,
                reason="Inspection disabled"
            )
        
        for inspector in self.inspectors:
            result = await inspector.inspect(request)
            
            if not result.allowed:
                return result
            
            # 如果需要确认，直接返回
            if result.action == InspectionAction.CONFIRM:
                return result
        
        return InspectionResult(
            allowed=True,
            action=InspectionAction.ALLOW,
            reason="All inspections passed"
        )
    
    def enable(self) -> None:
        """启用检查"""
        self._enabled = True
    
    def disable(self) -> None:
        """禁用检查"""
        self._enabled = False
    
    def create_default_chain(self) -> "ToolInspectionManager":
        """创建默认检查链"""
        self.inspectors = [
            SecurityInspector(),
            LegacyPermissionInspector(),
            RepetitionInspector(),
        ]
        return self
