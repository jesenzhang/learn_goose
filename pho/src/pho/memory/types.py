"""
Memory types and enums.
"""

from enum import Enum


class StorageType(str, Enum):
    """Type of memory storage backend."""
    MEMORY = "memory"
    FILE = "file"
    HYBRID = "hybrid"
    DATABASE = "database"


class MemoryPriority(str, Enum):
    """Priority level for storing memories."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class MemoryStats:
    """Statistics for memory operations."""
    total_stored: int = 0
    total_retrieved: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
