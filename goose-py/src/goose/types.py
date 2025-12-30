from __future__ import annotations
import json
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Union,Callable,TYPE_CHECKING
import time
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    computed_field,
    model_validator,
)

class NodeTypes:
    # --- 基础 ---
    UNDEFINED = "Undefined"
    ENTRY = "Entry"
    EXIT = "Exit"
    OUTPUT_EMITTER = "OutputEmitter"

    # --- AI & 代码 ---
    LLM = "LLM"
    CODE_RUNNER = "CodeRunner"
    LAMBDA = "Lambda"
    TEXT_PROCESSOR = "TextProcessor"
    INTENT_DETECTOR = "IntentDetector"
    QUESTION_ANSWER = "QuestionAnswer"

    # --- 控制流 ---
    LOOP = "Loop"
    BATCH = "Batch"
    BREAK = "Break"
    CONTINUE = "Continue"
    SELECTOR = "Selector"
    SUB_WORKFLOW = "SubWorkflow"

    # --- 变量与数据 ---
    VARIABLE_ASSIGNER = "VariableAssigner"
    VARIABLE_AGGREGATOR = "VariableAggregator"
    VARIABLE_ASSIGNER_WITHIN_LOOP = "VariableAssignerWithinLoop"
    JSON_SERIALIZATION = "JsonSerialization"
    JSON_DESERIALIZATION = "JsonDeserialization"

    # --- 工具与连接 ---
    TOOL = "Tool"
    PLUGIN = "Plugin"
    HTTP_REQUESTER = "HTTPRequester"
    INPUT_RECEIVER = "InputReceiver"

    # --- 知识库 ---
    KNOWLEDGE_RETRIEVER = "KnowledgeRetriever"
    KNOWLEDGE_INDEXER = "KnowledgeIndexer"
    KNOWLEDGE_DELETER = "KnowledgeDeleter"

    # --- 数据库 ---
    DATABASE_CUSTOM_SQL = "DatabaseCustomSQL"
    DATABASE_QUERY = "DatabaseQuery"
    DATABASE_INSERT = "DatabaseInsert"
    DATABASE_DELETE = "DatabaseDelete"
    DATABASE_UPDATE = "DatabaseUpdate"

    # --- 对话 ---
    CREATE_CONVERSATION = "CreateConversation"
    CONVERSATION_LIST = "ConversationList"
    CONVERSATION_UPDATE = "ConversationUpdate"
    CONVERSATION_DELETE = "ConversationDelete"
    CONVERSATION_HISTORY = "ConversationHistory"
    CLEAR_CONVERSATION_HISTORY = "ClearConversationHistory"

    MESSAGE_LIST = "MessageList"
    CREATE_MESSAGE = "CreateMessage"
    EDIT_MESSAGE = "EditMessage"
    DELETE_MESSAGE = "DeleteMessage"
    COMMENT = "Comment"


class NodeStatus:
    PENDING = "Pending"
    RUNNING = "Running"
    COMPLETED = "Completed"
    FAILED = "Failed"
    SKIPPED = "Skipped"


class ResourceType:
    WORKFLOW = "workflow"
    COMPONENT = "component"
    LAMBDA = "lambda"
    PLUGIN = "plugin"
    TOOL = "tool"
    MODEL = "model"
    KNOWLEDGE = "knowledge"
    PROMPT = "prompt"
    FILE = "file"
    VARIABLE = "variable"
    CUSTOM_FUNCTION = "function"


