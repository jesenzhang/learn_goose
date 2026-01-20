"""
Hook Manager - Enhanced version with configuration support and pipeline execution
"""

import logging
import asyncio
from typing import List, Optional, Dict, Any, Type, Callable
from .base import (
    AgentHook, HookResult, HookContext, HookAction, HookConfig
)

logger = logging.getLogger(__name__)


# ==================== Hook Registry ====================

class HookRegistry:
    """Hook 类注册表，支持动态创建"""

    _registry: Dict[str, Type[AgentHook]] = {}

    @classmethod
    def register(cls, hook_class: Type[AgentHook], name: Optional[str] = None):
        """注册 Hook 类"""
        hook_name = name or hook_class.name
        cls._registry[hook_name] = hook_class
        logger.debug(f"Registered hook class: {hook_name}")

    @classmethod
    def get(cls, name: str) -> Optional[Type[AgentHook]]:
        """获取 Hook 类"""
        return cls._registry.get(name)

    @classmethod
    def create(cls, config: HookConfig) -> Optional[AgentHook]:
        """根据配置创建 Hook 实例"""
        hook_class = cls.get(config.name)
        if hook_class:
            try:
                return hook_class(config)
            except Exception as e:
                logger.error(f"Failed to create hook {config.name}: {e}")
        return None

    @classmethod
    def list_registered(cls) -> List[str]:
        """列出所有已注册的 Hook"""
        return list(cls._registry.keys())


# ==================== Hook Configuration Loader ====================

class HookConfigLoader:
    """从配置文件加载 Hook 配置"""

    @staticmethod
    def from_dict(config_dict: Dict[str, Any]) -> List[HookConfig]:
        """从字典配置加载"""
        hooks = []

        for name, hook_cfg in config_dict.items():
            if not hook_cfg.get("enabled", True):
                continue

            hooks.append(HookConfig(
                name=name,
                enabled=hook_cfg.get("enabled", True),
                priority=hook_cfg.get("priority", 100),
                hook_type=hook_cfg.get("hook_type", "filter"),
                conditions=hook_cfg.get("conditions", {}),
                params=hook_cfg.get("params", {}),
                fail_on_error=hook_cfg.get("fail_on_error", False),
                error_message=hook_cfg.get("error_message")
            ))

        return hooks

    @staticmethod
    def from_config_loader(config_loader) -> List[HookConfig]:
        """从 ConfigLoader 加载"""
        hooks_config = config_loader.hooks
        return HookConfigLoader.from_dict(hooks_config)


# ==================== Enhanced Hook Manager ====================

