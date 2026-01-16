"""
Artifact Manager - 统一 artifact 管理器

集成多种存储后端，提供配置驱动的 artifact 管理。
基于以下设计模式：
1. ProviderFactory - 根据配置创建存储后端
2. Registry - 存储后端注册中心
3. Builder Pattern - 配置到实例的构建

使用方式：
```python
# 1. 初始化
from assistant.core.artifact_storage import ArtifactManager

artifact_mgr = ArtifactManager(config_path="config/assistant_config.yaml")

# 2. 存储数据
ref = await artifact_mgr.store(
    aid="art_abc123",
    artifact_type="dataset",
    data=dataset_data,
    text="推荐结果: 三彩"
)

# 3. 将引用存入 shared_memory
state.shared_memory[ref.id] = ref.to_dict()

# 4. 加载数据
data = await artifact_mgr.load_by_id(ref.id)

# 5. 删除数据
await artifact_mgr.delete_by_id(ref.id)

# 6. 会话结束时清理
await artifact_mgr.cleanup_session(session_id)
```
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass

from .base import ArtifactStorage, ArtifactRef, StorageType, StorageConfig
from .registry import ArtifactStorageRegistry, register_storage, get_registry
from .config import ArtifactStorageConfig, load_config

logger = logging.getLogger(__name__)


@dataclass
class ArtifactManagerConfig:
    """
    ArtifactManager 配置

    类似于 ProviderRegistry 和 SkillLoader 的配置设计。
    """
    # 全局配置
    enabled: bool = True
    default_storage: StorageType = StorageType.MEMORY
    cleanup_interval: int = 3600  # 清理间隔（秒）

    # 会话级别配置
    max_items_per_session: int = 50
    max_bytes_per_session: int = 50 * 1024 * 1024  # 50MB
    ttl: int = 86400  # 24小时

    # 存储后端特定配置
    storage_configs: Dict[StorageType, Dict[str, Any]] = None

    # 基础目录
    base_dir: str = "artifacts"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactManagerConfig":
        """从配置字典创建"""
        storage_type_str = data.get("default_storage", "memory")
        try:
            default_storage = StorageType(storage_type_str.lower())
        except ValueError:
            logger.warning(f"Unknown storage type: {storage_type_str}, using memory")
            default_storage = StorageType.MEMORY

        storage_configs = data.get("storage_configs", {})

        return cls(
            enabled=data.get("enabled", True),
            default_storage=default_storage,
            cleanup_interval=data.get("cleanup_interval", 3600),
            max_items_per_session=data.get("max_items_per_session", 50),
            max_bytes_per_session=data.get("max_bytes_per_session", 50 * 1024 * 1024),
            ttl=data.get("ttl", 86400),
            storage_configs=storage_configs,
            base_dir=data.get("base_dir", "artifacts"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "default_storage": self.default_storage.value,
            "cleanup_interval": self.cleanup_interval,
            "max_items_per_session": self.max_items_per_session,
            "max_bytes_per_session": self.max_bytes_per_session,
            "ttl": self.ttl,
            "storage_configs": self.storage_configs or {},
            "base_dir": self.base_dir,
        }


class ArtifactManager:
    """
    统一 Artifact 管理器

    功能：
    - 配置驱动的存储后端选择
    - 自动清理过期数据
    - 会话级别的数据隔离
    - 批量操作支持
    """

    def __init__(self, config: Optional[ArtifactManagerConfig] = None, config_path: Optional[str] = None):
        """
        初始化 ArtifactManager

        Args:
            config: 配置对象
            config_path: 配置文件路径（可选，用于自动加载）
        """
        self.logger = logger

        # 加载配置
        if config is None and config_path:
            config = load_config(config_path)
            if config and "artifact_manager" in config:
                self.config = ArtifactManagerConfig.from_dict(config["artifact_manager"])
                self.logger.info(f"Loaded ArtifactManager config from {config_path}")
            else:
                try:
                    self.config = ArtifactManagerConfig.from_dict(config)
                except Exception as e:
                    self.logger.error(f"Failed to load ArtifactManager config from {config_path}: {e}")
                    self.config = ArtifactManagerConfig()
        else:
            self.config = config or ArtifactManagerConfig()

        if not self.config.enabled:
            self.logger.warning("ArtifactManager is disabled")

        # 获取注册中心
        self.registry = get_registry()

        # 会话级别的存储后端：session_id -> ArtifactStorage
        self._session_storages: Dict[str, ArtifactStorage] = {}

        # 清理任务
        self._cleanup_task: Optional[asyncio.Task] = None

        # 启动清理任务
        if self.config.enabled:
            self._start_cleanup_task()

    async def get_storage(self, session_id: str|int) -> ArtifactStorage:
        """
        获取或创建会话的存储后端

        根据配置选择默认存储类型，但也支持临时覆盖。
        """
        session_id = str(session_id)
        if session_id in self._session_storages:
            return self._session_storages[session_id]

        # 获取默认存储类型的配置
        storage_config = self._get_storage_config(self.config.default_storage)

        # 创建存储后端
        storage = self.registry.create(storage_config, session_id)

        # 初始化
        await storage.initialize()

        self._session_storages[session_id] = storage
        self.logger.debug(f"Created {storage.config.storage_type.value} storage for session {session_id}")

        return storage

    async def store(
        self,
        session_id: str|int,
        artifact_id: str,
        artifact_type: str,
        data: Any,
        text: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        storage_type: Optional[StorageType] = None,
    ) -> ArtifactRef:
        """
        存储 artifact 数据

        Args:
            session_id: 会话 ID
            artifact_id: Artifact ID
            artifact_type: 数据类型
            data: 要存储的数据
            text: 文本描述
            metadata: 额外元数据
            storage_type: 指定存储类型（可选，默认使用配置）

        Returns:
            ArtifactRef 对象
        """
        if not self.config.enabled:
            raise RuntimeError("ArtifactManager is disabled")

        # 序列化数据并估算大小
        import json
        json_data = json.dumps(data, ensure_ascii=False)
        size = len(json_data.encode('utf-8'))

        # 创建引用对象
        ref = ArtifactRef(
            id=artifact_id,
            type=artifact_type,
            text=text,
            size=size,
            storage_type=storage_type or self.config.default_storage,
            metadata=metadata or {},
        )
        session_id = str(session_id)
        # 获取存储后端
        storage = await self.get_storage(session_id)

        # 存储数据
        await storage.store(ref, data)

        return ref

    async def load(self, session_id: str|int, artifact_id: str) -> Optional[Any]:
        """
        加载 artifact 数据

        Args:
            session_id: 会话 ID
            artifact_id: Artifact ID

        Returns:
            存储的数据，如果不存在返回 None
        """
        if not self.config.enabled:
            return None
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            # 尝试从数据库加载旧格式的引用
            ref = self._load_legacy_ref(session_id, artifact_id)
            if ref:
                # 迁移到新的存储后端
                return await self._load_with_storage(session_id, ref)

            return None

        # 构造引用对象
        ref = ArtifactRef(
            id=artifact_id,
            type="unknown",
            text="",
            size=0,
            storage_type=storage.config.storage_type,
            metadata={},
        )

        # 从存储加载
        return await storage.load(ref)

    async def load_by_ref(self, session_id: str|int, ref: ArtifactRef) -> Optional[Any]:
        """根据引用对象加载数据"""
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return None

        return await storage.load(ref)

    async def delete(self, session_id: str|int, artifact_id: str) -> bool:
        """
        删除 artifact 数据

        Args:
            session_id: 会话 ID
            artifact_id: Artifact ID

        Returns:
            是否删除成功
        """
        if not self.config.enabled:
            return False

        session_id = str(session_id)
        
        storage = self._session_storages.get(session_id)
        if storage is None:
            # 处理旧格式
            ref = self._load_legacy_ref(session_id, artifact_id)
            if ref:
                return await storage.delete(ref)
            return False

        ref = ArtifactRef(id=artifact_id, type="", text="", size=0,
                         storage_type=storage.config.storage_type, metadata={})
        return await storage.delete(ref)

    async def delete_by_ref(self, session_id: str|int, ref: ArtifactRef) -> bool:
        """根据引用对象删除"""
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return False

        return await storage.delete(ref)

    async def exists(self, session_id: str|int, artifact_id: str) -> bool:
        """检查 artifact 是否存在"""
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return False

        ref = ArtifactRef(id=artifact_id, type="", text="", size=0,
                         storage_type=storage.config.storage_type, metadata={})
        return await storage.exists(ref)

    async def cleanup_session(self, session_id: str|int) -> int:
        """
        清理会话的所有 artifacts

        Args:
            session_id: 会话 ID

        Returns:
            清理的数量
        """
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return 0

        count = await storage.cleanup_all()

        # 从缓存中删除
        del self._session_storages[session_id]

        # 清理数据库中的旧格式引用（如果需要）
        await self._cleanup_legacy_refs(session_id)

        self.logger.info(f"Cleaned up session {session_id}: {count} artifacts")
        return count

    async def cleanup_old(self, session_id: str|int, older_than_seconds: Optional[int] = None) -> int:
        """
        清理过期的 artifacts

        Args:
            session_id: 会话 ID
            older_than_seconds: 清理时间阈值（秒），默认使用 TTL

        Returns:
            清理的数量
        """
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return 0

        if older_than_seconds is None:
            older_than_seconds = self.config.ttl

        return await storage.cleanup_old(older_than_seconds)

    async def get_stats(self, session_id: str|int) -> Dict[str, Any]:
        """
        获取会话的统计信息

        Args:
            session_id: 会话 ID

        Returns:
            统计信息
        """
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return {}

        return await storage.get_stats()

    async def list_all(self, session_id: str|int) -> List[ArtifactRef]:
        """列出会话的所有 artifacts"""
        session_id = str(session_id)
        storage = self._session_storages.get(session_id)
        if storage is None:
            return []

        return await storage.list_all()

    async def health_check(self) -> Dict[str, Any]:
        """
        健康检查

        Returns:
            所有会话的存储后端健康状态
        """
        results = {}

        for session_id, storage in self._session_storages.items():
            try:
                healthy = await storage.health_check()
                results[session_id] = {
                    "storage_type": storage.config.storage_type.value,
                    "healthy": healthy,
                }
            except Exception as e:
                results[session_id] = {
                    "storage_type": storage.config.storage_type.value,
                    "healthy": False,
                    "error": str(e),
                }

        return results

    def _get_storage_config(self, storage_type: StorageType) -> StorageConfig:
        """获取存储类型的配置"""
        # 检查是否有特定配置
        if self.config.storage_configs and storage_type.value in self.config.storage_configs:
            config_data = self.config.storage_configs[storage_type.value]

            # 根据存储类型创建配置对象
            if storage_type == StorageType.MEMORY:
                from .memory import MemoryStorageConfig
                return MemoryStorageConfig(
                    max_items=config_data.get("max_items", self.config.max_items_per_session),
                    max_size_bytes=config_data.get("max_size_bytes", self.config.max_bytes_per_session),
                    ttl=config_data.get("ttl", self.config.ttl),
                )

            elif storage_type == StorageType.FILE:
                from .file import FileStorageConfig
                return FileStorageConfig(
                    base_dir=config_data.get("base_dir", self.config.base_dir),
                    compression=config_data.get("compression", False),
                    ttl=config_data.get("ttl", self.config.ttl),
                )

            elif storage_type == StorageType.HYBRID:
                from .hybrid import HybridStorageConfig
                return HybridStorageConfig(
                    base_dir=config_data.get("base_dir", self.config.base_dir),
                    memory_threshold=config_data.get("memory_threshold", 10 * 1024),
                    file_threshold=config_data.get("file_threshold", 100 * 1024),
                    compression=config_data.get("compression", True),
                    max_items=config_data.get("max_items", self.config.max_items_per_session),
                    max_size_bytes=config_data.get("max_size_bytes", self.config.max_bytes_per_session),
                    ttl=config_data.get("ttl", self.config.ttl),
                )

            elif storage_type == StorageType.DATABASE:
                from .database import DatabaseStorageConfig
                return DatabaseStorageConfig(
                    table_name=config_data.get("table_name", "artifacts"),
                    ttl=config_data.get("ttl", self.config.ttl),
                )

        # 使用默认配置
        return StorageConfig(
            storage_type=storage_type,
            enabled=True,
            ttl=self.config.ttl,
            max_items=self.config.max_items_per_session,
            max_size_bytes=self.config.max_bytes_per_session,
            cleanup_interval=self.config.cleanup_interval,
        )

    def _load_legacy_ref(self, session_id: str|int, artifact_id: str) -> Optional[ArtifactRef]:
        """加载旧格式的引用（从 shared_memory）"""
        # 这个方法由外部调用，从 shared_memory 中提取旧格式的引用
        return None

    async def _load_with_storage(self, session_id: str|int, ref: ArtifactRef) -> Optional[Any]:
        """使用存储后端加载引用数据"""
        storage = self._session_storages.get(session_id)
        if storage is None:
            return None

        return await storage.load(ref)

    async def _cleanup_legacy_refs(self, session_id: str|int) -> int:
        """清理旧的引用（从数据库）"""
        # 如果使用 DatabaseStorage，可能需要清理旧格式的引用
        return 0

    def _start_cleanup_task(self):
        """启动后台清理任务"""
        async def cleanup_loop():
            while self.config.enabled:
                await asyncio.sleep(self.config.cleanup_interval)
                await self._periodic_cleanup()

        self._cleanup_task = asyncio.create_task(cleanup_loop())
        self.logger.info(f"Started cleanup task (interval: {self.config.cleanup_interval}s)")

    async def _periodic_cleanup(self):
        """定期清理所有会话的过期数据"""
        now = datetime.now()

        for session_id, storage in list(self._session_storages.items()):
            try:
                # 清理超过 TTL 的数据
                threshold = self.config.ttl
                count = await storage.cleanup_old(threshold)

                if count > 0:
                    self.logger.debug(f"Periodic cleanup for {session_id}: {count} items")
            except Exception as e:
                self.logger.warning(f"Failed to cleanup session {session_id}: {e}")

    async def shutdown(self):
        """关闭 ArtifactManager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self.logger.info("Cleanup task stopped")

        # 关闭所有存储后端
        for storage in self._session_storages.values():
            try:
                if hasattr(storage, "shutdown"):
                    await storage.shutdown()
            except Exception as e:
                self.logger.warning(f"Failed to shutdown storage: {e}")

        self._session_storages.clear()
        self.logger.info("ArtifactManager shutdown")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.shutdown()


# ============================================================================
# 全局单例（可选，类似 ProviderFactory）
# ============================================================================

_global_manager: Optional[ArtifactManager] = None


def init_manager(config_path: Optional[str] = None) -> ArtifactManager:
    """
    初始化全局 ArtifactManager

    Args:
        config_path: 配置文件路径

    Returns:
        ArtifactManager 实例
    """
    global _global_manager

    if _global_manager is None:
        _global_manager = ArtifactManager(config_path=config_path)

    return _global_manager


def get_manager() -> Optional[ArtifactManager]:
    """获取全局 ArtifactManager 实例"""
    return _global_manager
