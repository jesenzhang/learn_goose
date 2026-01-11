import json
import time
from abc import ABC, abstractmethod
from typing import Optional, Dict, List
from pho.persistence import BaseRepository,with_table,TableSpec
from pho.registry import BaseRegistry
from .types import ResourceMetadata, ResourceKind, ResourceScope
from pydantic import BaseModel,Field
from datetime import datetime,timezone

# --- Trait (Interface) ---
RESOURCE_TABLE_SCHEMA = """
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
        """
RESOURCE_INDEX_SCHEMA = """
        CREATE INDEX IF NOT EXISTS idx_resources_owner ON resources(owner_id);
        """

class ResourceEntity(BaseModel):
    id: str = Field(..., description="Resource ID")
    owner_id: str = Field(..., description="Resource owner ID")
    kind: ResourceKind = Field(..., description="Resource kind")
    scope: ResourceScope = Field(..., description="Resource scope")
    provider: str = Field(..., description="Resource provider")
    config: dict = Field(..., description="Resource config")
    # created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)
    
# def register_resource_schema(pm: PersistenceManager):
#     pm.register_schema(RESOURCE_TABLE_SCHEMA)
#     pm.register_schema(RESOURCE_INDEX_SCHEMA)
        
class ResourceStore(ABC):
    """
    [Trait] 资源存储接口
    定义了底层的 CRUD 能力。
    """
    @abstractmethod
    async def get_metadata(self, resource_id: str, owner_id: str = None) -> Optional[ResourceMetadata]:
        pass

    @abstractmethod
    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        pass

# --- Implementation: System (Memory) ---
# 系统资源存储是内存操作，不需要适配 SQLAlchemy，保持原样即可

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
        return self._registry.get(resource_id)

    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        self.register(meta)

# --- Implementation: User (Database) ---


@with_table(name='resources',model=ResourceEntity,sql=[RESOURCE_TABLE_SCHEMA,RESOURCE_INDEX_SCHEMA],pk='id',priority=0,attr_name='resource_spec')
class UserResourceStore(BaseRepository,ResourceStore):
    """
    用户自定义资源 (SQL)
    适配 SQLAlchemy 风格 (:param_name)
    """
    
    async def get_metadata(self, resource_id: str, owner_id: str = None) -> Optional[ResourceMetadata]:
        
        entities:List[ResourceEntity] = await self._find(ResourceEntity,filters= {"id": resource_id, "owner_id": owner_id})
        if entities:
            e = entities[0]
            return ResourceMetadata(
                id=e.id,
                kind=ResourceKind(e.kind),
                scope=ResourceScope(e.scope),
                provider=e.provider,
                config=e.config
            )
        # if not owner_id:
        #     raise ValueError("UserResourceStore requires owner_id query parameter.")

        # # [Change] 使用 :param 命名参数风格
        # sql = "SELECT * FROM resources WHERE id = :id AND owner_id = :owner_id"
        
        # # [Change] 传入字典参数
        # row = await self.pm.fetch_one(sql, {"id": resource_id, "owner_id": owner_id})
        
        # if row:
        #     try:
        #         return ResourceMetadata(
        #             id=row["id"],
        #             kind=ResourceKind(row["kind"]),
        #             scope=ResourceScope(row["scope"]),
        #             provider=row["provider"],
        #             config=json.loads(row["config_json"])
        #         )
        #     except Exception as e:
        #         # 实际生产中建议使用 logging
        #         print(f"Error parsing resource {resource_id}: {e}")
        #         return None
        # return None

    async def save_metadata(self, meta: ResourceMetadata, owner_id: str = None) -> None:
        if not owner_id:
            raise ValueError("UserResourceStore requires owner_id for saving.")

        now = time.time()
        
        
        self._upsert(ResourceEntity,ResourceEntity(
            id=meta.id,
            owner_id=owner_id,
            kind=meta.kind.value,
            scope=meta.scope.value,
            provider=meta.provider,
            config=meta.config,
            created_at=now,
            updated_at=now
        ))
        
        # # [Change] 使用 :param 风格
        # # 注意：INSERT OR REPLACE 是 SQLite 特有语法。
        # # 如果要兼容 Postgres，需要改写为标准的 Upsert (ON CONFLICT DO UPDATE)
        # # 这里为了保持简单，沿用 SQLite 语法
        # sql = """
        # INSERT OR REPLACE INTO resources 
        # (id, owner_id, kind, scope, provider, config_json, created_at, updated_at)
        # VALUES (:id, :owner_id, :kind, :scope, :provider, :config_json, :created_at, :updated_at)
        # """
        
        # # [Change] 传入字典参数
        # params = {
        #     "id": meta.id,
        #     "owner_id": owner_id,
        #     "kind": meta.kind.value,
        #     "scope": meta.scope.value,
        #     "provider": meta.provider,
        #     "config_json": json.dumps(meta.config),
        #     "created_at": now, # 简化处理，每次都更新创建时间（Replace语义）
        #     "updated_at": now
        # }
        
        # await self.pm.execute(sql, params)