"""
Response Caching for Agent Execution

Caches LLM responses based on input to avoid redundant API calls.
Uses LRU (Least Recently Used) eviction policy.
"""

import hashlib
import json
import logging
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from collections import OrderedDict

from .core import AgentResponse, AgentStatus

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """A single cache entry"""
    response: AgentResponse
    created_at: float
    hit_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def touch(self):
        """Update last access time and increment hit count"""
        self.last_accessed = time.time()
        self.hit_count += 1


class AgentResponseCache:
    """
    LRU Cache for agent responses.

    Features:
    - Configurable max size
    - TTL (time-to-live) support
    - Cache key based on input hash
    - Thread-safe for async operations
    """

    def __init__(
        self,
        max_size: int = 128,
        ttl_seconds: Optional[float] = None,
        enabled: bool = True
    ):
        """
        Initialize the cache.

        Args:
            max_size: Maximum number of cached responses
            ttl_seconds: Optional time-to-live in seconds
            enabled: Whether caching is enabled
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.enabled = enabled
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def _make_key(self, input: str, style: str, **kwargs) -> str:
        """
        Create a cache key from input and context.

        Args:
            input: User input text
            style: Agent style
            **kwargs: Additional context variables

        Returns:
            SHA256 hash as hex string
        """
        # Normalize input
        normalized = {
            "input": input.strip().lower(),
            "style": style,
            "vars": kwargs,
        }

        # Create deterministic string
        key_str = json.dumps(normalized, sort_keys=True, default=str)

        # Hash it
        return hashlib.sha256(key_str.encode()).hexdigest()

    def get(self, input: str, style: str = "minimal", **kwargs) -> Optional[AgentResponse]:
        """
        Get cached response if available.

        Args:
            input: User input text
            style: Agent style
            **kwargs: Additional context variables

        Returns:
            Cached AgentResponse or None
        """
        if not self.enabled:
            return None

        key = self._make_key(input, style, **kwargs)

        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]

        # Check TTL
        if self.ttl_seconds:
            age = time.time() - entry.created_at
            if age > self.ttl_seconds:
                # Expired
                del self._cache[key]
                self._misses += 1
                logger.debug(f"Cache entry expired (age: {age:.1f}s)")
                return None

        # Update access time and move to end (LRU)
        entry.touch()
        self._cache.move_to_end(key)
        self._hits += 1

        logger.debug(f"Cache hit: {key[:16]}... (hits: {entry.hit_count})")
        return entry.response

    def put(self, input: str, response: AgentResponse, style: str = "minimal", **kwargs) -> None:
        """
        Store a response in the cache.

        Args:
            input: User input text
            response: Agent response to cache
            style: Agent style
            **kwargs: Additional context variables
        """
        if not self.enabled:
            return

        # Don't cache errors
        if response.status != AgentStatus.COMPLETED:
            return

        # Don't cache empty responses
        if not response.text or not response.text.strip():
            return

        key = self._make_key(input, style, **kwargs)

        # Create cache entry
        entry = CacheEntry(
            response=response,
            created_at=time.time(),
        )

        # Check if at capacity
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Evict oldest (first) entry
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"Cache evicted: {oldest_key[:16]}...")

        # Add/replace entry
        self._cache[key] = entry
        self._cache.move_to_end(key)
        logger.debug(f"Cache stored: {key[:16]}...")

    def clear(self) -> None:
        """Clear all cached entries"""
        self._cache.clear()
        logger.info("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache metrics
        """
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0

        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "enabled": self.enabled,
            "ttl_seconds": self.ttl_seconds,
        }

    def prune_expired(self) -> int:
        """
        Remove all expired entries based on TTL.

        Returns:
            Number of entries pruned
        """
        if not self.ttl_seconds:
            return 0

        now = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now - entry.created_at > self.ttl_seconds
        ]

        for key in expired_keys:
            del self._cache[key]

        if expired_keys:
            logger.info(f"Pruned {len(expired_keys)} expired cache entries")

        return len(expired_keys)


class CachedAgentMixin:
    """
    Mixin class to add caching capability to any agent engine.

    Usage:
        class MyAgentEngine(CachedAgentMixin, BaseEngine):
            async def execute(self, input: str, context: Context):
                # Check cache first
                cached = self.cache.get(input, "my_style")
                if cached:
                    return cached

                # Do actual work
                response = await self._do_work(input)

                # Store in cache
                self.cache.put(input, response, "my_style")
                return response
    """

    def __init__(self, *args, cache_size: int = 128, cache_ttl: Optional[float] = None, **kwargs):
        """
        Initialize with cache.

        Args:
            cache_size: Maximum cache size
            cache_ttl: Optional TTL in seconds
        """
        super().__init__(*args, **kwargs)
        self.cache = AgentResponseCache(
            max_size=cache_size,
            ttl_seconds=cache_ttl,
            enabled=True
        )

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return self.cache.get_stats()

    def clear_cache(self) -> None:
        """Clear the cache"""
        self.cache.clear()


__all__ = [
    "CacheEntry",
    "AgentResponseCache",
    "CachedAgentMixin",
]
