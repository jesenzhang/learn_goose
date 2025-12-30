from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field

# --- 基础类型 ---
# class InputSource(BaseModel):
#     """描述参数来源：固定值 or 引用"""
#     type: Literal["value", "reference"] = "value"
#     value: Any = None
#     ref_key: Optional[str] = None # e.g. "node_id.output_key"

# class NodeInput(BaseModel):
#     """节点的输入参数集合"""
#     # key 是参数名, value 是来源描述
#     parameters: Dict[str, InputSource] = Field(default_factory=dict)

# --- 节点定义 ---
class NodeConfig(BaseModel):
    """通用节点定义"""
    id: str
    type: str  # 组件类型: "start", "end", "llm", "code", "loop", "if-else"
    title: str = "Untitled"
    
    # 输入参数配置
    inputs:Dict[str, Any] = Field(default_factory=dict)
    
    # 节点特有配置 (例如 LLM 的 model_config, Loop 的 count 等)
    config: Dict[str, Any] = Field(default_factory=dict)
    # 2. 类型契约 (校验依据: 是什么)
    # [新增] 存储解析后的 TypeInfo，用于 DynamicModelFactory
    schema_info: Dict[str, Any] = Field(default_factory=dict)
    
    raw_data: Dict[str, Any] = Field(default_factory=dict)

    # 3. 错误策略
    error_policy: Dict[str, Any] = Field(default_factory=dict)


class EdgeConfig(BaseModel):
    """连线定义"""
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None # 用于区分不同的输出端口 (如 if-else 的 true/false)
    target_handle: Optional[str] = None

class WorkflowDefinition(BaseModel):
    """完整工作流定义"""
    id: str
    name: str = "Untitled Flow"
    nodes: List[NodeConfig]
    edges: List[EdgeConfig] = []

class ControlSignal:
    """控制流协议常量"""
    
    # [Branching] 激活的句柄 ID
    # 组件返回 {"_active_handle": "true"} -> Scheduler 只走 handle="true" 的边
    ACTIVE_HANDLE = "_active_handle"
    
    # [Loop Control] 循环控制信号
    # 组件返回 {"_control_signal": "BREAK"} -> 父级 Loop 组件捕获
    SIGNAL_KEY = "_control_signal"
    BREAK = "BREAK"
    CONTINUE = "CONTINUE"
    
    # [UI] 前端交互标记
    UI_TYPE = "_ui_type"