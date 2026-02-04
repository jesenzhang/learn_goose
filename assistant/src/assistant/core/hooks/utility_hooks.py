"""
实用 Hooks - 日志记录、输入验证、统计等
优先级: 150-199 (观察类 Hook，低优先级)
"""

import logging
import time
from typing import Optional, Dict, Any
from .base import AgentHook, HookResult, HookContext, HookConfig
from .manager import register_hook

logger = logging.getLogger(__name__)


@register_hook("request_logger")
class RequestLoggerHook(AgentHook):
    """
    请求日志 Hook

    记录所有请求的详细信息，用于调试和分析。
    """
    name = "request_logger"
    priority = 190  # 低优先级，观察类
    enabled = True

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)
        self.log_level = "INFO"
        self.log_details = True

        if config and config.params:
            self.log_level = config.params.get("log_level", "INFO")
            self.log_details = config.params.get("log_details", True)

    async def on_request_start(self, ctx: HookContext) -> Optional[HookResult]:
        """记录请求开始"""
        log_func = getattr(logger, self.log_level.lower(), logger.info)

        log_func(
            f"📥 Request Start | "
            f"Session: {ctx.state.session_id} | "
            f"Input: {ctx.user_input[:100]}{'...' if len(ctx.user_input) > 100 else ''}"
        )

        if self.log_details:
            ctx.set_shared("request_start_time", time.time())

        return None

    async def on_request_end(self, ctx: HookContext, result: Any = None) -> Optional[HookResult]:
        """记录请求结束"""
        log_func = getattr(logger, self.log_level.lower(), logger.info)

        elapsed = ctx.elapsed_time
        log_func(
            f"📤 Request End | "
            f"Session: {ctx.state.session_id} | "
            f"Duration: {elapsed:.2f}s | "
            f"Executed Hooks: {len(ctx.executed_hooks)}"
        )

        if self.log_details:
            log_func(f"   Executed: {', '.join(ctx.executed_hooks)}")
            if ctx.skipped_hooks:
                log_func(f"   Skipped: {', '.join(ctx.skipped_hooks)}")

        return None

    async def on_error(self, ctx: HookContext, error: Exception) -> Optional[HookResult]:
        """记录错误"""
        logger.error(
            f"❌ Request Error | "
            f"Session: {ctx.state.session_id} | "
            f"Error: {type(error).__name__}: {str(error)}"
        )
        return None


@register_hook("input_validator")
class InputValidatorHook(AgentHook):
    """
    输入验证 Hook

    验证用户输入的基本格式和限制。
    """
    name = "input_validator"
    priority = 50  # 验证类 Hook，中等优先级
    enabled = True

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)

        # 配置参数
        self.max_length = 5000
        self.min_length = 1
        self.allow_empty = False

        if config and config.params:
            self.max_length = config.params.get("max_length", 5000)
            self.min_length = config.params.get("min_length", 1)
            self.allow_empty = config.params.get("allow_empty", False)

    async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
        """验证输入"""
        user_input = ctx.user_input

        # 检查长度
        if len(user_input) > self.max_length:
            return HookResult.intercept(
                response=f"抱歉，您的输入太长了（{len(user_input)} 字符），请控制在 {self.max_length} 字符以内。",
                response_data={"reason": "too_long", "length": len(user_input)}
            )

        if len(user_input) < self.min_length and not self.allow_empty:
            return HookResult.intercept(
                response=f"抱歉，您的输入太短了（{len(user_input)} 字符），请至少输入 {self.min_length} 字符。",
                response_data={"reason": "too_short", "length": len(user_input)}
            )

        return None


@register_hook("statistics_collector")
class StatisticsCollectorHook(AgentHook):
    """
    统计收集 Hook

    收集使用统计数据，如请求计数、平均响应时间等。
    """
    name = "statistics_collector"
    priority = 195  # 观察类，最低优先级
    enabled = True

    # 类级别统计
    _stats = {
        "total_requests": 0,
        "total_intercepted": 0,
        "total_errors": 0,
        "response_times": [],
    }

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)

    async def on_request_start(self, ctx: HookContext) -> Optional[HookResult]:
        """记录请求开始"""
        StatisticsCollectorHook._stats["total_requests"] += 1
        ctx.set_shared("request_start_time", time.time())
        return None

    async def on_request_end(self, ctx: HookContext, result: Any = None) -> Optional[HookResult]:
        """收集统计信息"""
        start_time = ctx.get_shared("request_start_time")
        if start_time:
            elapsed = time.time() - start_time
            StatisticsCollectorHook._stats["response_times"].append(elapsed)

            # 只保留最近 1000 条
            if len(StatisticsCollectorHook._stats["response_times"]) > 1000:
                StatisticsCollectorHook._stats["response_times"] = \
                    StatisticsCollectorHook._stats["response_times"][-1000:]

        return None

    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取统计信息"""
        response_times = cls._stats["response_times"]
        avg_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            "total_requests": cls._stats["total_requests"],
            "total_intercepted": cls._stats["total_intercepted"],
            "total_errors": cls._stats["total_errors"],
            "avg_response_time": avg_time,
            "recent_requests": len(response_times),
        }

    @classmethod
    def reset_stats(cls):
        """重置统计"""
        cls._stats = {
            "total_requests": 0,
            "total_intercepted": 0,
            "total_errors": 0,
            "response_times": [],
        }
