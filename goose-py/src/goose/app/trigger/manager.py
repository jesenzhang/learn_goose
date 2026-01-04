import logging
import json
from typing import Dict, List, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from .repository import TriggerRepository
from goose.app.execution.service import ExecutionService
from .types import TriggerDefinition, TriggerType
from abc import ABC, abstractmethod

# 复用你提供的 Handler 代码 (CronHandler, WebhookHandler)
# 这里省略 Handler 的具体实现，假设它们已经定义在同一个文件或模块中 ...

logger = logging.getLogger("goose.server.trigger")

class ITriggerHandler(ABC):
    """Trigger 处理策略基类"""
    @abstractmethod
    async def register(self, trigger: TriggerDefinition): ...
    
    @abstractmethod
    async def unregister(self, trigger_id: str): ...


class TriggerManager:
    def __init__(self, execution_service: ExecutionService):
        self.exec_service = execution_service
        self.repo = TriggerRepository() # 直接使用 Repo

        self.cron_scheduler = AsyncIOScheduler()
        self.active_triggers: Dict[str, TriggerDefinition] = {}

        # 策略注册
        self.handlers: Dict[str, ITriggerHandler] = {
            TriggerType.SCHEDULE: CronHandler(self.cron_scheduler, self._dispatch),
            TriggerType.WEBHOOK: WebhookHandler(self._dispatch),
        }

    async def start(self):
        """系统启动时调用"""
        logger.info("⏰ Starting Trigger Manager...")
        if not self.cron_scheduler.running:
            self.cron_scheduler.start()
        
        await self.load_triggers()

    async def stop(self):
        """系统关闭时调用"""
        if self.cron_scheduler.running:
            self.cron_scheduler.shutdown()
        logger.info("⏰ Trigger Manager Stopped.")

    async def load_triggers(self):
        """[Warmup] 从数据库加载所有触发器"""
        triggers = await self.repo.list_active()
        await self.sync_triggers(triggers)
        logger.info(f"⏰ Loaded {len(self.active_triggers)} active triggers.")

    async def sync_triggers(self, triggers: List[TriggerDefinition]):
        """同步逻辑 (保持你原有的 Diff 逻辑不变)"""
        # ... (完全复用你的代码) ...
        # 这里为了演示简洁，只写注册部分
        for t in triggers:
            handler = self.handlers.get(t.type)
            if handler:
                await handler.register(t)
                self.active_triggers[t.id] = t

    async def _dispatch(self, trigger: TriggerDefinition, raw_data: Dict[str, Any]):
        """核心调度逻辑"""
        logger.info(f"⚡ Trigger Fired: {trigger.id} -> Workflow: {trigger.workflow_id}")

        try:
            # 1. 映射输入
            inputs = self._map_inputs(trigger.input_mapping, raw_data)

            # 2. 调用 Goose 的 ExecutionService
            # 注意：ExecutionService.run_workflow 已经是异步并会将任务放入后台
            run_id = await self.exec_service.run_workflow(
                wf_id=trigger.workflow_id,
                inputs=inputs
                # 可以扩展 run_workflow 接口，传入 source 信息用于审计
            )
            logger.info(f"   -> 🚀 Workflow Started: {run_id}")

        except Exception as e:
            logger.error(f"❌ Trigger Dispatch Failed: {e}", exc_info=True)

    def _map_inputs(self, mapping: Dict[str, str], raw_data: Dict) -> Dict:
        """复用你的映射逻辑"""
        if not mapping: return raw_data
        result = {}
        for target, source in mapping.items():
            # 这里可以引入 jsonpath-ng 来支持更复杂的 'body.data.value' 提取
            result[target] = raw_data.get(source) # 简单实现
        return result

    # --- Webhook 路由辅助 ---
    async def handle_webhook(self, trigger_id: str, request: Any):
        """供 API 层调用"""
        trigger = self.active_triggers.get(trigger_id)
        if not trigger or trigger.type != TriggerType.WEBHOOK:
            raise ValueError("Webhook not found or inactive")
        
        handler = self.handlers[TriggerType.WEBHOOK]
        await handler.handle_request(trigger, request)




# --- Implementations (保持不变) ---

class CronHandler(ITriggerHandler):
    def __init__(self, scheduler: AsyncIOScheduler, callback):
        self.scheduler = scheduler
        self.callback = callback

    async def register(self, trigger: TriggerDefinition):
        cron_exp = trigger.config.get("cron")
        if not cron_exp: return

        try:
            self.scheduler.add_job(
                self._job_wrapper,
                'cron',
                id=trigger.id,
                replace_existing=True,
                args=[trigger],
                **self._parse_cron(cron_exp) 
            )
        except Exception as e:
            logger.error(f"Invalid cron expression for {trigger.id}: {e}")

    async def unregister(self, trigger_id: str):
        if self.scheduler.get_job(trigger_id):
            self.scheduler.remove_job(trigger_id)

    async def _job_wrapper(self, trigger: TriggerDefinition):
        """Cron Job 回调包装"""
        import time
        await self.callback(trigger, {"timestamp": time.time(), "source": "cron"})

    def _parse_cron(self, exp: str) -> Dict:
        parts = exp.split()
        if len(parts) != 5: return {}
        return {
            "minute": parts[0], "hour": parts[1], 
            "day": parts[2], "month": parts[3], "day_of_week": parts[4]
        }

class WebhookHandler(ITriggerHandler):
    def __init__(self, callback):
        self.callback = callback

    async def register(self, trigger: TriggerDefinition):
        pass

    async def unregister(self, trigger_id: str):
        pass

    async def handle_request(self, trigger: TriggerDefinition, request: Request):
        try:
            body = await request.json()
        except:
            body = {}
            
        auth_header = request.headers.get("Authorization")
        expected_token = trigger.config.get("token")
        if expected_token and auth_header != expected_token:
            raise ValueError("Invalid Webhook Token")

        await self.callback(trigger, body)