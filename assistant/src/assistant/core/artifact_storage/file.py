"""
File Storage - 文件系统存储实现

基于 Config 文件存储和 LocalStorage 的设计：
- 会话隔离目录
- JSON 序列化
- 可选压缩
"""

import os
import json
import gzip
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime

from .base import ArtifactStorage, ArtifactRef, StorageConfig, StorageType
from .registry import register_storage

logger = logging.getLogger(__name__)


class FileStorageConfig(StorageConfig):
    """文件存储配置"""

    def __init__(
        self,
        base_dir: str = "artifacts",
        compression: bool = False,
        ttl: int = 86400,
        **kwargs
    ):
        super().__init__(storage_type=StorageType.FILE, **kwargs)
        self.base_dir = base_dir
        self.compression = compression
        self.ttl = ttl


@register_storage(StorageType.FILE, FileStorageConfig)
class FileStorage(ArtifactStorage):
    """
    文件系统存储实现

    特性：
    - 持久化存储
    - 会话隔离（artifacts/{session_id}/）
    - 可选 gzip 压缩
    - 进程重启后仍存在
    """

    def __init__(self, config: FileStorageConfig, session_id: str):
        super().__init__(config, session_id)
        self.base_dir = Path(config.base_dir)
        self.session_dir = self.base_dir / session_id
        self.compression = config.compression

    async def initialize(self) -> None:
        """创建会话目录"""
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.logger.debug(f"Initialized file storage at {self.session_dir}")

    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        """存储到文件"""
        await self.initialize()

        # 生成文件路径
        file_path = self._get_file_path(ref.id)

        # 序列化数据
        json_data = json.dumps(data, ensure_ascii=False)
        data_bytes = json_data.encode('utf-8')

        # 写入文件
        if self.compression:
            compressed = gzip.compress(data_bytes)
            file_path = file_path.with_suffix('.json.gz')
            with open(file_path, 'wb') as f:
                f.write(compressed)
            self.logger.debug(f"Stored compressed artifact {ref.id}: {len(data_bytes)} -> {len(compressed)} bytes")
        else:
            with open(file_path, 'wb') as f:
                f.write(data_bytes)
            self.logger.debug(f"Stored artifact {ref.id} to file: {len(data_bytes)} bytes")

        # 更新引用
        ref.storage_key = str(file_path)
        ref.metadata["file_path"] = str(file_path)
        if self.compression:
            ref.metadata["compressed"] = True

        return ref

    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        """从文件加载"""
        file_path = Path(ref.storage_key or self._get_file_path(ref.id))

        # 处理压缩文件
        if ref.metadata.get("compressed") or self.compression:
            file_path = file_path.with_suffix('.json.gz')

        if not file_path.exists():
            self.logger.warning(f"Artifact file not found: {file_path}")
            return None

        try:
            # 读取文件
            if ref.metadata.get("compressed") or self.compression:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    json_data = f.read()
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json_data = f.read()

            return json.loads(json_data)
        except Exception as e:
            self.logger.error(f"Failed to load artifact {ref.id}: {e}")
            return None

    async def delete(self, ref: ArtifactRef) -> bool:
        """删除文件"""
        file_path = Path(ref.storage_key or self._get_file_path(ref.id))

        # 处理压缩文件
        if ref.metadata.get("compressed") or self.compression:
            file_path = file_path.with_suffix('.json.gz')

        if not file_path.exists():
            return False

        try:
            file_path.unlink()
            self.logger.debug(f"Deleted artifact file: {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to delete artifact {ref.id}: {e}")
            return False

    async def exists(self, ref: ArtifactRef) -> bool:
        """检查文件是否存在"""
        file_path = Path(ref.storage_key or self._get_file_path(ref.id))

        # 处理压缩文件
        if ref.metadata.get("compressed") or self.compression:
            file_path = file_path.with_suffix('.json.gz')

        return file_path.exists()

    async def list_all(self) -> List[ArtifactRef]:
        """列出所有 artifacts（从文件系统重建）"""
        await self.initialize()

        all_refs = []

        # 扫描会话目录
        if not self.session_dir.exists():
            return all_refs

        for file_path in self.session_dir.glob("artifact_*.json*"):
            try:
                # 从文件名提取 artifact ID
                # 文件名格式: artifact_{hash}_{id}.json
                parts = file_path.stem.split('_')
                if len(parts) >= 3:
                    artifact_id = parts[2]
                else:
                    continue

                # 获取文件信息
                stat = file_path.stat()
                ref = ArtifactRef(
                    id=artifact_id,
                    type="unknown",
                    text=f"Artifact from file",
                    size=stat.st_size,
                    storage_type=StorageType.FILE,
                    created_at=stat.st_ctime,
                    storage_key=str(file_path),
                )
                all_refs.append(ref)
            except Exception as e:
                self.logger.warning(f"Failed to parse artifact file {file_path}: {e}")

        return all_refs

    async def cleanup_all(self) -> int:
        """清理所有文件（删除会话目录）"""
        if not self.session_dir.exists():
            return 0

        count = len(list(self.session_dir.glob("*.json*")))

        try:
            import shutil
            shutil.rmtree(self.session_dir)
            self.logger.info(f"Removed session directory: {self.session_dir}")
            return count
        except Exception as e:
            self.logger.error(f"Failed to cleanup session directory: {e}")
            return 0

    def _get_file_path(self, artifact_id: str) -> Path:
        """生成 artifact 文件路径"""
        # 使用 hash 避免文件名冲突和长度问题
        hash_part = hashlib.md5(artifact_id.encode()).hexdigest()[:8]
        filename = f"artifact_{hash_part}_{artifact_id}.json"
        return self.session_dir / filename
