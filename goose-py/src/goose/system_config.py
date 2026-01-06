import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# 默认配置路径
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "goose"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

class SystemConfig(BaseSettings):
    # --- 基础配置 ---
    env: str = "production"  # development / production
    db_url: str = "./goose.db"
    
    # --- 事件系统 ---
    event_bus_size: int = 1000
    event_ttl: int = 3600
    
    # --- 密钥配置 (支持 .env 读取) ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    
    silicon_api_key: str = "sk-..."
    silicon_base_url: str = "https://api.siliconflow.cn/v1"
    
    # --- JWT 安全 ---
    jwt_secret_key: str = Field(default="goose-insecure-secret-change-me", validation_alias="GOOSE_JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24

    # Pydantic 配置加载规则
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.env == "production"

# --- 全局单例实例化 ---
# 这样其他模块可以直接 `from goose.system_config import settings`
settings = SystemConfig()


# 全局单例
_global_config = settings

def get_config() -> SystemConfig:
    global _global_config
    if _global_config is None:
        _global_config = SystemConfig()
    return _global_config