from typing import Dict, Any, List, Optional, Type
from pydantic import BaseModel, Field, AliasChoices

# ==========================================
# 1. UI 定义 (完全复用您的代码)
# ==========================================
class Port(BaseModel):
    name: str 
    title: str
    type: str = "any"
    ui_widget: Optional[str] = None

class UIConfig(BaseModel):
    icon: str = "default"
    label: str = ""
    description: str = ""
    ports: Dict[str, List[Port]] = Field(
        default_factory=lambda: {"inputs": [], "outputs": []}
    )

# ==========================================
# 2. 逻辑定义
# ==========================================
class ComponentDefinition(BaseModel):
    # 静态配置 Schema (用于侧边栏表单)
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    # 动态输入 Schema (用于连线校验)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    # 输出 Schema (用于下游推导)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    # UI 元数据
    ui: UIConfig = Field(default_factory=UIConfig)

# ==========================================
# 3. 组件元数据 (Registry Item)
# ==========================================
class ComponentMeta(BaseModel):
    type: str = Field(..., validation_alias=AliasChoices("id", "type"))
    version: str = "1.0.0"
    author: str = "System"
    group: str = "default"
    tags: List[str] = []
    definition: ComponentDefinition
    runner_ref: str = ""

    @property
    def id(self) -> str: return self.type