class DomainType:
    """
    [Core/Memory Layer] 系统注册表领域 (Plural)
    对应 SystemRegistry 中的 Key
    """
    APPS = "apps"
    CHATS = "chats"
    TRIGGERS = "triggers"
    # 核心领域
    COMPONENTS = "components"
    LAMBDAS = "lambdas"

    WORKFLOWS = "workflows"
    EXECUTIONS = "executions"
    # 资源领域
    # --- 2. 资源聚合领域 (映射到 ResourceModel) ---
    # 这里的 Resource 是一个总称，用于泛型操作
    RESOURCES = "resources"  # -> ResourceModel (查所有类型)

    # 下面这些在逻辑上是独立的，但在物理上都映射到 ResourceModel
    # 允许 Service 层使用更具体的语义来调用 persistence
    MODELS = "models"  # -> ResourceModel
    TOOLS = "tools"  # -> ResourceModel
    KNOWLEDGE = (
        "knowledge"  # -> ResourceModel (建议去掉 s，保持单数或改为 knowledge_bases)
    )
    PLUGINS = "plugins"  # -> ResourceModel

    # 扩展领域预留
    VOICES = "voices"
    PROMPTS = "prompts"


class ToolSourceType:
    BUILTIN = "builtin"
    WORKFLOW = "workflow"
    PLUGIN = "plugin"


class ModelType:
    LLM = "llm"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class ToolAuthType(str, Enum):
    NONE = "none"
    BEARER = "bearer"
    HEADER = "header"

class ServiceType:
    """
    [Core Standard] 核心协议定义的服务类型
    """

    # 基础设置
    SANDBOX = "sandbox"  # 代码沙箱
    ASYNC_TASK = "async_task"  # 异步任务
    EVENT_BUS = "event_bus"  # 事件总线

    # 核心能力
    KNOWLEDGE = "knowledge"  # 知识库服务
    MODEL_FACTORY = "model_factory"  # 模型工厂
    RESOURCE_MANAGER = "resource_manager"  # 资源管理器 (Read-only)
    PERSISTENCE = "persistence"
    TRANSACTION = "transaction"

    # 基础设施特有
    REDIS = "redis"
    VECTOR_STORE = "vector_store"
    BLOB_STORAGE = "blob_storage"
    SQL_DATABASE = "sql_database"
    PERSISTENCE_STREAM = "persistence_stream"
    PERSISTENCE_STREAM_FACTORY = "persistence_stream_factory"

# --- 执行配置定义 (针对不同 SourceType) ---


class HttpExecutionConfig(BaseModel):
    """插件/API 执行配置"""

    url: str
    method: str = "POST"
    headers: Dict[str, str] = {}
    timeout: int = 60
    # 鉴权配置通常存储在加密的 Credential 表中，这里只存引用或非敏感信息
    auth_type: ToolAuthType = ToolAuthType.NONE
    auth_config: Dict[str, Any] = {}


class BuiltinExecutionConfig(BaseModel):
    """内置函数执行配置"""

    # 模块路径或注册表 Key, e.g., "opencoze.tools.web_search"
    entry_point: str
    # 允许传递一些静态参数
    kwargs: Dict[str, Any] = {}


class WorkflowExecutionConfig(BaseModel):
    """工作流引用配置"""

    workflow_id: str
    version_id: Optional[str] = None

class Document(BaseModel):
    id: str | None = Field(default=None, coerce_numbers_to_str=True)
    content: str = Field(..., description="The content of the document")
    metadata: dict = Field(default_factory=dict)

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

# 对应 model.rs 中的 MODEL_SPECIFIC_LIMITS
MODEL_LIMITS = {
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-3.5-turbo": 16_385,
    "claude-3-5-sonnet": 200_000,
    # ... 其他模型
}

DEFAULT_CONTEXT_LIMIT = 128_000

class ModelConfig(BaseModel):
    """对应 Rust: pub struct ModelConfig"""
    model_name: str
    context_limit: Optional[int] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    fast_model: Optional[str] = None
     
    toolshim: bool = False
    toolshim_model: Optional[str] = None
   
    def context_window(self) -> int:
        if self.context_limit:
            return self.context_limit
        # 简单的模糊匹配查找限制，模拟 Rust 的 get_model_specific_limit
        for key, limit in MODEL_LIMITS.items():
            if key in self.model_name:
                return limit
        return DEFAULT_CONTEXT_LIMIT

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
