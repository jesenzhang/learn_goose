"""
Config Module

配置管理系统，支持：
- YAML 配置文件读写
- 环境变量覆盖
- 密钥存储（keyring 或文件）
- 类型安全的配置获取/设置
- 配置热重载
- 配置备份/恢复
- 扩展配置管理
- 权限管理
- GooseMode 运行模式
- 实验特性管理

Reference: goose-rs/crates/goose/src/config/base.rs
"""

import os
import json
import yaml
import threading
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Type, TypeVar, Generic
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from abc import ABC, abstractmethod

logger = logging.getLogger("goose.config")

T = TypeVar("T")


class ConfigError(Exception):
    """配置错误"""
    
    def __init__(self, message: str, code: str = "CONFIG_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class ConfigValueType(str, Enum):
    """配置值类型"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    LIST = "list"
    DICT = "dict"


@dataclass
class ConfigEntry:
    """配置条目"""
    key: str
    value: Any
    value_type: ConfigValueType = ConfigValueType.STRING
    description: str = ""
    secret: bool = False
    default: Any = None


class SecretStorage(Enum):
    """密钥存储方式"""
    KEYRING = "keyring"
    FILE = "file"
    DISABLED = "disabled"


class KeyringBackend(ABC):
    """Keyring 后端抽象"""
    
    @abstractmethod
    def get_password(self, service: str, username: str) -> Optional[str]:
        pass
    
    @abstractmethod
    def set_password(self, service: str, username: str, password: str) -> bool:
        pass
    
    @abstractmethod
    def delete_password(self, service: str, username: str) -> bool:
        pass


class SystemKeyringBackend(KeyringBackend):
    """系统 Keyring 后端"""
    
    def __init__(self):
        self._backend = None
        self._initialize_backend()
    
    def _initialize_backend(self):
        """初始化 keyring 后端"""
        try:
            import keyring
            self._backend = keyring
        except ImportError:
            logger.warning("keyring package not installed, falling back to file-based storage")
            self._backend = None
    
    def get_password(self, service: str, username: str) -> Optional[str]:
        if self._backend is None:
            return None
        try:
            return self._backend.get_password(service, username)
        except Exception as e:
            logger.error(f"Failed to get password from keyring: {e}")
            return None
    
    def set_password(self, service: str, username: str, password: str) -> bool:
        if self._backend is None:
            return False
        try:
            self._backend.set_password(service, username, password)
            return True
        except Exception as e:
            logger.error(f"Failed to set password in keyring: {e}")
            return False
    
    def delete_password(self, service: str, username: str) -> bool:
        if self._backend is None:
            return False
        try:
            self._backend.delete_password(service, username)
            return True
        except Exception as e:
            logger.error(f"Failed to delete password from keyring: {e}")
            return False


class FileKeyringBackend(KeyringBackend):
    """文件密钥存储后端"""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._lock = threading.Lock()
    
    def _load_secrets(self) -> Dict[str, str]:
        """加载密钥文件"""
        if self.file_path.exists():
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.error(f"Failed to load secrets file: {e}")
        return {}
    
    def _save_secrets(self, secrets: Dict[str, str]):
        """保存密钥文件"""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, 'w', encoding='utf-8') as f:
                yaml.dump(secrets, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Failed to save secrets file: {e}")
    
    def get_password(self, service: str, username: str) -> Optional[str]:
        secrets = self._load_secrets()
        key = f"{service}:{username}"
        return secrets.get(key)
    
    def set_password(self, service: str, username: str, password: str) -> bool:
        secrets = self._load_secrets()
        key = f"{service}:{username}"
        secrets[key] = password
        self._save_secrets(secrets)
        return True
    
    def delete_password(self, service: str, username: str) -> bool:
        secrets = self._load_secrets()
        key = f"{service}:{username}"
        if key in secrets:
            del secrets[key]
            self._save_secrets(secrets)
            return True
        return False


class KeyringManager:
    """密钥管理器"""
    
    SERVICE_NAME = "goose"
    USERNAME = "secrets"
    
    _instance: Optional['KeyringManager'] = None
    _lock = threading.Lock()
    
    @classmethod
    def get_instance(cls) -> 'KeyringManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = KeyringManager()
        return cls._instance
    
    @classmethod
    def set_instance(cls, instance: 'KeyringManager'):
        with cls._lock:
            cls._instance = instance
    
    def __init__(self, storage_mode: SecretStorage = SecretStorage.KEYRING):
        self._storage_mode = storage_mode
        
        if storage_mode == SecretStorage.KEYRING:
            self._backend = SystemKeyringBackend()
            # 测试后端是否可用
            if self._backend.get_password(self.SERVICE_NAME, "test") is None:
                # 后端不可用，降级到文件存储
                logger.warning("Keyring not available, falling back to file-based storage")
                self._backend = self._create_file_backend()
        elif storage_mode == SecretStorage.FILE:
            self._backend = self._create_file_backend()
        else:
            self._backend = None
    
    def _create_file_backend(self) -> FileKeyringBackend:
        config_dir = Path(os.path.expanduser(os.path.expandvars("~/.config/goose")))
        secrets_file = config_dir / "secrets.yaml"
        return FileKeyringBackend(str(secrets_file))
    
    def get_secret(self, key: str) -> Optional[str]:
        """获取密钥"""
        if self._backend is None:
            return None
        return self._backend.get_password(self.SERVICE_NAME, key)
    
    def set_secret(self, key: str, value: str) -> bool:
        """设置密钥"""
        if self._backend is None:
            return False
        return self._backend.set_password(self.SERVICE_NAME, key, value)
    
    def delete_secret(self, key: str) -> bool:
        """删除密钥"""
        if self._backend is None:
            return False
        return self._backend.delete_password(self.SERVICE_NAME, key)


class GooseMode(str, Enum):
    """Goose 运行模式"""
    AUTO = "auto"
    APPROVE = "approve"
    SMART_APPROVE = "smart_approve"
    CHAT = "chat"
    
    @classmethod
    def from_string(cls, value: str) -> 'GooseMode':
        value = value.lower()
        for mode in cls:
            if mode.value == value:
                return mode
        return cls.AUTO
    
    @classmethod
    def default(cls) -> 'GooseMode':
        return cls.AUTO


class Config:
    """
    配置管理器
    
    功能：
    - 从 YAML 文件加载配置
    - 环境变量覆盖
    - 密钥安全存储 (keyring/文件)
    - 类型安全访问
    - 线程安全
    - 配置备份/恢复
    """
    
    DEFAULT_CONFIG_FILENAME = "config.yaml"
    DEFAULT_SECRETS_FILENAME = "secrets.yaml"
    DEFAULT_CONFIG_DIR = "~/.config/goose"
    BACKUP_SUFFIX = ".bak"
    
    def __init__(
        self,
        config_path: Optional[str] = None,
        secrets_path: Optional[str] = None,
        storage_mode: SecretStorage = SecretStorage.KEYRING
    ):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
            secrets_path: 密钥文件路径
            storage_mode: 密钥存储模式
        """
        self._config_path = self._resolve_path(config_path or self.DEFAULT_CONFIG_DIR)
        self._secrets_path = self._resolve_path(
            secrets_path or str(Path(self._config_path) / self.DEFAULT_SECRETS_FILENAME)
        )
        self._storage_mode = storage_mode
        
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._initialized = False
        
        self._keyring_manager = KeyringManager(storage_mode)
        self._setup_directories()
    
    def _resolve_path(self, path: str) -> str:
        """解析路径，支持 ~ 展开"""
        return os.path.expanduser(os.path.expandvars(path))
    
    def _setup_directories(self) -> None:
        """创建配置目录"""
        config_dir = Path(self._config_path)
        if config_dir.is_file():
            config_dir = config_dir.parent
        config_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_backup_paths(self) -> list:
        """获取备份文件路径列表"""
        paths = []
        config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
        
        if config_file.exists():
            paths.append(config_file.with_suffix(config_file.suffix + self.BACKUP_SUFFIX))
            for i in range(1, 6):
                paths.append(config_file.with_suffix(config_file.suffix + f"{self.BACKUP_SUFFIX}.{i}"))
        
        return paths
    
    def _rotate_backups(self) -> None:
        """轮转备份文件"""
        config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
        if not config_file.exists():
            return
        
        backup_paths = self._get_backup_paths()
        for i in range(len(backup_paths) - 2, -1, -1):
            current = backup_paths[i]
            next_backup = backup_paths[i + 1]
            if current.exists():
                try:
                    if next_backup.exists():
                        next_backup.unlink()
                    current.rename(next_backup)
                except Exception as e:
                    logger.warning(f"Failed to rotate backup {current}: {e}")
    
    def _create_backup(self) -> None:
        """创建配置备份"""
        import shutil
        config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
        if not config_file.exists():
            return
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except Exception:
            return
        
        self._rotate_backups()
        
        backup_path = config_file.with_suffix(config_file.suffix + self.BACKUP_SUFFIX)
        try:
            shutil.copy2(config_file, backup_path)
            logger.info(f"Created config backup: {backup_path}")
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    def _restore_from_backup(self) -> bool:
        """尝试从备份恢复配置"""
        import shutil
        config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
        backup_file = config_file.with_suffix(config_file.suffix + self.BACKUP_SUFFIX)
        
        if backup_file.exists():
            try:
                shutil.copy2(backup_file, config_file)
                logger.info(f"Restored config from backup: {backup_file}")
                return True
            except Exception as e:
                logger.warning(f"Failed to restore from backup: {e}")
        
        for i in range(1, 6):
            backup_path = config_file.with_suffix(config_file.suffix + f"{self.BACKUP_SUFFIX}.{i}")
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, config_file)
                    logger.info(f"Restored config from backup: {backup_path}")
                    return True
                except Exception as e:
                    logger.warning(f"Failed to restore from backup {i}: {e}")
        
        return False
    
    def load(self, auto_create: bool = True) -> None:
        """加载配置"""
        with self._lock:
            if self._initialized:
                return
            
            self._data = {}
            
            config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
            
            if config_file.exists():
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        self._data = yaml.safe_load(content) or {}
                    logger.info(f"Loaded config from {config_file}")
                except Exception as e:
                    logger.error(f"Failed to load config: {e}")
                    if not self._restore_from_backup():
                        if auto_create:
                            self._data = {}
                        else:
                            raise ConfigError(f"Failed to load config: {e}")
            elif auto_create:
                logger.info(f"Config file not found, creating default at {config_file}")
                self._data = {}
                self._save_config()
            
            self._initialized = True
    
    def _save_config(self) -> None:
        """保存配置到文件"""
        import shutil
        config_file = Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME
        temp_file = config_file.with_suffix(config_file.suffix + ".tmp")
        
        try:
            self._create_backup()
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)
            
            shutil.move(temp_file, config_file)
            logger.info(f"Saved config to {config_file}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            raise ConfigError(f"Failed to save config: {e}")
    
    def _get_env_key(self, key: str) -> str:
        """获取环境变量键名"""
        return key.upper().replace("_", "_")
    
    def _get_from_env(self, key: str) -> Optional[str]:
        """从环境变量获取值"""
        env_key = self._get_env_key(key)
        return os.environ.get(env_key)
    
    def _get_from_keyring(self, key: str) -> Optional[str]:
        """从 keyring 获取密钥"""
        return self._keyring_manager.get_secret(key)
    
    def _set_to_keyring(self, key: str, value: str) -> bool:
        """保存密钥到 keyring"""
        return self._keyring_manager.set_secret(key, value)
    
    def _delete_from_keyring(self, key: str) -> bool:
        """从 keyring 删除密钥"""
        return self._keyring_manager.delete_secret(key)
    
    def get(
        self,
        key: str,
        default: Optional[Any] = None,
        secret: bool = False
    ) -> Any:
        """
        获取配置值
        
        优先级：
        1. 环境变量 (精确匹配)
        2. 配置文件/keyring
        3. 默认值
        
        Args:
            key: 配置键
            default: 默认值
            secret: 是否为密钥
            
        Returns:
            配置值
        """
        if not self._initialized:
            self.load()
        
        with self._lock:
            env_value = self._get_from_env(key)
            if env_value is not None:
                return env_value
            
            if secret:
                keyring_value = self._get_from_keyring(key)
                if keyring_value is not None:
                    return keyring_value
            else:
                if key in self._data:
                    return self._data[key]
            
            return default
    
    def get_str(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取字符串配置"""
        return self.get(key, default)
    
    def get_int(self, key: str, default: Optional[int] = None) -> Optional[int]:
        """获取整数配置"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def get_float(self, key: str, default: Optional[float] = None) -> Optional[float]:
        """获取浮点数配置"""
        value = self.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def get_bool(self, key: str, default: Optional[bool] = None) -> Optional[bool]:
        """获取布尔配置"""
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)
    
    def get_list(self, key: str, default: Optional[list] = None) -> Optional[list]:
        """获取列表配置"""
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, list):
            return value
        return [value]
    
    def get_dict(self, key: str, default: Optional[dict] = None) -> Optional[dict]:
        """获取字典配置"""
        value = self.get(key)
        if value is None:
            return default
        if isinstance(value, dict):
            return value
        return default
    
    def set(self, key: str, value: Any, secret: bool = False) -> None:
        """
        设置配置值
        
        Args:
            key: 配置键
            value: 配置值
            secret: 是否为密钥
        """
        if not self._initialized:
            self.load()
        
        with self._lock:
            if secret:
                if not self._set_to_keyring(key, str(value)):
                    raise ConfigError(
                        f"Failed to store secret '{key}' in keyring. "
                        "Try setting GOOSE_DISABLE_KEYRING=true or use environment variables.",
                        code="KEYRING_ERROR"
                    )
            else:
                self._data[key] = value
                self._save_config()
    
    def set_str(self, key: str, value: str, secret: bool = False) -> None:
        """设置字符串配置"""
        self.set(key, value, secret)
    
    def set_int(self, key: str, value: int, secret: bool = False) -> None:
        """设置整数配置"""
        self.set(key, value, secret)
    
    def set_float(self, key: str, value: float, secret: bool = False) -> None:
        """设置浮点数配置"""
        self.set(key, value, secret)
    
    def set_bool(self, key: str, value: bool, secret: bool = False) -> None:
        """设置布尔配置"""
        self.set(key, value, secret)
    
    def set_list(self, key: str, value: list, secret: bool = False) -> None:
        """设置列表配置"""
        self.set(key, value, secret)
    
    def set_dict(self, key: str, value: dict, secret: bool = False) -> None:
        """设置字典配置"""
        self.set(key, value, secret)
    
    def delete(self, key: str, secret: bool = False) -> bool:
        """
        删除配置项
        
        Returns:
            是否成功删除
        """
        if not self._initialized:
            self.load()
        
        with self._lock:
            if secret:
                return self._delete_from_keyring(key)
            else:
                if key in self._data:
                    del self._data[key]
                    self._save_config()
                    return True
            return False
    
    def has(self, key: str, secret: bool = False) -> bool:
        """检查配置是否存在"""
        if not self._initialized:
            self.load()
        
        with self._lock:
            if secret:
                return self._get_from_keyring(key) is not None
            return key in self._data
    
    def all(self, secret: bool = False) -> Dict[str, Any]:
        """获取所有配置"""
        if not self._initialized:
            self.load()
        
        with self._lock:
            return dict(self._data)
    
    def clear(self, secret: bool = False) -> None:
        """清除所有配置"""
        with self._lock:
            if secret:
                pass
            else:
                self._data = {}
                self._save_config()
    
    def reload(self) -> None:
        """重新加载配置"""
        with self._lock:
            self._initialized = False
            self.load()
    
    @property
    def config_path(self) -> str:
        """获取配置路径"""
        return str(Path(self._config_path) / self.DEFAULT_CONFIG_FILENAME)
    
    @property
    def secrets_path(self) -> str:
        """获取密钥路径"""
        return self._secrets_path
    
    # Goose 特定配置方法
    
    def get_goose_provider(self) -> Optional[str]:
        """获取 Goose Provider"""
        return self.get_str("GOOSE_PROVIDER")
    
    def set_goose_provider(self, provider: str) -> None:
        """设置 Goose Provider"""
        self.set_str("GOOSE_PROVIDER", provider)
    
    def get_goose_model(self) -> Optional[str]:
        """获取 Goose Model"""
        return self.get_str("GOOSE_MODEL")
    
    def set_goose_model(self, model: str) -> None:
        """设置 Goose Model"""
        self.set_str("GOOSE_MODEL", model)
    
    def get_goose_mode(self) -> GooseMode:
        """获取 Goose Mode"""
        mode_str = self.get_str("GOOSE_MODE") or "auto"
        return GooseMode.from_string(mode_str)
    
    def set_goose_mode(self, mode: GooseMode) -> None:
        """设置 Goose Mode"""
        self.set_str("GOOSE_MODE", mode.value)
    
    def get_max_turns(self) -> Optional[int]:
        """获取最大回合数"""
        return self.get_int("GOOSE_MAX_TURNS")
    
    def set_max_turns(self, turns: int) -> None:
        """设置最大回合数"""
        self.set_int("GOOSE_MAX_TURNS", turns)


