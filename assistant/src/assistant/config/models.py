"""
Pydantic Configuration Models - Simplified.
"""

import os
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, RootModel, Field, field_validator
from ..skills.config import SkillConfig, SkillsConfig

class SystemConfig(BaseModel):
    """System-level configuration."""
    memory_enabled: bool = False
    timezone: str = "Asia/Shanghai"

class AgentConfig(BaseModel):
    """Agent persona and behavior configuration."""
    name: str = "Agent"
    description: str = "AI Assistant"
    system_template: str = "You are a helpful AI assistant named {name}."
    enabled_skills: Optional[List[str]] = None
    disabled_skills: Optional[List[str]] = None

class SecurityConfig(BaseModel):
    """Security configuration."""
    policy: str = "permissive"
    sensitive_tools: List[str] = Field(default_factory=list)


class DatabaseConfig(BaseModel):
    """Database configuration."""

    # 模式选择（use_remote 的别名，更清晰）
    mode: Optional[str] = None  # 从配置文件读取，最终由 factory 决定

    # 基础配置（兼容旧版）
    use_remote: bool = False

    # 远程数据库配置
    remote_db_url: Optional[str] = None
    remote_db_api_key: Optional[str] = None
    remote_db_timeout: int = 30
    remote_db_retry_count: int = 3  # 新增：重试次数
    remote_db_retry_delay: int = 1   # 新增：重试延迟（秒）

    # 本地数据库配置
    local_db_path: str = "museum_assistant.db"

    # 健康检查配置
    health_check_enabled: bool = True  # 启动时是否执行健康检查
    health_check_timeout: int = 5      # 健康检查超时（秒）

    def get_effective_config(self) -> dict:
        """
        获取最终生效的配置（考虑环境变量覆盖）

        Returns:
            {
                "use_remote": bool,
                "remote_db_url": str | None,
                "remote_db_api_key": str | None,
                "remote_db_timeout": int,
                "local_db_path": str
            }
        """
        # 环境变量优先级高于配置文件
        use_remote_env = os.getenv("USE_REMOTE_DB", "").lower()
        remote_url_env = os.getenv("REMOTE_DB_URL")
        remote_key_env = os.getenv("REMOTE_DB_API_KEY")
        local_path_env = os.getenv("LOCAL_DB_PATH")

        # 确定 use_remote
        if use_remote_env in ("true", "1", "yes"):
            use_remote = True
        elif use_remote_env in ("false", "0", "no"):
            use_remote = False
        else:
            # 如果没有环境变量，使用配置文件
            use_remote = self.use_remote

        return {
            "use_remote": use_remote,
            "remote_db_url": remote_url_env or self.remote_db_url,
            "remote_db_api_key": remote_key_env or self.remote_db_api_key,
            "remote_db_timeout": self.remote_db_timeout,
            "local_db_path": local_path_env or self.local_db_path,
        }


class BasicProviderConfig(BaseModel):
    provider: str = "openai"  # openai, ollama, azure...
    config: Optional[Dict[str, Any]] = None
    
class ProviderConfig(BaseModel):
    """External AI services."""
    llm: Optional[BasicProviderConfig] = None
    embedding: Optional[BasicProviderConfig] = None
    reranker: Optional[BasicProviderConfig] = None

class ToolConfig(BaseModel):
    sensitive: bool = False

class ToolsConfig(RootModel[Dict[str, ToolConfig]]):
    """Tools configuration mapping."""
    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)


# ==================== Hook Configuration Models ====================

class HookConditionConfig(BaseModel):
    """Hook 执行条件配置"""
    user_ids: Optional[List[str]] = None  # 仅对特定用户生效
    session_ids: Optional[List[str]] = None  # 仅对特定会话生效
    min_length: Optional[int] = None  # 输入最小长度
    max_length: Optional[int] = None  # 输入最大长度
    contains: Optional[List[str]] = None  # 输入包含特定关键词
    not_contains: Optional[List[str]] = None  # 输入不包含特定关键词
    custom: Optional[Dict[str, Any]] = None  # 自定义条件


class SingleHookConfig(BaseModel):
    """单个 Hook 的配置"""
    enabled: bool = True
    priority: int = 100

    # Hook 类型标识
    hook_type: str = "filter"  # filter, transformer, observer, validator

    # 执行条件
    conditions: Optional[HookConditionConfig] = None

    # Hook 参数
    params: Dict[str, Any] = Field(default_factory=dict)

    # 失败处理
    fail_on_error: bool = False
    error_message: Optional[str] = None


class HooksConfig(RootModel[Dict[str, SingleHookConfig]]):
    """
    Hooks 配置映射

    支持的 Hook 类型：
    - filter: 过滤类 Hook（FAQ、敏感词等）
    - transformer: 转换类 Hook（输入转换、格式化等）
    - observer: 观察类 Hook（日志、统计等）
    - validator: 验证类 Hook（输入验证、权限检查等）
    """
    def get(self, key: str, default: Any = None) -> Any:
        return self.root.get(key, default)

class AppConfig(BaseModel):
    """
    Root configuration.

    'intents' is now a generic Dict. Validation logic is moved to   Loader
    to transform this raw dict into 'intent.models.IntentDefinition'.
    """
    system: SystemConfig = Field(default_factory=SystemConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
    # [NEW] Skills configuration - per-skill settings
    skills_config: SkillsConfig = Field(default_factory=lambda: SkillsConfig({}))

    # [CHANGED] Raw dictionary for intents to avoid duplication with intent.models
    intents: Dict[str, Any] = Field(default_factory=dict)

    global_tools: List[str] = Field(default_factory=list)
    tools_config: ToolsConfig = Field(default_factory=lambda: ToolsConfig({}))

    # Hooks configuration
    hooks_config: HooksConfig = Field(default_factory=lambda: HooksConfig({}))

    class Config:
        extra = "allow"



def load_config_from_yaml(config_path: str) -> AppConfig:
    """
    Load configuration from YAML file and validate with Pydantic.

    Args:
        config_path: Path to the YAML configuration file

    Returns:
        Validated AppConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If config is invalid
    """
    import yaml
    from pathlib import Path

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_file, 'r', encoding='utf-8') as f:
        raw_config = yaml.safe_load(f) or {}

    return AppConfig(**raw_config)


def load_config_from_dict(raw_config: Dict[str, Any]) -> AppConfig:
    """
    Load configuration from dictionary and validate with Pydantic.

    Args:
        raw_config: Dictionary containing configuration

    Returns:
        Validated AppConfig instance
    """
    return AppConfig(**raw_config)
