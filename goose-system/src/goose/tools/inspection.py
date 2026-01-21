"""
Tool Inspection

工具检查器，实现安全检查、权限检查等。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base import Tool, ToolRequest


class InspectionAction(Enum):
    """检查动作"""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


@dataclass
class InspectionResult:
    """检查结果"""
    action: InspectionAction
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def allow(cls, message: Optional[str] = None) -> "InspectionResult":
        return InspectionResult(action=InspectionAction.ALLOW, message=message)
    
    @classmethod
    def deny(cls, message: str) -> "InspectionResult":
        return InspectionResult(action=InspectionAction.DENY, message=message)
    
    @classmethod
    def require_approval(cls, message: str) -> "InspectionResult":
        return InspectionResult(action=InspectionAction.REQUIRE_APPROVAL, message=message)


class ToolInspector(ABC):
    """工具检查器基类"""
    
    def __init__(self, name: str = "BaseInspector", priority: int = 0):
        self.name = name
        self.priority = priority
        self._tools: Dict[str, Tool] = {}
    
    def register_tool(self, tool: Tool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def unregister_tool(self, name: str) -> None:
        """注销工具"""
        self._tools.pop(name, None)
    
    @abstractmethod
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> InspectionResult:
        """检查工具请求"""
        pass
    
    @property
    def tools(self) -> Dict[str, Tool]:
        """获取注册的工俱"""
        return self._tools.copy()


class SecurityInspector(ToolInspector):
    """安全检查器"""
    
    def __init__(self):
        super().__init__("SecurityInspector", priority=100)
        
        # 危险模式
        self._dangerous_patterns = [
            (r"os\.system", "Command execution via os.system"),
            (r"subprocess", "Subprocess execution"),
            (r"eval\s*\(", "Dynamic code execution via eval"),
            (r"exec\s*\(", "Dynamic code execution via exec"),
            (r"__import__", "Dynamic module import"),
            (r"open\s*\(", "File system access"),
            (r"rm\s+-rf", "Destructive file operation"),
            (r"chmod\s+777", "Permission escalation"),
            (r"sudo\s+", "Privilege escalation"),
        ]
    
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> InspectionResult:
        """执行安全检查"""
        tool_name = request.name.lower()
        arguments = request.arguments or {}
        
        # 检查工具名
        if any(danger in tool_name for danger, _ in self._dangerous_patterns):
            return InspectionResult.deny(
                f"Potentially dangerous tool name: {tool_name}"
            )
        
        # 检查参数
        arguments_str = str(arguments).lower()
        for pattern, description in self._dangerous_patterns:
            import re
            if re.search(pattern, arguments_str, re.IGNORECASE):
                return InspectionResult.deny(
                    f"Potentially dangerous operation detected: {description}"
                )
        
        # 检查提示注入
        user_messages = [m for m in conversation if m.get("role") == "user"]
        if user_messages:
            last_user_msg = user_messages[-1].get("content", "")
            if self._check_prompt_injection(last_user_msg):
                return InspectionResult.deny(
                    "Potential prompt injection detected in user message"
                )
        
        return InspectionResult.allow()
    
    def _check_prompt_injection(self, text: str) -> bool:
        """检查提示注入"""
        injection_patterns = [
            r"ignore\s+(previous|above|all)\s+(instructions|prompts?)",
            r"system\s*message",
            r"you\s+are\s+(now|acting\s+as|a)",
            r"developer\s+mode",
            r"jailbreak",
            r"\\\(?\\?\(?system\\)?\\)?\\)?",
        ]
        
        import re
        text_lower = text.lower()
        for pattern in injection_patterns:
            if re.search(pattern, text_lower):
                return True
        return False


class PermissionInspector(ToolInspector):
    """权限检查器"""
    
    def __init__(self):
        super().__init__("PermissionInspector", priority=90)
        self._permission_levels: Dict[str, str] = {}  # tool_name -> level
        self._readonly_tools: set = set()
        self._default_level: str = "prompt"  # prompt / allow / deny
    
    def set_tool_permission(self, tool_name: str, level: str) -> None:
        """设置工具权限级别"""
        self._permission_levels[tool_name] = level
    
    def set_readonly_tools(self, tools: List[str]) -> None:
        """设置只读工具列表"""
        self._readonly_tools = set(tools)
    
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> InspectionResult:
        """执行权限检查"""
        tool_name = request.name
        
        # 检查只读工具
        if tool_name in self._readonly_tools:
            # 只读工具只能用于读取操作
            arguments = request.arguments or {}
            write_operations = ["write", "create", "update", "delete", "remove"]
            if any(op in arguments.get("mode", "").lower() for op in write_operations):
                return InspectionResult.deny(
                    f"Read-only tool '{tool_name}' cannot be used for write operations"
                )
        
        # 检查权限级别
        level = self._permission_levels.get(tool_name, self._default_level)
        
        if level == "allow":
            return InspectionResult.allow()
        elif level == "deny":
            return InspectionResult.deny(f"Tool '{tool_name}' has been disabled")
        else:  # "prompt"
            # 检查是否需要特殊权限
            if self._requires_approval(tool_name):
                return InspectionResult.require_approval(
                    f"Tool '{tool_name}' requires user approval"
                )
            return InspectionResult.allow()
    
    def _requires_approval(self, tool_name: str) -> bool:
        """检查是否需要批准"""
        sensitive_tools = [
            "write_file", "delete_file", "execute_code",
            "run_shell", "delete_folder", "network_request"
        ]
        return tool_name in sensitive_tools


class RepetitionInspector(ToolInspector):
    """重复检查器"""
    
    def __init__(self):
        super().__init__("RepetitionInspector", priority=10)
        self._last_tool_calls: List[Dict[str, Any]] = []
        self._max_repetitions: int = 3
    
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> InspectionResult:
        """检查重复调用"""
        # 记录当前调用
        current_call = {
            "name": request.name,
            "args": request.arguments
        }
        
        # 检查重复
        repetitions = 0
        for prev in reversed(self._last_tool_calls):
            if (prev["name"] == current_call["name"] and
                prev["args"] == current_call["args"]):
                repetitions += 1
            else:
                break
        
        # 更新记录
        self._last_tool_calls.append(current_call)
        if len(self._last_tool_calls) > 10:
            self._last_tool_calls = self._last_tool_calls[-10:]
        
        if repetitions >= self._max_repetitions:
            return InspectionResult.deny(
                f"Tool '{request.name}' has been called {repetitions + 1} times consecutively"
            )
        
        return InspectionResult.allow()


class InspectionManager:
    """检查器管理器"""
    
    def __init__(self):
        self._inspectors: List[ToolInspector] = []
    
    def add_inspector(self, inspector: ToolInspector) -> None:
        """添加检查器（按优先级排序）"""
        self._inspectors.append(inspector)
        self._inspectors.sort(key=lambda x: x.priority, reverse=True)
    
    def remove_inspector(self, name: str) -> bool:
        """移除检查器"""
        for i, inspector in enumerate(self._inspectors):
            if inspector.name == name:
                del self._inspectors[i]
                return True
        return False
    
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> List[InspectionResult]:
        """执行所有检查"""
        results = []
        for inspector in self._inspectors:
            result = await inspector.inspect(request, conversation)
            results.append(result)
            # 如果拒绝，立即返回
            if result.action == InspectionAction.DENY:
                break
        return results
    
    def process_results(
        self,
        results: List[InspectionResult]
    ) -> tuple[List[InspectionResult], List[InspectionResult], List[InspectionResult]]:
        """处理检查结果"""
        approved = []
        needs_approval = []
        denied = []
        
        for result in results:
            if result.action == InspectionAction.ALLOW:
                approved.append(result)
            elif result.action == InspectionAction.REQUIRE_APPROVAL:
                needs_approval.append(result)
            else:
                denied.append(result)
        
        return approved, needs_approval, denied
