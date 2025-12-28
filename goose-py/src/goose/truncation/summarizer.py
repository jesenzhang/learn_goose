from .base import ContextManager
from ..conversation import Message, Role, MessageMetadata
from ..providers.base import Provider

class SummarizationManager(ContextManager):
    def __init__(self, provider: Provider, max_tokens: int = 8000):
        self.provider = provider
        self.max_tokens = max_tokens

    async def process(self, messages: List[Message], system_prompt: str) -> List[Message]:
        # 1. 检查是否需要压缩
        # (复用 check_if_compaction_needed 逻辑)
        # ...
        
        # 2. 如果需要，执行 do_compact
        # ...
        
        return compacted_messages