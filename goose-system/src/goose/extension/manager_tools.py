"""
Extension Manager Tools

扩展管理工具，提供动态管理扩展的能力。
参考 goose-rs 的 extension_manager_extension 设计。

提供以下工具:
- list_extensions: 列出所有扩展
- enable_extension: 启用扩展
- disable_extension: 禁用扩展
- get_extension_config: 获取扩展配置
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ..tools.base import Tool
from ..tools.executor import ToolExecutor
from ..tools.inspection import PermissionLevel


@dataclass
class ExtensionToolInfo:
    """扩展工具信息"""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtensionInfo:
    """扩展信息"""
    name: str
    version: str = ""
    description: str = ""
    enabled: bool = True
    tools: List[ExtensionToolInfo] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


class ExtensionManagerTools:
    """
    扩展管理工具类
    
    提供扩展的查询和管理功能。
    """
    
    def __init__(
        self,
        extension_manager: Optional[Any] = None,
        permission_store: Optional[Any] = None
    ):
        """
        初始化扩展管理工具
        
        Args:
            extension_manager: 扩展管理器实例
            permission_store: 权限存储
        """
        self._manager = extension_manager
        self._permission_store = permission_store
        self._enabled_extensions: Dict[str, bool] = {}
        self._extension_configs: Dict[str, Dict[str, Any]] = {}
    
    def set_extension_manager(self, manager: Any) -> None:
        """设置扩展管理器"""
        self._manager = manager
    
    def _check_permission(self, tool_name: str) -> bool:
        """检查权限"""
        if not self._permission_store:
            return True
        
        level = self._permission_store.get_permission(tool_name)
        return level != PermissionLevel.NEVER_ALLOW
    
    def list_extensions(self) -> Dict[str, Any]:
        """
        列出所有扩展
        
        Returns:
            扩展列表信息
        """
        if not self._check_permission("list_extensions"):
            return {"error": "Permission denied", "tool": "list_extensions"}
        
        extensions = []
        
        if self._manager:
            try:
                ext_list = self._manager.list_extensions()
                for ext_name in ext_list:
                    config = self._extension_configs.get(ext_name, {})
                    enabled = self._enabled_extensions.get(ext_name, config.get("enabled", True))
                    
                    tools = []
                    if hasattr(self._manager, 'get_extension_tools'):
                        try:
                            tool_defs = self._manager.get_extension_tools(ext_name)
                            for tool in tool_defs:
                                tools.append({
                                    "name": tool.name if hasattr(tool, 'name') else str(tool),
                                    "description": getattr(tool, 'description', '')
                                })
                        except Exception:
                            pass
                    
                    extensions.append({
                        "name": ext_name,
                        "enabled": enabled,
                        "tools_count": len(tools),
                        "tools": tools,
                    })
            except Exception as e:
                return {"error": str(e)}
        else:
            for name, config in self._extension_configs.items():
                extensions.append({
                    "name": name,
                    "enabled": self._enabled_extensions.get(name, True),
                    "tools_count": 0,
                    "tools": [],
                })
            
            extensions.append({
                "name": "todo",
                "enabled": True,
                "tools_count": 1,
                "tools": [{"name": "todo_write", "description": "Write TODO list"}],
            })
            extensions.append({
                "name": "skills",
                "enabled": True,
                "tools_count": 3,
                "tools": [
                    {"name": "load_skill", "description": "Load a skill"},
                    {"name": "list_skills", "description": "List available skills"},
                    {"name": "run_skill", "description": "Run a skill"},
                ],
            })
        
        return {
            "content": json.dumps(extensions, indent=2),
            "extensions": extensions,
            "count": len(extensions),
        }
    
    def enable_extension(self, name: str) -> Dict[str, Any]:
        """
        启用扩展
        
        Args:
            name: 扩展名称
            
        Returns:
            操作结果
        """
        if not self._check_permission("enable_extension"):
            return {"error": "Permission denied", "tool": "enable_extension"}
        
        self._enabled_extensions[name] = True
        
        if name in self._extension_configs:
            self._extension_configs[name]["enabled"] = True
        
        if self._manager:
            try:
                self._manager.enable_extension(name)
            except Exception as e:
                return {"error": str(e)}
        
        return {
            "content": f"Enabled extension: {name}",
            "name": name,
            "enabled": True,
        }
    
    def disable_extension(self, name: str) -> Dict[str, Any]:
        """
        禁用扩展
        
        Args:
            name: 扩展名称
            
        Returns:
            操作结果
        """
        if not self._check_permission("disable_extension"):
            return {"error": "Permission denied", "tool": "disable_extension"}
        
        self._enabled_extensions[name] = False
        
        if name in self._extension_configs:
            self._extension_configs[name]["enabled"] = False
        
        if self._manager:
            try:
                self._manager.disable_extension(name)
            except Exception as e:
                return {"error": str(e)}
        
        return {
            "content": f"Disabled extension: {name}",
            "name": name,
            "enabled": False,
        }
    
    def get_extension_config(self, name: str) -> Dict[str, Any]:
        """
        获取扩展配置
        
        Args:
            name: 扩展名称
            
        Returns:
            扩展配置信息
        """
        if not self._check_permission("get_extension_config"):
            return {"error": "Permission denied", "tool": "get_extension_config"}
        
        if name in self._extension_configs:
            config = self._extension_configs[name]
            return {
                "content": json.dumps(config, indent=2),
                "config": config,
            }
        
        return {
            "error": f"Extension not found: {name}",
            "name": name,
        }
    
    def add_extension_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        添加扩展配置
        
        Args:
            config: 扩展配置
            
        Returns:
            操作结果
        """
        if not self._check_permission("add_extension_config"):
            return {"error": "Permission denied", "tool": "add_extension_config"}
        
        name = config.get("name")
        if not name:
            return {"error": "Extension name is required"}
        
        self._extension_configs[name] = config
        
        return {
            "content": f"Added extension config: {name}",
            "name": name,
            "config": config,
        }
    
    def remove_extension_config(self, name: str) -> Dict[str, Any]:
        """
        移除扩展配置
        
        Args:
            name: 扩展名称
            
        Returns:
            操作结果
        """
        if not self._check_permission("remove_extension_config"):
            return {"error": "Permission denied", "tool": "remove_extension_config"}
        
        if name in self._extension_configs:
            del self._extension_configs[name]
            self._enabled_extensions.pop(name, None)
            return {
                "content": f"Removed extension config: {name}",
                "name": name,
            }
        
        return {
            "error": f"Extension not found: {name}",
            "name": name,
        }
    
    def get_enabled_extensions(self) -> List[str]:
        """获取所有已启用的扩展"""
        return [name for name, enabled in self._enabled_extensions.items() if enabled]
    
    def get_disabled_extensions(self) -> List[str]:
        """获取所有已禁用的扩展"""
        return [name for name, enabled in self._enabled_extensions.items() if not enabled]


