"""
Artifact Storage Base Classes - 存储后端抽象定义

定义统一的存储接口，所有存储后端都需要实现这些方法。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class StorageType(str, Enum):
    """存储类型枚举"""
    MEMORY = "memory"          # 纯内存
    FILE = "file"              # 纯文件
    HYBRID = "hybrid"          # 混合（内存+文件）
    DATABASE = "database"      # 数据库


@dataclass
class ArtifactRef:
    """
    Artifact 引用对象

    这是存储在 shared_memory 中的轻量级对象，
    不包含实际数据，只包含元数据和引用信息。
    """
    id: str                              # Artifact ID
    type: str                            # 数据类型 (dataset, chart, table 等)
    text: str                            # 文本描述
    size: int                            # 原始数据大小（字节）
    storage_type: StorageType           # 存储类型
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外元数据
    storage_key: Optional[str] = None    # 存储后端使用的键（可选）

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于存储到 shared_memory）"""
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "size": self.size,
            "storage_type": self.storage_type.value,
            "created_at": self.created_at,
            "metadata": self.metadata,
            "storage_key": self.storage_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactRef":
        """从字典创建"""
        # 兼容旧格式
        if "storage" in data and "storage_type" not in data:
            # 旧格式使用 "storage" 字段
            storage_map = {
                "memory": StorageType.MEMORY,
                "compressed": StorageType.MEMORY,  # 旧格式的 compressed 归类为 memory
                "file": StorageType.FILE,
            }
            storage_type = storage_map.get(data.get("storage"), StorageType.MEMORY)
        else:
            storage_type = StorageType(data.get("storage_type", StorageType.MEMORY))

        return cls(
            id=data["id"],
            type=data.get("type", "dataset"),
            text=data.get("text", ""),
            size=data.get("size", 0),
            storage_type=storage_type,
            created_at=data.get("created_at", datetime.now().timestamp()),
            metadata=data.get("metadata", {}),
            storage_key=data.get("storage_key"),
        )


@dataclass
class StorageConfig:
    """
    存储后端配置基类

    所有存储后端的具体配置类都应该继承这个类。
    """
    storage_type: StorageType           # 存储类型

    # 通用配置
    enabled: bool = True                 # 是否启用
    ttl: int = 86400                     # 数据生存时间（秒），默认 24 小时

    # LRU 配置（仅内存相关）
    max_items: int = 50                  # 最大条目数
    max_size_bytes: int = 50 * 1024 * 1024  # 最大总字节数（50MB）

    # 清理配置
    cleanup_interval: int = 3600         # 清理间隔（秒）

    # 文件存储配置（仅文件相关）
    base_dir: str = "artifacts"          # 基础目录
    compression: bool = False            # 是否压缩

    # 数据库配置（仅数据库相关）
    table_name: str = "artifacts"        # 表名

    def validate(self) -> bool:
        """验证配置是否有效"""
        return self.enabled

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        from pydantic import BaseModel

        class StorageConfigModel(BaseModel):
            storage_type: str
            enabled: bool
            ttl: int
            max_items: int
            max_size_bytes: int
            cleanup_interval: int
            base_dir: str
            compression: bool
            table_name: str

        return StorageConfigModel(
            storage_type=self.storage_type.value,
            enabled=self.enabled,
            ttl=self.ttl,
            max_items=self.max_items,
            max_size_bytes=self.max_size_bytes,
            cleanup_interval=self.cleanup_interval,
            base_dir=self.base_dir,
            compression=self.compression,
            table_name=self.table_name,
        ).model_dump()


