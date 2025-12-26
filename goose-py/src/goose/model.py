# model.py
from typing import Optional
from pydantic import BaseModel

# 对应 model.rs 中的 MODEL_SPECIFIC_LIMITS
MODEL_LIMITS = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385,
    "claude-3-5-sonnet": 200_000,
    # ... 其他模型
}

DEFAULT_CONTEXT_LIMIT = 128_000

class ModelConfig(BaseModel):
    """对应 Rust: pub struct ModelConfig"""
    model_name: str
    context_limit: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    
    def context_window(self) -> int:
        if self.context_limit:
            return self.context_limit
        # 简单的模糊匹配查找限制，模拟 Rust 的 get_model_specific_limit
        for key, limit in MODEL_LIMITS.items():
            if key in self.model_name:
                return limit
        return DEFAULT_CONTEXT_LIMIT