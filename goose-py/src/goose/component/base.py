from abc import ABC
from typing import ClassVar
from .node import ComponentNode

class Component(ComponentNode, ABC):
    """
    [定义层] Component
    这是开发者在扩展新组件时继承的基类。
    它在 ComponentNode 的基础上，增加了用于前端显示和注册的元数据。
    """
    
    # --- 元数据 (Metadata) ---
    name: ClassVar[str]          # 唯一标识 (e.g. "llm_chat")
    label: ClassVar[str]         # 显示名称 (e.g. "AI 对话")
    description: ClassVar[str] = "" 
    group: ClassVar[str] = "Common" # 分组
    icon: ClassVar[str] = "box"     # 图标
    version: ClassVar[str] = "1.0.0"

    # 注意：execute 方法已经在 ComponentNode 中声明为 abstract，
    # 这里不需要重写，直接留给具体组件实现。