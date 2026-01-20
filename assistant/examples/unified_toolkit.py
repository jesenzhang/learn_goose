"""
Unified Tool System - Combining the best of goose-py and pho toolkits.

Features:
- Simple and flexible tool registration (like pho)
- Deep system integration (like goose-py)
- Enhanced execution with inspector chains (like pho)
- MCP/OpenAI compatibility (like goose-py)
- Multiple registration methods (decorator, skill, MCP, builtin)
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union, Protocol
from dataclasses import dataclass, field
from enum import Enum
from collections import OrderedDict
from abc import ABC, abstractmethod

from pydantic import BaseModel, Field
import time
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib


logger = logging.getLogger(__name__)


# ============================================================================
# Core Types and Enums
# ============================================================================

class ToolSourceType(str, Enum):
    """Types of tool registration"""
    DECORATOR = "decorator"     # Registered via @register_tool decorator
    SKILL = "skill"             # Loaded from skill directory (SKILL.md)
    MCP = "mcp"                 # From MCP extension
    BUILTIN = "builtin"         # Built-in tool


class ToolStatus(str, Enum):
    """Tool execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CACHED = "cached"


@dataclass
class ToolMetadata:
    """Metadata for a registered tool"""
    name: str
    description: str
    function: Callable
    category: Optional[str] = None
    enabled: bool = True
    source_type: ToolSourceType
    permission: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Unique identifier"""
        return self.name


# ============================================================================
# Tool Base Classes
# ============================================================================

class ToolError(Exception):
    """Base tool execution error"""
    pass


class ToolInputSchema(BaseModel):
    """Base model for tool input validation"""
    class Config:
        extra = "forbid"

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
        

# ============================================================================
# Execution Context and Results
# ============================================================================

@dataclass
class ExecutionContext:
    """Enhanced execution context (like pho)"""
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    variables: Dict[str, Any] = field(default_factory=dict)

    # Services that can be injected (like pho)
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
    """Enhanced execution result (like pho)"""
    status: ToolStatus
    tool_name: str
    result: Optional[Any] = None
    error: Optional[str] = None
    cached: bool = False
    execution_time: float = 0.0
    inspector_logs: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status in (ToolStatus.COMPLETED, ToolStatus.CACHED)

    @property
    def is_failure(self) -> bool:
        return self.status == ToolStatus.FAILED

    @property
    def is_blocked(self) -> bool:
        return self.status == ToolStatus.BLOCKED

class ToolInspector(ABC):
    """
    拦截器基类：用于在工具执行前后插入逻辑
    """
    async def before_execution(self, tool_name: str, args: Dict[str, Any], context: ExecutionContext) -> None:
        pass

    async def after_execution(self, result: ExecutionResult, context: ExecutionContext) -> None:
        pass
    

class BaseTool(ABC):
    """
    Base tool class combining the best of both systems.

    Features:
    - Simple interface (like pho)
    - Standardized execution (like goose-py)
    - Pydantic validation (like both)
    """

    name: str = ""
    description: str = ""
    input_schema: Optional[Type[ToolInputSchema]] = None
    category: Optional[str] = None

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._validate_metadata()

    def _validate_metadata(self):
        """Validate tool metadata"""
        if not hasattr(self, 'name') or not self.name:
            raise ValueError(f"Tool {self.__class__.__name__} must have a name")
        if not hasattr(self, 'description') or not self.description:
            raise ValueError(f"Tool {self.__class__.__name__} must have a description")

    @property
    def schema(self) -> Dict[str, Any]:
        """Get JSON Schema for tool input"""
        if self.input_schema is None:
            return {"type": "object", "properties": {}, "required": []}

        # Pydantic V2 兼容
        try:
            return self.input_schema.model_json_schema()
        except AttributeError:
            return self.input_schema.schema() # V1 Fallback

    def validate_params(self, params: Dict[str, Any]) -> BaseModel:
        if self.input_schema is None:
            return params # type: ignore
        try:
            return self.input_schema.model_validate(params)
        except AttributeError:
             return self.input_schema.parse_obj(params) # V1 Fallback

    @abstractmethod
    async def execute(self, params: BaseModel) -> Any:
        """
        Execute the tool.

        Args:
            params: Validated parameters (Pydantic model)

        Returns:
            Tool result (any type)

        Raises:
            ToolError: If execution fails
        """
        pass

    async def run(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run tool with validation and error handling.

        Args:
            params: Raw parameter dictionary

        Returns:
            Result dict with status and content/error
        """
       
        validated_params = self.validate_params(params)
        result = await self.execute(validated_params)

        return result

    