class ArtifactStorage(ABC):
    """
    Artifact 存储后端抽象基类

    所有存储后端都必须实现这个接口。

    设计原则：
    1. 简单性 - 只包含核心 CRUD 操作
    2. 可测试性 - 所有方法都是幂等且可独立测试
    3. 可观测性 - 提供统计和日志记录
    """

    def __init__(self, config: StorageConfig, session_id: str|int):
        """
        初始化存储后端

        Args:
            config: 存储配置
            session_id: 会话 ID，用于隔离不同会话的数据
        """
        self.config = config
        self.session_id = str(session_id)
        self.logger = logger.getChild(f"{self.__class__.__name__}[{self.session_id}]")

    # ========================================================================
    # 核心操作 (必须实现)
    # ========================================================================

    @abstractmethod
    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        """
        存储 artifact 数据

        Args:
            ref: Artifact 引用对象
            data: 要存储的数据（可以是任意类型）

        Returns:
            更新后的 ArtifactRef（可能包含 storage_key 等额外信息）
        """
        pass

    @abstractmethod
    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        """
        加载 artifact 数据

        Args:
            ref: Artifact 引用对象

        Returns:
            存储的数据，如果不存在返回 None
        """
        pass

    @abstractmethod
    async def delete(self, ref: ArtifactRef) -> bool:
        """
        删除 artifact 数据

        Args:
            ref: Artifact 引用对象

        Returns:
            是否删除成功
        """
        pass

    @abstractmethod
    async def exists(self, ref: ArtifactRef) -> bool:
        """
        检查 artifact 是否存在

        Args:
            ref: Artifact 引用对象

        Returns:
            是否存在
        """
        pass

    # ========================================================================
    # 批量操作（可选，提供默认实现）
    # ========================================================================

    async def store_batch(self, items: List[tuple[ArtifactRef, Any]]) -> List[ArtifactRef]:
        """批量存储"""
        results = []
        for ref, data in items:
            result = await self.store(ref, data)
            results.append(result)
        return results

    async def load_batch(self, refs: List[ArtifactRef]) -> List[Optional[Any]]:
        """批量加载"""
        results = []
        for ref in refs:
            data = await self.load(ref)
            results.append(data)
        return results

    async def delete_batch(self, refs: List[ArtifactRef]) -> int:
        """批量删除，返回成功删除的数量"""
        count = 0
        for ref in refs:
            if await self.delete(ref):
                count += 1
        return count

    # ========================================================================
    # 清理操作（可选，提供默认实现）
    # ========================================================================

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        """
        清理过期的 artifacts

        Args:
            older_than_seconds: 清理时间阈值（秒），默认使用配置的 TTL

        Returns:
            清理的数量
        """
        # 默认实现：子类可以优化
        if older_than_seconds is None:
            older_than_seconds = self.config.ttl

        # 获取所有 artifacts
        all_refs = await self.list_all()
        now = datetime.now().timestamp()

        to_delete = [
            ref for ref in all_refs
            if now - ref.created_at > older_than_seconds
        ]

        count = await self.delete_batch(to_delete)
        if count > 0:
            self.logger.info(f"Cleaned up {count} old artifacts")

        return count

    async def cleanup_all(self) -> int:
        """
        清理所有 artifacts（会话结束时调用）

        Returns:
            清理的数量
        """
        all_refs = await self.list_all()
        return await self.delete_batch(all_refs)

    # ========================================================================
    # 查询操作（可选，提供默认实现）
    # ========================================================================

    async def list_all(self) -> List[ArtifactRef]:
        """
        列出所有 artifacts

        Returns:
            所有 ArtifactRef 列表
        """
        # 默认实现：子类应该优化
        raise NotImplementedError(f"{self.__class__.__name__} does not support listing")

    async def get_stats(self) -> Dict[str, Any]:
        """
        获取存储统计信息

        Returns:
            统计信息字典
        """
        all_refs = await self.list_all()
        total_size = sum(ref.size for ref in all_refs)

        return {
            "storage_type": self.config.storage_type.value,
            "session_id": self.session_id,
            "total_count": len(all_refs),
            "total_size": total_size,
        }

    # ========================================================================
    # 生命周期管理（可选）
    # ========================================================================

    async def initialize(self) -> None:
        """初始化存储后端（创建表、目录等）"""
        pass

    async def shutdown(self) -> None:
        """关闭存储后端（清理资源）"""
        pass

    # ========================================================================
    # 健康检查（可选）
    # ========================================================================

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        return True
