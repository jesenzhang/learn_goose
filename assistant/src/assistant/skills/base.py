"""
Skill Base Classes - Foundation for skill implementation.

This module provides:
- Skill base class
- Tool decorator
- Skill metadata
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from dataclasses import dataclass, field
from enum import Enum
import inspect
from functools import wraps

class SkillType(str, Enum):
    """Skill availability scope."""
    GLOBAL = "global"      # Available in all contexts
    CONTEXTUAL = "contextual"  # Requires activation


@dataclass
class ToolMetadata:
    """Metadata for a tool function."""
    name: str
    description: str
    label: Optional[str] = None  # 中文显示名称，用于前端渲染
    parameters: Dict[str, Any] = field(default_factory=dict)
    is_sensitive: bool = False
    handler: Optional[Callable] = None

    def to_schema(self) -> Dict[str, Any]:
        """Convert to OpenAI function calling schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters or {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True
                }
            }
        }


class SkillBase(ABC):
    """
    Base class for all skills.

    Skills provide domain-specific tools and context for the agent.
    They can be global (always available) or contextual (require activation).

    Usage:
        class MySkill(SkillBase):
            name = "my_skill"
            description = "My custom skill"

            @skill_tool
            def do_something(self, arg: str, ctx: ServiceContext) -> str:
                return f"Done: {arg}"
    """

    # Class-level metadata (override in subclasses)
    name: str = ""
    description: str = ""
    label: Optional[str] = None  # 技能中文显示名称
    skill_type: SkillType = SkillType.CONTEXTUAL
    version: str = "1.0.0"

    def __init__(self):
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name' attribute")
        if not self.description:
            raise ValueError(f"{self.__class__.__name__} must define 'description' attribute")

        self._tools: Dict[str, ToolMetadata] = {}
        self._register_tools()

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Get skill-specific system prompt.

        This prompt is injected when the skill is active.
        Should describe the skill's capabilities and usage guidelines.

        Returns:
            System prompt string
        """
        pass

    def _register_tools(self) -> None:
        """Auto-register methods decorated with @skill_tool."""
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if hasattr(attr, '_is_skill_tool'):
                metadata: ToolMetadata = attr._tool_metadata
                metadata.handler = getattr(self, attr_name)
                self._tools[metadata.name] = metadata

    def get_tools(self) -> List[ToolMetadata]:
        """Get all tools provided by this skill."""
        return list(self._tools.values())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Get OpenAI function calling schemas for all tools."""
        return [tool.to_schema() for tool in self._tools.values()]

    def get_tool(self, name: str) -> Optional[Callable]:
        """Get tool handler by name."""
        tool = self._tools.get(name)
        return tool.handler if tool else None

    def has_tool(self, name: str) -> bool:
        """Check if skill provides a tool."""
        return name in self._tools

    async def execute_tool(self, name: str, *args, **kwargs) -> Any:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            *args: Positional arguments
            **kwargs: Keyword arguments (including ctx)

        Returns:
            Tool result

        Raises:
            ValueError: If tool not found
        """
        handler = self.get_tool(name)
        if not handler:
            raise ValueError(f"Tool '{name}' not found in skill '{self.name}'")
        return await handler(*args, **kwargs)

    def on_activate(self, context: 'ServiceContext') -> None:
        """
        Called when skill is activated.

        Override to perform initialization.
        """
        pass

    def on_deactivate(self, context: 'ServiceContext') -> None:
        """
        Called when skill is deactivated.

        Override to perform cleanup.
        """
        pass


# Tool decorator
def skill_tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    label: Optional[str] = None,  # 中文显示名称
    sensitive: bool = False,
    parameters: Optional[Dict[str, Any]] = None
):
    """
    Decorator to mark a method as a skill tool.

    Usage:
        class MySkill(SkillBase):
            @skill_tool(description="Does something cool", label="做很酷的事情")
            async def my_tool(self, arg: str, ctx: ServiceContext) -> str:
                return f"Result: {arg}"

    Args:
        name: Tool name (defaults to method name)
        description: Tool description for LLM
        label: 中文显示名称，用于前端渲染
        sensitive: Whether tool requires approval
        parameters: Parameter schema (optional)
    """
    def decorator(func: Callable) -> Callable:
        # 1. 分析原始函数的参数签名
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

        # 2. 创建 Wrapper 进行参数过滤
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # args[0] 是 self (因为是类方法)
            
            # 过滤 kwargs
            if has_var_keyword:
                filtered_kwargs = kwargs
            else:
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}
            
            # 执行
            if inspect.iscoroutinefunction(func):
                return await func(*args, **filtered_kwargs)
            else:
                return func(*args, **filtered_kwargs)

        # 3. 附加元数据
        # 注意：这里把 metadata 挂在 wrapper 上，而不是原 func 上，
        # 因为 SkillBase._register_tools 获取的是 getattr(self, name)，拿到的是 wrapper
        wrapper._is_skill_tool = True
        wrapper._tool_metadata = ToolMetadata(
            name=name or func.__name__,
            description=description or func.__doc__ or "No description",
            label=label,  # 中文显示名称
            parameters=parameters or {},
            is_sensitive=sensitive,
            # Handler 会在 SkillBase._register_tools 里被再次赋值为 bound method
            # 这里先留空或者指向 wrapper 自身
            handler=None
        )
        return wrapper

    return decorator


class GlobalSkill(SkillBase):
    """
    Base class for global skills.

    Global skills are always available and don't require activation.
    """

    skill_type = SkillType.GLOBAL

    def get_system_prompt(self) -> str:
        return f"""
You have access to the {self.name} capability.

{self.description}

Available tools: {', '.join(self._tools.keys())}
"""


class ContextualSkill(SkillBase):
    """
    Base class for contextual skills.

    Contextual skills require explicit activation.
    """

    skill_type = SkillType.CONTEXTUAL

    def get_system_prompt(self) -> str:
        return f"""
=== ACTIVATED SKILL: {self.name} ===

{self.description}

You are now in {self.name} mode. Available tools:
{chr(10).join(f'- {name}: {meta.description}' for name, meta in self._tools.items())}

Follow these instructions:
1. Use the available tools to accomplish user requests
2. If the request is outside this skill's scope, call exit_skill
3. Be concise and helpful
"""

