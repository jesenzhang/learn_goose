# src/goose/app/trigger/service.py
from typing import Dict, Any, List, Optional
from fastapi import Request

from goose.trigger.types import Trigger, TriggerType
from goose.trigger.repository import TriggerRepository
from goose.trigger.manager import TriggerManager

class TriggerService:
    """
    【职责】业务逻辑、数据持久化、通知 Manager
    """
    def __init__(self, manager: TriggerManager):
        # Service 依赖 Manager，用于通知状态变更
        self.manager = manager
        self.repo = TriggerRepository()

    async def create_trigger(self, workflow_id: str, type: TriggerType, config: Dict, input_mapping: Dict = None) -> Trigger:
        """[CRUD] 创建触发器"""
        # 1. 业务校验
        if type == TriggerType.SCHEDULE:
            if "cron" not in config:
                raise ValueError("Schedule trigger requires 'cron' config")
            # 这里还可以调用 croniter.is_valid(config['cron']) 进行校验

        # 2. 构建对象
        trigger = Trigger(
            workflow_id=workflow_id,
            type=type,
            config=config,
            input_mapping=input_mapping or {},
            enabled=True 
        )

        # 3. 存库
        await self.repo.create(trigger)

        # 4. 通知 Manager 热更新
        await self.manager.refresh_trigger(trigger.id)
        
        return trigger

    async def update_trigger(self, trigger_id: str, **kwargs) -> Optional[Trigger]:
        """[CRUD] 更新触发器"""
        # 1. 更新数据库
        # 假设 repo.update_by 返回受影响行数或对象
        await self.repo.update_by_id(trigger_id, **kwargs)
        
        # 2. 通知 Manager 热更新
        # Manager 会重新读取数据库，所以只需要告诉它 ID 即可
        await self.manager.refresh_trigger(trigger_id)
        
        return await self.repo.get(trigger_id)

    async def delete_trigger(self, trigger_id: str):
        """[CRUD] 删除触发器"""
        # 1. 删库
        await self.repo.delete(trigger_id)
        
        # 2. 通知 Manager
        # Manager 发现库里没了，会从 active_triggers 移除并取消 cron job
        await self.manager.refresh_trigger(trigger_id)

    async def toggle_trigger(self, trigger_id: str, enabled: bool):
        """[Action] 启用/禁用"""
        await self.repo.update_by_id(trigger_id, {"enabled": enabled})
        await self.manager.refresh_trigger(trigger_id)

    async def list_triggers(self, workflow_id: str = None) -> List[Trigger]:
        """[Query] 查询列表 - 只读操作不需要通知 Manager"""
        filters = {}
        if workflow_id:
            filters["workflow_id"] = workflow_id
        return await self.repo.list(filters)

    # --- Webhook Forwarding ---
    
    async def process_webhook(self, trigger_id: str, request: Request):
        """
        [Entry] API 层调用的入口
        Service 层只负责转发，具体的鉴权和处理交给 Manager (因为它有缓存)
        """
        # 可以在这里记录审计日志： "收到 Webhook 请求..."
        await self.manager.handle_webhook(trigger_id, request)