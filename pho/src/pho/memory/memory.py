"""
Memory Storage - LRU 内存存储实现

基于 goose-rs 中 AnalysisCache 的设计：
- 使用 LRU 缓存自动淘汰
- 线程安全（如果需要）
- 快速访问
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

try:
    from functools import lru_cache
except ImportError:
    # Python < 3.9 fallback
    from backports.functools_lru_cache import lru_cache

from .base import ArtifactStorage, ArtifactRef, StorageConfig, StorageType
from .registry import register_storage

logger = logging.getLogger(__name__)


class LRUCache:
    """简单的 LRU 缓存实现"""

    def __init__(self, max_size: int = 128):
        self.max_size = max_size
        self.cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, access_time)
        self.access_order: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            value, _ = self.cache[key]
            # 更新访问时间
            self.cache[key] = (value, datetime.now().timestamp())
            # 更新访问顺序
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
            return value
        return None

    def put(self, key: str, value: Any) -> None:
        now = datetime.now().timestamp()

        if key in self.cache:
            # 更新现有值
            self.cache[key] = (value, now)
            if key in self.access_order:
                self.access_order.remove(key)
            self.access_order.append(key)
        else:
            # 添加新值，检查是否需要淘汰
            if len(self.cache) >= self.max_size:
                # 淘汰最旧的
                oldest = self.access_order.pop(0)
                del self.cache[oldest]

            self.cache[key] = (value, now)
            self.access_order.append(key)

    def remove(self, key: str) -> bool:
        if key in self.cache:
            del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)
            return True
        return False

    def keys(self) -> List[str]:
        return list(self.cache.keys())

    def size(self) -> int:
        return len(self.cache)


class MemoryStorageConfig(StorageConfig):
    """内存存储配置"""

    def __init__(
        self,
        max_items: int = 50,
        max_size_bytes: int = 50 * 1024 * 1024,
        ttl: int = 86400,
        **kwargs
    ):
        super().__init__(storage_type=StorageType.MEMORY, **kwargs)
        self.max_items = max_items
        self.max_size_bytes = max_size_bytes
        self.ttl = ttl


@register_storage(StorageType.MEMORY, MemoryStorageConfig)
class MemoryStorage(ArtifactStorage):
    """
    LRU 内存存储实现

    特性：
    - 快速访问（内存级别）
    - LRU 自动淘汰
    - 进程重启后丢失
    """

    def __init__(self, config: MemoryStorageConfig, session_id: str):
        super().__init__(config, session_id)
        self.cache: LRUCache = LRUCache(max_size=config.max_items)
        self.total_size = 0

    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        """存储到内存"""
        # 检查是否需要清理
        await self._maybe_cleanup()

        # 生成存储键
        storage_key = f"{self.session_id}:{ref.id}"

        # 存储数据
        self.cache.put(storage_key, data)
        self.total_size += ref.size

        # 更新引用
        ref.storage_key = storage_key

        self.logger.debug(f"Stored artifact {ref.id} ({ref.size} bytes)")
        return ref

    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        """从内存加载"""
        storage_key = ref.storage_key or f"{self.session_id}:{ref.id}"
        return self.cache.get(storage_key)

    async def delete(self, ref: ArtifactRef) -> bool:
        """从内存删除"""
        storage_key = ref.storage_key or f"{self.session_id}:{ref.id}"

        # 先获取数据以计算大小
        data = self.cache.get(storage_key)
        if data is not None:
            size = len(str(data).encode('utf-8')) if data else 0
            self.total_size -= min(size, self.total_size)

        return self.cache.remove(storage_key)

    async def exists(self, ref: ArtifactRef) -> bool:
        """检查是否存在"""
        storage_key = ref.storage_key or f"{self.session_id}:{ref.id}"
        return storage_key in self.cache.keys()

    async def list_all(self) -> List[ArtifactRef]:
        """列出所有 artifacts（无法从缓存重建完整 ref，返回空列表）"""
        # 内存存储不保存完整的 ArtifactRef，所以无法列出
        # 实际使用中，shared_memory 中保存了 ref，所以不需要这个功能
        return []

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        base_stats = await super().get_stats()
        base_stats.update({
            "cache_size": self.cache.size(),
            "cache_capacity": self.config.max_items,
            "total_memory_bytes": self.total_size,
            "max_memory_bytes": self.config.max_size_bytes,
        })
        return base_stats

    async def _maybe_cleanup(self) -> None:
        """检查并执行 LRU 清理"""
        if self.total_size > self.config.max_size_bytes:
            # 删除最旧的 20%
            to_remove = max(1, int(self.cache.size() * 0.2))

            keys = self.cache.keys()
            for i in range(min(to_remove, len(keys))):
                key = keys[i]
                self.cache.remove(key)

            self.logger.info(f"LRU cleanup: removed {to_remove} items due to size limit")
