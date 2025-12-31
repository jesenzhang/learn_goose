import json
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from goose.persistence.manager import PersistenceManager
from .types import ResourceMetadata, ResourceKind, ResourceScope

# --- Trait (Interface) ---

class ResourceStore(ABC):
    """
    [Trait] 资源存储接口
    定义了底层的 CRUD 能力。
    注意：为了兼容 UserStore，接口中增加了 owner_id 参数。
    SystemStore 实现时可以忽略该参数。
    """
    @abstractmethod
    async def get_metadata(self, resource_id: str, owner_id: str = None) -> Optional[ResourceMetadata]:
        pass

    @abstractmethod
    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        pass

# --- Implementation: System (Memory) ---

class SystemResourceStore(ResourceStore):
    """
    系统内置资源 (Hardcoded / Config file)
    无状态，全局共享。
    """
    def __init__(self):
        self._registry: Dict[str, ResourceMetadata] = {}

    def register(self, meta: ResourceMetadata):
        # 强制标记为 SYSTEM 作用域
        meta.scope = ResourceScope.SYSTEM
        self._registry[meta.id] = meta

    async def get_metadata(self, resource_id: str, owner_id: str = None) -> Optional[ResourceMetadata]:
        # SystemStore 忽略 owner_id，因为它对所有人可见
        return self._registry.get(resource_id)

    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        self.register(meta)

# --- Implementation: User (Database) ---

class UserResourceStore(ResourceStore):
    """
    用户自定义资源 (SQL)
    [Stateless DAO] 不绑定具体用户，owner_id 必须在方法调用时传入。
    """
    def __init__(self, pm: PersistenceManager):
        self.pm = pm
        self._init_schema()

    def _init_schema(self):
        """
        [Schema Registration]
        定义 resources 表结构。
        """
        self.pm.register_schema("""
        CREATE TABLE IF NOT EXISTS resources (
            id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            scope TEXT NOT NULL,
            provider TEXT NOT NULL,
            config_json TEXT NOT NULL,
            created_at REAL,
            updated_at REAL
        );
        -- 加上 owner_id 索引，加速查询
        CREATE INDEX IF NOT EXISTS idx_resources_owner ON resources(owner_id);
        """)

    async def get_metadata(self, resource_id: str, owner_id: str = None) -> Optional[ResourceMetadata]:
        """
        查询用户资源。
        必须提供 owner_id，防止越权访问。
        """
        if not owner_id:
            raise ValueError("UserResourceStore requires owner_id query parameter.")

        sql = "SELECT * FROM resources WHERE id = ? AND owner_id = ?"
        row = await self.pm.fetch_one(sql, (resource_id, owner_id))
        
        if row:
            try:
                return ResourceMetadata(
                    id=row["id"],
                    kind=ResourceKind(row["kind"]),
                    scope=ResourceScope(row["scope"]),
                    provider=row["provider"],
                    config=json.loads(row["config_json"])
                )
            except Exception as e:
                # 容错：防止坏数据导致 Crash
                print(f"Error parsing resource {resource_id}: {e}")
                return None
        return None

    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        if not owner_id:
            raise ValueError("UserResourceStore requires owner_id for saving.")

        now = time.time()
        # Upsert Logic (SQLite Replace or Insert)
        sql = """
        INSERT OR REPLACE INTO resources 
        (id, owner_id, kind, scope, provider, config_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        await self.pm.execute(sql, (
            meta.id,
            owner_id,
            meta.kind.value,
            meta.scope.value,
            meta.provider,
            json.dumps(meta.config),
            now, # created_at (简化处理，Replace会重置时间)
            now  # updated_at
        ))