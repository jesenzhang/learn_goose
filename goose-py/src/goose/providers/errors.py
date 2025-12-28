from typing import Optional

class ProviderError(Exception):
    """
    所有 Provider 相关错误的基类。
    对应 Rust: pub enum ProviderError
    """
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def __str__(self):
        return self.message

class AuthenticationError(ProviderError):
    """
    认证失败（如 API Key 无效）。
    对应 Rust: ProviderError::Authentication(String)
    """
    pass

class UsageError(ProviderError):
    """
    使用错误（如参数无效、模型不支持该功能）。
    对应 Rust: ProviderError::UsageError(String)
    """
    pass

class ExecutionError(ProviderError):
    """
    执行错误（通用运行时错误，如 API 返回 500）。
    对应 Rust: ProviderError::ExecutionError(String)
    """
    pass

class RequestFailedError(ProviderError):
    """
    网络请求失败（如连接超时、DNS 错误）。
    对应 Rust: ProviderError::RequestFailed(String)
    """
    pass

class ContextLengthExceededError(ProviderError):
    """
    上下文长度超出限制。
    对应 Rust: ProviderError::ContextLengthExceeded(String)
    
    注意：这个异常非常关键，Agent 层捕获到它后会触发 `compact_messages` 逻辑。
    """
    def __init__(self, message: str, current_tokens: Optional[int] = None, limit: Optional[int] = None):
        super().__init__(message)
        self.current_tokens = current_tokens
        self.limit = limit

class ModelNotSupportedError(ProviderError):
    """
    请求的模型不存在或不支持。
    """
    pass