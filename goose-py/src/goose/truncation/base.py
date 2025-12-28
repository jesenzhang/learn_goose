from abc import ABC, abstractmethod
from typing import List
from ..conversation import Message

class ContextManager(ABC):
    @abstractmethod
    async def process(self, messages: List[Message], system_prompt: str) -> List[Message]:
        """处理消息列表，返回符合上下文限制的新列表"""
        pass