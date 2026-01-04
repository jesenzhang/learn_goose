# server/dto.py
from pydantic import BaseModel, Field
from goose.components import ComponentMeta
from goose.workflow import WorkflowDefinition
from typing import List, Dict, Any, Optional,Literal, Generic, TypeVar
from datetime import datetime

# 通用响应模型
T = TypeVar('T')

# --- 通用响应 ---
class ApiResponse(BaseModel, Generic[T]):
    """统一API响应格式"""
    code: int = 0
    msg: str = "success"
    data: Optional[T] = None

class Pagination(BaseModel):
    """分页信息"""
    page: int = 1
    page_size: int = 10
    total: int = 0

class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应格式"""
    code: int = 0
    msg: str = "success"
    data: List[T] = []
    pagination: Pagination = Field(default_factory=Pagination)
    
    
# --- 组件列表响应 ---
class ListComponentsResponse(BaseModel):
    """
    符合 Coze 前端协议的组件列表响应
    """
    official_components: Dict[str, List[ComponentMeta]] = Field(default_factory=dict)
    custom_components: Dict[str, List[ComponentMeta]] = Field(default_factory=dict)


# --- 工作流相关请求 ---
class WorkflowReq(BaseModel):
    workflow: WorkflowDefinition 
    title: str = "Untitled Workflow"


# --- 执行记录响应 ---
class ExecutionModelDTO(BaseModel):
    """ExecutionModel的Pydantic版本，用于API响应"""
    id: str
    workflow_id: str
    status: str
    inputs: Dict[str, Any]
    outputs: Optional[Dict[str, Any]] = None
    logs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime

class RunReq(BaseModel):
    inputs: Dict[str, Any] = Field(default_factory=dict)
    
    # [新增] 目标节点 ID (Run to Node)
    # 如果设置了此字段，工作流将在该节点执行完毕后停止
    target_node_id: Optional[str] = Field(None, description="Debug模式：运行至指定节点后停止")

class ResumeReq(BaseModel):
    """恢复运行请求"""
    inputs: Dict[str, Any] = Field(default_factory=dict, description="可选：补充或覆盖之前的变量")
     
class SingleNodeRunReq(BaseModel):
    """单节点测试请求"""
    node_type: str = Field(..., description="组件类型标识, e.g. 'model.llm'")
    config: Dict[str, Any] = Field(default_factory=dict, description="组件静态配置")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="运行时输入")
    mock_context: Dict[str, Any] = Field(default_factory=dict, description="模拟的上下文变量")
    
# --- Request ---
class CreateApiComponentReq(BaseModel):
    key: str = Field(..., pattern="^[a-zA-Z0-9_]+$", description="唯一标识")
    name: str = Field(..., description="组件名称")
    description: str = ""
    url: str = Field(..., description="API 地址")
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST"
    input_definitions: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema inputs")
    output_definitions: List[Dict[str, Any]] = Field(default_factory=list, description="Output variables")

# --- Response (Frontend View) ---
class ComponentView(BaseModel):
    """前端组件面板使用的视图对象"""
    type: str
    label: str
    group: str
    icon: Optional[str] = None
    description: Optional[str] = None
    # VueFlow/ReactFlow 特有的端口定义
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    
class ChatReq(BaseModel):
    conversation_id: str
    query: str
    stream: bool = True

# --- Responses ---
class ExecutionDTO(BaseModel):
    id: str
    workflow_id: str
    status: str
    inputs: Optional[Dict[str, Any]]
    outputs: Optional[Dict[str, Any]]
    error: Optional[str]
    created_at: Any
    
    

# --- Shared Properties ---
class AppBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=200)
    icon: Optional[str] = Field(None, description="Avatar URL")
    
    # [核心关联]
    workflow_id: str = Field(..., description="关联的工作流ID")

    # [交互配置]
    opening_statement: Optional[str] = Field(None, description="开场白")
    suggested_questions: List[str] = Field(default_factory=list, description="预设引导问题")
    
    # [高级配置]
    # 允许在不修改 Workflow 的情况下覆盖某些参数 (如 LLM 温度)
    model_config_override: Dict[str, Any] = Field(default_factory=dict)

# --- Requests ---
class CreateAppReq(AppBase):
    pass

class UpdateAppReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    workflow_id: Optional[str] = None
    opening_statement: Optional[str] = None
    suggested_questions: Optional[List[str]] = None
    model_config_override: Optional[Dict[str, Any]] = None
    is_published: Optional[bool] = None

# --- Responses ---
class AppResponse(AppBase):
    id: str
    creator_id: str
    is_published: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 额外信息：关联的工作流名称 (方便前端展示)
    workflow_name: Optional[str] = None