# ============================================================================
# Tool Registry (Unified)
# ============================================================================

class ToolRegistry:
    """
    Unified tool registry combining the best of both systems.

    Features:
    - Simple registration (like pho)
    - System integration (like goose-py)
    - Multiple registration methods
    - Metadata management
    """

    def __init__(self):
        """Initialize registry"""
        self._tools: Dict[str, ToolMetadata] = {}
        self._by_type: Dict[ToolSourceType, Dict[str, ToolMetadata]] = {
            t: {} for t in ToolSourceType
        }
        self._by_category: Dict[str, Dict[str, ToolMetadata]] = {}
        self._decorators: List[Callable] = []

    # ========================================================================
    # Registration Methods
    # ========================================================================

    def register_tool_class(
        self,
        tool_class: Type[BaseTool],
        source_type: ToolSourceType = ToolSourceType.BUILTIN,
        category: Optional[str] = None,
        **metadata
    ) -> None:
        """
        Register a tool class.

        Args:
            tool_class: BaseTool subclass
            source_type: Type of registration
            category: Tool category
            source: Source identifier
            **metadata: Additional metadata
        """
        # Create tool instance to get metadata
        tool_instance = tool_class()
        tool_name = tool_instance.name
        tool_desc = tool_instance.description

        metadata_obj = ToolMetadata(
            name=tool_name,
            description=tool_desc,
            source_type=source_type,
            function=tool_instance.run,  # Use the run method
            category=category or tool_instance.category,
            schema=tool_instance.schema,
            parameters=tool_instance.schema.get("properties", {}),
            **metadata
        )

        self._register_metadata(metadata_obj)

    def register_function(
        self,
        name: str,
        func: Callable,
        description: str = "",
        source_type: ToolSourceType = ToolSourceType.DECORATOR,
        category: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        **metadata
    ) -> None:
        """
        Register a function as a tool.

        Args:
            name: Tool name
            func: Function to register
            description: Tool description
            source_type: Type of registration
            category: Tool category
            source: Source identifier
            schema: Parameter schema
            **metadata: Additional metadata
        """
        # Extract schema if not provided
        if schema is None:
            schema = self._extract_function_schema(func)

        metadata_obj = ToolMetadata(
            name=name,
            description=description or getattr(func, "__doc__", "") or "",
            source_type=source_type,
            function=func,
            category=category,
            schema=schema,
            parameters=schema.get("properties", {}),
            **metadata
        )

        self._register_metadata(metadata_obj)

    def _register_metadata(self, metadata: ToolMetadata) -> None:
        """Internal method to register metadata"""
        self._tools[metadata.name] = metadata
        self._by_type[metadata.source_type][metadata.name] = metadata

        if metadata.category:
            if metadata.category not in self._by_category:
                self._by_category[metadata.category] = {}
            self._by_category[metadata.category][metadata.name] = metadata

        logger.debug(f"Registered tool: {metadata.name} (type: {metadata.source_type.value})")

    def register_decorator(
        self,
        name: str,
        description: str = "",
        category: Optional[str] = None,
        **kwargs
    ) -> Callable:
        """
        Decorator for tool registration.

        Usage:
            @registry.register_decorator("my_tool", description="Does something")
            def my_tool(arg1: str, arg2: int) -> str:
                return f"Result: {arg1} {arg2}"
        """
        def decorator(func: Callable) -> Callable:
            self.register_function(
                name=name,
                func=func,
                description=description,
                source_type=ToolSourceType.DECORATOR,
                category=category,
                **kwargs
            )
            return func
        return decorator

    def unregister(self, name: str) -> bool:
        """Unregister a tool"""
        if name not in self._tools:
            return False

        metadata = self._tools[name]

        # Remove from all indexes
        del self._tools[name]
        del self._by_type[metadata.source_type][name]

        if metadata.category and metadata.category in self._by_category:
            self._by_category[metadata.category].pop(name, None)

        logger.debug(f"Unregistered tool: {name}")
        return True

    # ========================================================================
    # Query Methods
    # ========================================================================

    def get(self, name: str) -> Optional[ToolMetadata]:
        """Get tool metadata by name"""
        return self._tools.get(name)

    def get_function(self, name: str) -> Optional[Callable]:
        """Get tool function by name"""
        metadata = self.get(name)
        return metadata.function if metadata else None

    def list_all(self) -> Dict[str, ToolMetadata]:
        """List all registered tools"""
        return self._tools.copy()

    def list_by_type(self, tool_type: ToolSourceType) -> Dict[str, ToolMetadata]:
        """List tools by type"""
        return self._by_type[tool_type].copy()

    def list_by_category(self, category: str) -> Dict[str, ToolMetadata]:
        """List tools by category"""
        return self._by_category.get(category, {}).copy()

    def list_enabled(self) -> Dict[str, ToolMetadata]:
        """List only enabled tools"""
        return {
            name: meta for name, meta in self._tools.items()
            if meta.enabled
        }

    def list_categories(self) -> List[str]:
        """List all categories"""
        return list(self._by_category.keys())

    # ========================================================================
    # Schema Extraction
    # ========================================================================

    def _extract_function_schema(self, func: Callable) -> Dict[str, Any]:
        """Extract JSON schema from function signature"""
        sig = inspect.signature(func)
        parameters = {}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_info = {
                "type": "string",
                "description": param_name
            }

            # Try to get type annotation
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = self._type_to_string(param.annotation)

            # Check for default value
            if param.default != inspect.Parameter.empty:
                param_info["default"] = param.default

            parameters[param_name] = param_info

        return {
            "type": "object",
            "properties": parameters,
            "required": [
                p for p in parameters
                if sig.parameters[p].default == inspect.Parameter.empty
                and p not in ("self", "cls")
            ]
        }

    def _type_to_string(self, type_hint: type) -> str:
        """Convert type annotation to string"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        return type_map.get(type_hint, "string")

    # ========================================================================
    # OpenAI/MCP Format Export
    # ========================================================================

    def to_openai_functions(self) -> List[Dict[str, Any]]:
        """
        Export tools as OpenAI function-calling format.

        Returns:
            List of function definitions
        """
        functions = []

        for metadata in self.list_enabled().values():
            func_def = {
                "name": metadata.name,
                "description": metadata.description,
                "parameters": metadata.schema or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            functions.append(func_def)

        return functions

    def to_mcp_tools(self) -> List[Dict[str, Any]]:
        """
        Export tools as MCP format.

        Returns:
            List of MCP tool definitions
        """
        tools = []

        for metadata in self.list_enabled().values():
            tool_def = {
                "name": metadata.name,
                "description": metadata.description,
                "inputSchema": metadata.schema or {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
            tools.append(tool_def)

        return tools

    # ========================================================================
    # Statistics
    # ========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics"""
        return {
            "total_tools": len(self._tools),
            "by_type": {
                t.value: len(tools)
                for t, tools in self._by_type.items()
            },
            "by_category": {
                cat: len(tools)
                for cat, tools in self._by_category.items()
            },
            "enabled": len(self.list_enabled()),
            "disabled": len(self._tools) - len(self.list_enabled()),
        }

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __repr__(self) -> str:
        return f"UnifiedToolRegistry({len(self)} tools)"


