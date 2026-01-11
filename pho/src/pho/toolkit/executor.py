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

from .registry import ToolRegistry, ToolMetadata
from ..agent.inspectors.base import InspectorChain, InspectorResult

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """Status of tool execution"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CACHED = "cached"


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
        inspector_chain: Optional[InspectorChain] = None,
        enable_cache: bool = True,
        max_retries: int = 0,
        retry_delay: float = 0.1
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
        self.inspector_chain = inspector_chain or InspectorChain()
        self.enable_cache = enable_cache
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._cache: Dict[str, Any] = {}

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
        import time
        start_time = time.time()
        context = context or ExecutionContext()

        # Check tool exists
        metadata = self.registry.get(tool_name)
        if not metadata:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                tool_name=tool_name,
                error=f"Tool not found: {tool_name}",
                execution_time=time.time() - start_time
            )

        # Check if tool is enabled
        if not metadata.enabled:
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                tool_name=tool_name,
                error=f"Tool is disabled: {tool_name}",
                execution_time=time.time() - start_time
            )

        # Run inspector chain
        inspect_result = await self.inspector_chain.inspect(
            tool_name=tool_name,
            tool_args=tool_args,
            context=context.to_dict()
        )

        # Handle inspector results
        if inspect_result.is_denied():
            return ExecutionResult(
                status=ExecutionStatus.BLOCKED,
                tool_name=tool_name,
                error=inspect_result.error_message or inspect_result.reason,
                execution_time=time.time() - start_time,
                inspector_actions=[f"Denied: {inspect_result.reason}"]
            )

        if inspect_result.is_replaced():
            # Inspector provided a replacement result
            await self.inspector_chain.after_call(
                tool_name, tool_args, inspect_result.replacement_result, context.to_dict()
            )
            return ExecutionResult(
                status=ExecutionStatus.CACHED,
                tool_name=tool_name,
                result=inspect_result.replacement_result,
                cached=True,
                execution_time=time.time() - start_time,
                inspector_actions=[f"Replaced: {inspect_result.reason}"]
            )

        # Use modified args if any
        final_args = inspect_result.modified_args if inspect_result.is_modified() else tool_args

        # Check cache
        cache_key = self._make_cache_key(tool_name, final_args)
        if self.enable_cache and cache_key in self._cache:
            result = self._cache[cache_key]
            await self.inspector_chain.after_call(
                tool_name, final_args, result, context.to_dict()
            )
            return ExecutionResult(
                status=ExecutionStatus.CACHED,
                tool_name=tool_name,
                result=result,
                cached=True,
                execution_time=time.time() - start_time
            )

        # Execute with retries
        inspector_actions = []
        if inspect_result.reason:
            inspector_actions.append(f"Allowed: {inspect_result.reason}")

        for attempt in range(self.max_retries + 1):
            try:
                result = await self._execute_function(
                    metadata.function, final_args, context
                )

                # Cache successful result
                if self.enable_cache:
                    self._cache[cache_key] = result

                # Notify inspector chain
                await self.inspector_chain.after_call(
                    tool_name, final_args, result, context.to_dict()
                )

                return ExecutionResult(
                    status=ExecutionStatus.COMPLETED,
                    tool_name=tool_name,
                    result=result,
                    execution_time=time.time() - start_time,
                    inspector_actions=inspector_actions
                )

            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"Tool execution failed (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(self.retry_delay)
                else:
                    logger.error(f"Tool execution failed after {attempt + 1} attempts: {e}")
                    return ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        tool_name=tool_name,
                        error=str(e),
                        execution_time=time.time() - start_time,
                        inspector_actions=inspector_actions
                    )

    async def _execute_function(
        self,
        func: Callable,
        tool_args: Dict[str, Any],
        context: ExecutionContext
    ) -> Any:
        """Execute a function with dependency injection"""
        call_args = tool_args.copy()

        # Try to get signature
        try:
            sig = inspect.signature(func)
            params = sig.parameters
        except ValueError:
            # Built-in function, call directly
            return await self._run_func(func, call_args)

        # Check for **kwargs
        has_kwargs = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in params.values()
        )

        # Dependency injection
        # 1. Inject 'ctx' parameter if requested
        if "ctx" in params or has_kwargs:
            call_args["ctx"] = context

        # 2. Inject individual services if requested
        if has_kwargs or "state" in params:
            if context.state is not None:
                call_args["state"] = context.state
        if has_kwargs or "db" in params:
            if context.db is not None:
                call_args["db"] = context.db
        if has_kwargs or "ai_services" in params:
            if context.ai_services is not None:
                call_args["ai_services"] = context.ai_services

        # 3. Legacy injections (for compatibility)
        if has_kwargs or "_state" in params:
            if context.state is not None:
                call_args["_state"] = context.state
        if has_kwargs or "_db" in params:
            if context.db is not None:
                call_args["_db"] = context.db
        if has_kwargs or "_ai" in params:
            if context.ai_services is not None:
                call_args["_ai"] = context.ai_services

        return await self._run_func(func, call_args)

    async def _run_func(self, func: Callable, args: Dict[str, Any]) -> Any:
        """Run sync or async function"""
        if inspect.iscoroutinefunction(func):
            return await func(**args)
        else:
            # Run sync function in thread pool
            # Use functools.partial to pass keyword arguments
            import functools
            loop = asyncio.get_event_loop()
            partial_func = functools.partial(func, **args)
            return await loop.run_in_executor(None, partial_func)

    # ========================================================================
    # Cache Management
    # ========================================================================

    def _make_cache_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        """Create cache key from tool name and arguments"""
        import hashlib
        import json

        # Sort args for consistent hashing
        sorted_args = json.dumps(args, sort_keys=True, default=str)
        key_str = f"{tool_name}:{sorted_args}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def clear_cache(self) -> None:
        """Clear result cache"""
        self._cache.clear()

    def get_cache_size(self) -> int:
        """Get cache size"""
        return len(self._cache)

    # ========================================================================
    # Batch Execution
    # ========================================================================

    async def execute_batch(
        self,
        calls: List[tuple[str, Dict[str, Any]]],
        context: Optional[ExecutionContext] = None,
        parallel: bool = True
    ) -> List[ExecutionResult]:
        """
        Execute multiple tool calls.

        Args:
            calls: List of (tool_name, tool_args) tuples
            context: Execution context
            parallel: Whether to execute in parallel

        Returns:
            List of ExecutionResults
        """
        if parallel:
            tasks = [
                self.execute(name, args, context)
                for name, args in calls
            ]
            return await asyncio.gather(*tasks)
        else:
            results = []
            for name, args in calls:
                result = await self.execute(name, args, context)
                results.append(result)
            return results


__all__ = [
    "ExecutionStatus",
    "ExecutionContext",
    "ExecutionResult",
    "ToolExecutor",
]
