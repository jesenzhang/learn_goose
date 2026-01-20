import inspect
import logging
from typing import Dict, Any, Optional, Callable, List, Union, Type
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
from abc import ABC, abstractmethod
from pydantic import BaseModel,Field,create_model


logger = logging.getLogger(__name__)


class ToolSourceType(str, Enum):
    """Types of tool registration"""
    DECORATOR = "decorator"     # Registered via @register_tool decorator
    SKILL = "skill"             # Loaded from skill directory (SKILL.md)
    MCP = "mcp"                 # From MCP extension
    BUILTIN = "builtin"         # Built-in tool

@dataclass
class ToolInfo:
    """Metadata about a tool."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Return tool identifier."""
        return self.name



class ToolState(str, Enum):
    """Tool execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CACHED = "cached"



@dataclass
class ToolDefinition:
    """Metadata for a registered tool"""
    name: str
    description: str
    function: Callable
    source_type: ToolSourceType
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: Optional[str] = None
    enabled: bool = True
    permission: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    
    @property
    def id(self) -> str:
        """Unique identifier"""
        return self.name

# ============================================================================
# Tool Base Classes
# ============================================================================

@dataclass
class ToolResult:
    """Result of a tool execution."""
    content: str = ""
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    state: ToolState = ToolState.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "content": self.content,
            "artifacts": self.artifacts,
            "error": self.error,
            "state": self.state.value,
            "metadata": self.metadata,
        }
        
    # 辅助方法：判断是否成功
    @property
    def is_success(self) -> bool:
        return self.state == ToolState.COMPLETED and self.error is None

class ToolError(Exception):
    """Base exception for tool errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ToolInputSchema(BaseModel):
    """Base model for tool input validation"""
    class Config:
        extra = "forbid"


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
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters: Dict[str, Any] = {}
        if self.input_schema:
            parameters = {
                name: {
                    "type": field_info.annotation.__name__ if hasattr(field_info.annotation, "__name__") else str(field_info.annotation),
                    "description": field_info.description or "",
                    "default": field_info.default if field_info.default is not Field.default else None,
                }
                for name, field_info in self.input_schema.model_fields.items()
            }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
        
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

    async def run(self, params: Dict[str, Any]) -> ToolResult:
        """
        外壳方法：负责校验参数、捕获异常，并统一包装为 ToolResult
        """
        try:
            # 1. 参数校验
            validated_params = self.validate_params(params)
            
            # 2. 执行具体逻辑
            raw_result = await self.execute(validated_params)
            
            # 3. 结果包装 (自动归一化)
            return self._wrap_success(raw_result)

        except ToolError as e:
            # 捕获预期的工具错误（如：文件不存在）
            return ToolResult(
                error=e.message,
                state=ToolState.FAILED,
                metadata=e.details
            )
        except Exception as e:
            # 捕获未知的系统错误（如：网络超时，代码Bug）
            return ToolResult(
                error=f"System Error: {str(e)}",
                state=ToolState.FAILED
            )

    def _wrap_success(self, result: Any) -> ToolResult:
        """将各种类型的原始返回值转换为 ToolResult"""
        if isinstance(result, ToolResult):
            return result
            
        # 如果是字典或列表，转为 JSON 字符串，保留原始对象在 metadata 中
        if isinstance(result, (dict, list)):
            content = json.dumps(result, ensure_ascii=False, indent=2)
            return ToolResult(content=content, metadata={"raw": result})
            
        # 默认转为字符串
        return ToolResult(content=str(result))



class FunctionTool(BaseTool):
    """
    一个通用的适配器，将普通函数包装成 BaseTool。
    这样普通函数也能获得参数校验、异常捕获和结果标准化的能力。
    """
    def __init__(self, func: Callable, schema: Dict[str, Any], **kwargs):
        self._func = func
        # 动态创建 Pydantic 模型，用于 BaseTool.validate_params
        # 注意：这里简化了逻辑，生产环境可能需要更复杂的 create_model 逻辑
        self.input_schema = self._create_input_model(func, schema)
        
        # 初始化基类
        super().__init__(config=kwargs)
        self.name = kwargs.get("name", func.__name__)
        self.description = kwargs.get("description", func.__doc__ or "")
        self.category = kwargs.get("category")

    async def execute(self, params: BaseModel) -> Any:
        """
        核心逻辑：解包 Pydantic 对象，调用原始函数
        """
        # 1. 将 Pydantic 对象转为字典
        kwargs = params.model_dump() # Pydantic V2
        
        # 2. 处理依赖注入 (Context/State/DB)
        # 注意：这里需要配合 Executor 的注入逻辑，或者在这里手动处理
        # 简单起见，我们假设 Executor 依然负责注入，或者函数本身不依赖注入
        # 如果需要注入，这里需要获取 context，这通常通过 self.config 或其他方式传递
        
        # 3. 调用原始函数
        if inspect.iscoroutinefunction(self._func):
            return await self._func(**kwargs)
        else:
            return self._func(**kwargs)

    def _create_input_model(self, func: Callable, json_schema: Dict[str, Any]) -> Type[BaseModel]:
        """
        (高级) 将 JSON Schema 或 函数签名 动态转换为 Pydantic Model 类
        为了简单演示，这里我们可以暂时忽略 strict schema，
        或者使用 pydantic.create_model 动态创建。
        """
        # 这里为了演示 BaseTool 流程，我们假设 params 直接传进来就是合法的
        # 实际实现中，你需要在这里把 registry 提取的 schema 转回 Pydantic model
        # 这是一个比较复杂的元编程话题。
        pass
        
    # 为了简化，我们可以重写 validate_params，
    # 如果 FunctionTool 初始化太复杂，可以直接跳过 Pydantic 校验，
    # 依靠函数自身的类型提示。
    def validate_params(self, params: Dict[str, Any]) -> BaseModel:
        # 偷懒做法：如果不方便动态生成 Model，可以用个简单的 DictWrapper
        # 但最好的做法是在注册时生成好 Model
        class DynamicModel(BaseModel):
            class Config:
                extra = "allow" # 允许任意参数
        
        return DynamicModel(**params)


class InvalidTool(BaseTool):
    """Tool that represents an invalid or unknown tool request."""

    name = "invalid"
    description = "Invalid tool - used for unknown tool names"

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            content="",
            error=f"Unknown tool: {params.get('tool_name', 'unknown')}",
            state=ToolState.ERROR,
        )
        