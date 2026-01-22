"""
Tool Interceptor - 工具拦截器

实现 allowed-tools 权限控制逻辑。

Reference: Agent Skills 架构设计手册 - 工具拦截与权限网关
"""

from dataclasses import dataclass
from typing import Dict, Set, List, Optional, Callable, Any, FrozenSet


@dataclass
class ToolPermission:
    """工具权限结果"""
    tool_name: str
    allowed: bool
    reason: Optional[str] = None


class ToolInterceptor:
    """
    工具拦截器
    
    功能:
    1. 解析 SKILL.md 中的 allowed-tools 列表
    2. 拦截 LLM 的工具调用请求
    3. 根据当前激活的技能进行权限检查
    4. 拒绝未授权的工具调用
    
    Reference: 文档 "工具拦截与权限网关" 部分
    """
    
    # 全局禁止的工具列表 (安全敏感)
    GLOBAL_BLOCKED_TOOLS: FrozenSet[str] = frozenset({
        "Bash", "Shell", "Cmd", "Exec",  # 代码执行工具
        "Delete", "Remove",  # 危险的文件操作
        "System", "Admin", "Root",  # 系统级操作
    })
    
    def __init__(self):
        self._skill_permissions: Dict[str, Set[str]] = {}
        self._custom_blocked: Set[str] = set()
        self._custom_allowed: Set[str] = set()
        self._on_permission_checked: Optional[Callable[[ToolPermission], None]] = None
    
    def register_skill_tools(self, skill_name: str, allowed_tools: List[str]) -> None:
        """
        注册技能的允许工具列表
        
        Args:
            skill_name: 技能名称
            allowed_tools: 允许的工具列表 (为空表示允许所有)
        """
        self._skill_permissions[skill_name] = set(allowed_tools)
    
    def unregister_skill(self, skill_name: str) -> None:
        """注销技能"""
        self._skill_permissions.pop(skill_name, None)
    
    def block_tool(self, tool_name: str) -> None:
        """全局禁止某个工具"""
        self._custom_blocked.add(tool_name)
    
    def allow_tool(self, tool_name: str) -> None:
        """全局允许某个工具（覆盖技能配置）"""
        self._custom_allowed.add(tool_name)
    
    def set_permission_callback(self, callback: Callable[[ToolPermission], None]) -> None:
        """
        设置权限检查后的回调函数
        
        Args:
            callback: 接收 ToolPermission 的回调
        """
        self._on_permission_checked = callback
    
    def check_permission(
        self,
        tool_name: str,
        active_skills: List[str]
    ) -> ToolPermission:
        """
        检查工具调用权限
        
        权限检查优先级:
        1. 全局禁止的工具 -> 拒绝
        2. 自定义全局允许 -> 允许
        3. 技能允许列表为空 -> 允许所有
        4. 工具在允许列表中 -> 允许
        5. 其他情况 -> 拒绝
        
        Args:
            tool_name: 工具名称
            active_skills: 当前激活的技能列表 (L2 状态)
            
        Returns:
            ToolPermission: 权限结果
        """
        result = self._check_permission_impl(tool_name, active_skills)
        
        if self._on_permission_checked:
            self._on_permission_checked(result)
        
        return result
    
    def _check_permission_impl(
        self,
        tool_name: str,
        active_skills: List[str]
    ) -> ToolPermission:
        """权限检查实现"""
        
        # 1. 检查全局禁止 (安全敏感工具)
        if tool_name in self.GLOBAL_BLOCKED_TOOLS:
            return ToolPermission(
                tool_name=tool_name,
                allowed=False,
                reason=f"Tool '{tool_name}' is globally blocked for security"
            )
        
        # 2. 检查自定义禁止
        if tool_name in self._custom_blocked:
            return ToolPermission(
                tool_name=tool_name,
                allowed=False,
                reason=f"Tool '{tool_name}' is blocked by configuration"
            )
        
        # 3. 检查自定义允许
        if tool_name in self._custom_allowed:
            return ToolPermission(
                tool_name=tool_name,
                allowed=True
            )
        
        # 4. 检查技能权限
        for skill in active_skills:
            allowed = self._skill_permissions.get(skill, set())
            
            # 空列表表示允许所有工具
            if not allowed:
                return ToolPermission(
                    tool_name=tool_name,
                    allowed=True,
                    reason=f"Skill '{skill}' allows all tools"
                )
            
            # 工具在允许列表中
            if tool_name in allowed:
                return ToolPermission(
                    tool_name=tool_name,
                    allowed=True,
                    reason=f"Tool '{tool_name}' is allowed by skill '{skill}'"
                )
        
        # 5. 无技能允许此工具
        return ToolPermission(
            tool_name=tool_name,
            allowed=False,
            reason=f"Tool '{tool_name}' not in allowed-tools of active skills: {active_skills}"
        )
    
    def get_skill_permissions(self, skill_name: str) -> Set[str]:
        """获取技能的允许工具列表"""
        return self._skill_permissions.get(skill_name, set())
    
    def get_all_permissions(self) -> Dict[str, Set[str]]:
        """获取所有技能的权限配置"""
        return dict(self._skill_permissions)
    
    def clear(self) -> None:
        """清空所有配置"""
        self._skill_permissions.clear()
        self._custom_blocked.clear()
        self._custom_allowed.clear()
    
    def is_tool_allowed_anywhere(self, tool_name: str) -> bool:
        """检查工具是否被任何技能允许"""
        for allowed in self._skill_permissions.values():
            if tool_name in allowed:
                return True
        return False
    
    def get_blocked_tools_report(self) -> Dict[str, Any]:
        """获取阻止工具调用的报告"""
        return {
            "globally_blocked": list(self.GLOBAL_BLOCKED_TOOLS),
            "custom_blocked": list(self._custom_blocked),
            "skill_permissions": self.get_all_permissions(),
        }
