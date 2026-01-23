"""
Permission Management

权限管理系统，支持：
- 工具级权限控制
- 权限级别 (always_allow, confirm, deny)
- 按扩展管理权限
- 持久化存储

Reference: goose-rs/crates/goose/src/config/permission.rs
"""

import os
import yaml
import threading
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger("goose.config.permission")


class PermissionLevel(str, Enum):
    """权限级别"""
    ALWAYS_ALLOW = "always_allow"
    CONFIRM = "confirm"
    DENY = "deny"
    
    @classmethod
    def from_string(cls, value: str) -> 'PermissionLevel':
        value = value.lower()
        for level in cls:
            if level.value == value:
                return level
        return cls.CONFIRM
    
    @classmethod
    def default(cls) -> 'PermissionLevel':
        return cls.CONFIRM


@dataclass
class ToolPermission:
    """工具权限配置"""
    tool_name: str
    level: PermissionLevel = PermissionLevel.CONFIRM
    description: str = ""


@dataclass
class ExtensionPermissions:
    """扩展权限配置"""
    extension_name: str
    default_level: PermissionLevel = PermissionLevel.CONFIRM
    tools: Dict[str, ToolPermission] = field(default_factory=dict)
    
    def get_tool_level(self, tool_name: str) -> PermissionLevel:
        """获取工具权限级别"""
        if tool_name in self.tools:
            return self.tools[tool_name].level
        return self.default_level
    
    def set_tool_level(self, tool_name: str, level: PermissionLevel) -> None:
        """设置工具权限级别"""
        if tool_name not in self.tools:
            self.tools[tool_name] = ToolPermission(tool_name=tool_name)
        self.tools[tool_name].level = level
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "extension_name": self.extension_name,
            "default_level": self.default_level.value,
            "tools": {
                name: {"level": perm.level.value, "description": perm.description}
                for name, perm in self.tools.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ExtensionPermissions':
        """从字典创建"""
        ext_perms = cls(
            extension_name=data.get("extension_name", ""),
            default_level=PermissionLevel.from_string(data.get("default_level", "confirm"))
        )
        for name, perm_data in data.get("tools", {}).items():
            ext_perms.tools[name] = ToolPermission(
                tool_name=name,
                level=PermissionLevel.from_string(perm_data.get("level", "confirm")),
                description=perm_data.get("description", "")
            )
        return ext_perms


class PermissionManager:
    """权限管理器"""
    
    PERMISSIONS_FILE = "permissions.yaml"
    
    _instance: Optional['PermissionManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'PermissionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = PermissionManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'PermissionManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = config_dir or os.path.expanduser("~/.config/goose")
        self._permissions_file = Path(self._config_dir) / self.PERMISSIONS_FILE
        self._permissions: Dict[str, ExtensionPermissions] = {}
        self._default_level = PermissionLevel.CONFIRM
        self._lock = threading.Lock()
        self._load_permissions()
    
    def _load_permissions(self) -> None:
        """加载权限配置"""
        if self._permissions_file.exists():
            try:
                with open(self._permissions_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                self._default_level = PermissionLevel.from_string(
                    data.get("default_level", "confirm")
                )
                
                for ext_name, ext_data in data.get("extensions", {}).items():
                    if isinstance(ext_data, dict):
                        self._permissions[ext_name] = ExtensionPermissions.from_dict({
                            "extension_name": ext_name,
                            **ext_data
                        })
            except Exception as e:
                logger.error(f"Failed to load permissions: {e}")
    
    def _save_permissions(self) -> None:
        """保存权限配置"""
        try:
            self._permissions_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                "default_level": self._default_level.value,
                "extensions": {
                    name: ext_perms.to_dict()
                    for name, ext_perms in self._permissions.items()
                }
            }
            
            with open(self._permissions_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Saved permissions to {self._permissions_file}")
        except Exception as e:
            logger.error(f"Failed to save permissions: {e}")
    
    def get_default_level(self) -> PermissionLevel:
        """获取默认权限级别"""
        return self._default_level
    
    def set_default_level(self, level: PermissionLevel) -> None:
        """设置默认权限级别"""
        with self._lock:
            self._default_level = level
            self._save_permissions()
    
    def get_extension_permissions(self, extension_name: str) -> ExtensionPermissions:
        """获取扩展权限配置"""
        with self._lock:
            if extension_name not in self._permissions:
                self._permissions[extension_name] = ExtensionPermissions(
                    extension_name=extension_name,
                    default_level=self._default_level
                )
            return self._permissions[extension_name]
    def set_extension_default_level(self, extension_name: str, level: PermissionLevel) -> None:
        """设置扩展默认权限级别"""
        with self._lock:
            if extension_name not in self._permissions:
                self._permissions[extension_name] = ExtensionPermissions(
                    extension_name=extension_name,
                    default_level=level
                )
            else:
                self._permissions[extension_name].default_level = level
            self._save_permissions()
    
    def set_tool_permission(
        self,
        extension_name: str,
        tool_name: str,
        level: PermissionLevel
    ) -> None:
        """设置工具权限"""
        with self._lock:
            if extension_name not in self._permissions:
                self._permissions[extension_name] = ExtensionPermissions(
                    extension_name=extension_name,
                    default_level=self._default_level
                )
            self._permissions[extension_name].set_tool_level(tool_name, level)
            self._save_permissions()
    
    def get_tool_permission(
        self,
        extension_name: str,
        tool_name: str
    ) -> PermissionLevel:
        """获取工具权限"""
        ext_perms = self.get_extension_permissions(extension_name)
        return ext_perms.get_tool_level(tool_name)
    
    def check_permission(
        self,
        extension_name: str,
        tool_name: str
    ) -> bool:
        """
        检查工具是否被允许执行
        
        Returns:
            True 如果允许执行，False 如果需要确认
        """
        level = self.get_tool_permission(extension_name, tool_name)
        return level == PermissionLevel.ALWAYS_ALLOW
    
    def needs_confirmation(
        self,
        extension_name: str,
        tool_name: str
    ) -> bool:
        """检查工具是否需要确认"""
        level = self.get_tool_permission(extension_name, tool_name)
        return level == PermissionLevel.CONFIRM
    
    def is_denied(
        self,
        extension_name: str,
        tool_name: str
    ) -> bool:
        """检查工具是否被拒绝"""
        level = self.get_tool_permission(extension_name, tool_name)
        return level == PermissionLevel.DENY
    
    def remove_extension(self, extension_name: str) -> bool:
        """删除扩展权限配置"""
        with self._lock:
            if extension_name in self._permissions:
                del self._permissions[extension_name]
                self._save_permissions()
                return True
            return False
    
    def get_all_extensions(self) -> List[str]:
        """获取所有有权限配置的扩展"""
        return list(self._permissions.keys())
    
    def reset_extension_permissions(self, extension_name: str) -> None:
        """重置扩展权限为默认"""
        with self._lock:
            if extension_name in self._permissions:
                self._permissions[extension_name].default_level = self._default_level
                self._permissions[extension_name].tools = {}
                self._save_permissions()


# 全局快捷函数

def get_permission_manager() -> PermissionManager:
    """获取权限管理器单例"""
    return PermissionManager.get_instance()


def get_tool_permission(extension_name: str, tool_name: str) -> PermissionLevel:
    """获取工具权限"""
    return get_permission_manager().get_tool_permission(extension_name, tool_name)


def set_tool_permission(
    extension_name: str,
    tool_name: str,
    level: PermissionLevel
) -> None:
    """设置工具权限"""
    get_permission_manager().set_tool_permission(extension_name, tool_name, level)


def check_permission(extension_name: str, tool_name: str) -> bool:
    """检查工具是否被允许执行"""
    return get_permission_manager().check_permission(extension_name, tool_name)


def needs_confirmation(extension_name: str, tool_name: str) -> bool:
    """检查工具是否需要确认"""
    return get_permission_manager().needs_confirmation(extension_name, tool_name)


def is_denied(extension_name: str, tool_name: str) -> bool:
    """检查工具是否被拒绝"""
    return get_permission_manager().is_denied(extension_name, tool_name)


def set_default_permission_level(level: PermissionLevel) -> None:
    """设置默认权限级别"""
    get_permission_manager().set_default_level(level)


def remove_extension_permissions(extension_name: str) -> bool:
    """删除扩展权限配置"""
    return get_permission_manager().remove_extension(extension_name)
