from typing import Type, Optional, Dict, Any,Callable
from pydantic import BaseModel,ConfigDict,create_model
import logging

from .base import Component
from .protocol import ComponentMeta, ComponentDefinition, UIConfig, Port
from goose.registry import RegistryEntry,BaseRegistry
from goose.utils.type_converter import TypeConverter
from goose.utils.definition_builder import DefinitionBuilder

logger = logging.getLogger("goose.component.registry")

component_registry = BaseRegistry('components')

def register_component(
    name: str,
    group: str,
    label: str = "",
    type: str = None,  # Optional: if None, use name or class logic
    description: str = "",
    icon: str = "default",
    version: str = "1.0.0",  # [New] Version
    author: str = "System",  # [New] Author
    source: str = "system",
    
    config_model: Type[BaseModel] = None,
    input_model: Type[BaseModel] = None,
    output_model: Type[BaseModel] = None,
    
    config_schema: Optional[Dict[str, Any]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    
    is_custom: bool = False,
):
    def wrapper(cls: Type[Component]):
        nonlocal type
        # Use provided type ID, or fall back to name
        comp_id = type or name
        setattr(cls, 'type', type) 
        
        # =====================================================
        # 1. 归一化 (Normalization) -> 统一转为 Pydantic Model
        # =====================================================

        # Helper: 处理输入源优先级 (Model > Schema > Inference)
        def resolve_model(
            explicit_model: Optional[Type[BaseModel]],
            explicit_schema: Optional[Dict[str, Any]],
            inference_func: Callable,
            model_name_suffix: str,
        ) -> Type[BaseModel]:
            # A. 显式传入了 Model (最高优先级)
            if explicit_model:
                return explicit_model

            # B. 显式传入了 Schema (动态组件常用)
            if explicit_schema:
                return TypeConverter.json_schema_to_pydantic(
                    explicit_schema, f"{name}{model_name_suffix}"
                )

            # C. 自动推断 (TypeInfo -> Pydantic)
            type_info = inference_func(cls.execute)
            if type_info:
                return TypeConverter.to_pydantic(
                    type_info, f"{name}{model_name_suffix}"
                )

            # D. 无法推断，返回空模型
            return create_model(
                f"{name}{model_name_suffix}", __config__=ConfigDict(extra="ignore")
            )

        # 执行归一化
        final_config_model = resolve_model(
            config_model,
            config_schema,
            lambda _: None,  # Config 无法从 execute 推断，通常只能显式传
            "Config",
        )

        final_input_model = resolve_model(
            input_model,
            input_schema,
            TypeConverter.infer_input_schema,  # 使用 infer_input_schema
            "Input",
        )

        final_output_model = resolve_model(
            output_model,
            output_schema,
            TypeConverter.infer_output_schema,  # 使用 infer_output_schema
            "Output",
        )
        
        definition = DefinitionBuilder.build(
            label=label,
            description=description,
            icon=icon,
            version=version,
            author=author,
            group=group,
            config_model=final_config_model,
            input_model=final_input_model,
            output_model=final_output_model,
        )

        meta = ComponentMeta(
            type=comp_id,
            source=source,
            definition=definition,
            runner_ref=f"{cls.__module__}.{cls.__name__}",
            tags=["custom"] if is_custom else ["system"],
        )
        entry = RegistryEntry(id=comp_id, body=cls, meta=meta)
        component_registry.register(entry)

        
        return cls
    return wrapper



# class ComponentRegistry(BaseRegistry[Component,ComponentMeta]):
#     """组件注册单例"""
#     _registry: Dict[str, Component] = {}

#     @classmethod
#     def register(cls, component_cls: Type[Component]):
#         """装饰器：注册组件类"""
#         instance = component_cls()
#         if instance.name in cls._registry:
#             logger.warning(f"Overwriting component: {instance.name}")
#         cls._registry[instance.name] = instance
#         return component_cls

#     @classmethod
#     def get(cls, name: str) -> Component:
#         """获取组件实例"""
#         return cls._registry.get(name)

#     @classmethod
#     def list_definitions(cls) -> List[Dict[str, Any]]:
#         """导出所有组件定义给前端 (用于左侧组件拖拽栏)"""
#         return [
#             {
#                 "type": comp.name,
#                 "label": comp.label,
#                 "description": comp.description,
#                 "group": comp.group,
#                 "icon": comp.icon,
#                 "config_schema": comp.config_model.model_json_schema(),
#                 # 前端初始化的默认数据结构
#                 "defaultData": {
#                     "label": comp.label,
#                     "inputs": {}, 
#                     "config": {}
#                 }
#             }
#             for comp in cls._registry.values()
#         ]

# # 快捷装饰器
# def register_component(cls):
#     return ComponentRegistry.register(cls)



