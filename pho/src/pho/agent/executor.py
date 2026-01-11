"""
Tool Executor - Handles function introspection, dependency injection, and execution.
"""

import inspect
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, TypeVar, cast

# 引入你的上下文定义
from ..skills.context import create_context, ServiceContext, AIServices
from ..core.state import AgentState
from ..db.manager import DatabaseManager # 假设这是你的具体DB类

logger = logging.getLogger(__name__)

class ToolExecutor:
    """
    负责智能执行工具函数，自动注入上下文依赖。
    """

    def __init__(
        self,
        session_id: str,
        state: AgentState,
        db: DatabaseManager,
        ai_services: Optional[AIServices] = None,
        extra_services: Optional[Dict[str, Any]] = None
    ):
        self.session_id = session_id
        self.state = state
        self.db = db
        self.ai_services = ai_services
        self.extra_services = extra_services or {}

    def _create_context(self) -> ServiceContext[AgentState, DatabaseManager]:
        """
        创建强类型的 ServiceContext。
        """
        # 利用 create_context 的泛型支持
        ctx = create_context(
            session_id=self.session_id,
            state=self.state,
            db=self.db,
            ai_services=self.ai_services, # 这里不再需要转 dict，create_context 应该适配 AIServices
            **self.extra_services
        )
        return ctx

    async def execute(self, func: Callable, tool_args: Dict[str, Any]) -> Any:
        """
        智能执行函数：
        1. 分析函数签名
        2. 注入 ctx 或其他遗留参数
        3. 处理同步/异步调用
        """
        if not callable(func):
            raise ValueError(f"Tool must be callable, got {type(func)}")

        # 1. 准备参数
        call_args = tool_args.copy()
        
        try:
            sig = inspect.signature(func)
        except ValueError:
            # 内置函数等无法获取签名的，直接尝试调用
            return await self._run_func(func, call_args)

        params = sig.parameters
        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

        # 2. 依赖注入逻辑
        # 规则 A: 显式请求 'ctx' 参数，或者参数类型注解包含 'ServiceContext'
        needs_ctx = False
        if 'ctx' in params:
            annotation = str(params['ctx'].annotation)
            # 宽松检查：只要注解里包含 ServiceContext 或者是 AgentContext 别名
            if "ServiceContext" in annotation or "AgentContext" in annotation or params['ctx'].annotation == inspect.Parameter.empty:
                needs_ctx = True
        
        # 规则 B: 如果有 **kwargs，我们通常也注入 ctx 以防万一
        if needs_ctx or has_kwargs:
            ctx = self._create_context()
            call_args['ctx'] = ctx

        # 3. 遗留注入 (Legacy Injection) - 仅当函数显式要求或有 kwargs 时注入
        # 建议逐步废弃这些，统一用 ctx
        if has_kwargs or '_state' in params: call_args['_state'] = self.state
        if has_kwargs or '_db' in params: call_args['_db'] = self.db
        if has_kwargs or '_ai' in params: call_args['_ai'] = self.ai_services
        if has_kwargs or '_ctx' in params: call_args['_ctx'] = {"session_id": self.session_id} # 旧版字典ctx

        # 4. 执行
        return await self._run_func(func, call_args)

    async def _run_func(self, func: Callable, args: Dict[str, Any]) -> Any:
        """统一处理同步/异步执行"""
        if inspect.iscoroutinefunction(func):
            return await func(**args)
        else:
            return await asyncio.to_thread(func, **args)