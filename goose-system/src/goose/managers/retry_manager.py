"""
Retry Manager

自动重试逻辑，支持指数退避策略。
"""

from dataclasses import dataclass, field
from typing import Callable, Any, Optional
import asyncio
import random


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_exceptions: tuple = (Exception,)


@dataclass
class RetryState:
    """重试状态"""
    attempt: int = 0
    total_delay: float = 0.0
    last_error: Optional[str] = None


class RetryManager:
    """
    重试管理器
    
    职责：
    - 工具执行失败后的自动重试
    - 指数退避策略
    - 最大重试次数控制
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        带重试的执行
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            函数执行结果
            
        Raises:
            最后一次尝试的错误
        """
        state = RetryState()
        last_error = None
        
        for attempt in range(self.config.max_retries + 1):
            state.attempt = attempt
            
            try:
                result = func(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                last_error = e
                state.last_error = str(e)
                
                if attempt >= self.config.max_retries:
                    raise
                
                delay = self._calculate_delay(attempt)
                state.total_delay += delay
                
                await asyncio.sleep(delay)
        
        raise last_error
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算延迟时间"""
        delay = self.config.base_delay * (
            self.config.exponential_base ** attempt
        )
        
        # 限制最大延迟
        delay = min(delay, self.config.max_delay)
        
        # 添加随机抖动
        if self.config.jitter:
            delay = delay * (0.5 + random.random())
        
        return delay
    
    def create_state(self) -> RetryState:
        """创建新的重试状态"""
        return RetryState()


async def with_retry(
    func: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs
) -> Any:
    """
    装饰器风格的带重试执行
    
    Usage:
        result = await with_retry(
            my_function,
            arg1, arg2,
            config=RetryConfig(max_retries=5),
            kwarg1=value1
        )
    """
    manager = RetryManager(config)
    return await manager.execute_with_retry(func, *args, **kwargs)
