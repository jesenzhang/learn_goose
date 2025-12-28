from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TypeVar, Generic
from pydantic import BaseModel

# 上下文对象：在 DAG 节点间传递的数据
class WorkflowContext(BaseModel):
    session_id: str
    variables: Dict[str, Any] = {} # 全局变量
    
    def get(self, key: str, default=None):
        return self.variables.get(key, default)
    
    def set(self, key: str, value: Any):
        self.variables[key] = value

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")

class Runnable(ABC, Generic[TInput, TOutput]):
    """
    所有工作流节点的基础接口。
    """
    
    @abstractmethod
    async def invoke(self, input: TInput, context: WorkflowContext) -> TOutput:
        """
        执行节点逻辑。
        :param input: 上一个节点的输出，或者指定的输入参数
        :param context: 工作流的全局上下文 (包含 session_id)
        :return: 节点的输出
        """
        pass

    # 未来可以扩展:
    # async def stream(...)
    # async def batch(...)