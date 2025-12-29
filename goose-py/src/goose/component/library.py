from typing import Dict, Any, Optional,List
from pydantic import Field,ConfigDict

from .base import Component
from .registry import register_component
from goose.workflow.nodes import FunctionNode, AgentNode
from goose.agent import Agent
from goose.workflow import Runnable
from goose.providers import ProviderFactory
# ==================================
# 1. LLM / Agent 组件
# ==================================

class LLMConfig(BaseModel):
    id: str = Field(..., description="模型 ID (e.g., gpt-4)")
    
    model: Optional[str] = Field(None, description="模型名称", alias="model_name")
    base_url: Optional[str] = Field(None, description="API Base URL")
    api_key: Optional[str] = Field(None, description="API Key")

    batch: bool = Field(False, description="是否启用批量处理")
    
    # 输出格式: "text" 或 "json_object"
    response_format: str = Field("text", description="输出模式")
    
    # 动态输出定义，通常由前端传过来告诉后端输出变量叫什么名字
    output_definitions: List[Dict[str, Any]] = Field(default_factory=list, description="Dynamic output definitions")

    enable_reasoning: bool = False 
    prompt: str = Field(..., description="用户提示词")
    system_prompt: str = Field("", description="系统提示词")
    
    tools: List[str] = Field(default_factory=list, description="挂载的工具列表")
    
    temperature: float = 0.7
    max_tokens: int = 4096
    max_iterations: int = 5 

    model_config = ConfigDict(extra='allow')

@register_component
class LLMComponent(Component):
    name = "llm_chat"
    label = "LLM 对话"
    group = "AI 能力"
    icon = "cpu"
    config_model = LLMConfig

    def create_node(self, node_id: str, config: Dict[str, Any], inputs: Dict[str, Any]) -> Runnable:
        # 1. 验证配置
        cfg = LLMConfig(**config)
        
        # 2. 构造 Agent (这里应该结合 ResourceLoader，暂简化)
        # 假设我们有一个简单的 Agent 工厂
        agent = ProviderFactory.create("siliconflow", config)
        print(f"Created Provider: {type(agent).__name__}")
        
        async def mock_reply(session_id, user_input):
            from ..events import Event, EventType
            yield Event(type=EventType.TEXT, text=f"Mock AI Reply ({cfg.model}): {user_input}")
        agent.reply = mock_reply

        # 3. 返回 AgentNode
        # AgentNode 继承自 CozeNodeMixin，可以直接处理 inputs 映射
        return AgentNode(agent, inputs=inputs, name=cfg.title)


# ==================================
# 2. Code / Python 组件
# ==================================

class CodeConfig(BaseModel):
    code: str = Field(
        "def main(**kwargs):\n    return {'result': 'ok'}", 
        description="Python 代码"
    )

@register_component
class CodeComponent(Component):
    name = "python_code"
    label = "Python 代码"
    group = "高级"
    icon = "code"
    config_model = CodeConfig

    def create_node(self, node_id: str, config: Dict[str, Any], inputs: Dict[str, Any]) -> Runnable:
        cfg = CodeConfig(**config)
        
        # 动态编译代码 (生产环境请加沙箱!)
        local_scope = {}
        exec(cfg.code, {}, local_scope)
        func = local_scope.get("main", lambda **k: {"error": "main not found"})
        
        return FunctionNode(func, inputs=inputs, name=cfg.title)


# ==================================
# 3. Start 组件
# ==================================

@register_component
class StartComponent(Component):
    name = "start"
    label = "开始"
    group = "基础"
    icon = "play"

    def create_node(self, node_id: str, config: Dict[str, Any], inputs: Dict[str, Any]) -> Runnable:
        # Start 节点通常不需要执行逻辑，只是作为数据源
        # 但在 Graph 中它需要存在。
        return FunctionNode(lambda **kwargs: kwargs, inputs=inputs, name="Start")