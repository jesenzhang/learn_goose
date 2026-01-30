"""
Tool Executor - Handles function introspection, dependency injection, and execution.
"""

import inspect
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, TypeVar, cast, Protocol,List

# 引入你的上下文定义
from ..skills.context import create_context, ServiceContext, AIServices
from ..core.state import AgentState
from ..core.context import RequestContext

logger = logging.getLogger(__name__)


class DatabaseProtocol(Protocol):
    """数据库协议 - 定义数据库操作接口"""

    def save_state(self, session_id: str, state: Dict[str, Any]) -> bool:
        """保存状态"""
        ...

    def load_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """加载状态"""
        ...

    def delete_state(self, session_id: str) -> bool:
        """删除状态"""
        ...

    def list_sessions(self) -> List[Dict[str, Any]]:
        """列出会话"""
        ...

    def save_event(self, session_id: str, event: Dict[str, Any]) -> bool:
        """保存事件"""
        ...

    def load_events(
        self,
        session_id: int,
        run_id: str,
        seq_id: int = -1,
        limit: Optional[int] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """加载事件"""
        ...

    def add_memory(self, user_id: str, content: str) -> bool:
        """添加记忆"""
        ...

    def get_memories(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """获取记忆"""
        ...

    def search_memories(self, user_id: str, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索记忆"""
        ...

    def delete_memory(self, memory_id: int) -> bool:
        """删除记忆"""
        ...

    def health_check(self) -> bool:
        """健康检查"""
        ...

    def close(self):
        """关闭连接"""
        ...


class ToolExecutor:
    """
    负责智能执行工具函数，自动注入上下文依赖。
    """

    def __init__(
        self,
        session_id: str,
        state: AgentState,
        db: DatabaseProtocol,
        ai_services: Optional[AIServices] = None,
        request_context: Optional[RequestContext] = None,
        extra_services: Optional[Dict[str, Any]] = None
    ):
        self.session_id = session_id
        self.state = state
        self.db = db
        self.ai_services = ai_services
        self.extra_services = extra_services or {}
        self.request_context = request_context

    def _create_context(self) -> ServiceContext[AgentState, DatabaseProtocol]:
        """
        创建强类型的 ServiceContext。
        """
        # 利用 create_context 的泛型支持
        ctx = create_context(
            session_id=self.session_id,
            state=self.state,
            db=self.db,
            ai_services=self.ai_services,
            req_ctx=self.request_context,
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