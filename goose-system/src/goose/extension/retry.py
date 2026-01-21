"""
Retry Manager

Implements retry logic for operations that may fail temporarily.
Reference: goose-rs retry_manager.rs

Features:
- Configurable retry attempts
- Exponential backoff
- Jitter for avoiding thundering herd
- Retry on specific error types
"""

import asyncio
import random
import logging
from dataclasses import dataclass, field
from typing import Callable, Type, Any, Optional
from enum import Enum

logger = logging.getLogger("goose.retry")


class BackoffStrategy(str, Enum):
    """Backoff strategies."""
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


@dataclass
class RetryConfig:
    """Retry configuration."""
    max_attempts: int = 3
    initial_delay: float = 1.0
    max_delay: float = 60.0
    multiplier: float = 2.0
    jitter: float = 0.1
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    retry_on: tuple[Type[Exception], ...] = (Exception,)


@dataclass
class RetryState:
    """Current retry state."""
    attempt: int = 0
    total_delay: float = 0.0
    last_exception: Optional[Exception] = None


class RetryManager:
    """
    Retry manager with configurable backoff.

    Reference: goose-rs RetryManager
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()

    async def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args,
        retry_config: Optional[RetryConfig] = None,
        **kwargs
    ) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            retry_config: Optional override config
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            The last exception if all retries exhausted
        """
        config = retry_config or self.config
        state = RetryState()

        while True:
            state.attempt += 1
            try:
                return await func(*args, **kwargs)
            except config.retry_on as e:
                state.last_exception = e

                if state.attempt >= config.max_attempts:
                    logger.warning(
                        f"Retry failed after {state.attempt} attempts: {e}"
                    )
                    raise

                delay = self._calculate_delay(state.attempt, config)
                state.total_delay += delay

                logger.debug(
                    f"Retry attempt {state.attempt}/{config.max_attempts} "
                    f"after {delay:.2f}s: {e}"
                )

                await asyncio.sleep(delay)

    def _calculate_delay(self, attempt: int, config: RetryConfig) -> float:
        """Calculate delay for current attempt."""
        if config.backoff == BackoffStrategy.FIXED:
            delay = config.initial_delay
        elif config.backoff == BackoffStrategy.EXPONENTIAL:
            delay = config.initial_delay * (config.multiplier ** (attempt - 1))
            delay = min(delay, config.max_delay)
        elif config.backoff == BackoffStrategy.LINEAR:
            delay = config.initial_delay * attempt
        else:
            delay = config.initial_delay

        jitter_range = delay * config.jitter
        jitter = random.uniform(-jitter_range, jitter_range)

        return max(0, delay + jitter)

    def get_state(self, state: RetryState) -> dict:
        """Get retry state as dict."""
        return {
            "attempt": state.attempt,
            "total_delay": state.total_delay,
            "last_exception": str(state.last_exception) if state.last_exception else None
        }


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
    retry_on: tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """
    Decorator to add retry logic to async functions.

    Usage:
        @with_retry(max_attempts=3, initial_delay=0.5)
        async def fragile_operation():
            ...
    """
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            manager = RetryManager(RetryConfig(
                max_attempts=max_attempts,
                initial_delay=initial_delay,
                backoff=backoff,
                retry_on=retry_on
            ))
            return await manager.execute_with_retry(func, *args, **kwargs)
        return wrapper
    return decorator
