from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

# --- 核心依赖 ---
from goose.types import ParameterDefinition, DataType
from goose.resources.ui import UI
from goose.utils.template import TemplateRenderer
from goose.utils.type_converter import DataValidator

# --- 组件架构 ---
from goose.component.base import Component
from goose.component.registry import register_component

# ==========================================
# 1. Start Component (开始节点)
# ==========================================

class StartConfig(BaseModel):
    """Start 节点配置"""
    # 使用 ParameterDefinition 支持递归/嵌套结构定义
    # 前端识别 x-ui-component: TypeBuilder 后渲染树状编辑表格
    variables: List[ParameterDefinition] = Field(
        default_factory=list,
        description="定义工作流的输入参数结构",
        json_schema_extra={
            "x-ui-component": "TypeBuilder",
            "x-ui-props": {
                "description": "配置启动参数",
                "allowed_root_types": ["string", "number", "boolean", "object", "array"]
            }
        }
    )

@register_component
class StartComponent(Component):
    name = "start"
    label = "开始"
    description = "工作流入口，定义和校验初始参数"
    icon = "play-circle" 
    group = "Basic"
    
    # 绑定配置模型
    config_model = StartConfig
    
    # Start 节点的输入来自 Scheduler 启动时的参数，结构不定，不做预校验
    input_model = None 

    async def execute(self, inputs: Dict[str, Any], config: StartConfig) -> Dict[str, Any]:
        """
        执行逻辑：
        1. 接收外部传入的 inputs (dict)。
        2. 根据 config.variables 定义的 Schema (TypeInfo) 进行严格校验和清洗。
        """
        validated_data = {}
        
        # 1. 遍历定义的参数进行清洗
        for param in config.variables:
            key = param.key
            type_info = param.type_info
            
            # 获取原始值
            raw_val = inputs.get(key)
            
            # 使用 DataValidator 进行递归校验 (复用 type_converter.py 中的逻辑)
            # 这会自动处理 Object 嵌套、Array 元素校验、默认值填充等
            is_valid, result = DataValidator.validate_with_typeinfo(raw_val, type_info)
            
            if not is_valid:
                # result 在验证失败时是错误信息列表
                error_msgs = "; ".join(result) if isinstance(result, list) else str(result)
                raise ValueError(f"Input '{key}' validation failed: {error_msgs}")
            
            validated_data[key] = result

        # 2. 透传未定义的参数 (允许隐式参数通过，增强灵活性)
        for k, v in inputs.items():
            if k not in validated_data:
                validated_data[k] = v
                
        return validated_data


# ==========================================
# 2. End Component (结束节点)
# ==========================================

class EndConfig(BaseModel):
    output_mode: Literal["return_vars", "answer_content"] = Field(
        "return_vars", 
        description="输出模式",
        json_schema_extra=UI.Radio(options=[
            {"label": "返回所有变量", "value": "return_vars"},
            {"label": "自定义回答内容", "value": "answer_content"}
        ])
    )
    
    # 仅在 answer_content 模式下使用的模版
    content_template: str = Field(
        "", 
        description="回答内容模板 (支持 {{var}} 插值)",
        json_schema_extra=UI.TextArea(
            rows=5, 
            placeholder="处理完成！AI的建议是：\n{{ llm_node.output }}"
        )
    )

@register_component
class EndComponent(Component):
    name = "end"
    label = "结束"
    description = "工作流出口，格式化最终结果"
    icon = "stop-circle"
    group = "Basic"
    
    config_model = EndConfig
    input_model = None # 接受任意上游输入
    
    async def execute(self, inputs: Dict[str, Any], config: EndConfig) -> Dict[str, Any]:
        
        final_output = {}

        # 模式 1: 构造特定的回答内容 (模板渲染)
        if config.output_mode == "answer_content":
            # 使用 Jinja2 渲染模板
            # inputs 包含了所有上游节点的数据
            rendered_text = TemplateRenderer.render(config.content_template, inputs)
            
            final_output = {
                "output": rendered_text,
                "type": "text", # 标记类型，方便前端展示
                # 也可以保留原始数据以供调试
                "_raw_inputs": inputs 
            }
        
        # 模式 2: 返回所有上游变量 (透传)
        else:
            final_output = inputs

        return final_output


# ==========================================
# 3. Output Component (中间输出节点)
# ==========================================

class OutputConfig(BaseModel):
    content: str = Field(
        ..., 
        description="输出内容 (支持 {{var}} 插值)",
        json_schema_extra=UI.TextArea(
            rows=3, 
            placeholder="正在搜索关键词: {{ search_node.query }}..."
        )
    )
    stream: bool = Field(
        True, 
        description="是否流式输出到前端",
        json_schema_extra=UI.Switch()
    )

@register_component
class OutputComponent(Component):
    name = "output"
    label = "中间输出"
    description = "在工作流运行过程中向用户发送消息"
    icon = "message-square"
    group = "Basic"
    
    config_model = OutputConfig
    input_model = None

    async def execute(self, inputs: Dict[str, Any], config: OutputConfig) -> Dict[str, Any]:
        # 1. 渲染内容
        rendered_content = TemplateRenderer.render(config.content, inputs)
        
        # 2. 构造返回结构
        # Scheduler 或 SSE Handler 会识别 _ui_type 并将其推送给前端
        # 这种方式避免了在组件内部直接操作 Streamer，保持了组件的纯粹性
        return {
            "output": rendered_content,
            "is_stream": config.stream,
            
            # --- 前端协议字段 ---
            "_ui_type": "message", # 告诉前端这是一个消息气泡
            "_ui_content": rendered_content,
            "_ui_is_intermediate": True # 标记为中间过程消息
        }