"""
Permission Configuration

对齐 goose-rs/crates/goose/src/config/permission.rs 的权限管理器。

功能：
- PermissionLevel: AlwaysAllow, AskBefore, NeverAllow
- PermissionConfig: always_allow, ask_before, never_allow 列表
- PermissionManager: 管理用户权限和智能批准权限
"""

import os
import yaml
import threading
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

logger = logging.getLogger("goose.config.permission_config")


class PermissionLevel(str, Enum):
    """权限级别（对齐 goose-rs）"""
    ALWAYS_ALLOW = "always_allow"
    ASK_BEFORE = "ask_before"
    NEVER_ALLOW = "never_allow"

    @classmethod
    def from_string(cls, value: str) -> "PermissionLevel":
        """从字符串创建权限级别"""
        value_lower = value.lower().replace("-", "_")
        for level in cls:
            if level.value == value_lower:
                return level
        return cls.ASK_BEFORE


@dataclass
class PermissionConfig:
    """权限配置（对齐 goose-rs）"""
    always_allow: List[str] = field(default_factory=list)
    ask_before: List[str] = field(default_factory=list)
    never_allow: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "always_allow": self.always_allow,
            "ask_before": self.ask_before,
            "never_allow": self.never_allow,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PermissionConfig":
        return cls(
            always_allow=data.get("always_allow", []),
            ask_before=data.get("ask_before", []),
            never_allow=data.get("never_allow", []),
        )


# Permission categories (matches goose-rs constants)
USER_PERMISSION = "user"
SMART_APPROVE_PERMISSION = "smart_approve"
PERMISSION_FILE = "permission.yaml"


