"""
Artifact Storage Module - 可插拔存储后端管理系统

设计模式（基于代码库分析）：
1. Registry Pattern - 存储后端注册（类似 ProviderRegistry）
2. Factory Pattern - 根据配置创建后端（类似 ProviderFactory）
3. Adapter Pattern - 统一接口，不同实现（类似 WorkflowAdapter）
4. Repository Pattern - 数据访问层抽象（类似 SessionStorage）

存储策略：
- MemoryStorage: LRU 内存存储（类似 AnalysisCache）
- FileStorage: 文件系统存储（类似 LocalStorage）
- HybridStorage: 混合存储（类似 Config keyring + file）
- DatabaseStorage: SQLite 存储（类似 SessionStorage）
"""

from .base import ArtifactStorage, ArtifactRef, StorageConfig
from .memory import MemoryStorage
from .file import FileStorage
from .hybrid import HybridStorage
from .database import DatabaseStorage
from .registry import ArtifactStorageRegistry, register_storage
from .manager import ArtifactManager,init_manager,get_manager

__all__ = [
    # Base
    "ArtifactStorage",
    "ArtifactRef",
    "StorageConfig",

    # Implementations
    "MemoryStorage",
    "FileStorage",
    "HybridStorage",
    "DatabaseStorage",

    # Registry
    "ArtifactStorageRegistry",
    "register_storage",

    # Manager
    "ArtifactManager",
    "init_manager",
    "get_manager"
]

# 注册内置存储后端
from .registry import _register_builtin_storages
_register_builtin_storages()
