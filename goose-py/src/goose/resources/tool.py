from enum import Enum
from typing import Dict, Any, Optional, Callable
from pydantic import BaseModel

class ToolSourceType(str, Enum):
    PLUGIN = "plugin"       # HTTP API 插件 (OpenAPI)
    BUILTIN = "builtin"     # 本地 Python 函数
    WORKFLOW = "workflow"   # 子工作流

class ToolDefinition(BaseModel):
    """
    [Metadata] 工具元数据定义
    用于描述工具的属性、来源和调用方式，不包含运行时的状态。
    """
    id: str
    name: str
    description: Optional[str] = None
    source_type: ToolSourceType
    
    # --- 执行所需配置 ---
    # PLUGIN: 包含 url, method, auth, headers 等
    execution_config: Optional[Dict[str, Any]] = None
    
    # BUILTIN: 指向实际的 Python 函数对象 (从 goose.tools.registry 获取或直接引用)
    func: Optional[Callable] = None
    
    # WORKFLOW: 指向子工作流 ID
    workflow_id: Optional[str] = None
    
    # 扩展字段：输入参数 Schema 等
    args_schema: Optional[Dict[str, Any]] = None

class ToolDefinitionRegistry:
    """
    [Resource Manager] 工具定义注册表
    负责存储和检索工具的'定义'信息。
    """
    _definitions: Dict[str, ToolDefinition] = {}

    @classmethod
    def register(cls, tool_def: ToolDefinition):
        cls._definitions[tool_def.id] = tool_def

    @classmethod
    def get(cls, tool_id: str) -> Optional[ToolDefinition]:
        return cls._definitions.get(tool_id)
        
    @classmethod
    def list_all(cls):
        return list(cls._definitions.values())