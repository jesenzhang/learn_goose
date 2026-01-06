# src/goose/app/trigger/manager.py
import logging
from typing import Dict, Any
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request

from goose.trigger.types import Trigger, TriggerType
from goose.trigger.repository import TriggerRepository
from .handlers import ITriggerHandler, CronHandler, WebhookHandler
from goose.command.bus import CommandBus
from goose.app.commands import RunWorkflowCommand

logger = logging.getLogger(__name__)

class TriggerManager:
    """
    【职责】生命周期管理、状态维护、事件分发
    它是 Singleton (单例) 的，通常随应用启动
    """
    def __init__(self, bus: CommandBus):
        self.repo = TriggerRepository()
        self.bus = bus
        
        # 核心组件
        self.cron_scheduler = AsyncIOScheduler()
        self.active_triggers: Dict[str, Trigger] = {}
        
        # 策略注册
        self.handlers: Dict[TriggerType, ITriggerHandler] = {
            TriggerType.SCHEDULE: CronHandler(self.cron_scheduler, self._dispatch),
            TriggerType.WEBHOOK: WebhookHandler(self._dispatch),
        }

    # --- Lifecycle ---

    async def start(self):
        """应用启动时调用"""
        logger.info("⏰ Starting Trigger Manager...")
        if not self.cron_scheduler.running:
            self.cron_scheduler.start()
        
        # 加载所有启用的 Trigger
        triggers = await self.repo.list_active()
        for t in triggers:
            await self.register_trigger(t)
        logger.info(f"⏰ Trigger Manager started with {len(self.active_triggers)} triggers.")

    async def stop(self):
        """应用关闭时调用"""
        if self.cron_scheduler.running:
            self.cron_scheduler.shutdown()
        logger.info("⏰ Trigger Manager stopped.")

    # --- State Management (供 Service 调用) ---

    async def refresh_trigger(self, trigger_id: str):
        """
        [关键] Service 通知 Manager 数据变了，请刷新内存状态
        """
        trigger = await self.repo.get(trigger_id)
        
        # 情况 1: Trigger 不存在了 (被删了) 或 被禁用了 -> 移除
        if not trigger or not trigger.enabled:
            await self.unregister_trigger(trigger_id)
            return

        # 情况 2: Trigger 存在且启用 -> 注册/更新
        await self.register_trigger(trigger)

    async def register_trigger(self, trigger: Trigger):
        """内部方法：注册单个 Trigger"""
        handler = self.handlers.get(trigger.type)
        if handler:
            await handler.register(trigger)
            self.active_triggers[trigger.id] = trigger

    async def unregister_trigger(self, trigger_id: str):
        """内部方法：移除单个 Trigger"""
        # 先从内存里拿旧的 Trigger 才知道是什么类型
        trigger = self.active_triggers.pop(trigger_id, None)
        if trigger:
            handler = self.handlers.get(trigger.type)
            if handler:
                await handler.unregister(trigger_id)

    # --- Event Dispatching ---

    async def handle_webhook(self, trigger_id: str, request: Request):
        """
        处理 Webhook 请求入口
        注意：这里是从内存 active_triggers 查，速度快且能过滤掉已禁用的
        """
        trigger = self.active_triggers.get(trigger_id)
        if not trigger:
            raise ValueError("Trigger not found or inactive")
        
        if trigger.type != TriggerType.WEBHOOK:
            raise ValueError(f"Trigger {trigger_id} is not a webhook")

        handler = self.handlers[TriggerType.WEBHOOK]
        if isinstance(handler, WebhookHandler):
            await handler.handle_request(trigger, request)

    async def _dispatch(self, trigger: Trigger, raw_data: Dict[str, Any]):
        """
        核心调度逻辑：触发器被激发 -> 启动工作流
        """
        logger.info(f"⚡ Trigger Fired: {trigger.id} ({trigger.type})")
        
        # 1. 映射输入参数 (Input Mapping)
        inputs = self._map_inputs(trigger.input_mapping, raw_data)
        # 1. 构造命令
        cmd = RunWorkflowCommand(
            workflow_id=trigger.workflow_id,
            user_id=trigger.user_id,
            inputs=inputs,
            source=f"trigger:{trigger.type}"
        )
        # 2. 发送命令 (并拿到返回值 run_id)
        # 此时 TriggerManager 完全不知道背后是谁在跑，也没直接引用 Service
        try:
            run_id = await self.bus.send(cmd)
            logger.info(f"🚀 Workflow Started: {run_id}")
        except Exception as e:
            logger.error(f"Failed to dispatch: {e}")

    def _map_inputs(self, mapping: Dict[str, str], raw_data: Dict) -> Dict:
        """简单的 Dict 映射逻辑"""
        if not mapping: return raw_data
        result = {}
        for target_key, source_key in mapping.items():
            result[target_key] = raw_data.get(source_key)
        return result