class GlobalConfig:
    """全局配置单例"""
    
    _instance: Optional[Config] = None
    _lock = threading.Lock()
    
    @classmethod
    def get(cls) -> Config:
        """获取全局配置实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = Config()
                    cls._instance.load()
        return cls._instance
    
    @classmethod
    def set_instance(cls, config: Config) -> None:
        """设置全局配置实例（用于测试）"""
        with cls._lock:
            cls._instance = config


def get_config() -> Config:
    """获取全局配置"""
    return GlobalConfig.get()


def config_get(key: str, default: Optional[Any] = None) -> Any:
    """快捷获取配置"""
    return get_config().get(key, default)


def config_set(key: str, value: Any, secret: bool = False) -> None:
    """快捷设置配置"""
    get_config().set(key, value, secret)


@dataclass
class GooseConfig:
    """Goose 配置结构"""
    goose_provider: Optional[str] = None
    goose_model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    @classmethod
    def from_config(cls, config: Optional[Config] = None) -> "GooseConfig":
        """从配置加载"""
        if config is None:
            config = get_config()
        
        return cls(
            goose_provider=config.get("goose_provider"),
            goose_model=config.get("goose_model"),
            temperature=config.get_float("temperature"),
            max_tokens=config.get_int("max_tokens"),
            api_key=config.get("api_key", secret=True),
            base_url=config.get("base_url"),
        )
    
    def apply(self, config: Config) -> None:
        """应用到配置"""
        if self.goose_provider:
            config.set("goose_provider", self.goose_provider)
        if self.goose_model:
            config.set("goose_model", self.goose_model)
        if self.temperature is not None:
            config.set("temperature", self.temperature)
        if self.max_tokens is not None:
            config.set("max_tokens", self.max_tokens)
        if self.api_key:
            config.set("api_key", self.api_key, secret=True)
        if self.base_url:
            config.set("base_url", self.base_url)


def create_config(
    config_dir: Optional[str] = None,
    auto_load: bool = True
) -> Config:
    """
    创建配置管理器
    
    Args:
        config_dir: 配置目录
        auto_load: 是否自动加载
        
    Returns:
        Config 实例
    """
    config = Config(config_path=config_dir)
    if auto_load:
        config.load()
    return config


def reset_config() -> None:
    """重置全局配置"""
    GlobalConfig._instance = None


# 扩展配置导出
from .extensions import (
    ExtensionType,
    ExtensionEnabled,
    ExtensionConfig,
    ExtensionEntry,
    ExtensionManager,
    BuiltinExtensionConfig,
    StdioExtensionConfig,
    StreamableHttpExtensionConfig,
    set_extension,
    get_extension_by_name,
    remove_extension,
    set_extension_enabled,
    get_all_extensions,
    get_enabled_extensions,
    get_all_extension_names,
    is_extension_enabled,
    name_to_key,
    DEFAULT_DISPLAY_NAME,
    DEFAULT_EXTENSION,
    DEFAULT_EXTENSION_DESCRIPTION,
    DEFAULT_EXTENSION_TIMEOUT,
)

# 权限配置导出
from .permission import (
    PermissionLevel,
    ToolPermission,
    ExtensionPermissions,
    PermissionManager,
    get_permission_manager,
    get_tool_permission,
    set_tool_permission,
    check_permission,
    needs_confirmation,
    is_denied,
    set_default_permission_level,
    remove_extension_permissions,
)

# 实验配置导出
from .experiments import (
    ExperimentState,
    Experiment,
    ExperimentManager,
    get_experiment_manager,
    get_all_experiments,
    is_experiment_enabled,
    set_experiment_enabled,
    enable_experiment,
    disable_experiment,
    reset_experiment,
    register_experiment,
)

# OAuth 配置导出
from .oauth import (
    OAuthProvider,
    OAuthToken,
    OAuthConfig,
    OAuthError,
    OAuthClient,
    DeviceCodeClient,
    DeviceCodeResponse,
    OpenRouterOAuth,
    TetrateOAuth,
    OAuthManager,
    get_oauth_manager,
    authenticate_with_openrouter,
    authenticate_with_tetrate,
    get_oauth_token,
    is_oauth_authenticated,
    refresh_oauth_token,
    logout_oauth,
)

# Provider 配置导出
from .providers import (
    ProviderType,
    ProviderKey,
    ProviderMetadata,
    ModelInfo,
    Provider,
    LLMProvider,
    ProviderRegistry,
    ProviderTester,
    get_provider_registry,
    list_providers,
    get_provider_metadata,
    search_providers,
    fetch_provider_models,
    test_provider_config,
)

# CLI 配置导出
from .cli import (
    ConfigCLI,
    CLIColor,
    InteractiveInput,
    run_configure,
)

__all__ = [
    # 基础类
    "Config",
    "ConfigError",
    "ConfigEntry",
    "ConfigValueType",
    "SecretStorage",
    # Keyring
    "KeyringManager",
    "KeyringBackend",
    "SystemKeyringBackend",
    "FileKeyringBackend",
    # Goose 模式
    "GooseMode",
    # 配置结构
    "GooseConfig",
    # 快捷函数
    "get_config",
    "config_get",
    "config_set",
    "create_config",
    "reset_config",
    # 扩展配置
    "ExtensionType",
    "ExtensionEnabled",
    "ExtensionConfig",
    "ExtensionEntry",
    "ExtensionManager",
    "BuiltinExtensionConfig",
    "StdioExtensionConfig",
    "StreamableHttpExtensionConfig",
    "set_extension",
    "get_extension_by_name",
    "remove_extension",
    "set_extension_enabled",
    "get_all_extensions",
    "get_enabled_extensions",
    "get_all_extension_names",
    "is_extension_enabled",
    "name_to_key",
    "DEFAULT_DISPLAY_NAME",
    "DEFAULT_EXTENSION",
    "DEFAULT_EXTENSION_DESCRIPTION",
    "DEFAULT_EXTENSION_TIMEOUT",
    # 权限配置
    "PermissionLevel",
    "ToolPermission",
    "ExtensionPermissions",
    "PermissionManager",
    "get_permission_manager",
    "get_tool_permission",
    "set_tool_permission",
    "check_permission",
    "needs_confirmation",
    "is_denied",
    "set_default_permission_level",
    "remove_extension_permissions",
    # 实验配置
    "ExperimentState",
    "Experiment",
    "ExperimentManager",
    "get_experiment_manager",
    "get_all_experiments",
    "is_experiment_enabled",
    "set_experiment_enabled",
    "enable_experiment",
    "disable_experiment",
    "reset_experiment",
    "register_experiment",
    # OAuth 配置
    "OAuthProvider",
    "OAuthToken",
    "OAuthConfig",
    "OAuthError",
    "OAuthClient",
    "DeviceCodeClient",
    "DeviceCodeResponse",
    "OpenRouterOAuth",
    "TetrateOAuth",
    "OAuthManager",
    "get_oauth_manager",
    "authenticate_with_openrouter",
    "authenticate_with_tetrate",
    "get_oauth_token",
    "is_oauth_authenticated",
    "refresh_oauth_token",
    "logout_oauth",
    # Provider 配置
    "ProviderType",
    "ProviderKey",
    "ProviderMetadata",
    "ModelInfo",
    "Provider",
    "LLMProvider",
    "ProviderRegistry",
    "ProviderTester",
    "get_provider_registry",
    "list_providers",
    "get_provider_metadata",
    "search_providers",
    "fetch_provider_models",
    "test_provider_config",
    # CLI 配置
    "ConfigCLI",
    "CLIColor",
    "InteractiveInput",
    "run_configure",
]