# ============================================================================
# Enhanced Tool Executor (like pho but simplified)
# ============================================================================

class ToolExecutor:
    """
    Enhanced tool executor with dependency injection and error handling.

    Simplified version of pho's ToolExecutor, focusing on essential features.
    """

    def __init__(
        self,
        registry: ToolRegistry,
        enable_cache: bool = True,
        max_retries: int = 0,
        retry_delay: float = 0.1,
        max_workers: int = 4,  # 线程池最大线程数
        cache_ttl: int = 300,
        inspectors: Optional[List[ToolInspector]] = None
    ):
        """
        Initialize ToolExecutor.

        Args:
            registry: Tool registry
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

    async def execute(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[ExecutionContext] = None
    ) -> ExecutionResult:
        context = context or ExecutionContext()
        start_time = time.time()
        
        # 1. 查找工具
        metadata = self.registry.get(tool_name)
        if not metadata:
            return self._build_result(ToolStatus.FAILED, tool_name, error="Tool not found", start_time=start_time)
        
        if not metadata.enabled:
            return self._build_result(ToolStatus.BLOCKED, tool_name, error="Tool disabled", start_time=start_time)

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
                result = self._build_result(ToolStatus.CACHED, tool_name, result=cached_val, cached=True, start_time=start_time)
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
            
            result = self._build_result(ToolStatus.COMPLETED, tool_name, result=raw_result, start_time=start_time)

        except Exception as e:
            logger.exception(f"Tool execution error: {tool_name}")
            result = self._build_result(ToolStatus.FAILED, tool_name, error=str(e), start_time=start_time)

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

    def _build_result(self, status: ToolStatus, name: str, result=None, error=None, cached=False, start_time=0.0):
        return ExecutionResult(
            status=status,
            tool_name=name,
            result=result,
            error=error,
            cached=cached,
            execution_time=time.time() - start_time
        )
    
    def shutdown(self):
        """关闭线程池"""
        self._thread_pool.shutdown(wait=True)
        


# ============================================================================
# Global Registry and Convenience Functions
# ============================================================================

# Global registry instance
_global_registry: Optional[ToolRegistry] = None
_global_executor: Optional[ToolExecutor] = None


def get_global_registry() -> ToolRegistry:
    """Get the global tool registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry


