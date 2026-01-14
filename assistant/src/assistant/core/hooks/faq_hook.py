"""
FAQ Hook - FAQ 拦截 Hook
优先级: 10 (最高优先级，在意图识别前执行)
"""

import logging
from typing import Optional
from .base import AgentHook, HookResult, HookContext, HookConfig
from .manager import register_hook
from ..executor import ToolExecutor
from ...conversation import CallToolResult

logger = logging.getLogger(__name__)


@register_hook("faq_interceptor")
class FAQHook(AgentHook):
    """
    FAQ 拦截 Hook

    在意图识别前执行，如果命中 FAQ 则直接返回答案，拦截后续流程。
    """
    name = "faq_interceptor"
    priority = 10
    enabled = True

    def __init__(self, config: Optional[HookConfig] = None):
        super().__init__(config)
        self.faq_tool_name = "query_faq"
        self.faq_hit_key = "_faq_already_queried"  # 存储在 state.shared_memory 中

    async def on_user_input(self, ctx: HookContext) -> Optional[HookResult]:
        """
        用户输入时触发 FAQ 查询
        """
        # 检查是否已经查询过 FAQ（避免重复查询）
        # 使用 state.shared_memory 而不是 ctx.shared_data，这样整个请求期间都可以访问
        if ctx.state.shared_memory.get(self.faq_hit_key):
            logger.debug("FAQ already queried in this request, skipping")
            return None

        # 1. 检查环境是否有 query_faq 工具
        tool_func = None
        if ctx.gen.skill_loader:
            tool_func = ctx.gen.skill_loader.get_tool_func(self.faq_tool_name)

        if not tool_func:
            logger.debug(f"{self.faq_tool_name} tool not available")
            return None

        # 2. 创建临时执行环境
        executor = ToolExecutor(ctx.state.session_id, ctx.state, None, ctx.gen.ai_services, ctx.req_ctx)

        try:
            # 3. 调用 FAQ 工具
            result = await executor.execute(tool_func, {"query": ctx.user_input})

            # 4. 标记已查询（避免后续重复查询）
            # 存储到 state.shared_memory，这样整个请求期间（包括意图识别阶段）都能访问到
            ctx.state.shared_memory[self.faq_hit_key] = True

            # 5. 判断是否命中
            # FAQ 工具返回格式：
            # - 未命中：返回字符串 "None"
            # - 命中：返回 CallToolResult
            if isinstance(result, str) and result == "None":
                logger.debug(f"❌ FAQ not found for: {ctx.user_input[:50]}...")
                return None

            if isinstance(result, CallToolResult):
                # FAQ 命中！拦截并返回结果
                logger.info(f"✅ FAQ hit for: {ctx.user_input[:50]}...")

                # 提取响应文本
                response_text = ""
                for content in result.content:
                    if content.text:
                        response_text = content.text
                        break

                return HookResult.intercept(
                    response=response_text or "FAQ 命中",
                    response_data=result  # 传递完整的 CallToolResult
                )

            logger.debug(f"❌ FAQ returned unexpected type: {type(result)}")

        except Exception as e:
            logger.error(f"Error executing FAQ hook: {e}", exc_info=True)
            # FAQ 失败不应阻断主流程

        return None
