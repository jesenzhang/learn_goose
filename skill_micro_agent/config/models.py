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

class AppConfig(BaseModel):
    """
    Root configuration.

    'intents' is now a generic Dict. Validation logic is moved to the Loader
    to transform this raw dict into 'intent.models.IntentDefinition'.
    """
    system: SystemConfig = Field(default_factory=SystemConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)

    # [NEW] Skills configuration - per-skill settings
    skills_config: SkillsConfig = Field(default_factory=lambda: SkillsConfig({}))

    # [CHANGED] Raw dictionary for intents to avoid duplication with intent.models
    intents: Dict[str, Any] = Field(default_factory=dict)

    global_tools: List[str] = Field(default_factory=list)
    tools_config: ToolsConfig = Field(default_factory=lambda: ToolsConfig({}))

    class Config:
        extra = "allow"

    def get_api_key(self) -> str:
        """Get API key from environment."""
        return os.getenv(self.model.api_key_env, "")

   


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
