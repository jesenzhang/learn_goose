"""
Tool Inspection

工具检查器，实现安全检查、权限检查等。
参考 goose-rs 的工具权限系统设计。
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum

from .base import Tool, ToolRequest


class PermissionLevel(str, Enum):
    """工具权限级别，与 goose-rs 兼容"""
    ALWAYS_ALLOW = "always"      # 无需批准即可运行
    ASK_BEFORE = "ask"           # 需要确认
    NEVER_ALLOW = "never"        # 无法使用


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


class PermissionStore:
    """工具权限存储，支持持久化配置"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化权限存储
        
        Args:
            config_path: 权限配置文件路径
        """
        self.config_path = config_path
        self._permissions: Dict[str, PermissionLevel] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """从配置文件加载权限设置"""
        if not self.config_path:
            return
        
        import json
        import os
        
        if not os.path.exists(self.config_path):
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for tool_name, level in data.items():
                try:
                    self._permissions[tool_name] = PermissionLevel(level)
                except ValueError:
                    pass
        except Exception:
            pass
    
    def save_config(self) -> None:
        """保存权限配置到文件"""
        if not self.config_path:
            return
        
        import json
        import os
        
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        
        data = {name: level.value for name, level in self._permissions.items()}
        
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def get_permission(self, tool_name: str) -> PermissionLevel:
        """获取工具权限级别"""
        return self._permissions.get(tool_name, PermissionLevel.ASK_BEFORE)
    
    def set_permission(
        self,
        tool_name: str,
        level: PermissionLevel,
        save: bool = True
    ) -> None:
        """设置工具权限级别"""
        self._permissions[tool_name] = level
        if save:
            self.save_config()
    
    def set_permissions(
        self,
        permissions: Dict[str, PermissionLevel],
        save: bool = True
    ) -> None:
        """批量设置工具权限"""
        self._permissions.update(permissions)
        if save:
            self.save_config()
    
    def reset_permission(self, tool_name: str, save: bool = True) -> bool:
        """重置工具权限到默认值"""
        if tool_name in self._permissions:
            del self._permissions[tool_name]
            if save:
                self.save_config()
            return True
        return False
    
    def reset_all(self, save: bool = True) -> None:
        """重置所有权限"""
        self._permissions.clear()
        if save:
            self.save_config()
    
    def get_all_permissions(self) -> Dict[str, PermissionLevel]:
        """获取所有自定义权限设置"""
        return self._permissions.copy()
    
    def get_always_allow_tools(self) -> List[str]:
        """获取所有设置为 Always Allow 的工具"""
        return [name for name, level in self._permissions.items()
                if level == PermissionLevel.ALWAYS_ALLOW]
    
    def get_never_allow_tools(self) -> List[str]:
        """获取所有设置为 Never Allow 的工具"""
        return [name for name, level in self._permissions.items()
                if level == PermissionLevel.NEVER_ALLOW]
    
    def get_ask_before_tools(self) -> List[str]:
        """获取所有设置为 Ask Before 的工具"""
        return [name for name, level in self._permissions.items()
                if level == PermissionLevel.ASK_BEFORE]


class PermissionInspector(ToolInspector):
    """权限检查器"""
    
    def __init__(
        self,
        store: Optional[PermissionStore] = None,
        default_level: PermissionLevel = PermissionLevel.ASK_BEFORE
    ):
        """
        初始化权限检查器
        
        Args:
            store: 权限存储实例
            default_level: 默认权限级别
        """
        super().__init__("PermissionInspector", priority=90)
        self._store = store or PermissionStore()
        self._default_level = default_level
        self._readonly_tools: set = set()
    
    @property
    def store(self) -> PermissionStore:
        """获取权限存储"""
        return self._store
    
    def set_tool_permission(
        self,
        tool_name: str,
        level: PermissionLevel,
        save: bool = True
    ) -> None:
        """设置工具权限级别"""
        self._store.set_permission(tool_name, level, save)
    
    def set_permissions(
        self,
        permissions: Dict[str, PermissionLevel],
        save: bool = True
    ) -> None:
        """批量设置工具权限"""
        self._store.set_permissions(permissions, save)
    
    def set_readonly_tools(self, tools: List[str]) -> None:
        """设置只读工具列表"""
        self._readonly_tools = set(tools)
    
    def get_permission(self, tool_name: str) -> PermissionLevel:
        """获取工具权限级别"""
        return self._store.get_permission(tool_name)
    
    async def inspect(
        self,
        request: ToolRequest,
        conversation: List[Dict[str, Any]]
    ) -> InspectionResult:
        """执行权限检查"""
        tool_name = request.name
        
        level = self._store.get_permission(tool_name)
        
        if level == PermissionLevel.ALWAYS_ALLOW:
            return InspectionResult.allow("Always allowed")
        
        if level == PermissionLevel.NEVER_ALLOW:
            return InspectionResult.deny(f"Tool '{tool_name}' has been disabled (Never Allow)")
        
        # ASK_BEFORE - 需要检查是否需要批准
        return InspectionResult.require_approval(
            f"Tool '{tool_name}' requires user approval"
        )
    
    def _requires_approval(self, tool_name: str) -> bool:
        """检查是否需要批准"""
        sensitive_tools = [
            "write", "edit", "delete", "remove",
            "run_bash", "bash",
        ]
        return any(sensitive in tool_name.lower() for sensitive in sensitive_tools)


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
    
    def get_inspector(self, name: str) -> Optional[ToolInspector]:
        """获取检查器"""
        for inspector in self._inspectors:
            if inspector.name == name:
                return inspector
        return None
    
    @property
    def inspectors(self) -> List[ToolInspector]:
        """获取所有检查器"""
        return self._inspectors.copy()
    
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
    
    def create_default_chain(
        self,
        permission_store: Optional[PermissionStore] = None
    ) -> "InspectionManager":
        """
        创建默认检查链
        
        Args:
            permission_store: 权限存储实例
            
        Returns:
            InspectionManager 实例
        """
        self._inspectors = []
        
        security_inspector = SecurityInspector()
        self._inspectors.append(security_inspector)
        
        permission_inspector = PermissionInspector(store=permission_store)
        self._inspectors.append(permission_inspector)
        
        repetition_inspector = RepetitionInspector()
        self._inspectors.append(repetition_inspector)
        
        self._inspectors.sort(key=lambda x: x.priority, reverse=True)
        
        return self
    
    def can_execute_tool(
        self,
        tool_name: str,
        permission_store: Optional[PermissionStore] = None
    ) -> bool:
        """检查工具是否可以执行（不需用户确认）"""
        level = permission_store.get_permission(tool_name) if permission_store else PermissionLevel.ASK_BEFORE
        return level == PermissionLevel.ALWAYS_ALLOW
    
    def must_ask_permission(
        self,
        tool_name: str,
        permission_store: Optional[PermissionStore] = None
    ) -> bool:
        """检查工具是否需要用户确认"""
        level = permission_store.get_permission(tool_name) if permission_store else PermissionLevel.ASK_BEFORE
        return level == PermissionLevel.ASK_BEFORE
    
    def is_blocked(
        self,
        tool_name: str,
        permission_store: Optional[PermissionStore] = None
    ) -> bool:
        """检查工具是否被阻止"""
        level = permission_store.get_permission(tool_name) if permission_store else PermissionLevel.ASK_BEFORE
        return level == PermissionLevel.NEVER_ALLOW
