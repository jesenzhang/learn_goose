"""
Model Configuration - Separated into Connection and Runtime parameters.

设计原则：
- ConnectionConfig: 构造参数，定义如何连接到模型服务
- InferenceConfig: 运行时参数，定义每次调用的行为
- ModelConfig: 组合配置，向后兼容
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


# 对应 model.rs 中的 MODEL_SPECIFIC_LIMITS
MODEL_LIMITS = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385,
    "claude-3-5-sonnet": 200_000,
    "qwen": 128_000,
    "qwen3": 32_768,
    "deepseek": 64_000,
    # ... 其他模型
}

DEFAULT_CONTEXT_LIMIT = 128_000


class ConnectionConfig(BaseModel):
    """
    连接配置 - 用于构造 Provider 实例。

    这些参数在 Provider 初始化时确定，运行时不会改变。
    """
    provider: str = "openai"
    model_name: str = "gpt-4o"
    base_url: Optional[str] = None
    api_key_env: str = "OPENAI_API_KEY"
    api_key: Optional[str] = None

    # 连接参数
    timeout: Optional[float] = Field(default=60.0, description="连接超时时间（秒）")
    max_retries: int = Field(default=5, description="最大重试次数")
    organization: Optional[str] = None
    project: Optional[str] = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)

    # 容量限制
    context_limit: Optional[int] = Field(default=None, description="模型上下文窗口大小")

    def context_window(self) -> int:
        """获取模型的上下文窗口大小"""
        if self.context_limit:
            return self.context_limit
        # 简单的模糊匹配查找限制
        for key, limit in MODEL_LIMITS.items():
            if key in self.model_name:
                return limit
        return DEFAULT_CONTEXT_LIMIT


class InferenceConfig(BaseModel):
    """
    推理配置 - 运行时参数，控制每次生成的行为。

    这些参数可以在每次调用时覆盖。
    """
    temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="采样温度")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最大生成 token 数")
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="nucleus sampling 参数")
    frequency_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    presence_penalty: Optional[float] = Field(default=None, ge=-2.0, le=2.0)
    stop: Optional[list[str]] = Field(default=None, description="停止序列")

    # 高级选项
    toolshim: bool = Field(default=False, description="是否使用工具垫片模式")
    fast_model: Optional[str] = Field(default=None, description="快速推理模型名称")

    def to_api_params(self) -> Dict[str, Any]:
        """
        转换为 API 调用参数。

        只返回非 None 的参数，避免覆盖默认值。
        """
        params = {}
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if self.max_tokens is not None:
            params["max_tokens"] = self.max_tokens
        if self.top_p is not None:
            params["top_p"] = self.top_p
        if self.frequency_penalty is not None:
            params["frequency_penalty"] = self.frequency_penalty
        if self.presence_penalty is not None:
            params["presence_penalty"] = self.presence_penalty
        if self.stop:
            params["stop"] = self.stop
        return params

    def merge(self, **kwargs) -> 'InferenceConfig':
        """
        合并运行时覆盖参数。

        Example:
            config = InferenceConfig(temperature=0.7)
            merged = config.merge(temperature=0.5, max_tokens=1000)
        """
        current = self.model_dump(exclude_none=True)
        current.update(kwargs)
        return InferenceConfig(**current)


class ModelConfig(BaseModel):
    """
    统一的模型配置对象（向后兼容）。

    组合了 ConnectionConfig 和 InferenceConfig。
    """
    # === 连接配置 ===
    provider: str = "openai"
    model_name: str = "gpt-4o"
    base_url: Optional[str] = None
    api_key_env: str = "OPENAI_API_KEY"
    api_key: Optional[str] = None
    timeout: Optional[float] = Field(default=60.0)
    max_retries: int = Field(default=5)
    organization: Optional[str] = None
    project: Optional[str] = None
    extra_headers: Dict[str, str] = Field(default_factory=dict)
    context_limit: Optional[int] = None

    # === 推理配置 ===
    temperature: float = 0.1
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    stop: Optional[list[str]] = None

    # === 高级选项 ===
    toolshim: bool = False
    toolshim_model: Optional[str] = None
    fast_model: Optional[str] = None

    # === Embedding 专用 ===
    embedding_model_name: Optional[str] = "text-embedding-3-small"

    def context_window(self) -> int:
        """获取模型的上下文窗口大小"""
        if self.context_limit:
            return self.context_limit
        for key, limit in MODEL_LIMITS.items():
            if key in self.model_name:
                return limit
        return DEFAULT_CONTEXT_LIMIT

    def get_connection_config(self) -> ConnectionConfig:
        """提取连接配置部分"""
        return ConnectionConfig(
            provider=self.provider,
            model_name=self.model_name,
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            organization=self.organization,
            project=self.project,
            extra_headers=self.extra_headers,
            context_limit=self.context_limit
        )

    def get_inference_config(self) -> InferenceConfig:
        """提取推理配置部分"""
        return InferenceConfig(
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            top_p=self.top_p,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            stop=self.stop,
            toolshim=self.toolshim,
            fast_model=self.fast_model
        )

    def to_api_params(self) -> Dict[str, Any]:
        """
        转换为 API 调用参数。

       便捷方法，等同于 self.get_inference_config().to_api_params()
        """
        return self.get_inference_config().to_api_params()
