from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar
from .types import ResourceMetadata

T = TypeVar("T")

class ResourceBuilder(ABC, Generic[T]):
    """
    [Trait] 资源构建器
    负责将纯文本的 Metadata 转换为可执行的 Python 对象 (Instance)。
    """
    @abstractmethod
    async def build(self, metadata: ResourceMetadata) -> T:
        """
        根据 metadata.provider 和 metadata.config 创建实例。
        支持 async 是因为某些资源初始化可能需要联网 (如连接 VectorDB)。
        """
        pass