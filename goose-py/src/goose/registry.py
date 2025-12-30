import logging
from tkinter import Entry
from typing import Dict, TypeVar, Generic, List, Optional, Any, Type, TYPE_CHECKING
from pydantic import BaseModel

logger = logging.getLogger("goose.registry")

# ==========================================
# 1. 基础数据结构 (保持不变)
# ==========================================

B = TypeVar("B") # Body
M = TypeVar("M") # Meta

class RegistryEntry(BaseModel, Generic[B, M]):
    id: str
    body: B
    meta: M
    class Config:
        arbitrary_types_allowed = True

class BaseRegistry(Generic[B, M]):
    def __init__(self, name: str):
        self._name = name
        self._entries: Dict[str, RegistryEntry[B, M]] = {}

    def register(self, entry: RegistryEntry[B, M]):
        if not entry:
            logger.warning("⚠️ Empty entry cannot be registered.")
            return
        
        if entry.id in self._entries:
            logger.warning(f"⚠️ Overwriting {self._name}: {entry.id}")
        self._entries[entry.id] = entry
        logger.debug(f"✅ Registered {self._name}: {entry.id}")

    def get_entry(self, key: str) -> Optional[RegistryEntry[B, M]]:
        e = self._entries.get(key)
        return e if e else None
    
    def get(self, key: str) -> Optional[B]:
        e = self._entries.get(key)
        return e.body if e else None
    
    def get_body(self, key: str) -> Optional[B]:
        e = self._entries.get(key)
        return e.body if e else None
    
    def get_meta(self, key: str) -> Optional[M]:
        e = self._entries.get(key)
        return e.meta if e else None
    
    def list_entries(self) -> List[RegistryEntry[B, M]]:
        return list(self._entries.values())
    
    def list_meta(self) -> List[M]:
        return [e.meta for e in self._entries.values()]
    
    def list_body(self) -> List[B]:
        return [e.body for e in self._entries.values()]
    
    def clear(self):
        self._entries.clear()

# ==========================================
# 2. SystemRegistry (支持动态属性代理)
# ==========================================

class SystemRegistry:
    """
    [Core] 系统注册中心 (Singleton)
    
    特性:
    1. 全局单例: 无论实例化多少次，id() 都是一样的。
    2. 动态属性: registry.knowledge 会自动创建注册器。
    3. 显式注册: 支持 register_domain 覆盖默认行为。
    """
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        """
        [魔法方法 1] 单例守卫
        拦截实例化过程，如果实例已存在，直接返回，不再创建新对象。
        """
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 内部存储所有的子注册器
        # Key: 领域名称 (e.g., "components", "tools")
        # Value: 具体的 Registry 实例
        if self._initialized:
            return
        
        self._domains: Dict[str, BaseRegistry] = {}
        self._initialized = True
        logger.info("🚀 SystemRegistry initialized (Singleton).")

    def register_domain(self, name: str, registry_instance: BaseRegistry):
        """
        [显式注册] 注册一个新的领域注册器。
        用于自定义注册器 (如 ComponentRegistry, ToolRegistry)。
        """
        if name in self._domains:
            logger.warning(f"⚠️ Domain '{name}' is being overwritten.")
        self._domains[name] = registry_instance
        logger.info(f"🌍 Domain registered: system.{name}")

    def __getattr__(self, name: str) -> BaseRegistry:
        """
        [魔法方法] 属性访问代理。
        当你调用 registry.knowledge 时：
        1. 如果已存在，直接返回。
        2. 如果不存在，自动创建一个默认的 BaseRegistry 并注册。
        """
        # 避免无限递归访问内部属性
        if name.startswith("_"):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        if name not in self._domains:
            logger.info(f"✨ Auto-initializing domain registry: {name}")
            self._domains[name] = BaseRegistry(name)
        
        return self._domains[name]

    def __dir__(self):
        """帮助 IDE 和 dir() 函数发现动态属性"""
        return list(self.__dict__.keys()) + list(self._domains.keys())

# 1. 创建全局单例实例
sys_registry = SystemRegistry()

