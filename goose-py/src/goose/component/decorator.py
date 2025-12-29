from typing import Type, Optional, Dict, Any
from pydantic import BaseModel

from .base import Component
from .protocol import ComponentMeta, ComponentDefinition, UIConfig, Port
from .registry import ComponentRegistry # 假设您已经有了一个简单的 Registry

def register_component(
    name: str,
    group: str = "Common",
    label: str = None,
    description: str = "",
    icon: str = "box",
    config_model: Type[BaseModel] = None,
    input_model: Type[BaseModel] = None,
    output_model: Type[BaseModel] = None,
):
    def wrapper(cls: Type[Component]):
        cls.type = name # 注入 type
        
        # 1. 生成 Schema
        c_schema = config_model.model_json_schema() if config_model else {}
        i_schema = input_model.model_json_schema() if input_model else {}
        o_schema = output_model.model_json_schema() if output_model else {}

        # 2. 自动生成 UI Ports (根据 Input/Output Schema)
        # 这是一个简单的推导逻辑，实际可以更复杂
        inputs_ports = [
            Port(name=k, title=props.get("title", k), type=props.get("type", "any"))
            for k, props in i_schema.get("properties", {}).items()
        ]
        outputs_ports = [
            Port(name=k, title=props.get("title", k), type=props.get("type", "any"))
            for k, props in o_schema.get("properties", {}).items()
        ]

        # 3. 构建元数据
        definition = ComponentDefinition(
            config_schema=c_schema,
            input_schema=i_schema,
            output_schema=o_schema,
            ui=UIConfig(
                label=label or name,
                description=description,
                icon=icon,
                ports={"inputs": inputs_ports, "outputs": outputs_ports}
            )
        )

        meta = ComponentMeta(
            type=name,
            group=group,
            definition=definition,
            runner_ref=f"{cls.__module__}.{cls.__name__}"
        )

        # 4. 实例化并注册
        instance = cls()
        instance.set_models(config_model, input_model, output_model)
        
        # 注册到系统
        ComponentRegistry.register(name, instance, meta)
        
        return cls
    return wrapper