# core/protocol/type.py
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Union,Callable

from pydantic import BaseModel, ConfigDict, Field


# --------------------------
# 复用你定义的 DataType 枚举和 TypeInfo 模型（完整保留）
# --------------------------
class DataType(str,Enum):
    """基础数据类型枚举（扩展支持time/file）"""

    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "list"  # 对应数组类型，别名是list
    TIME = "time"
    FILE = "file"


class TypeInfo(BaseModel):
    # --- 核心类型定义 ---
    type: DataType

    # --- 递归定义 ---
    # 使用 Dict 保证查找效率和唯一性
    properties: Optional[Dict[str, "TypeInfo"]] = None

    # 数组元素类型
    elem_type_info: Optional["TypeInfo"] = Field(default=None, alias="elem_type")

    # --- UI/业务元数据 ---
    title: Optional[str] = None
    description: Optional[str] = None
    required: bool = False
    default: Any = None

    # [新增] 只有在 UI 渲染顺序非常重要时才需要。
    # 通常 Pydantic/Python 3.7+ 的 Dict 已经是有序的，所以这个字段可能是不必要的。
    # property_order: List[str] = []

    # --- 领域扩展 ---
    file_type: Optional[str] = None
    time_format: Optional[str] = None

    # --- 血缘/调试信息 (从 Parameter 借鉴) ---
    # 这些是"实例"属性而非"类型"属性，但为了方便可以放在这里
    original_source: Optional[str] = Field(None, description="e.g. node_id.output_key")

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True  # 关键：序列化时将 Enum 转为 str
    )

# 解决 Pydantic 递归模型的引用问题
TypeInfo.model_rebuild()


# 3. 节点动态配置容器
class DynamicConfig(BaseModel):
    input_parameters: List[TypeInfo] = Field(default_factory=list)
    output_parameters: List[TypeInfo] = Field(default_factory=list)
    
    model_config = ConfigDict(use_enum_values=True)

class InputMapping(BaseModel):
    name: str
    value: Any = None # 支持 {{ var }} 引用
    
class ParameterDefinition(BaseModel):
    """
    [优化版] 变量定义
    将 'Key' (变量名) 与 'Value Schema' (TypeInfo) 分离，
    从而支持定义复杂的嵌套对象或数组结构。
    """
    key: str = Field(..., description="变量名/字段名")
    
    # 复用 TypeInfo 来描述值的结构 (支持递归 properties 和 elem_type)
    type_info: TypeInfo = Field(..., description="值的类型描述")
    
    # 业务属性
    label: Optional[str] = None # 前端显示的友好名称
    description: Optional[str] = None
    
    model_config = {"populate_by_name": True}
