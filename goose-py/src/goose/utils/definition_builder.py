from typing import Type, List, Dict, Any, Optional
from pydantic import BaseModel
from goose.components.protocol import (
    ComponentDefinition, 
    UIConfig, 
    Port
)

class DefinitionBuilder:
    """
    [Builder] 负责构建 ComponentDefinition
    """

    @staticmethod
    def build(
        # 1. 显式传入 UI 信息
        label: str,
        description: str = "",
        icon: str = "default",
        group: str = "default",
        author: str = "System",
        version: str = "1.0.0",
        
        # 2. 传入 Pydantic 模型
        config_model: Optional[Type[BaseModel]] = None,
        input_model: Optional[Type[BaseModel]] = None,
        output_model: Optional[Type[BaseModel]] = None
    ) -> ComponentDefinition:
        
        # ... (Schema 生成逻辑保持不变) ...
        config_schema = config_model.model_json_schema() if config_model else {}
        input_schema = input_model.model_json_schema() if input_model else {}
        output_schema = output_model.model_json_schema() if output_model else {}

        # ... (Port 提取逻辑保持不变) ...
        input_ports = DefinitionBuilder._extract_ports(input_model, input_schema) if input_model else []
        output_ports = DefinitionBuilder._extract_ports(output_model, output_schema) if output_model else []
        
        config_ports = DefinitionBuilder._extract_ports(config_model, config_schema) if config_model else []

        # 构建 UI Config
        ui_config = UIConfig(
            label=label,
            description=description,
            icon=icon,
            group= group,
            author=author,
            version=version,
            ports={
                "inputs": input_ports + config_ports,
                "outputs": output_ports
            }
            
        )

        return ComponentDefinition(
            config_schema=config_schema,
            input_schema=input_schema,
            output_schema=output_schema,
            ui=ui_config
        )
        
    @staticmethod
    def _extract_ports(model: Type[BaseModel], json_schema: Dict[str, Any]) -> List[Port]:
        """
        从 Pydantic 模型提取端口定义列表
        """
        ports = []
        # 从生成的 JSON Schema 中获取属性定义 (这样能获取到 Field(..., title="xxx") 的处理结果)
        properties = json_schema.get("properties", {})
        
        # 遍历模型的字段定义
        for name, field in model.model_fields.items():
            # 1. 获取 Schema 中的信息
            prop_info = properties.get(name, {})
            
            # 2. 提取 UI 元数据
            # 优先取 Field(title="...")，没有则用字段名
            title = prop_info.get("title", name)
            
            # 提取类型描述 (用于前端连线颜色区分)
            # 简单处理：如果是 $ref (引用对象)，则标记为 "object"
            if "$ref" in prop_info:
                type_str = "object"
            else:
                type_str = prop_info.get("type", "any")

            # 3. 提取自定义 UI Widget 提示
            # 方式 A: 从 json_schema_extra 提取 (推荐 Pydantic V2 写法)
            # field.json_schema_extra 可以是 dict 或函数
            extra = field.json_schema_extra
            ui_widget = "default"
            if isinstance(extra, dict):
                ui_widget = extra.get("x-ui-widget", "default")
            
            # 方式 B: 兼容旧写法，从生成的 schema properties 里找 (如果使用了 Field(json_schema_extra={...}))
            if ui_widget == "default":
                ui_widget = prop_info.get("x-ui-widget", "default")

            # 4. 构建端口对象
            ports.append(Port(
                name=name,
                title=title,
                type=type_str,
                # Pydantic V2 判断必填: field.is_required()
                required=field.is_required(), 
                description=prop_info.get("description", ""),
                ui_widget=ui_widget
            ))
            
        return ports