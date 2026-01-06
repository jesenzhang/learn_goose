# src/goose/server/repositories.py
import json
import logging

from goose.persistence import BaseRepository,TableSpec,with_table
from goose.server.routers import trigger
from .types import Trigger,TriggerType
from typing import List
import time

logger = logging.getLogger("goose.app.trigger.repo")

TRIGGER_SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id TEXT PRIMARY KEY,
    type TEXT,
    workflow_id TEXT,
    user_id TEXT, 
    enabled INTEGER DEFAULT 1,
    config TEXT,        -- JSON
    input_mapping TEXT, -- JSON
    created_at REAL,
    updated_at REAL
);
"""

@with_table(name="triggers", sql=TRIGGER_SCHEMA ,model=Trigger,pk="id",priority=0,attr_name="trigger_spec")
class TriggerRepository(BaseRepository):
    async def get(self, trigger_id: str) -> Trigger:
        return await self._get(Trigger, trigger_id)
    
    async def create(self, trigger: Trigger) -> Trigger:
        await self._insert(Trigger, trigger)
    
    async def update_by_id(self, trigger_id:str, **kwargs) -> Trigger:
        await self._update_by(Trigger, filters={"id": trigger_id}, **kwargs)
        return trigger
    
    async def delete(self, trigger_id: str) -> Trigger:
        await self._delete_by(Trigger, filters={"id": trigger_id})
    
    async def list(self, filters: dict = None) -> List[Trigger]:
        return await self._find(Trigger, filters=filters)
    
    async def get_active_triggers(self, workflow_id: str = None) -> List[Trigger]:
        """查询激活的 triggers"""
        try:
            # 1. 基础筛选条件：启用状态
            filters = {"enabled": True}
            
            # 2. 可选：按工作流筛选
            if workflow_id:
                filters["workflow_id"] = workflow_id
                
            # 3. 执行查询
            # 这里 filters={"enabled": True} 是完美的 Pythonic 写法
            return await self._find(Trigger, filters=filters)
        except Exception as e:
            logger.error(f"Failed to get active triggers: {e}")
            raise
    
    async def list_active(self) -> List[Trigger]:
        """加载所有启用的触发器"""
        try:
            triggers: List[Trigger] = await self._find(Trigger, filters={"enabled": True})
            return triggers
        except Exception as e:
            logger.error(f"Failed to list active triggers: {e}")
            raise
       
    async def toggle_trigger(self, trigger_id: str, enable: bool):
        """开关 trigger"""
        try:
            await self._update_by(
                Trigger,
                filters={"id": trigger_id},
                enabled=enable, # 直接传 bool 即可
                updated_at=time.time()
            )
        except Exception as e:
            logger.error(f"Failed to toggle trigger {trigger_id}: {e}")
            raise
        
    async def save(self, trigger: Trigger):
        """Upsert 触发器"""
        try:    
            await self._upsert(Trigger,trigger)
        except Exception as e:
            logger.error(f"Failed to save trigger {trigger.id}: {e}")
            raise