class PermissionManager:
    """
    权限管理器（对齐 goose-rs PermissionManager）

    功能：
    - 用户权限管理（user category）
    - 智能批准权限管理（smart_approve category）
    - 持久化到 YAML 文件
    - 线程安全
    """

    _instance: Optional["PermissionManager"] = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "PermissionManager":
        """获取全局单例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = PermissionManager()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "PermissionManager") -> None:
        """设置全局实例（用于测试）"""
        with cls._lock:
            cls._instance = instance

    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化权限管理器

        Args:
            config_dir: 配置目录，默认为 ~/.config/goose
        """
        if config_dir is None:
            config_dir = Path.home() / ".config" / "goose"

        self.config_path = config_dir / PERMISSION_FILE
        self.permission_map: Dict[str, PermissionConfig] = {}
        self._lock = threading.RLock()

        self._load()

    def _load(self) -> None:
        """从文件加载权限"""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="="utf-8") as f:
                    data = yaml.safe_load(f) or {}

                # 加载权限配置
                self.permission_map = {}
                for key, value in data.items():
                    if isinstance(value, dict):
                        self.permission_map[key] = PermissionConfig.from_dict(value)

                logger.info(f"Loaded permissions from {self.config_path}")
            except Exception as e:
                logger.error(f"Failed to load permissions: {e}")
                self.permission_map = {}
        else:
            logger.info(f"Permission file not found: {self.config_path}")
            self.permission_map = {}
            # 确保目录存在
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

    def _save(self) -> None:
        """保存权限到文件"""
        try:
            data = {
                key: config.to_dict()
                for key, config in self.permission_map.items()
            }

            # 原子性写入
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

            temp_path.replace(self.config_path)

            logger.debug(f"Saved permissions to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save permissions: {e}")

    def get_permission_names(self) -> List[str]:
        """获取所有权限名称（键）"""
        with self._lock:
            return list(self.permission_map.keys())

    def _get_permission_config(self, name: str) -> PermissionConfig:
        """获取权限配置"""
        with self._lock:
            return self.permission_map.get(name, PermissionConfig())

    def _get_or_create_permission_config(self, name: str) -> PermissionConfig:
        """获取或创建权限配置"""
        with self._lock:
            if name not in self.permission_map:
                self.permission_map[name] = PermissionConfig()
            return self.permission_map[name]

    def get_user_permission(self, principal_name: str) -> Optional[PermissionLevel]:
        """
        获取用户权限级别

        Args:
            principal_name: 工具/主体名称

        Returns:
            权限级别，如果未配置则返回 None
        """
        config = self._get_permission_config(USER_PERMISSION)

        if principal_name in config.always_allow:
            return PermissionLevel.ALWAYS_ALLOW
        elif principal_name in config.ask_before:
            return PermissionLevel.ASK_BEFORE
        elif principal_name in config.never_allow:
            return PermissionLevel.NEVER_ALLOW

        return None

    def get_smart_approve_permission(self, principal_name: str) -> Optional[PermissionLevel]:
        """
        获取智能批准权限级别

        Args:
            principal_name: 工具/主体名称

        Returns:
            权限级别，如果未配置则返回 None
        """
        config = self._get_permission_config(SMART_APPROVE_PERMISSION)

        if principal_name in config.always_allow:
            return PermissionLevel.ALWAYS_ALLOW
        elif principal_name in config.ask_before:
            return PermissionLevel.ASK_BEFORE
        elif principal_name in config.never_allow:
            return PermissionLevel.NEVER_ALLOW

        return None

    def get_config_path(self) -> Path:
        """获取配置文件路径"""
        return self.config_path

    def _update_permission(
        self,
        name: str,
        principal_name: str,
        level: PermissionLevel
    ) -> None:
        """
        更新权限级别

        Args:
            name: 权限类别（user 或 smart_approve）
            principal_name: 工具/主体名称
            level: 权限级别
        """
        config = self._get_or_create_permission_config(name)

        # 从所有列表中移除 principal（避免重复）
        config.always_allow = [
            p for p in config.always_allow if p != principal_name
        ]
        config.ask_before = [
            p for p in config.ask_before if p != principal_name
        ]
        config.never_allow = [
            p for p in config.never_allow if p != principal_name
        ]

        # 添加到对应列表
        if level == PermissionLevel.ALWAYS_ALLOW:
            config.always_allow.append(principal_name)
        elif level == PermissionLevel.ASK_BEFORE:
            config.ask_before.append(principal_name)
        elif level == PermissionLevel.NEVER_ALLOW:
            config.never_allow.append(principal_name)

        # 保存
        self._save()

    def update_user_permission(
        self,
        principal_name: str,
        level: PermissionLevel
    ) -> None:
        """
        更新用户权限级别

        Args:
            principal_name: 工具/主体名称
            level: 权限级别
        """
        self._update_permission(USER_PERMISSION, principal_name, level)

    def update_smart_approve_permission(
        self,
        principal_name: str,
        level: PermissionLevel
    ) -> None:
        """
        更新智能批准权限级别

        Args:
            principal_name: 工具/主体名称
            level: 权限级别
        """
        self._update_permission(SMART_APPROVE_PERMISSION, principal_name, level)

    def remove_extension(self, extension_name: str) -> None:
        """
        移除所有以扩展名称开头的权限条目

        Args:
            extension_name: 扩展名称
        """
        with self._lock:
            for config in self.permission_map.values():
                # 保留不以 extension_name 开头的条目
                config.always_allow = [
                    p for p in config.always_allow if not p.startswith(extension_name)
                ]
                config.ask_before = [
                    p for p in config.ask_before if not p.startswith(extension_name)
                ]
                config.never_allow = [
                    p for p in config.never_allow if not p.startswith(extension_name)
                ]

            self._save()

    def get_all_permissions(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有权限（用于显示/调试）

        Returns:
            字典格式的权限数据
        """
        with self._lock:
            return {
                key: config.to_dict()
                for key, config in self.permission_map.items()
            }

    def clear(self) -> None:
        """清空所有权限"""
        with self._lock:
            self.permission_map.clear()
            self._save()

    def reload(self) -> None:
        """重新加载权限"""
        self._load()


# 全局快捷函数

def get_permission_manager() -> PermissionManager:
    """获取全局权限管理器"""
    return PermissionManager.instance()


def get_user_permission(principal_name: str) -> Optional[PermissionLevel]:
    """获取用户权限级别"""
    return get_permission_manager().get_user_permission(principal_name)


def get_smart_approve_permission(principal_name: str) -> Optional[PermissionLevel]:
    """获取智能批准权限级别"""
    return get_permission_manager().get_smart_approve_permission(principal_name)


def update_user_permission(principal_name: str, level: PermissionLevel) -> None:
    """更新用户权限级别"""
    get_permission_manager().update_user_permission(principal_name, level)


def update_smart_approve_permission(principal_name: str, level: PermissionLevel) -> None:
    """更新智能批准权限级别"""
    get_permission_manager().update_smart_approve_permission(principal_name, level)


def remove_extension(extension_name: str) -> None:
    """移除扩展权限"""
    get_permission_manager().remove_extension(extension_name)
