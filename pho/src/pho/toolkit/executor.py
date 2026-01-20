"""
Enhanced Tool Executor - Handles tool execution with inspector chain support.

Features:
- Dependency injection for context, state, services
- Inspector chain integration
- Sync/async function handling
- Error handling and retries
- Result caching
"""

import inspect
import asyncio
import logging
from typing import Any, Callable, Dict, Optional, List, Type
from dataclasses import dataclass, field
from enum import Enum
import time
from concurrent.futures import ThreadPoolExecutor
from abc import ABC, abstractmethod
from collections import OrderedDict
import hashlib
import json
from .registry import ToolRegistry,get_global_registry
from ..agent.inspectors.base import InspectorChain, InspectorResult
from .tool import ToolState, ToolDefinition,ToolSourceType,ToolError,ToolInputSchema,ToolResult

logger = logging.getLogger(__name__)

# ============================================================================
# 2. 核心组件：缓存与拦截器 (新增优化)
# ============================================================================

class InMemoryCache:
    """
    一个简单的带有 TTL (生存时间) 和 LRU (最近最少使用) 淘汰机制的内存缓存。
    """
    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        # 使用 OrderedDict 实现 LRU，key -> (value, expire_at)
        self._store: OrderedDict = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        
        value, expire_at = self._store[key]
        
        # 检查过期
        if time.time() > expire_at:
            del self._store[key]
            return None
            
        # 命中缓存，将其移动到末尾 (表示最近使用了)
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        # 如果缓存满了，移除第一个元素 (最久未使用的)
        if len(self._store) >= self.max_size and key not in self._store:
            self._store.popitem(last=False)
            
        actual_ttl = ttl if ttl is not None else self.default_ttl
        expire_at = time.time() + actual_ttl
        self._store[key] = (value, expire_at)
        self._store.move_to_end(key)

    def clear(self):
        self._store.clear()
        


@dataclass
class ExecutionContext:
    """Context provided to tools during execution"""
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)

    # Services that can be injected
    state: Optional[Any] = None
    db: Optional[Any] = None
    ai_services: Optional[Any] = None

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the context"""
        return getattr(self, key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_role": self.user_role,
            "variables": self.variables,
        }

class ToolInspector(ABC):
    """
    拦截器基类：用于在工具执行前后插入逻辑
    """
    async def before_execution(self, tool_name: str, args: Dict[str, Any], context: ExecutionContext) -> None:
        pass

    async def after_execution(self, result: ExecutionResult, context: ExecutionContext) -> None:
        pass

class ExecutionStatus(str, Enum):
    """Status of tool execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CACHED = "cached"


@dataclass
class ExecutionResult:
    """Result of tool execution"""
    status: ExecutionStatus
    tool_name: str
    result: Optional[Any] = None
    error: Optional[str] = None
    cached: bool = False
    execution_time: float = 0.0
    inspector_actions: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.CACHED)

    @property
    def is_failure(self) -> bool:
        return self.status == ExecutionStatus.FAILED

    @property
    def is_blocked(self) -> bool:
        return self.status == ExecutionStatus.BLOCKED