def get_global_executor() -> ToolExecutor:
    """Get the global tool executor instance"""
    global _global_executor
    if _global_executor is None:
        registry = get_global_registry()
        _global_executor = ToolExecutor(registry)
    return _global_executor


def register_tool(
    name: str,
    description: str = "",
    category: Optional[str] = None,
    **kwargs
) -> Callable:
    """
    Global decorator for tool registration.

    Usage:
        @register_tool("my_tool", description="Does something")
        def my_tool(arg1: str) -> str:
            return arg1
    """
    return get_global_registry().register_decorator(
        name=name,
        description=description,
        category=category,
        **kwargs
    )


def register_tool_class(
    tool_class: Type[BaseTool],
    source_type: ToolSourceType = ToolSourceType.BUILTIN,
    category: Optional[str] = None,
    **kwargs
) -> None:
    """
    Register a tool class globally.

    Args:
        tool_class: BaseTool subclass
        source_type: Type of registration
        category: Tool category
        **kwargs: Additional metadata
    """
    get_global_registry().register_tool_class(
        tool_class=tool_class,
        source_type=source_type,
        category=category,
        **kwargs
    )


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


# ============================================================================
# Example Tool Implementations
# ============================================================================

# Example tool using BaseTool class
class ExampleTool(BaseTool):
    """Example tool demonstrating the BaseTool interface."""

    name = "example"
    description = "An example tool that demonstrates the BaseTool interface"
    category = "examples"

    class Params(ToolInputSchema):
        message: str = Field(..., description="Message to process")
        uppercase: bool = Field(default=False, description="Convert to uppercase")

    input_schema = Params

    async def execute(self, params: Params) -> str:
        """Execute the example tool."""
        result = params.message
        if params.uppercase:
            result = result.upper()
        return f"Processed: {result}"


# Example function-based tool
@register_tool(
    name="echo",
    description="Echo back the input message",
    category="examples"
)
def echo_tool(message: str) -> str:
    """Echo the message back to the user."""
    return f"Echo: {message}"


# ============================================================================
# Initialization
# ============================================================================

def initialize_toolkit():
    """Initialize the unified toolkit with example tools."""
    # Register example tools
    register_tool_class(ExampleTool)

    logger.info("Unified toolkit initialized with example tools")


__all__ = [
    # Core types
    "ToolSourceType",
    "ToolStatus",
    "ToolMetadata",
    "ExecutionContext",
    "ExecutionResult",

    # Base classes
    "ToolError",
    "ToolInputSchema",
    "BaseTool",

    # Registry and execution
    "ToolRegistry",
    "ToolExecutor",
    "get_global_registry",
    "get_global_executor",

    # Registration functions
    "register_tool",
    "register_tool_class",

    # Execution function
    "execute_tool",

    # Initialization
    "initialize_toolkit",
]