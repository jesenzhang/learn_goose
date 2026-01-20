"""
Generic Skill - Dynamically created skill from functions.
"""

import inspect
from typing import Any, Callable, Dict, List
from .base import SkillBase, ContextualSkill, ToolMetadata

class GenericSkill(ContextualSkill):
    """
    Generic skill created from a set of functions.
    """

    def __init__(self, name: str, description: str, functions: Dict[str, Callable], label: str = None):
        # Temporarily store functions to register after parent init
        self._pending_functions = functions

        # Set attributes required by Base
        self.name = name
        self.description = description
        self.label = label  # 技能中文显示名称

        # Initialize Base (creates self._tools)
        super().__init__()

        # Register functions
        for func_name, func in self._pending_functions.items():
            self._register_function(func_name, func)

    def get_system_prompt(self) -> str:
        return f"""
=== SKILL: {self.name} ===
{self.description}
Available tools: {', '.join(self._tools.keys())}
"""

    def _register_function(self, name: str, func: Callable) -> None:
        doc = func.__doc__ or f"Tool: {name}"
        params = self.extract_params(func) # Use static method

        metadata = ToolMetadata(
            name=name,
            description=doc,
            parameters=params,
            handler=self.make_handler(func) # Use static method
        )
        self._tools[name] = metadata

    @staticmethod
    def extract_params(func: Callable) -> Dict[str, Any]:
        """Static utility to extract parameter schema."""
        try:
            sig = inspect.signature(func)
        except ValueError:
            return {"type": "object", "properties": {}}

        properties = {}
        required = []

        for param_name, param in sig.parameters.items():
            if param_name in ('_state', '_ctx', 'ctx', '_ai', '_db', 'kwargs', 'args'):
                continue

            # Default to string if no annotation
            param_type = param.annotation if param.annotation != inspect.Parameter.empty else str
            properties[param_name] = {"type": GenericSkill._type_to_string(param_type)}

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }

    @staticmethod
    def _type_to_string(t: Any) -> str:
        type_map = {
            str: "string", int: "integer", float: "number", 
            bool: "boolean", list: "array", dict: "object"
        }
        return type_map.get(t, "string")

    # =========================================================================
    # [FIXED] 智能参数过滤 Wrapper
    # =========================================================================
    @staticmethod
    def make_handler(func: Callable) -> Callable:
        """
        Static utility to create async wrapper.
        Includes argument filtering to prevent TypeError when extra args (like ctx) are injected.
        """
        # 1. 预先检查底层函数的签名
        sig = inspect.signature(func)
        # 检查是否接受 **kwargs
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        # 获取所有有效参数名
        valid_params = set(sig.parameters.keys())

        async def wrapper(**kwargs):
            # 2. 过滤参数
            if has_var_keyword:
                # 如果底层函数接受 **kwargs，则透传所有参数（包括 ctx）
                filtered_kwargs = kwargs
            else:
                # 否则，只传递底层函数显式声明的参数
                filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}

            # 3. 执行
            if inspect.iscoroutinefunction(func):
                return await func(**filtered_kwargs)
            else:
                return func(**filtered_kwargs)
        
        return wrapper