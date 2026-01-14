"""
Service Context - Dependency Injection for Skills
Refactored for Type Safety and IDE Autocompletion.
"""

import time
from typing import Any, Dict, Optional, TypeVar, Generic, TYPE_CHECKING,cast,Union
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

# 使用 TYPE_CHECKING 避免循环导入，同时保留 IDE 提示
if TYPE_CHECKING:
    from ..providers.base import BaseEmbedding, BaseReranker
    from ..core.context import RequestContext

# 定义泛型，T_State 和 T_DB 可以由使用者指定具体的类
T_State = TypeVar('T_State', bound=Any)
T_DB = TypeVar('T_DB', bound=Any)

# =============================================================================
# 1. 强类型 AI 服务容器
# =============================================================================

@dataclass
class AIServices:
    """
    强类型 AI 服务容器。
    替代原来的 Dict[str, Any]，提供 IDE 自动补全。
    """
    embedding: Optional["BaseEmbedding"] = None
    reranker: Optional["BaseReranker"] = None
    
    # 预留字典以支持未定义的扩展服务
    extras: Dict[str, Any] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        """兼容旧的字典访问方式"""
        if hasattr(self, key):
            return getattr(self, key)
        return self.extras.get(key)

# =============================================================================
# 2. Service Locator (保持不变，用于解耦通用服务)
# =============================================================================

class ServiceLocator(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any: pass
    @abstractmethod
    def has(self, key: str) -> bool: pass

class DictServiceLocator(ServiceLocator):
    def __init__(self, services: Optional[Dict[str, Any]] = None):
        self._services = services or {}
    def register(self, key: str, service: Any) -> None:
        self._services[key] = service
    def get(self, key: str, default: Any = None) -> Any:
        return self._services.get(key, default)
    def has(self, key: str) -> bool:
        return key in self._services

# =============================================================================
# 3. 优化后的 Service Context
# =============================================================================

class ServiceContext(Generic[T_State, T_DB]):
    """
    Main service context with Type Hinting.
    """

    def __init__(
        self,
        session_id: str,
        state: Optional[T_State] = None,
        db: Optional[T_DB] = None,
        # [CHANGED] 接收强类型容器，默认为空容器而不是 None
        ai_services: Union[AIServices, Dict[str, Any], None] = None,
        locator: Optional[ServiceLocator] = None,
        request_context: Optional['RequestContext'] = None
    ):
        self._session_id = session_id
        self._state = state
        self._db = db
        # 确保 _ai_services 永远不为 None，避免 .embedding 报错
        self._ai_services = ai_services or AIServices()
        self._locator = locator or DictServiceLocator()
        self._request_context = request_context
        self._created_at = time.time()

    # --- Core Properties ---
    @property
    def request(self) -> 'RequestContext':
        """访问当前请求的上下文参数"""
        return self._request_context
    
    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def state(self) -> T_State:
        """
        Agent state object (Type Safe).
        """
        if self._state is None:
            raise RuntimeError("State not available in this context")
        return self._state

    @property
    def db(self) -> T_DB:
        """
        Database manager (Type Safe).
        """
        if self._db is None:
            raise RuntimeError("Database not available in this context")
        return self._db

    # --- ✨ AI Services Shortcuts (IDE Friendly) ---

    @property
    def ai(self) -> AIServices:
        """访问 AI 服务容器"""
        return self._ai_services

    @property
    def embedding(self) -> "BaseEmbedding":
        """
        直接访问 Embedding 服务。
        如果服务未配置，抛出明确错误。
        """
        if not self._ai_services.embedding:
            raise RuntimeError("Embedding service is not configured in this context.")
        return self._ai_services.embedding

    @property
    def reranker(self) -> "BaseReranker":
        """
        直接访问 Reranker 服务。
        """
        if not self._ai_services.reranker:
            raise RuntimeError("Reranker service is not configured in this context.")
        return self._ai_services.reranker

    # --- Helpers ---

    def get_state_value(self, key: str, default: Any = None) -> Any:
        try:
            # 假设 state 有 shared_memory 属性（Duck Typing）
            return self.state.shared_memory.get(key, default)
        except (AttributeError, TypeError):
            return default

    def set_state_value(self, key: str, value: Any) -> None:
        try:
            self.state.shared_memory[key] = value
        except (AttributeError, TypeError):
            pass

    # --- Generic Access ---
    
    def get_service(self, key: str, default: Any = None) -> Any:
        return self._locator.get(key, default)


# =============================================================================
# 4. 优化后的构造工厂
# =============================================================================

class ServiceContextBuilder:
    def __init__(self, session_id: str):
        self._session_id = session_id
        self._state = None
        self._db = None
        # 初始化为空容器
        self._ai_services = AIServices()
        self._services = {}
        self._request_context = None

    def with_state(self, state: Any) -> 'ServiceContextBuilder':
        self._state = state
        return self

    def with_db(self, db: Any) -> 'ServiceContextBuilder':
        self._db = db
        return self

    # [CHANGED] 强类型设置方法
    def with_embedding(self, service: "BaseEmbedding") -> 'ServiceContextBuilder':
        self._ai_services.embedding = service
        return self

    def with_reranker(self, service: "BaseReranker") -> 'ServiceContextBuilder':
        self._ai_services.reranker = service
        return self

    # 兼容旧逻辑：直接传字典
    def with_ai_services_dict(self, services: Dict[str, Any]) -> 'ServiceContextBuilder':
        if "embedding" in services:
            self._ai_services.embedding = services["embedding"]
        if "reranker" in services:
            self._ai_services.reranker = services["reranker"]
        # 其他未知的放入 extras
        for k, v in services.items():
            if k not in ["embedding", "reranker"]:
                self._ai_services.extras[k] = v
        return self

    def with_request_context(self, req: 'RequestContext') -> 'ServiceContextBuilder':
        self._request_context = req
        return self
    
    def with_service(self, key: str, service: Any) -> 'ServiceContextBuilder':
        self._services[key] = service
        return self

    def build(self) -> ServiceContext:
        locator = DictServiceLocator(self._services)
        return ServiceContext(
            session_id=self._session_id,
            state=self._state,
            db=self._db,
            request_context=self._request_context,
            ai_services=self._ai_services,
            locator=locator
        )

def create_context(
    session_id: str,
    state: Optional[T_State] = None,
    db: Optional[T_DB] = None,
    ai_services: Union[AIServices, Dict[str, Any], None] = None,
    **services
) ->"ServiceContext[T_State, T_DB]":  # 返回值绑定泛型
    """
    Quick creation helper.
    Accepts ai_services as dict for compatibility but converts to AIServices internally.
    """
    builder = ServiceContextBuilder(session_id)
    if state: builder.with_state(state)
    if db: builder.with_db(db)
    
    if ai_services:
        if isinstance(ai_services, AIServices):
            # 直接赋值
            builder._ai_services = ai_services
        elif isinstance(ai_services, dict):
            # 兼容旧字典
            builder.with_ai_services_dict(ai_services)
        
    for k, v in services.items():
        builder.with_service(k, v)
        
    return cast(ServiceContext[T_State, T_DB], builder.build())