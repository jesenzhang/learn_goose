from abc import ABC, abstractmethod
from typing import Any, Dict, TypeVar, Generic
from .context import WorkflowContext

TInput = TypeVar("TInput")
TOutput = TypeVar("TOutput")

class Runnable(ABC, Generic[TInput, TOutput]):
    """
    工作流节点的标准接口。
    类似于 LangChain 的 Runnable 或 LangGraph 的 Node。
    """
    
    @abstractmethod
    async def invoke(self, input: TInput, context: WorkflowContext) -> TOutput:
        """
        执行节点逻辑。
        :param input: 上游节点的输出 (如果是起始节点，则为初始输入)
        :param context: 全局上下文 (Session ID, 共享变量)
        :return: 本节点的输出 (将传递给下游节点)
        """
        pass