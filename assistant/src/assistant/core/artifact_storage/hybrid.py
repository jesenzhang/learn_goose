"""
Hybrid Storage - 混合存储实现

基于 Config keyring + file 和 AnalysisCache 的混合设计：
- 小数据存内存（快速访问）
- 大数据存文件（节省内存）
- 自动 LRU 淘汰
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import ArtifactStorage, ArtifactRef, StorageConfig, StorageType
from .memory import MemoryStorage, MemoryStorageConfig
from .file import FileStorage, FileStorageConfig
from .registry import register_storage
    
logger = logging.getLogger(__name__)


class HybridStorageConfig(StorageConfig):
    """混合存储配置"""

    def __init__(
        self,
        # 内存阈值
        memory_threshold: int = 10 * 1024,  # 10KB
        # 文件阈值
        file_threshold: int = 100 * 1024,   # 100KB
        # 其他配置
        base_dir: str = "artifacts",
        compression: bool = True,
        max_items: int = 50,
        max_size_bytes: int = 50 * 1024 * 1024,
        ttl: int = 86400,
        **kwargs
    ):
        super().__init__(storage_type=StorageType.HYBRID, **kwargs)
        self.memory_threshold = memory_threshold
        self.file_threshold = file_threshold
        self.base_dir = base_dir
        self.compression = compression
        self.max_items = max_items
        self.max_size_bytes = max_size_bytes
        self.ttl = ttl


@register_storage(StorageType.HYBRID, HybridStorageConfig)
class HybridStorage(ArtifactStorage):
    """
    混合存储实现

    策略：
    - 小于 memory_threshold: 内存存储
    - 介于两者之间: 内存存储（压缩）
    - 大于 file_threshold: 文件存储

    特性：
    - 自动选择最优存储方式
    - LRU 内存管理
    - 文件持久化
    - 透明的读取接口
    """

    def __init__(self, config: HybridStorageConfig, session_id: str):
        super().__init__(config, session_id)

        # 创建子存储
        self.memory_config = MemoryStorageConfig(
            max_items=config.max_items,
            max_size_bytes=config.max_size_bytes,
            ttl=config.ttl,
        )
        self.memory = MemoryStorage(self.memory_config, session_id)

        self.file_config = FileStorageConfig(
            base_dir=config.base_dir,
            compression=config.compression,
            ttl=config.ttl,
        )
        self.file = FileStorage(self.file_config, session_id)

    async def initialize(self) -> None:
        """初始化文件存储"""
        await self.file.initialize()

    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        """根据大小选择存储方式"""
        # 估算数据大小
        import json
        json_data = json.dumps(data, ensure_ascii=False)
        size = len(json_data.encode('utf-8'))

        # 更新 ref 的大小
        ref.size = size

        # 决定存储方式
        if size <= self.config.memory_threshold:
            # 小数据：直接内存
            actual_storage = self.memory
            ref.metadata["storage_backend"] = "memory"
            ref.metadata["compressed"] = False
            self.logger.debug(f"Using memory storage for {ref.id} ({size} bytes)")

        elif size <= self.config.file_threshold:
            # 中等数据：内存压缩
            import gzip
            compressed = gzip.compress(json_data.encode('utf-8'))
            ref.size = len(compressed)  # 更新为压缩后大小
            ref.metadata["storage_backend"] = "memory_compressed"
            ref.metadata["compressed"] = True
            actual_storage = self.memory
            self.logger.debug(f"Using compressed memory for {ref.id}: {size} -> {len(compressed)} bytes")

        else:
            # 大数据：文件存储
            actual_storage = self.file
            ref.metadata["storage_backend"] = "file"
            ref.metadata["compressed"] = self.file_config.compression
            self.logger.debug(f"Using file storage for {ref.id} ({size} bytes)")

        # 存储到选定的后端
        return await actual_storage.store(ref, data)

    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        """从正确的后端加载"""
        backend = ref.metadata.get("storage_backend", "memory")

        if backend == "file":
            return await self.file.load(ref)
        else:
            # memory 或 memory_compressed 都用 memory 存储
            return await self.memory.load(ref)

    async def delete(self, ref: ArtifactRef) -> bool:
        """从正确的后端删除"""
        backend = ref.metadata.get("storage_backend", "memory")

        if backend == "file":
            return await self.file.delete(ref)
        else:
            return await self.memory.delete(ref)

    async def exists(self, ref: ArtifactRef) -> bool:
        """检查是否存在"""
        backend = ref.metadata.get("storage_backend", "memory")

        if backend == "file":
            return await self.file.exists(ref)
        else:
            return await self.memory.exists(ref)

    async def list_all(self) -> List[ArtifactRef]:
        """列出所有 artifacts（合并两个后端）"""
        # 文件存储可以列出，内存存储无法列出
        return await self.file.list_all()

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息（合并两个后端）"""
        memory_stats = await self.memory.get_stats()
        file_stats = await self.file.get_stats()

        return {
            "storage_type": StorageType.HYBRID.value,
            "session_id": self.session_id,
            "memory_backend": memory_stats,
            "file_backend": file_stats,
            "memory_threshold": self.config.memory_threshold,
            "file_threshold": self.config.file_threshold,
        }

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        """清理过期数据（两个后端都清理）"""
        memory_count = await self.memory.cleanup_old(older_than_seconds)
        file_count = await self.file.cleanup_old(older_than_seconds)

        total = memory_count + file_count
        if total > 0:
            self.logger.info(f"Cleaned up {total} artifacts (memory: {memory_count}, file: {file_count})")

        return total

    async def cleanup_all(self) -> int:
        """清理所有数据"""
        memory_count = await self.memory.cleanup_all()
        file_count = await self.file.cleanup_all()

        total = memory_count + file_count
        self.logger.info(f"Cleaned up all artifacts: {total} total")

        return total

    async def shutdown(self) -> None:
        """关闭存储后端"""
        # 文件存储可能需要清理
        await self.file.shutdown()
