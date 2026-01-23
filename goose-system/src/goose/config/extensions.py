"""
Extension Configuration

扩展配置管理，支持：
- 内置扩展 (builtin)
- Stdio 扩展 (命令行扩展)
- Streamable HTTP 扩展 (MCP HTTP 扩展)

Reference: goose-rs/crates/goose/src/config/extensions.rs
"""

import os
import json
import yaml
import threading
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.config.extensions")

DEFAULT_DISPLAY_NAME = "Goose"
DEFAULT_EXTENSION = "builtin"
DEFAULT_EXTENSION_DESCRIPTION = "Goose - AI Agent"
DEFAULT_EXTENSION_TIMEOUT = 300  # seconds


class ExtensionType(str, Enum):
    """扩展类型"""
    BUILTIN = "builtin"
    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class ExtensionEnabled(str, Enum):
    """扩展启用状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"


@dataclass
class BuiltinExtensionConfig:
    """内置扩展配置"""
    name: str
    display_name: Optional[str] = None
    timeout: Optional[int] = DEFAULT_EXTENSION_TIMEOUT
    bundled: Optional[bool] = True
    description: str = ""
    available_tools: List[str] = field(default_factory=list)


@dataclass
class StdioExtensionConfig:
    """Stdio 扩展配置"""
    name: str
    cmd: str
    args: List[str] = field(default_factory=list)
    envs: Dict[str, str] = field(default_factory=dict)
    env_keys: List[str] = field(default_factory=list)
    description: str = ""
    timeout: Optional[int] = DEFAULT_EXTENSION_TIMEOUT
    bundled: Optional[bool] = None
    available_tools: List[str] = field(default_factory=list)


@dataclass
class StreamableHttpExtensionConfig:
    """Streamable HTTP 扩展配置"""
    name: str
    uri: str
    headers: Dict[str, str] = field(default_factory=dict)
    envs: Dict[str, str] = field(default_factory=dict)
    env_keys: List[str] = field(default_factory=list)
    description: str = ""
    timeout: Optional[int] = DEFAULT_EXTENSION_TIMEOUT
    bundled: Optional[bool] = None
    available_tools: List[str] = field(default_factory=list)


@dataclass
class ExtensionConfig:
    """扩展配置 (联合类型)"""
    type: ExtensionType
    builtin: Optional[BuiltinExtensionConfig] = None
    stdio: Optional[StdioExtensionConfig] = None
    streamable_http: Optional[StreamableHttpExtensionConfig] = None
    
    @classmethod
    def builtin_ext(cls, name: str, **kwargs) -> 'ExtensionConfig':
        """创建内置扩展配置"""
        return cls(
            type=ExtensionType.BUILTIN,
            builtin=BuiltinExtensionConfig(name=name, **kwargs)
        )
    
    @classmethod
    def stdio_ext(cls, name: str, cmd: str, args: List[str] = None, **kwargs) -> 'ExtensionConfig':
        """创建 Stdio 扩展配置"""
        return cls(
            type=ExtensionType.STDIO,
            stdio=StdioExtensionConfig(
                name=name,
                cmd=cmd,
                args=args or [],
                **kwargs
            )
        )
    
    @classmethod
    def streamable_http_ext(cls, name: str, uri: str, **kwargs) -> 'ExtensionConfig':
        """创建 Streamable HTTP 扩展配置"""
        return cls(
            type=ExtensionType.STREAMABLE_HTTP,
            streamable_http=StreamableHttpExtensionConfig(
                name=name,
                uri=uri,
                **kwargs
            )
        )
    
    def name(self) -> str:
        """获取扩展名称"""
        if self.builtin:
            return self.builtin.name
        elif self.stdio:
            return self.stdio.name
        elif self.streamable_http:
            return self.streamable_http.name
        return ""
    
    def display_name(self) -> str:
        """获取显示名称"""
        if self.builtin and self.builtin.display_name:
            return self.builtin.display_name
        elif self.stdio and self.stdio.description:
            return self.stdio.description
        elif self.streamable_http and self.streamable_http.description:
            return self.streamable_http.description
        return self.name()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {"type": self.type.value}
        if self.builtin:
            result["builtin"] = {
                "name": self.builtin.name,
                "display_name": self.builtin.display_name,
                "timeout": self.builtin.timeout,
                "bundled": self.builtin.bundled,
                "description": self.builtin.description,
                "available_tools": self.builtin.available_tools,
            }
        elif self.stdio:
            result["stdio"] = {
                "name": self.stdio.name,
                "cmd": self.stdio.cmd,
                "args": self.stdio.args,
                "envs": self.stdio.envs,
                "env_keys": self.stdio.env_keys,
                "description": self.stdio.description,
                "timeout": self.stdio.timeout,
                "bundled": self.stdio.bundled,
                "available_tools": self.stdio.available_tools,
            }
        elif self.streamable_http:
            result["streamable_http"] = {
                "name": self.streamable_http.name,
                "uri": self.streamable_http.uri,
                "headers": self.streamable_http.headers,
                "envs": self.streamable_http.envs,
                "env_keys": self.streamable_http.env_keys,
                "description": self.streamable_http.description,
                "timeout": self.streamable_http.timeout,
                "bundled": self.streamable_http.bundled,
                "available_tools": self.streamable_http.available_tools,
            }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExtensionConfig':
        """从字典创建"""
        ext_type = ExtensionType(data.get("type", "builtin"))
        
        if ext_type == ExtensionType.BUILTIN:
            builtin_data = data.get("builtin", {})
            return cls.builtin_ext(
                name=builtin_data.get("name", ""),
                display_name=builtin_data.get("display_name"),
                timeout=builtin_data.get("timeout"),
                bundled=builtin_data.get("bundled"),
                description=builtin_data.get("description", ""),
                available_tools=builtin_data.get("available_tools", []),
            )
        elif ext_type == ExtensionType.STDIO:
            stdio_data = data.get("stdio", {})
            return cls.stdio_ext(
                name=stdio_data.get("name", ""),
                cmd=stdio_data.get("cmd", ""),
                args=stdio_data.get("args", []),
                envs=stdio_data.get("envs", {}),
                env_keys=stdio_data.get("env_keys", []),
                description=stdio_data.get("description", ""),
                timeout=stdio_data.get("timeout"),
                bundled=stdio_data.get("bundled"),
                available_tools=stdio_data.get("available_tools", []),
            )
        elif ext_type == ExtensionType.STREAMABLE_HTTP:
            http_data = data.get("streamable_http", {})
            return cls.streamable_http_ext(
                name=http_data.get("name", ""),
                uri=http_data.get("uri", ""),
                headers=http_data.get("headers", {}),
                envs=http_data.get("envs", {}),
                env_keys=http_data.get("env_keys", []),
                description=http_data.get("description", ""),
                timeout=http_data.get("timeout"),
                bundled=http_data.get("bundled"),
                available_tools=http_data.get("available_tools", []),
            )
        
        return cls(type=ext_type)


@dataclass
class ExtensionEntry:
    """扩展条目"""
    enabled: bool
    config: ExtensionConfig


class ExtensionManager:
    """扩展配置管理器"""
    
    EXTENSIONS_KEY = "extensions"
    
    _instance: Optional['ExtensionManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'ExtensionManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = ExtensionManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'ExtensionManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(self, config_dir: Optional[str] = None):
        self._config_dir = config_dir or os.path.expanduser("~/.config/goose")
        self._extensions_file = Path(self._config_dir) / "extensions.yaml"
        self._extensions: Dict[str, ExtensionEntry] = {}
        self._lock = threading.Lock()
        self._load_extensions()
    
    def _load_extensions(self) -> None:
        """加载扩展配置"""
        if self._extensions_file.exists():
            try:
                with open(self._extensions_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f) or {}
                
                for key, entry_data in data.items():
                    if isinstance(entry_data, dict):
                        config_data = entry_data.get("config", {})
                        config = ExtensionConfig.from_dict(config_data)
                        self._extensions[key] = ExtensionEntry(
                            enabled=entry_data.get("enabled", False),
                            config=config,
                        )
            except Exception as e:
                logger.error(f"Failed to load extensions: {e}")
    
    def _save_extensions(self) -> None:
        """保存扩展配置"""
        try:
            self._extensions_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for key, entry in self._extensions.items():
                data[key] = {
                    "enabled": entry.enabled,
                    "config": entry.config.to_dict(),
                }
            
            with open(self._extensions_file, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Saved extensions to {self._extensions_file}")
        except Exception as e:
            logger.error(f"Failed to save extensions: {e}")
    
    def set_extension(self, entry: ExtensionEntry) -> None:
        """设置扩展"""
        with self._lock:
            key = self._to_key(entry.config.name())
            self._extensions[key] = entry
            self._save_extensions()
    
    def get_extension(self, name: str) -> Optional[ExtensionEntry]:
        """获取扩展"""
        with self._lock:
            key = self._to_key(name)
            return self._extensions.get(key)
    
    def remove_extension(self, name: str) -> bool:
        """删除扩展"""
        with self._lock:
            key = self._to_key(name)
            if key in self._extensions:
                del self._extensions[key]
                self._save_extensions()
                return True
            return False
    
    def set_extension_enabled(self, name: str, enabled: bool) -> None:
        """设置扩展启用状态"""
        with self._lock:
            key = self._to_key(name)
            if key in self._extensions:
                self._extensions[key].enabled = enabled
                self._save_extensions()
    
    def get_all_extensions(self) -> List[ExtensionEntry]:
        """获取所有扩展"""
        with self._lock:
            return list(self._extensions.values())
    
    def get_enabled_extensions(self) -> List[ExtensionEntry]:
        """获取已启用的扩展"""
        with self._lock:
            return [e for e in self._extensions.values() if e.enabled]
    
    def get_all_extension_names(self) -> List[str]:
        """获取所有扩展名称"""
        with self._lock:
            return [self._from_key(k) for k in self._extensions.keys()]
    
    @staticmethod
    def _to_key(name: str) -> str:
        """将名称转换为键"""
        return name.lower().replace(" ", "_").replace("-", "_")
    
    @staticmethod
    def _from_key(key: str) -> str:
        """将键转换为名称"""
        return key


def name_to_key(name: str) -> str:
    """将名称转换为键"""
    return ExtensionManager._to_key(name)


def set_extension(entry: ExtensionEntry) -> None:
    """设置扩展"""
    ExtensionManager.get_instance().set_extension(entry)


def get_extension_by_name(name: str) -> Optional[ExtensionEntry]:
    """按名称获取扩展"""
    return ExtensionManager.get_instance().get_extension(name)


def remove_extension(name: str) -> bool:
    """删除扩展"""
    return ExtensionManager.get_instance().remove_extension(name)


def set_extension_enabled(name: str, enabled: bool) -> None:
    """设置扩展启用状态"""
    ExtensionManager.get_instance().set_extension_enabled(name, enabled)


def get_all_extensions() -> List[ExtensionEntry]:
    """获取所有扩展"""
    return ExtensionManager.get_instance().get_all_extensions()


def get_enabled_extensions() -> List[ExtensionEntry]:
    """获取已启用的扩展"""
    return ExtensionManager.get_instance().get_enabled_extensions()


def get_all_extension_names() -> List[str]:
    """获取所有扩展名称"""
    return ExtensionManager.get_instance().get_all_extension_names()


def is_extension_enabled(name: str) -> bool:
    """检查扩展是否启用"""
    entry = get_extension_by_name(name)
    return entry.enabled if entry else False
