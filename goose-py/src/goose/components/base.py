from abc import ABC, abstractmethod
from typing import Dict, Any, Type, ClassVar
from .node import ComponentNode

class Component(ComponentNode, ABC):
    """
    [定义层] Component
    这是开发者在扩展新组件时继承的基类。
    它在 ComponentNode 的基础上，增加了用于前端显示和注册的元数据。
    """
    type: ClassVar[str] 
    
    # 注意：execute 方法已经在 ComponentNode 中声明为 abstract，
    # 这里不需要重写，直接留给具体组件实现。