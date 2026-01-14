"""
Artifact Storage Config - 配置加载模块

基于 SkillLoader 和 ConfigLoader 的设计：
- YAML 配置文件
- 环境变量覆盖
- 默认值
- 配置验证
"""

import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class MemoryStorageConfig(BaseModel):
    """内存存储配置"""
    max_items: int = Field(default=50, description="最大条目数")
    max_size_bytes: int = Field(default=50 * 1024 * 1024, description="最大字节数")
    ttl: int = Field(default=86400, description="数据生存时间（秒）")


class FileStorageConfig(BaseModel):
    """文件存储配置"""
    base_dir: str = Field(default="artifacts", description="基础目录")
    compression: bool = Field(default=False, description="是否压缩")
    ttl: int = Field(default=86400, description="数据生存时间（秒）")


class HybridStorageConfig(BaseModel):
    """混合存储配置"""
    memory_threshold: int = Field(default=10 * 1024, description="内存阈值（字节）")
    file_threshold: int = Field(default=100 * 1024, description="文件阈值（字节）")
    base_dir: str = Field(default="artifacts", description="基础目录")
    compression: bool = Field(default=True, description="是否压缩")
    max_items: int = Field(default=50, description="最大条目数")
    max_size_bytes: int = Field(default=50 * 1024 * 1024, description="最大字节数")
    ttl: int = Field(default=86400, description="数据生存时间（秒）")


class DatabaseStorageConfig(BaseModel):
    """数据库存储配置"""
    table_name: str = Field(default="artifacts", description="表名")
    ttl: int = Field(default=86400, description="数据生存时间（秒）")


class ArtifactStorageConfig(BaseModel):
    """
    ArtifactManager 配置模型

    使用 Pydantic 进行验证和类型检查。
    """
    enabled: bool = Field(default=True, description="是否启用")
    default_storage: str = Field(default="memory", description="默认存储类型")
    cleanup_interval: int = Field(default=3600, description="清理间隔（秒）")
    max_items_per_session: int = Field(default=50, description="每会话最大条目数")
    max_bytes_per_session: int = Field(default=50 * 1024 * 1024, description="每会话最大字节数")
    ttl: int = Field(default=86400, description="数据生存时间（秒）")
    storage_configs: Dict[str, Any] = Field(default_factory=dict, description="各存储类型的特定配置")

    @field_validator('storage_configs', mode='before')
    @classmethod
    def validate_storage_configs(cls, v: dict) -> dict:
        """验证存储配置"""
        # 确保存储类型的键名正确
        valid_types = {'memory', 'file', 'hybrid', 'database'}
        for key in list(v.keys()):
            if key not in valid_types:
                logger.warning(f"Invalid storage type key: {key}, removing")
                del v[key]
        return v

    @field_validator('default_storage')
    @classmethod
    def validate_default_storage(cls, v: str) -> str:
        """验证默认存储类型"""
        valid_types = {'memory', 'file', 'hybrid', 'database'}
        if v.lower() not in valid_types:
            logger.warning(f"Invalid default_storage: {v}, using 'memory'")
            return 'memory'
        return v.lower()


def load_config(config_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    加载 artifact 管理器配置

    Args:
        config_path: 配置文件路径，默认从环境变量或默认位置读取

    Returns:
        配置字典，如果配置不存在返回 None
    """
    # 1. 确定配置文件路径
    if config_path is None:
        # 优先级：环境变量 > 当前目录 config.yaml > 用户目录配置
        config_path = os.getenv("ARTIFACT_MANAGER_CONFIG")
        if config_path is None:
            # 尝试当前目录的 config 文件
            current_dir = Path.cwd()
            config_file = current_dir / "artifact_manager_config.yaml"

            if config_file.exists():
                config_path = str(config_file)
            else:
                # 检查用户目录
                home_dir = Path.home()
                user_config = home_dir / ".config" / "goose" / "artifact_manager.yaml"

                if user_config.exists():
                    config_path = str(user_config)
                else:
                    return None

    # 2. 读取 YAML 文件
    if not config_path or not Path(config_path).exists():
        logger.warning(f"ArtifactManager config file not found: {config_path}")
        return None

    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 3. 环境变量覆盖
        if 'artifact_manager' in config:
            artifact_config = config['artifact_manager']

            # 应用环境变量覆盖
            override_key = "ARTIFACT_MANAGER_OVERRIDE"
            if override_key in os.environ:
                try:
                    override_data = yaml.safe_load(os.environ[override_key])
                    artifact_config.update(override_data)
                    logger.info(f"Applied environment override for artifact_manager")
                except Exception as e:
                    logger.warning(f"Failed to parse environment override: {e}")

            # 验证配置
            validated = ArtifactStorageConfig(**artifact_config)
            return validated.model_dump()

        return config

    except Exception as e:
        logger.error(f"Failed to load ArtifactManager config from {config_path}: {e}")
        return None


def get_default_config() -> Dict[str, Any]:
    """
    获取默认配置

    Returns:
        默认配置字典
    """
    return ArtifactStorageConfig().model_dump()
