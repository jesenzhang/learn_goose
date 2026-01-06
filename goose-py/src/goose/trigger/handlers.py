# src/goose/app/trigger/handlers.py
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Awaitable
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from goose.trigger.types import Trigger, TriggerType

logger = logging.getLogger(__name__)

class ITriggerHandler(ABC):
    """触发器处理策略接口"""
    @abstractmethod
    async def register(self, trigger: Trigger):
        """将触发器注册到底层系统 (如 Scheduler)"""
        pass
    
    @abstractmethod
    async def unregister(self, trigger_id: str):
        """从底层系统移除"""
        pass

class CronHandler(ITriggerHandler):
    def __init__(self, scheduler: AsyncIOScheduler, callback: Callable[[Trigger, Dict], Awaitable[None]]):
        self.scheduler = scheduler
        self.callback = callback

    async def register(self, trigger: Trigger):
        cron_exp = trigger.config.get("cron")
        if not cron_exp:
            logger.warning(f"Trigger {trigger.id} missing cron expression")
            return

        try:
            # 使用 replace_existing=True 确保更新时覆盖旧任务
            self.scheduler.add_job(
                self._job_wrapper,
                'cron',
                id=trigger.id,
                replace_existing=True,
                args=[trigger],
                **self._parse_cron(cron_exp)
            )
            logger.debug(f"Registered cron job: {trigger.id} -> {cron_exp}")
        except Exception as e:
            logger.error(f"Failed to schedule trigger {trigger.id}: {e}")

    async def unregister(self, trigger_id: str):
        if self.scheduler.get_job(trigger_id):
            self.scheduler.remove_job(trigger_id)
            logger.debug(f"Removed cron job: {trigger_id}")

    async def _job_wrapper(self, trigger: Trigger):
        """Cron 触发时的回调包装"""
        # 可以在这里加锁或去重
        await self.callback(trigger, {"timestamp": time.time(), "source": "cron"})

    def _parse_cron(self, exp: str) -> Dict[str, str]:
        """简单的 Cron 解析，建议生产环境使用标准库如 croniter"""
        parts = exp.split()
        if len(parts) != 5: return {}
        return {
            "minute": parts[0], "hour": parts[1], 
            "day": parts[2], "month": parts[3], "day_of_week": parts[4]
        }

class WebhookHandler(ITriggerHandler):
    def __init__(self, callback: Callable[[Trigger, Dict], Awaitable[None]]):
        self.callback = callback

    async def register(self, trigger: Trigger):
        # Webhook 是被动的，不需要向 Scheduler 注册什么
        # 这里主要是在 Manager 的 active_triggers 字典里占个位
        pass

    async def unregister(self, trigger_id: str):
        pass

    async def handle_request(self, trigger: Trigger, request: Request):
        """处理实际的 HTTP 请求"""
        # 1. 提取 Body
        try:
            body = await request.json()
        except:
            body = {}
            
        # 2. 鉴权 (简单的 Token 验证)
        expected_token = trigger.config.get("token")
        auth_header = request.headers.get("Authorization")
        if expected_token and auth_header != expected_token:
            raise ValueError("Invalid Webhook Token")

        # 3. 触发回调
        await self.callback(trigger, body)