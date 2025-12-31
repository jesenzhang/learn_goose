from typing import Any, Dict, Optional
from .types import ResourceKind, ResourceMetadata
from .store import SystemResourceStore, UserResourceStore
from .builder import ResourceBuilder

class ResourceManager:
    """
    [Service] 资源管理器
    Context-aware: 绑定了当前的 user_id (owner_id)。
    """
    def __init__(
        self, 
        system_store: SystemResourceStore, 
        user_store: UserResourceStore,
        user_id: Optional[str] = None
    ):
        self.sys_store = system_store
        self.user_store = user_store
        self.user_id = user_id
        
        # Builder 注册表
        self._builders: Dict[str, ResourceBuilder] = {}

    def register_builder(self, kind: ResourceKind, builder: ResourceBuilder):
        self._builders[kind] = builder

    async def get_instance(self, resource_id: str) -> Any:
        # 1. 查找 Metadata
        meta = await self._get_metadata(resource_id)
        
        if not meta:
            raise ValueError(f"Resource not found: {resource_id}")

        # 2. 调度 Builder
        builder = self._builders.get(meta.kind)
        if builder:
            return await builder.build(meta)
        
        # 3. 没注册 Builder，返回原始数据
        return meta

    async def _get_metadata(self, resource_id: str) -> Optional[ResourceMetadata]:
        # 策略 1: 查用户私有资源 (必须有 user_id)
        if self.user_id:
            meta = await self.user_store.get_metadata(resource_id, owner_id=self.user_id)
            if meta: 
                return meta
        
        # 策略 2: 查系统资源 (无需 user_id)
        return await self.sys_store.get_metadata(resource_id)