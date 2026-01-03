import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, ClassVar, Union, Callable, List
from pydantic import BaseModel, ValidationError
import re
import asyncio
import inspect

from .runnable import Runnable
from .context import WorkflowContext
from ..agent import Agent
from goose.toolkit import Tool
from ..utils.concurrency import run_blocking
from .resolver import ValueResolver 

logger = logging.getLogger("goose.workflow.nodes")


class CozeNodeMixin:
    """
    Mixin: 提供 Coze/Dify 风格的参数映射功能。
    核心能力：
    1. 解析引用: {{ node_id.key }}
    2. 解析变量: {{ item }} (用于 Map/Loop)
    3. 递归解析: 支持字典和列表结构的配置解析
    """
    
    def resolve_inputs(self,data: Dict[str, Any], context: WorkflowContext, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        委托给 ValueResolver 进行解析
        """
        if not data:
            return {}
        return ValueResolver.resolve(data, context, overrides)

    def _resolve_any(self, value: Any, context: WorkflowContext, overrides: Dict[str, Any]) -> Any:
        """递归解析任意类型的值"""
        if isinstance(value, str):
            return self._resolve_string(value, context, overrides)
        elif isinstance(value, dict):
            return {k: self._resolve_any(v, context, overrides) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._resolve_any(v, context, overrides) for v in value]
        else:
            return value

    def _resolve_string(self, template: str, context: WorkflowContext, overrides: Dict[str, Any]) -> Any:
        """解析单个字符串值"""
        if not template:
            return template
            
        template = template.strip()

        # 1. 检查 Overrides (精确匹配 {{ var }})
        # 用于 Loop/Map 中的 item 引用
        var_match = re.match(r"^\{\{\s*([a-zA-Z0-9_]+)\s*\}\}$", template)
        if var_match:
            key = var_match.group(1)
            if key in overrides:
                return overrides[key]

        # 2. 检查引用 (Reference {{ node.key }})
        ref_match = re.match(r"^\{\{\s*([a-zA-Z0-9_\-]+)\.(.+)\s*\}\}$", template)
        if ref_match:
            node_id = ref_match.group(1)
            path_str = ref_match.group(2).strip()
            return self._get_deep_value(context, node_id, path_str)

        # 3. (Todo) 支持混合字符串插值 "Hello {{ name }}"
        # 目前简单处理：如果是纯引用则替换对象，否则返回原字符串
        # 如需支持混合插值，建议引入 Jinja2 或 TemplateRenderer
        return template

    def _get_deep_value(self, context: WorkflowContext, node_id: str, path_str: str) -> Any:
        """
        递归查找 context.node_outputs 中的值
        """
        # 从 Scheduler 的 Context 中获取节点输出
        # Start 节点的输入数据通常也存储在 node_outputs['start'] 中
        node_output = context.node_outputs.get(node_id)
        
        if node_output is None:
            # 找不到上游节点输出，返回 None 或保留模板字符串
            return None

        current_data = node_output
        keys = path_str.split(".")
        
        try:
            for k in keys:
                # 数组索引支持 (e.g. list.0.name)
                if isinstance(current_data, list) and k.isdigit():
                    idx = int(k)
                    if 0 <= idx < len(current_data):
                        current_data = current_data[idx]
                    else:
                        return None
                elif isinstance(current_data, dict):
                    current_data = current_data.get(k)
                elif hasattr(current_data, k):
                    # 支持对象属性访问 (Pydantic Model)
                    current_data = getattr(current_data, k)
                else:
                    return None # Path 不存在
                
                if current_data is None:
                    return None
            return current_data
        except Exception:
            return None


class ComponentNode(Runnable, CozeNodeMixin, ABC):
    """
    [机制层] ComponentNode
    封装了组件在工作流中运行的所有通用逻辑：
    1. 继承 Runnable -> 可被 Scheduler 调度
    2. 继承 CozeNodeMixin -> 可解析 {{ ref }} 引用
    3. 实现 Pydantic 校验 -> 保证输入输出类型安全
    """

    # --- 契约定义 (由子类提供) ---
    config_model: ClassVar[Optional[Type[BaseModel]]] = None
    input_model: ClassVar[Optional[Type[BaseModel]]] = None
    output_model: ClassVar[Optional[Type[BaseModel]]] = None

    def __init__(self):
        super().__init__()

    
    def set_config_model(self, config_model: Type[BaseModel]):
        self.config_model = config_model
    def set_input_model(self, input_model: Type[BaseModel]):
        self.input_model = input_model
    def set_output_model(self, output_model: Type[BaseModel]):
        self.output_model = output_model

    async def invoke(self, inputs: Dict[str, Any], config: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        """
        [Template Method] 标准执行流
        Scheduler 调用的唯一入口。
        """
        try:
            raw_config =config
            
            node_id = config.get("id", "unknown")
            
            resolved_inputs = self.resolve_inputs(inputs,context)
            
            # 2. 校验配置 (Validation - Config)
            validated_config = self._validate_model(
                raw_config, self.config_model, "Config"
            )

            # 3. 校验输入 (Validation - Inputs)
            validated_inputs = self._validate_model(
                resolved_inputs, self.input_model, "Input"
            )
            sig = inspect.signature(self.execute)
            params = sig.parameters
            call_kwargs = {}
            if "context" in params or any(p.kind == p.VAR_KEYWORD for p in params.values()):
                call_kwargs["context"] = context
            if "config" in params or any(p.kind == p.VAR_KEYWORD for p in params.values()):
                call_kwargs["config"] = validated_config
            
            # 4. 执行业务逻辑 (Execution)
            # 此时传入的已是 Pydantic 对象
            result = await self.execute(inputs=validated_inputs,**call_kwargs)

            # 5. 处理结果 (Normalization)
            return self._normalize_output(result)

        except Exception as e:
            # 统一错误处理，附带节点信息
            node_label = getattr(self, "label", self.__class__.__name__)
            logger.error(f"❌ Node '{node_label}' ({node_id}) failed: {e}", exc_info=True)
            raise e

    @abstractmethod
    async def execute(self, inputs: Any,**kwargs) -> Any:
        """
        [Hook] 子类必须实现的业务逻辑。
        """
        pass

    def _validate_model(self, data: Dict, model: Type[BaseModel], label: str) -> Any:
        """辅助方法：Pydantic 校验"""
        if model is None:
            return data or {}
        try:
            # 2. 校验
            validated = model.model_validate(data or {})
            # 如果模型是动态生成的“允许任意字段”的空模型 (对应 inputs: Dict)
            # 我们应该返回它的 model_dump() (即字典)，而不是对象
            # 否则 execute(self, inputs: Dict) 接收到的是一个 BaseModel 实例，会报错
            if not model.model_fields and hasattr(model, "model_config") and model.model_config.get("extra") == "allow":
                # 检查是否是那个仅用于占位的空模型
                if not model.model_fields: 
                    return validated.model_dump()
            
            return validated
        except ValidationError as e:
            raise ValueError(f"{label} Validation Error: {e}")

    def _normalize_output(self, result: Any) -> Dict[str, Any]:
        """辅助方法：确保返回字典"""
        if result is None: return {}
        
        if self.output_model and isinstance(result, self.output_model):
            return result.model_dump()
        
        if isinstance(result, BaseModel):
            return result.model_dump()
            
        if not isinstance(result, dict):
            return {"output": result}
            
        return result
    
    
class BaseCozeNode(Runnable, CozeNodeMixin):
    """
    所有 Coze 风格节点的基类。
    关键特性：在 invoke 阶段自动执行 resolve_inputs。
    """
    def __init__(self):
        # 显式声明无参 init，防止调用者错误传递状态
        pass
        
    async def invoke(self, input_data: Any, context: WorkflowContext) -> Dict[str, Any]:
        """
        标准入口：解析参数 -> 执行核心逻辑
        """
        # 1. 解析参数 (Inputs Mapping -> Real Values)
        kwargs = self.resolve_inputs(input_data,context)
        
        # 2. 如果 Scheduler 传入了 input_data (通常是 Start 节点的情况)，合并进去
        if input_data and isinstance(input_data, dict):
            kwargs.update(input_data)
        
        # 3. 执行核心逻辑 (多态)
        return await self.execute_with_args(kwargs, context)

    async def execute_with_args(self, kwargs: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        """
        核心执行逻辑 (抽象方法)。
        kwargs 已经是解析好的真实值 (e.g. "Goose" 而不是 "{{ start.name }}")。
        """
        raise NotImplementedError


class FunctionNode(BaseCozeNode):
    def __init__(self, func: Callable, inputs: Dict[str, Any], name: str = "Func"):
        super().__init__(inputs)
        self.func = func
        self.name = name

    async def execute_with_args(self, kwargs: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        logger.info(f"⚡ [FunctionNode: {self.name}] Args Keys: {list(kwargs.keys())}")
        try:
            if asyncio.iscoroutinefunction(self.func):
                result = await self.func(**kwargs)
            else:
                result = self.func(**kwargs)
            
            # 规范化输出
            if isinstance(result, dict):
                return result
            return {"output": result}
        except Exception as e:
            logger.error(f"❌ [FunctionNode: {self.name}] Error: {e}", exc_info=True)
            raise e


class AgentNode(BaseCozeNode):
    def __init__(self, agent: Agent, inputs: Dict[str, Any], name: str = None):
        super().__init__(inputs)
        self.agent = agent
        self.name = name or agent.name

    async def execute_with_args(self, kwargs: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        # 1. 获取已解析的输入
        user_input = kwargs.get("input") or str(kwargs)
        
        # 2. [关键修复] 使用主 Workflow Session ID
        # 避免 "FOREIGN KEY constraint failed" 错误
        target_session_id = context.session_id
        
        logger.info(f"🤖 [AgentNode: {self.name}] Input: {str(user_input)[:100]}... Session: {target_session_id}")
        
        final_response = []
        # 调用 Agent
        async for event in self.agent.reply(target_session_id, user_input=str(user_input)):
           
            final_response.append(event.text)
            # 这里可以扩展处理 ToolCall 等其他事件
        
        result_text = "".join(final_response)
        
        # 返回结果 (可以是 dict，Scheduler 已修复支持 Any 类型输出)
        return {
            "output": result_text,
            "request": user_input
        }


class ToolNode(BaseCozeNode):
    def __init__(self, tool: Tool, inputs: Dict[str, Any]):
        super().__init__(inputs)
        self.tool = tool

    async def execute_with_args(self, kwargs: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        logger.info(f"🛠️ [ToolNode: {self.tool.name}] Args: {kwargs}")
        try:
            if asyncio.iscoroutinefunction(self.tool.run):
                result = await self.tool.run(**kwargs)
            else:
                result = await run_blocking(self.tool.run, **kwargs)
            
            # ToolResult 处理
            if hasattr(result, 'is_error') and result.is_error:
                raise RuntimeError(f"Tool execution failed: {result.content}")
            
            # 提取文本内容
            output_text = ""
            if hasattr(result, 'content') and result.content:
                output_text = result.content[0].text
            else:
                output_text = str(result)

            return {"output": output_text}
        except Exception as e:
            logger.error(f"❌ Tool Error: {e}", exc_info=True)
            raise e


class MapNode(BaseCozeNode):
    """
    [高级节点] Map Node
    并发地对列表中的每个元素执行子节点逻辑。
    """
    def __init__(self, node: BaseCozeNode, inputs: Dict[str, Any], max_concurrency: int = 5):
        super().__init__(inputs)
        
        # 强制要求子节点必须是 BaseCozeNode (实现了 resolve_inputs)
        if not isinstance(node, BaseCozeNode):
            raise TypeError("MapNode child must be a BaseCozeNode (AgentNode, FunctionNode, etc.)")
            
        self.node = node
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def execute_with_args(self, kwargs: Dict[str, Any], context: WorkflowContext) -> Dict[str, Any]:
        """
        kwargs 是 MapNode 自身的参数，通常包含一个名为 'list' 的列表。
        """
        data_list = kwargs.get("list", [])
        if not isinstance(data_list, list):
            logger.warning(f"MapNode input 'list' is not a list: {type(data_list)}. Converting to empty list.")
            data_list = []

        logger.info(f"🔄 [MapNode] Processing {len(data_list)} items")

        async def worker(item, index):
            async with self.semaphore:
                # [核心逻辑]
                # 1. 构造 Override 字典，注入 {{ item }} 和 {{ index }}
                # 这样子节点的 inputs_mapping 配置 (如 input="{{ item.name }}") 就能正确解析
                overrides = {"item": item, "index": index}
                
                # 2. 为子节点解析参数
                # 注意：我们调用子节点的 resolve_inputs，利用子节点的 inputs_mapping + 我们的 overrides
                child_kwargs = self.node.resolve_inputs(context, overrides=overrides)
                
                # 3. 调用子节点的执行逻辑
                return await self.node.execute_with_args(child_kwargs, context)

        # 并发执行
        tasks = [worker(item, i) for i, item in enumerate(data_list)]
        if tasks:
            results = await asyncio.gather(*tasks)
        else:
            results = []
        
        return {"output": results}