class HookManager:
    """
    增强的 Hook 管理器

    功能：
    1. Hook 注册与管理
    2. 配置文件加载
    3. Pipeline 执行
    4. 错误处理与日志
    """

    def __init__(self):
        self._hooks: List[AgentHook] = []
        self._hook_map: Dict[str, AgentHook] = {}

    # ==================== Hook 注册 ====================

    def register(self, hook: AgentHook) -> None:
        """注册单个 Hook"""
        if hook.name in self._hook_map:
            logger.warning(f"Hook {hook.name} already registered, replacing")

        self._hook_map[hook.name] = hook
        self._rebuild_hook_list()
        logger.info(f"🪝 Hook registered: {hook.name} (priority={hook.priority}, enabled={hook.enabled})")

    def register_all(self, hooks: List[AgentHook]) -> None:
        """批量注册 Hooks"""
        for hook in hooks:
            self._hook_map[hook.name] = hook
        self._rebuild_hook_list()
        logger.info(f"🪝 Registered {len(hooks)} hooks")

    def unregister(self, name: str) -> bool:
        """注销 Hook"""
        if name in self._hook_map:
            del self._hook_map[name]
            self._rebuild_hook_list()
            logger.info(f"🪝 Hook unregistered: {name}")
            return True
        return False

    def _rebuild_hook_list(self) -> None:
        """重建 Hook 列表（按优先级排序）"""
        self._hooks = sorted(
            [h for h in self._hook_map.values() if h.enabled],
            key=lambda h: h.priority
        )

    def load_from_config(self, configs: List[HookConfig]) -> int:
        """从配置加载 Hooks"""
        loaded = 0
        for config in configs:
            hook = HookRegistry.create(config)
            if hook:
                self.register(hook)
                loaded += 1
        logger.info(f"🪝 Loaded {loaded} hooks from config")
        return loaded

    # ==================== Hook 查询 ====================

    def get_hook(self, name: str) -> Optional[AgentHook]:
        """获取指定 Hook"""
        return self._hook_map.get(name)

    def get_hooks_by_type(self, hook_type: str) -> List[AgentHook]:
        """按类型获取 Hooks"""
        return [h for h in self._hooks if h.config and h.config.hook_type == hook_type]

    def list_hooks(self) -> List[str]:
        """列出所有 Hook 名称"""
        return list(self._hook_map.keys())

    # ==================== Pipeline 执行 ====================

    async def execute_pipeline(
        self,
        hook_method: str,
        ctx: HookContext,
        *args,
        **kwargs
    ) -> HookResult:
        """
        执行 Hook Pipeline

        Args:
            hook_method: 要调用的 Hook 方法名
            ctx: Hook 上下文
            *args, **kwargs: 传递给 Hook 方法的参数

        Returns:
            HookResult: 最终执行结果
        """
        current_result = HookResult.continue_()
        modified_input = ctx.user_input

        for hook in self._hooks:
            # 检查是否应该执行
            if not hook.should_execute(ctx):
                ctx.mark_skipped(hook.name, "disabled or conditions not met")
                continue

            try:
                # 获取 Hook 方法
                method = getattr(hook, hook_method, None)
                if not method:
                    continue

                # 更新上下文中的输入（如果被修改过）
                if modified_input != ctx.user_input:
                    # 注意：这里可能需要创建新的 HookContext
                    ctx.user_input = modified_input

                # 执行 Hook
                result = await method(ctx, *args, **kwargs)

                if result:
                    ctx.mark_executed(hook.name)

                    # 处理不同的动作类型
                    if result.action == HookAction.INTERCEPT:
                        logger.info(f"🛑 Pipeline intercepted by: {hook.name}")
                        return result

                    elif result.action == HookAction.SKIP:
                        logger.info(f"⏭️ Pipeline skipped by: {hook.name}")
                        return result

                    elif result.action == HookAction.MODIFY:
                        if result.modified_input:
                            modified_input = result.modified_input
                            logger.debug(f"✏️ Input modified by: {hook.name}")
                        if result.modified_data:
                            ctx.shared_data.update(result.modified_data)

                    elif result.action == HookAction.RETRY:
                        logger.info(f"🔄 Retry requested by: {hook.name}, reason: {result.retry_reason}")
                        # 重试逻辑由调用方处理
                        return result

            except Exception as e:
                logger.error(f"❌ Error in hook {hook.name}.{hook_method}: {e}", exc_info=True)
                # 根据配置决定是否继续
                if hook.config and hook.config.fail_on_error:
                    return HookResult.intercept(
                        response=hook.config.error_message or f"Hook {hook.name} failed",
                        data={"error": str(e)}
                    )
                # 否则继续执行后续 Hook

        return current_result

    # ==================== 快捷执行方法 ====================

    async def on_request_start(self, ctx: HookContext) -> HookResult:
        """执行请求开始 Hooks"""
        return await self.execute_pipeline("on_request_start", ctx)

    async def on_user_input(self, ctx: HookContext) -> HookResult:
        """执行用户输入 Hooks（核心 Pipeline）"""
        result = await self.execute_pipeline("on_user_input", ctx)

        # 如果输入被修改，更新上下文
        if result.action == HookAction.MODIFY and result.modified_input:
            ctx.user_input = result.modified_input

        return result

    async def on_intent_detect_start(self, ctx: HookContext) -> HookResult:
        """执行意图识别开始 Hooks"""
        return await self.execute_pipeline("on_intent_detect_start", ctx)

    async def on_intent_detected(self, ctx: HookContext, intent_data: Any) -> HookResult:
        """执行意图识别后 Hooks"""
        return await self.execute_pipeline("on_intent_detected", ctx, intent_data)

    async def on_tool_start(self, ctx: HookContext, tool_name: str, args: Dict[str, Any]) -> HookResult:
        """执行工具开始 Hooks"""
        return await self.execute_pipeline("on_tool_start", ctx, tool_name, args)

    async def on_tool_end(self, ctx: HookContext, tool_name: str, args: Dict[str, Any], result: Any) -> HookResult:
        """执行工具结束 Hooks"""
        return await self.execute_pipeline("on_tool_end", ctx, tool_name, args, result)

    async def on_response_generated(self, ctx: HookContext, response: str) -> HookResult:
        """执行响应生成后 Hooks"""
        return await self.execute_pipeline("on_response_generated", ctx, response)

    async def on_request_end(self, ctx: HookContext, result: Any = None) -> HookResult:
        """执行请求结束 Hooks"""
        return await self.execute_pipeline("on_request_end", ctx, result)

    async def on_error(self, ctx: HookContext, error: Exception) -> HookResult:
        """执行错误处理 Hooks"""
        return await self.execute_pipeline("on_error", ctx, error)


# ==================== 装饰器支持 ====================

def register_hook(name: Optional[str] = None):
    """Hook 类注册装饰器"""
    def decorator(cls: Type[AgentHook]):
        HookRegistry.register(cls, name)
        return cls
    return decorator