class ToolExecutor:
    """
    Enhanced tool executor with inspector chain support.

    Features:
    - Inspector chain for security/permission/repetition checks
    - Dependency injection
    - Sync/async execution
    - Error handling
    - Execution timing
    """

    def __init__(
        self,
        registry: ToolRegistry,
        enable_cache: bool = True,
        max_retries: int = 0,
        retry_delay: float = 0.1,
        max_workers: int = 4,  # 线程池最大线程数
        cache_ttl: int = 300,
        inspectors: Optional[List[ToolInspector]] = None,
    ):
        """
        Initialize ToolExecutor.

        Args:
            registry: Tool registry
            inspector_chain: Optional inspector chain for validation
            enable_cache: Whether to cache results
            max_retries: Number of retries on failure
            retry_delay: Delay between retries
        """
        
        self.registry = registry
        self.enable_cache = enable_cache
        self.inspectors = inspectors or []
        
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        # 1. 初始化高性能缓存
        self.cache = InMemoryCache(max_size=500, default_ttl=float(cache_ttl))
        
        # 2. 初始化线程池 (用于执行同步工具，避免阻塞 asyncio loop)
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="tool_worker")

    # ========================================================================
    # Main Execution
    # ========================================================================

    async def execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[ExecutionContext] = None
    ) -> ExecutionResult:
        """
        Execute a tool with full inspection chain.

        Args:
            tool_name: Name of tool to execute
            tool_args: Arguments to pass to tool
            context: Execution context

        Returns:
            ExecutionResult with status and result/error
        """
       
        start_time = time.time()
        context = context or ExecutionContext()

        # 1. 查找工具
        metadata = self.registry.get(tool_name)
        if not metadata:
            return self._build_result(ToolState.FAILED, tool_name, error="Tool not found", start_time=start_time)
        
        if not metadata.enabled:
            return self._build_result(ToolState.BLOCKED, tool_name, error="Tool disabled", start_time=start_time)


        # 2. 前置拦截器 (Before Execution)
        for inspector in self.inspectors:
            try:
                await inspector.before_execution(tool_name, tool_args, context)
            except Exception as e:
                logger.warning(f"Inspector {inspector.__class__.__name__} failed in before_execution: {e}")

        # 3. 检查缓存
        cache_key = self._make_cache_key(tool_name, tool_args)
        if self.enable_cache:
            cached_val = self.cache.get(cache_key)
            if cached_val is not None:
                result = self._build_result(ToolState.CACHED, tool_name, result=cached_val, cached=True, start_time=start_time)
                # 依然需要运行后置拦截器
                await self._run_after_inspectors(result, context)
                return result

        # 4. 执行工具 (核心逻辑)
        try:
            # 依赖注入处理
            func = metadata.function
            call_args = self._inject_dependencies(func, tool_args, context)
            
            # 区分 异步 vs 同步 执行
            if inspect.iscoroutinefunction(func):
                raw_result = await func(**call_args)
            else:
                # 放入线程池执行同步函数
                loop = asyncio.get_running_loop()
                raw_result = await loop.run_in_executor(
                    self._thread_pool,
                    lambda: func(**call_args)
                )
            
            # 5. 写入缓存
            if self.enable_cache:
                self.cache.set(cache_key, raw_result)
            
            result = self._build_result(ToolState.COMPLETED, tool_name, result=raw_result, start_time=start_time)

        except Exception as e:
            logger.exception(f"Tool execution error: {tool_name}")
            result = self._build_result(ToolState.FAILED, tool_name, error=str(e), start_time=start_time)

        # 6. 后置拦截器 (After Execution)
        await self._run_after_inspectors(result, context)
        
        return result

    async def _run_after_inspectors(self, result: ExecutionResult, context: ExecutionContext):
        for inspector in self.inspectors:
            try:
                await inspector.after_execution(result, context)
            except Exception as e:
                logger.warning(f"Inspector {inspector.__class__.__name__} failed in after_execution: {e}")

    def _inject_dependencies(self, func: Callable, args: Dict[str, Any], context: ExecutionContext) -> Dict[str, Any]:
        """依赖注入：自动注入 ctx, db, state 等"""
        final_args = args.copy()
        
        try:
            sig = inspect.signature(func)
            params = sig.parameters
        except ValueError:
            return final_args # 可能是 built-in 函数，不做注入

        has_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

        # 注入规则 map
        inject_map = {
            "ctx": context,
            "state": context.state,
            "db": context.db,
            "ai_services": context.ai_services
        }

        for param_name, inject_val in inject_map.items():
            if (param_name in params or has_kwargs) and inject_val is not None:
                # 只有当参数未被显式传递时才注入
                if param_name not in final_args:
                    final_args[param_name] = inject_val
        
        return final_args

    def _make_cache_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """生成确定性的 Cache Key"""
        # 过滤掉无法序列化的对象（如 context 如果不小心被传进来的话）
        clean_args = {k: v for k, v in args.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))}
        sorted_str = json.dumps(clean_args, sort_keys=True, default=str)
        return hashlib.md5(f"{tool_name}:{sorted_str}".encode()).hexdigest()

    def _build_result(
        self, 
        status: ToolState, 
        name: str, 
        result: Any = None, 
        error: Optional[str] = None, 
        cached: bool = False, 
        start_time: float = 0.0
    ) -> ExecutionResult:
        
        final_status = status
        final_error = error
        final_result = result

        # 【关键修改】检测 result 是否为标准化的 ToolResult
        if isinstance(result, ToolResult):
            # 1. 同步状态：如果工具内部标记为 FAILED，执行结果也应视为 FAILED
            if result.state == ToolState.FAILED:
                final_status = ToolState.FAILED
                # 优先使用 ToolResult 中的错误信息
                if result.error:
                    final_error = result.error
            
            # 2. 如果工具处于 COMPLETED 状态，但外部传入了 error (极其罕见)，保留外部 error
            
            # 3. 决定 ExecutionResult.result 存什么
            # 策略 A: 直接存 ToolResult 对象 (推荐，保留所有元数据)
            final_result = result 
            
            # 策略 B: 只存 content 字符串 (如果上层只想要纯文本)
            # final_result = result.content 

        return ExecutionResult(
            status=final_status,
            tool_name=name,
            result=final_result,
            error=final_error,
            cached=cached,
            execution_time=time.time() - start_time
        )
    
    def shutdown(self):
        """关闭线程池"""
        self._thread_pool.shutdown(wait=True)

    # ========================================================================
    # Batch Execution
    # ========================================================================

    async def execute_batch(
        self,
        calls: List[tuple[str, Dict[str, Any]]],
        context: Optional[ExecutionContext] = None,
        parallel: bool = True,
        max_concurrency: int = 10  # 新增：防止瞬间并发过大打挂服务
    ) -> List[ExecutionResult]:
        """
        Execute multiple tool calls safely.
        
        Features:
        - Fault Tolerance: One failure does not stop others.
        - Concurrency Control: Limits maximum parallel tasks.
        - Standardized Output: Always returns List[ExecutionResult].
        """
        context = context or ExecutionContext()
        
        if not calls:
            return []

        if parallel:
            # 使用 Semaphore 限制最大并发数
            semaphore = asyncio.Semaphore(max_concurrency)

            async def _bounded_execute(name: str, args: Dict[str, Any]) -> ExecutionResult:
                async with semaphore:
                    try:
                        return await self.execute(name, args, context)
                    except Exception as e:
                        # 最后的兜底：防止 execute 内部未能捕获的异常导致 gather 崩溃
                        # 虽然 execute 内部已经有 try-except，但为了 batch 的绝对安全，这里再加一层
                        logger.exception(f"Unexpected error in batch execution for {name}")
                        return ExecutionResult(
                            tool_name=name,
                            status=ToolState.FAILED,
                            error=f"Batch execution panic: {str(e)}"
                        )

            tasks = [
                _bounded_execute(name, args) 
                for name, args in calls
            ]
            
            # return_exceptions=True 是关键：确保即使有任务崩溃，也能拿到所有结果
            # 注意：因为我们上面的 _bounded_execute 已经捕获了所有异常并返回 Result，
            # 这里的 results 理论上全都是 ExecutionResult，不会有 Exception 对象。
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 为了类型安全，做一次清洗（以防万一有漏网之鱼）
            final_results = []
            for r in results:
                if isinstance(r, ExecutionResult):
                    final_results.append(r)
                elif isinstance(r, Exception):
                    # 只有当 _bounded_execute 自身逻辑写错时才会走到这里
                    final_results.append(ExecutionResult(
                        tool_name="unknown",
                        status=ToolState.FAILED,
                        error=f"Unhandled batch exception: {str(r)}"
                    ))
                else:
                    final_results.append(r) # Should not happen
            
            return final_results

        else:
            # 串行执行
            results = []
            for name, args in calls:
                # 串行执行时，execute 方法内部已经封装了 try-except，
                # 所以这里直接 await 即可，不用担心单个失败中断循环（除非 execute 实现有误）
                result = await self.execute(name, args, context)
                results.append(result)
            return results

# Global registry instance

_global_executor: Optional[ToolExecutor] = None


def get_global_executor() -> ToolExecutor:
    """Get the global tool executor instance"""
    global _global_executor
    if _global_executor is None:
        registry = get_global_registry()
        _global_executor = ToolExecutor(registry)
    return _global_executor


async def execute_tool(
    name: str,
    **kwargs
) -> ExecutionResult:
    """
    Execute a tool by name (global convenience function).

    Args:
        name: Tool name
        **kwargs: Tool arguments

    Returns:
        ExecutionResult
    """
    return await get_global_executor().execute(name, kwargs)

# Global registry instance for convenient access

tool_executor = get_global_executor()