def create_extension_manager_tools(
    extension_manager: Optional[Any] = None,
    permission_store: Optional[Any] = None
) -> List[Tool]:
    """
    创建扩展管理工具列表
    
    Args:
        extension_manager: 扩展管理器实例
        permission_store: 权限存储
        
    Returns:
        工具列表
    """
    tools = []
    
    def list_extensions_fn():
        """List all extensions"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.list_extensions()
    
    def enable_extension_fn(name: str):
        """Enable an extension by name"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.enable_extension(name)
    
    def disable_extension_fn(name: str):
        """Disable an extension by name"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.disable_extension(name)
    
    def get_extension_config_fn(name: str):
        """Get extension configuration"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.get_extension_config(name)
    
    def add_extension_config_fn(config: Dict[str, Any]):
        """Add extension configuration"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.add_extension_config(config)
    
    def remove_extension_config_fn(name: str):
        """Remove extension configuration"""
        em = ExtensionManagerTools(extension_manager, permission_store)
        return em.remove_extension_config(name)
    
    return [
        Tool(
            name="list_extensions",
            description="List all installed extensions with their status and tools",
            parameters={
                "type": "object",
                "properties": {},
                "required": []
            },
        ),
        Tool(
            name="enable_extension",
            description="Enable an extension by name",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Extension name to enable"}
                },
                "required": ["name"]
            },
        ),
        Tool(
            name="disable_extension",
            description="Disable an extension by name",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Extension name to disable"}
                },
                "required": ["name"]
            },
        ),
        Tool(
            name="get_extension_config",
            description="Get the configuration of an extension",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Extension name"}
                },
                "required": ["name"]
            },
        ),
        Tool(
            name="add_extension_config",
            description="Add or update extension configuration",
            parameters={
                "type": "object",
                "properties": {
                    "config": {
                        "type": "object",
                        "description": "Extension configuration object"
                    }
                },
                "required": ["config"]
            },
        ),
        Tool(
            name="remove_extension_config",
            description="Remove extension configuration",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Extension name to remove"}
                },
                "required": ["name"]
            },
        ),
    ]


def register_extension_manager_tools(
    executor: ToolExecutor,
    extension_manager: Optional[Any] = None,
    permission_store: Optional[Any] = None
) -> None:
    """
    注册扩展管理工具到执行器
    
    Args:
        executor: 工具执行器
        extension_manager: 扩展管理器
        permission_store: 权限存储
    """
    em = ExtensionManagerTools(extension_manager, permission_store)
    
    executor.register_handler("list_extensions", em.list_extensions)
    executor.register_handler("enable_extension", em.enable_extension)
    executor.register_handler("disable_extension", em.disable_extension)
    executor.register_handler("get_extension_config", em.get_extension_config)
    executor.register_handler("add_extension_config", em.add_extension_config)
    executor.register_handler("remove_extension_config", em.remove_extension_config)
