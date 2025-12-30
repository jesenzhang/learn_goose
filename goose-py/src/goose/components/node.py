import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Type, Optional, ClassVar, Union
from pydantic import BaseModel, ValidationError

# 引入底层能力
from ..workflow.runnable import Runnable, WorkflowContext
from ..workflow.nodes import BaseCozeNode

logger = logging.getLogger("goose.component")

class ComponentNode(BaseCozeNode, ABC):
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

    def __init__(self, inputs: Dict[str, Any] = None, node_id: str = None, raw_config: Dict[str, Any] = None):
        super().__init__(inputs, node_id, raw_config)
        
    async def invoke(self, inputs: Any, context: WorkflowContext) -> Dict[str, Any]:
        """
        [Template Method] 标准执行流
        Scheduler 调用的唯一入口。
        """
        try:
            self.set_inputs(inputs) # 设置输入
            
            # 1. 解析动态引用 (Resolution)
            # context -> raw_inputs (dict)
            resolved_inputs = self.resolve_inputs(context)
            
            if inputs and isinstance(inputs, dict):
                resolved_inputs.update(inputs)
            
            # 2. 校验配置 (Validation - Config)
            validated_config = self._validate_model(
                self.raw_config, self.config_model, "Config"
            )

            # 3. 校验输入 (Validation - Inputs)
            validated_inputs = self._validate_model(
                resolved_inputs, self.input_model, "Input"
            )

            # 4. 执行业务逻辑 (Execution)
            # 此时传入的已是 Pydantic 对象
            result = await self.execute(validated_inputs, validated_config)

            # 5. 处理结果 (Normalization)
            return self._normalize_output(result)

        except Exception as e:
            # 统一错误处理，附带节点信息
            node_label = getattr(self, "label", self.__class__.__name__)
            logger.error(f"❌ Node '{node_label}' ({self.node_id}) failed: {e}", exc_info=True)
            raise e

    @abstractmethod
    async def execute(self, inputs: Any, config: Any) -> Any:
        """
        [Hook] 子类必须实现的业务逻辑。
        """
        pass

    def _validate_model(self, data: Dict, model: Type[BaseModel], label: str) -> Any:
        """辅助方法：Pydantic 校验"""
        if model is None:
            return data # 如果没定义模型，透传字典
        try:
            return model.model_validate(data or {})
        except ValidationError as e:
            raise ValueError(f"{label} Validation Error: {e}")

    def _normalize_output(self, result: Any) -> Dict[str, Any]:
        """辅助方法：确保返回字典"""
        if self.output_model and isinstance(result, self.output_model):
            return result.model_dump()
        
        if isinstance(result, BaseModel):
            return result.model_dump()
            
        if not isinstance(result, dict):
            return {"output": result}
            
        return result