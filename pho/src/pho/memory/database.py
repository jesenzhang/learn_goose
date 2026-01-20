"""
Database Storage - SQLite 数据库存储实现

基于 SessionStorage 的设计：
- 连接池
- 事务管理
- Schema 版本控制
- 会话隔离
"""

import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from .base import ArtifactStorage, ArtifactRef, StorageConfig, StorageType
from .registry import register_storage

from ...db import get_db

logger = logging.getLogger(__name__)


class DatabaseStorageConfig(StorageConfig):
    """数据库存储配置"""

    def __init__(
        self,
        table_name: str = "artifacts",
        ttl: int = 86400,
        **kwargs
    ):
        super().__init__(storage_type=StorageType.DATABASE, **kwargs)
        self.table_name = table_name
        self.ttl = ttl


@register_storage(StorageType.DATABASE, DatabaseStorageConfig)
class DatabaseStorage(ArtifactStorage):
    """
    SQLite 数据库存储实现

    特性：
    - 持久化存储
    - 事务安全
    - 连接池复用
    - 自动清理过期数据
    """

    # 创建表的 SQL
    CREATE_TABLE_SQL = """
        CREATE TABLE IF NOT EXISTS {table_name} (
            session_id TEXT NOT NULL,
            artifact_id TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            artifact_text TEXT,
            artifact_size INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            storage_backend TEXT,
            metadata TEXT,
            PRIMARY KEY (session_id, artifact_id)
        )
    """

    # 创建索引的 SQL
    CREATE_INDEX_SQL = """
        CREATE INDEX IF NOT EXISTS idx_{table_name}_created
        ON {table_name}(created_at DESC)
    """

    CREATE_INDEX_SESSION_SQL = """
        CREATE INDEX IF NOT EXISTS idx_{table_name}_session
        ON {table_name}(session_id, created_at DESC)
    """

    def __init__(self, config: DatabaseStorageConfig, session_id: str):
        super().__init__(config, session_id)
        self.table_name = config.table_name
        self._db = get_db()
        self._initialized = False

    async def initialize(self) -> None:
        """初始化数据库表"""
        if self._initialized:
            return

        try:
            # 获取连接并创建表
            with self._db._transaction() as conn:
                conn.execute(self.CREATE_TABLE_SQL.format(table_name=self.table_name))
                conn.execute(self.CREATE_INDEX_SQL.format(table_name=self.table_name))
                conn.execute(self.CREATE_INDEX_SESSION_SQL.format(table_name=self.table_name))

            self._initialized = True
            self.logger.debug(f"Initialized database storage table: {self.table_name}")
        except Exception as e:
            self.logger.error(f"Failed to initialize database storage: {e}")
            raise

    async def store(self, ref: ArtifactRef, data: Any) -> ArtifactRef:
        """存储到数据库"""
        await self.initialize()

        # 序列化数据
        data_json = json.dumps(data, ensure_ascii=False)
        storage_backend = ref.metadata.get("storage_backend", "database")

        try:
            with self._db._transaction() as conn:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (session_id, artifact_id, artifact_type, artifact_text,
                     artifact_size, data_json, created_at, storage_backend, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.session_id,
                        ref.id,
                        ref.type,
                        ref.text,
                        ref.size,
                        data_json,
                        ref.created_at,
                        storage_backend,
                        json.dumps(ref.metadata, ensure_ascii=False),
                    )
                )

            self.logger.debug(f"Stored artifact {ref.id} in database")
            return ref

        except Exception as e:
            self.logger.error(f"Failed to store artifact {ref.id}: {e}")
            raise

    async def load(self, ref: ArtifactRef) -> Optional[Any]:
        """从数据库加载"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                row = conn.execute(
                    f"SELECT data_json FROM {self.table_name} WHERE session_id = ? AND artifact_id = ?",
                    (self.session_id, ref.id)
                ).fetchone()

                if row:
                    return json.loads(row[0])

            return None

        except Exception as e:
            self.logger.error(f"Failed to load artifact {ref.id}: {e}")
            return None

    async def delete(self, ref: ArtifactRef) -> bool:
        """从数据库删除"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                result = conn.execute(
                    f"DELETE FROM {self.table_name} WHERE session_id = ? AND artifact_id = ?",
                    (self.session_id, ref.id)
                )

                deleted = result.rowcount > 0
                if deleted:
                    self.logger.debug(f"Deleted artifact {ref.id} from database")

                return deleted

        except Exception as e:
            self.logger.error(f"Failed to delete artifact {ref.id}: {e}")
            return False

    async def exists(self, ref: ArtifactRef) -> bool:
        """检查是否存在"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                row = conn.execute(
                    f"SELECT 1 FROM {self.table_name} WHERE session_id = ? AND artifact_id = ? LIMIT 1",
                    (self.session_id, ref.id)
                ).fetchone()

                return row is not None

        except Exception as e:
            self.logger.error(f"Failed to check artifact existence {ref.id}: {e}")
            return False

    async def list_all(self) -> List[ArtifactRef]:
        """列出当前会话的所有 artifacts"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                rows = conn.execute(
                    f"SELECT artifact_id, artifact_type, artifact_text,artifact_size, created_at, storage_backend, metadata FROM {self.table_name} WHERE session_id = ? ORDER BY created_at DESC",
                    (self.session_id,)
                ).fetchall()

                return [
                    ArtifactRef(
                        id=row[0],
                        type=row[1],
                        text=row[2],
                        size=row[3],
                        storage_type=StorageType.DATABASE,
                        created_at=row[4],
                        metadata=json.loads(row[6]) if row[6] else {},
                    )
                    for row in rows
                ]

        except Exception as e:
            self.logger.error(f"Failed to list artifacts: {e}")
            return []

    async def cleanup_old(self, older_than_seconds: Optional[int] = None) -> int:
        """清理过期的 artifacts"""
        await self.initialize()

        if older_than_seconds is None:
            older_than_seconds = self.config.ttl

        threshold = datetime.now().timestamp() - older_than_seconds

        try:
            with self._db._transaction() as conn:
                result = conn.execute(
                    f"DELETE FROM {self.table_name} WHERE session_id = ? AND created_at < ?",
                    (self.session_id, threshold)
                )

                count = result.rowcount
                if count > 0:
                    self.logger.info(f"Cleaned up {count} old artifacts from database")

                return count

        except Exception as e:
            self.logger.error(f"Failed to cleanup old artifacts: {e}")
            return 0

    async def cleanup_all(self) -> int:
        """清理当前会话的所有 artifacts"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                result = conn.execute(
                    f"DELETE FROM {self.table_name} WHERE session_id = ?",
                    (self.session_id,)
                )

                count = result.rowcount
                if count > 0:
                    self.logger.info(f"Cleaned up all {count} artifacts from database")

                return count

        except Exception as e:
            self.logger.error(f"Failed to cleanup all artifacts: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        await self.initialize()

        try:
            with self._db._transaction() as conn:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) as count,
                           SUM(artifact_size) as total_size,
                           MIN(created_at) as oldest_created,
                           MAX(created_at) as newest_created
                    FROM {self.table_name}
                    WHERE session_id = ?
                    """,
                    (self.session_id,)
                ).fetchone()

                if row:
                    return {
                        "storage_type": StorageType.DATABASE.value,
                        "session_id": self.session_id,
                        "total_count": row[0],
                        "total_size": row[1] or 0,
                        "oldest_created": row[2],
                        "newest_created": row[3],
                        "table_name": self.table_name,
                    }

            return {
                "storage_type": StorageType.DATABASE.value,
                "session_id": self.session_id,
                "total_count": 0,
                "total_size": 0,
            }

        except Exception as e:
            self.logger.error(f"Failed to get stats: {e}")
            return {}
