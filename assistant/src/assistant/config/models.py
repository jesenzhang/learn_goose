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
    hot_reload_enabled: bool = False

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
    local_db_path: Optional[str] = "museum_assistant.db"
    remote_db_url: Optional[str] = "${REMOTE_DB_URL:http://localhost:8500}"
    remote_db_api_key: Optional[str] = "${REMOTE_DB_API_KEY:}"
    use_remote: bool = False


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

# Truncation and ChatRecall configuration
# Note: These use Pydantic wrapping for YAML parsing, then convert to module dataclass at runtime
class TruncationConfigWrapper(BaseModel):
    """Pydantic wrapper for TruncationConfig (for YAML parsing)"""
    enabled: bool = True
    threshold: float = 0.8
    auto_compact: bool = True
    max_messages_before_compact: int = 50
    keep_recent_messages: int = 5
    check_interval: int = 5

class ChatRecallConfigWrapper(BaseModel):
    """Pydantic wrapper for ChatRecallConfig (for YAML parsing)"""
    enabled: bool = True
    max_results: int = 10
    max_session_messages: int = 3
    min_similarity: float = 0.3
    query_expand_max_msgs: int = 4
    query_max_chars: int = 800
    query_rewrite_enabled: bool = False
    query_rewrite_max_msgs: int = 6
    query_rewrite_max_chars: int = 800
    query_rewrite_prompt: Optional[str] = None
    use_semantic: bool = False
    semantic_top_k: int = 20
    use_rerank: bool = False
    rerank_top_k: int = 10
    rerank_threshold: float = 0.0
    session_memory_enabled: bool = True
    session_memory_use_llm: bool = False
    session_summary_max_chars: int = 400
    session_facts_max_items: int = 20
    session_entities_max_items: int = 30
    session_topics_max_items: int = 20

class MemoryStoreConfigWrapper(BaseModel):
    """Pydantic wrapper for memory store config."""
    enabled: bool = True
    store_type: str = "memory"
    base_dir: str = "memories"
    db_path: str = "memory_store.db"
    memory_threshold: int = 10 * 1024
    file_threshold: int = 100 * 1024
    compression: bool = True
    max_items: int = 50
    max_size_bytes: int = 50 * 1024 * 1024
    ttl: int = 86400
    cleanup_interval: int = 3600
    plugin_path: Optional[str] = None
    plugin_settings: Dict[str, Any] = Field(default_factory=dict)

class MemoryConfigWrapper(BaseModel):
    """Pydantic wrapper for memory config."""
    enabled: bool = True
    store: MemoryStoreConfigWrapper = Field(default_factory=MemoryStoreConfigWrapper)
    stores: Optional[Dict[str, MemoryStoreConfigWrapper]] = None
    routing: Optional[Dict[str, str]] = None
    chatrecall: ChatRecallConfigWrapper = Field(default_factory=ChatRecallConfigWrapper)

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

class EventsConfigWrapper(BaseModel):
    """Pydantic wrapper for events config."""
    replay_cache_size: int = 64
    replay_batch_size: int = 200

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
    skills_directory: str = "agent_skills"
    skills_config: SkillsConfig = Field(default_factory=lambda: SkillsConfig({}))

    # [CHANGED] Raw dictionary for intents to avoid duplication with intent.models
    intents: Dict[str, Any] = Field(default_factory=dict)

    global_tools: List[str] = Field(default_factory=list)
    tools_config: ToolsConfig = Field(default_factory=lambda: ToolsConfig({}))

    # Hooks configuration
    hooks_config: HooksConfig = Field(default_factory=lambda: HooksConfig({}))

    events: EventsConfigWrapper = Field(default_factory=EventsConfigWrapper)

    truncation: TruncationConfigWrapper = Field(default_factory=TruncationConfigWrapper)
    chatrecall: ChatRecallConfigWrapper = Field(default_factory=ChatRecallConfigWrapper)
    memory: MemoryConfigWrapper = Field(default_factory=MemoryConfigWrapper)
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
