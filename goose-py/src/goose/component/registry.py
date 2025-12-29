import logging
from typing import Dict, Type, List, Any
from .base import Component

logger = logging.getLogger("goose.component.registry")

class ComponentRegistry:
    """组件注册单例"""
    _registry: Dict[str, Component] = {}

    @classmethod
    def register(cls, component_cls: Type[Component]):
        """装饰器：注册组件类"""
        instance = component_cls()
        if instance.name in cls._registry:
            logger.warning(f"Overwriting component: {instance.name}")
        cls._registry[instance.name] = instance
        return component_cls

    @classmethod
    def get(cls, name: str) -> Component:
        """获取组件实例"""
        return cls._registry.get(name)

    @classmethod
    def list_definitions(cls) -> List[Dict[str, Any]]:
        """导出所有组件定义给前端 (用于左侧组件拖拽栏)"""
        return [
            {
                "type": comp.name,
                "label": comp.label,
                "description": comp.description,
                "group": comp.group,
                "icon": comp.icon,
                "configSchema": comp.config_schema,
                # 前端初始化的默认数据结构
                "defaultData": {
                    "label": comp.label,
                    "inputs": {}, 
                    "config": {}
                }
            }
            for comp in cls._registry.values()
        ]

# 快捷装饰器
def register_component(cls):
    return ComponentRegistry.register(cls)

