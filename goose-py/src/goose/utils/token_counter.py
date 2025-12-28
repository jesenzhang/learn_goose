import tiktoken
import json
import logging
from typing import List, Dict, Any, Optional
from collections import OrderedDict
from ..conversation import Message, MessageContent, TextContent, ToolRequest, ToolResponse, Role

# --- Constants from Rust Implementation ---
MAX_TOKEN_CACHE_SIZE = 10_000

# Token use for various bits of tool calls
FUNC_INIT = 7
PROP_INIT = 3
PROP_KEY = 3
ENUM_INIT = -3
ENUM_ITEM = 3
FUNC_END = 12

class TokenCounter:
    _instance = None

    def __new__(cls, model_name: str = "gpt-4o"):
        if cls._instance is None:
            cls._instance = super(TokenCounter, cls).__new__(cls)
            cls._instance._initialize(model_name)
        return cls._instance

    def _initialize(self, model_name: str):
        try:
            self.tokenizer = tiktoken.encoding_for_model(model_name)
        except KeyError:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Cache mechanism (mimicking Rust's DashMap with limited size)
        self.token_cache: OrderedDict[str, int] = OrderedDict()

    def count_tokens(self, text: str) -> int:
        """
        Calculates tokens with caching. (Base function)
        """
        if not text:
            return 0

        # Check cache
        if text in self.token_cache:
            self.token_cache.move_to_end(text) # LRU update
            return self.token_cache[text]

        # Calculate
        tokens = self.tokenizer.encode(text, allowed_special={'<|endoftext|>', '<|im_start|>', '<|im_end|>'})
        count = len(tokens)

        # Cache eviction management
        if len(self.token_cache) >= MAX_TOKEN_CACHE_SIZE:
            self.token_cache.popitem(last=False) # Remove oldest

        self.token_cache[text] = count
        return count

    # 兼容性别名
    def count_string(self, text: str) -> int:
        return self.count_tokens(text)

    def count_message(self, message: Message) -> int:
        """
        [新增] 计算单条消息的 Token
        逻辑提取自 Rust 的 count_chat_tokens 循环体
        """
        # Rust logic: let tokens_per_message = 4;
        num_tokens = 4
        
        for content in message.content:
            if isinstance(content, TextContent):
                num_tokens += self.count_tokens(content.text)
            
            elif isinstance(content, ToolRequest):
                # Rust: format!("{}:{}:{:?}", id, name, arguments)
                if content.tool_call.value:
                    tool_call = content.tool_call.value
                    args_str = json.dumps(tool_call.arguments)
                    text = f"{content.id}:{tool_call.name}:{args_str}"
                    num_tokens += self.count_tokens(text)
            
            elif isinstance(content, ToolResponse):
                 if content.tool_result.value:
                    for item in content.tool_result.value.content:
                        if item.text:
                            num_tokens += self.count_tokens(item.text)
        
        # 注意：这里不加 reply primer (3)，那个是整个对话加一次
        return num_tokens

    def count_messages(self, messages: List[Message]) -> int:
        """
        [新增] 计算消息列表的总 Token (用于历史记录截断)
        """
        total = 0
        for msg in messages:
            total += self.count_message(msg)
        
        # 加上 Reply primer (3)
        total += 3
        return total

    def count_tokens_for_tools(self, tools: List[Dict[str, Any]]) -> int:
        """
        Strictly aligned with Rust `count_tokens_for_tools`
        """
        func_token_count = 0
        if not tools:
            return 0

        for tool in tools:
            func_token_count += FUNC_INIT
            
            name = tool.get("name", "")
            description = tool.get("description", "") or ""
            description = description.rstrip('.')

            line = f"{name}:{description}"
            func_token_count += self.count_tokens(line)

            # Handle Schema Properties
            schema = tool.get("input_schema", tool.get("parameters", {}))
            properties = schema.get("properties", {})
            
            if properties:
                func_token_count += PROP_INIT
                for key, value in properties.items():
                    func_token_count += PROP_KEY
                    
                    p_name = key
                    p_type = value.get("type", "")
                    p_desc = value.get("description", "") or ""
                    p_desc = p_desc.rstrip('.')

                    line = f"{p_name}:{p_type}:{p_desc}"
                    func_token_count += self.count_tokens(line)

                    # Handle Enums
                    if "enum" in value and isinstance(value["enum"], list):
                        func_token_count += ENUM_INIT 
                        for item in value["enum"]:
                            if isinstance(item, str):
                                func_token_count += ENUM_ITEM
                                func_token_count += self.count_tokens(item)
            
            func_token_count += FUNC_END

        return func_token_count

    def count_chat_tokens(
        self,
        system_prompt: str,
        messages: List[Message],
        tools: List[Dict[str, Any]]
    ) -> int:
        """
        Strictly aligned with Rust `count_chat_tokens`
        """
        num_tokens = 0
        tokens_per_message = 4

        # 1. System Prompt
        if system_prompt:
            num_tokens += self.count_tokens(system_prompt) + tokens_per_message

        # 2. Messages (使用 count_message 复用逻辑)
        for message in messages:
            if not message.metadata.agent_visible:
                continue
            num_tokens += self.count_message(message)
        
        # 3. Tools
        if tools:
            num_tokens += self.count_tokens_for_tools(tools)

        # 4. Reply Primer
        num_tokens += 3 
        return num_tokens

# Factory function
def create_token_counter(model_name: str = "gpt-4o") -> TokenCounter:
    return TokenCounter(model_name)


def estimate_tokens(text: str) -> int:
    """
    粗略估算 Token 数。
    对于英文，约 4 字符 = 1 Token。
    对于中文，约 0.7 字符 = 1 Token。
    这里使用保守的加权平均。
    """
    if not text:
        return 0
    return len(text) // 3  # 简单粗暴但有效的估算

def count_message_tokens(msg: Message) -> int:
    """计算单条消息的 Token"""
    count = 0
    # 估算 Role 开销
    count += 5 
    
    for content in msg.content:
        if isinstance(content, TextContent):
            count += estimate_tokens(content.text)
        elif isinstance(content, ToolRequest):
            # 工具调用的 JSON 开销
            if content.tool_call.value:
                count += estimate_tokens(str(content.tool_call.value.arguments))
                count += estimate_tokens(content.tool_call.value.name)
        elif isinstance(content, ToolResponse):
            # 工具结果通常很大，是压缩的重点
            for raw in content.tool_result.content:
                if raw.text:
                    count += estimate_tokens(raw.text)
    return count

def count_history_tokens(messages: List[Message]) -> int:
    return sum(count_message_tokens(m) for m in messages)