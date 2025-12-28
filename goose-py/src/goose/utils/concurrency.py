import asyncio
import functools
from typing import Any, Callable, TypeVar

T = TypeVar("T")

async def run_blocking(func: Callable[..., T], *args, **kwargs) -> T:
    """
    将同步/阻塞代码放入线程池执行，防止阻塞 Event Loop。
    这是对齐 Rust 并发能力的关键。
    """
    loop = asyncio.get_running_loop()
    # 使用 partial 包装 kwargs
    pfunc = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, pfunc)

async def run_with_timeout(coro, timeout_sec: float):
    """带超时的异步执行"""
    return await asyncio.wait_for(coro, timeout=timeout_sec)