import os
import yaml
from typing import Dict, Any, Optional, List
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# 默认配置路径 (类比 Rust 的 dirs::home_dir)
DEFAULT_CONFIG_DIR = Path.home() / ".config" / "goose"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"
class SystemConfig(BaseSettings):
    # 基础配置
    env: str = "production"  # development / production
    db_url: str = "./temp_test_data/test_goose.db"
    
    # 事件系统配置
    event_bus_size: int = 1000
    event_ttl: int = 3600
    
    # 密钥配置 (自动读取环境变量 OPENAI_API_KEY 等)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    serpapi_api_key: str = ""
    
    silicon_api_key: str = "sk-climzomnsicqdepumaymoshvgviaggcgounvovaqglltepkd"
    silicon_base_url: str = "https://api.siliconflow.cn/v1"
    
    class Config:
        env_file = ".env"  # 自动读取当前目录下的 .env 文件
        env_prefix = "GOOSE_"
        
    @classmethod
    def load(cls, config_path: Path = DEFAULT_CONFIG_FILE) -> "SystemConfig":
        """加载配置：默认值 -> 配置文件 -> 环境变量 (最高优先级)"""
        
        # 1. 基础默认值
        config_data = {}
        
        # 2. 读取 YAML
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    yaml_data = yaml.safe_load(f)
                    if yaml_data:
                        config_data.update(yaml_data)
            except Exception as e:
                print(f"⚠️ Warning: Failed to load config from {config_path}: {e}")

        # 3. 环境变量覆盖 (仅处理核心字段)
        env_map = {
            "GOOSE_PROVIDER": "GOOSE_PROVIDER",
            "GOOSE_MODEL": "GOOSE_MODEL",
            "OPENAI_API_KEY": "OPENAI_API_KEY",
            "OPENAI_BASE_URL": "OPENAI_BASE_URL",
        }
        
        for env_key, field_name in env_map.items():
            val = os.getenv(env_key)
            if val:
                config_data[field_name] = val

        return cls(**config_data)


# 全局单例
_global_config = None

def get_config() -> SystemConfig:
    global _global_config
    if _global_config is None:
        _global_config = SystemConfig.load()
    return _global_config