from typing import Any, Callable, Dict, Type, TypeVar, Optional

T = TypeVar("T")

class IoCContainer:
    def __init__(self):
        # 存储: { ClassType: Instance }
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable] = {}

    def register_instance(self, interface: Type[T], instance: T):
        """注册单例：绑定接口与实例"""
        self._services[interface] = instance

    def register_factory(self, interface: Type[T], factory: Callable[..., T]):
        """注册工厂"""
        self._factories[interface] = factory

    def get(self, interface: Type[T], **kwargs) -> T:
        """
        获取实例
        关键点：返回值类型是 T，IDE 可以识别！
        """
        # 1. 查单例
        if interface in self._services:
            return self._services[interface]
        
        # 2. 查工厂
        if interface in self._factories:
            return self._factories[interface](**kwargs)

        raise ValueError(f"Service '{interface.__name__}' not registered")

