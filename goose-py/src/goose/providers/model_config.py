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
    """统一的模型配置对象"""
    provider: str = "openai"  # openai, ollama, azure...
    model_name: str = "gpt-4o"      # 模型名称
    base_url: Optional[str] = None
    api_key_env: str = "OPENAI_API_KEY"
    api_key: Optional[str] = None
    
    # 运行时参数
    context_limit: Optional[int] = None
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    timeout: float = 60.0
    fast_model: Optional[str] = None
    
    toolshim: bool = False
    toolshim_model: Optional[str] = None
    
    # 高级参数
    organization: Optional[str] = None
    project: Optional[str] = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    
    # Embedding 专用 (可选，或者拆分出 EmbeddingConfig)
    embedding_model_name: Optional[str] = "text-embedding-3-small"
    
    def context_window(self) -> int:
        if self.context_limit:
            return self.context_limit
        # 简单的模糊匹配查找限制，模拟 Rust 的 get_model_specific_limit
        for key, limit in MODEL_LIMITS.items():
            if key in self.model_name:
                return limit
        return DEFAULT_CONTEXT_LIMIT