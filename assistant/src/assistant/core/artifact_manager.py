"""
Artifact Manager - 分层存储管理器

策略：
1. 小数据 (<10KB) -> 内存 (LRU缓存)
2. 中等数据 (10KB-100KB) -> 压缩后内存
3. 大数据 (>100KB) -> 临时文件

自动清理：
- LRU 淘汰策略
- 定期清理过期数据
- 会话结束时清理所有文件
"""

import os
import json
import gzip
import hashlib
import logging
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ArtifactRef:
    """Artifact 引用，存储在 shared_memory 中"""
    id: str
    type: str
    text: str
    size: int  # 原始数据大小（字节）
    storage: str  # 'memory', 'compressed', 'file'
    path: Optional[str] = None  # 文件存储路径（仅 storage='file' 时）
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().timestamp()


class ArtifactManager:
    """
    Artifact 数据管理器

    特性：
    - 分层存储（内存/压缩/文件）
    - LRU 自动淘汰
    - 会话隔离
    - 自动清理
    """

    # 存储阈值（字节）
    SMALL_SIZE_LIMIT = 10 * 1024      # 10KB
    LARGE_SIZE_LIMIT = 100 * 1024     # 100KB

    # LRU 配置
    MAX_MEMORY_ITEMS = 50             # 最大内存条目数
    MAX_TOTAL_MEMORY = 50 * 1024 * 1024  # 最大总内存 50MB

    # 清理配置
    CLEANUP_INTERVAL = 3600           # 清理间隔（秒）
    ARTIFACT_TTL = 86400              # Artifact 生存时间（24小时）

    def __init__(self, session_id: str, base_dir: str = "artifacts"):
        self.session_id = session_id
        self.base_dir = Path(base_dir)
        self.session_dir = self.base_dir / session_id

        # 内存存储：id -> (data, access_time)
        self._memory_cache: Dict[str, tuple] = {}

        # 索引：id -> ArtifactRef（用于 LRU 追踪）
        self._index: Dict[str, ArtifactRef] = {}

        # 创建会话目录
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 启动时清理旧文件
        self._cleanup_session_dir()

    def store(self, aid: str, artifact_type: str, data: Any, text: str = "") -> ArtifactRef:
        """
        存储 artifact，返回引用对象

        Args:
            aid: Artifact ID
            artifact_type: 数据类型
            data: 原始数据
            text: 文本描述

        Returns:
            ArtifactRef 对象（存储在 shared_memory 中）
        """
        # 序列化数据
        json_data = json.dumps(data, ensure_ascii=False)
        size = len(json_data.encode('utf-8'))

        # 决定存储方式
        if size <= self.SMALL_SIZE_LIMIT:
            storage = "memory"
            ref = ArtifactRef(id=aid, type=artifact_type, text=text, size=size, storage=storage)
            self._memory_cache[aid] = (data, datetime.now().timestamp())
        elif size <= self.LARGE_SIZE_LIMIT:
            storage = "compressed"
            compressed = gzip.compress(json_data.encode('utf-8'))
            ref = ArtifactRef(id=aid, type=artifact_type, text=text, size=size, storage=storage)
            self._memory_cache[aid] = (compressed, datetime.now().timestamp())
            logger.debug(f"Compressed artifact {aid}: {size} -> {len(compressed)} bytes")
        else:
            storage = "file"
            file_path = self._get_file_path(aid)
            # 写入文件
            with open(file_path, 'wb') as f:
                f.write(json_data.encode('utf-8'))
            ref = ArtifactRef(
                id=aid,
                type=artifact_type,
                text=text,
                size=size,
                storage=storage,
                path=str(file_path)
            )
            logger.info(f"Stored artifact {aid} to file: {size} bytes")

        # 更新索引
        self._index[aid] = ref

        # 检查是否需要清理
        self._maybe_cleanup()

        return ref

    def load(self, aid: str) -> Optional[Any]:
        """
        加载 artifact 数据

        Args:
            aid: Artifact ID

        Returns:
            原始数据，如果不存在返回 None
        """
        ref = self._index.get(aid)
        if not ref:
            return None

        # 更新访问时间（用于 LRU）
        if aid in self._memory_cache:
            data, _ = self._memory_cache[aid]
            self._memory_cache[aid] = (data, datetime.now().timestamp())

        # 根据存储方式加载
        if ref.storage == "memory":
            return self._memory_cache[aid][0]
        elif ref.storage == "compressed":
            compressed, _ = self._memory_cache[aid]
            json_data = gzip.decompress(compressed).decode('utf-8')
            return json.loads(json_data)
        elif ref.storage == "file":
            try:
                with open(ref.path, 'r', encoding='utf-8') as f:
                    json_data = f.read()
                return json.loads(json_data)
            except FileNotFoundError:
                logger.warning(f"Artifact file not found: {ref.path}")
                return None

        return None

    def delete(self, aid: str) -> bool:
        """删除指定的 artifact"""
        ref = self._index.get(aid)
        if not ref:
            return False

        # 从内存删除
        self._memory_cache.pop(aid, None)

        # 删除文件
        if ref.storage == "file" and ref.path:
            try:
                os.remove(ref.path)
                logger.debug(f"Deleted artifact file: {ref.path}")
            except FileNotFoundError:
                pass

        # 从索引删除
        del self._index[aid]

        return True

    def cleanup_old(self, older_than: timedelta = None) -> int:
        """
        清理过期的 artifacts

        Args:
            older_than: 清理时间阈值，默认使用 ARTIFACT_TTL

        Returns:
            清理的数量
        """
        if older_than is None:
            older_than = timedelta(seconds=self.ARTIFACT_TTL)

        now = datetime.now().timestamp()
        to_delete = []

        for aid, ref in self._index.items():
            if now - ref.created_at > older_than.total_seconds():
                to_delete.append(aid)

        for aid in to_delete:
            self.delete(aid)

        if to_delete:
            logger.info(f"Cleaned up {len(to_delete)} old artifacts")

        return len(to_delete)

    def cleanup_all(self) -> int:
        """清理所有 artifacts（会话结束时调用）"""
        count = len(self._index)
        for aid in list(self._index.keys()):
            self.delete(aid)

        # 清理会话目录
        try:
            import shutil
            if self.session_dir.exists():
                shutil.rmtree(self.session_dir)
                logger.info(f"Removed session directory: {self.session_dir}")
        except Exception as e:
            logger.warning(f"Failed to remove session directory: {e}")

        return count

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        total_size = sum(ref.size for ref in self._index.values())
        memory_items = sum(1 for ref in self._index.values() if ref.storage == "memory")
        compressed_items = sum(1 for ref in self._index.values() if ref.storage == "compressed")
        file_items = sum(1 for ref in self._index.values() if ref.storage == "file")

        return {
            "total_count": len(self._index),
            "total_size": total_size,
            "memory_items": memory_items,
            "compressed_items": compressed_items,
            "file_items": file_items,
            "session_dir": str(self.session_dir)
        }

    def _get_file_path(self, aid: str) -> Path:
        """生成 artifact 文件路径"""
        # 使用 hash 避免文件名冲突
        hash_part = hashlib.md5(aid.encode()).hexdigest()[:8]
        return self.session_dir / f"artifact_{hash_part}.json"

    def _cleanup_session_dir(self):
        """启动时清理会话目录中的孤立文件"""
        if not self.session_dir.exists():
            return

        # 获取所有有效的 artifact 文件
        valid_files = set()
        for ref in self._index.values():
            if ref.storage == "file" and ref.path:
                valid_files.add(Path(ref.path).name)

        # 删除无效文件
        for file_path in self.session_dir.glob("artifact_*.json"):
            if file_path.name not in valid_files:
                try:
                    file_path.unlink()
                    logger.debug(f"Cleaned up orphaned file: {file_path}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup file {file_path}: {e}")

    def _maybe_cleanup(self):
        """检查并执行 LRU 清理"""
        total_items = len(self._index)
        total_memory = sum(ref.size for ref in self._index.values())

        # 检查是否超过限制
        if total_items > self.MAX_MEMORY_ITEMS or total_memory > self.MAX_TOTAL_MEMORY:
            # 按 LRU 排序
            sorted_items = sorted(
                self._index.items(),
                key=lambda x: x[1].created_at
            )

            # 删除最旧的 20%
            to_remove = int(len(sorted_items) * 0.2) + 1
            for aid, _ in sorted_items[:to_remove]:
                self.delete(aid)

            logger.info(f"LRU cleanup: removed {to_remove} artifacts")
