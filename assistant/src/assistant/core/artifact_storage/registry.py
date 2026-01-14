"""
Artifact Storage Registry - 存储后端注册中心

基于 ProviderRegistry 和 SkillLoader 的设计模式：
1. 装饰器注册 (@register_storage)
2. 配置驱动创建
3. 多种存储后端支持
"""

import logging
from typing import Dict, Type, Optional, List
from .base import ArtifactStorage, StorageConfig, StorageType

logger = logging.getLogger(__name__)


class ArtifactStorageRegistry:
    """
    Artifact 存储后端注册中心

    类似 ProviderRegistry 的设计，用于管理不同的存储后端。
    """

    def __init__(self):
        # storage_type -> (storage_class, config_class)
        self._storages: Dict[StorageType, tuple[Type[ArtifactStorage], Type[StorageConfig]]] = {}

    def register(
        self,
        storage_type: StorageType,
        storage_class: Type[ArtifactStorage],
        config_class: Type[StorageConfig]
    ):
        """
        注册存储后端

        Args:
            storage_type: 存储类型
            storage_class: 存储实现类
            config_class: 配置类
        """
        self._storages[storage_type] = (storage_class, config_class)
        logger.debug(f"Registered storage backend: {storage_type.value} -> {storage_class.__name__}")

    def get(self, storage_type: StorageType) -> Optional[tuple[Type[ArtifactStorage], Type[StorageConfig]]]:
        """获取存储后端"""
        return self._storages.get(storage_type)

    def create(self, config: StorageConfig, session_id: str) -> ArtifactStorage:
        """
        根据配置创建存储后端实例

        Args:
            config: 存储配置
            session_id: 会话 ID

        Returns:
            存储后端实例
        """
        entry = self.get(config.storage_type)
        if entry is None:
            raise ValueError(f"Unknown storage type: {config.storage_type}")

        storage_class, _ = entry
        return storage_class(config, session_id)

    def list_types(self) -> List[str]:
        """列出所有注册的存储类型"""
        return [st.value for st in self._storages.keys()]

    def list_storages(self) -> List[Dict[str, str]]:
        """列出所有存储后端信息"""
        return [
            {
                "type": st.value,
                "class": sc.__name__,
            }
            for st, (sc, _) in self._storages.items()
        ]


# 全局注册中心实例
_global_registry = ArtifactStorageRegistry()


def register_storage(
    storage_type: StorageType,
    config_class: Type[StorageConfig] = None
):
    """
    装饰器：注册存储后端

    用法：
    ```python
    @register_storage(StorageType.MEMORY)
    class MemoryStorage(ArtifactStorage):
        ...
    ```

    Args:
        storage_type: 存储类型
        config_class: 配置类（可选，默认使用 StorageConfig）
    """
    def decorator(storage_class: Type[ArtifactStorage]):
        _global_registry.register(
            storage_type,
            storage_class,
            config_class or StorageConfig
        )
        return storage_class

    return decorator


def get_registry() -> ArtifactStorageRegistry:
    """获取全局注册中心"""
    return _global_registry


def _register_builtin_storages():
    """注册内置存储后端"""
    # 延迟导入避免循环依赖
    from .memory import MemoryStorage
    from .file import FileStorage
    from .hybrid import HybridStorage
    from .database import DatabaseStorage

    # 注册会在模块导入时通过装饰器自动完成
    logger.debug("Built-in storage backends registered")
