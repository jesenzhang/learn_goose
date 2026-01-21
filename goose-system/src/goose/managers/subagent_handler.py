"""
Subagent Handler

子代理处理器。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from enum import Enum
import uuid


class SubagentStatus(str, Enum):
    """子代理状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentConfig:
    """子代理配置"""
    name: str
    instructions: str
    max_turns: int = 10
    tools: List[str] = field(default_factory=list)
    parent_agent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubagentConfig":
        return cls(
            name=data.get("name", "subagent"),
            instructions=data.get("instructions", ""),
            max_turns=data.get("max_turns", 10),
            tools=data.get("tools", []),
            parent_agent_id=data.get("parent_agent_id"),
            metadata=data.get("metadata", {})
        )


@dataclass
class SubagentResult:
    """子代理结果"""
    status: SubagentStatus
    messages: List[Dict[str, Any]] = field(default_factory=list)
    output: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "messages": self.messages,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata
        }


class SubagentHandler:
    """
    子代理处理器
    
    职责：
    - 子 Agent 创建和隔离
    - 任务配置和执行
    - 结果收集
    """
    
    def __init__(self, agent: "Agent"):
        self.agent = agent
        self.active_subagents: Dict[str, "Subagent"] = {}
        self.max_nesting_depth: int = 2
    
    async def execute_subagent(
        self,
        task_config: SubagentConfig
    ) -> SubagentResult:
        """
        执行子代理
        
        Args:
            task_config: 子代理配置
            
        Returns:
            子代理执行结果
        """
        # 检查嵌套深度
        if self._get_current_depth() >= self.max_nesting_depth:
            return SubagentResult(
                status=SubagentStatus.FAILED,
                error="Maximum subagent nesting depth exceeded"
            )
        
        # 创建隔离的 Agent
        subagent = self._create_isolated_agent(task_config)
        
        try:
            # 执行任务
            result = await self._run_subagent(subagent, task_config)
            return result
        except Exception as e:
            return SubagentResult(
                status=SubagentStatus.FAILED,
                error=str(e)
            )
    
    def _create_isolated_agent(self, config: SubagentConfig) -> "Agent":
        """创建隔离的 Agent 实例"""
        from ..agent.base import Agent, AgentConfig

        agent_config = AgentConfig(
            max_turns=config.max_turns,
            session_id=f"subagent_{uuid.uuid4().hex[:8]}"
        )

        agent = Agent(provider=self.agent.config.provider, config=agent_config)

        if config.instructions:
            agent.conversation.set_system_prompt(config.instructions)

        return agent
    
    async def _run_subagent(
        self,
        agent: "Agent",
        config: SubagentConfig
    ) -> SubagentResult:
        """运行子代理"""
        # 记录状态
        subagent_id = str(uuid.uuid4())
        self.active_subagents[subagent_id] = agent
        
        try:
            # 执行回复循环 (简化版本)
            messages = []
            
            # 模拟执行 - 在实际实现中会运行完整的 Agent.reply() 循环
            messages.append({
                "role": "assistant",
                "content": f"Subagent '{config.name}' started"
            })
            
            return SubagentResult(
                status=SubagentStatus.COMPLETED,
                messages=messages,
                output=f"Subagent '{config.name}' completed",
                metadata={"config": config.name}
            )
        finally:
            self.active_subagents.pop(subagent_id, None)
    
    def _get_current_depth(self) -> int:
        """获取当前嵌套深度"""
        return len(self.active_subagents)
    
    def cancel_subagent(self, subagent_id: str) -> bool:
        """取消子代理"""
        if subagent_id in self.active_subagents:
            self.active_subagents[subagent_id].cancel()
            del self.active_subagents[subagent_id]
            return True
        return False
    
    def cancel_all(self) -> None:
        """取消所有子代理"""
        for subagent in self.active_subagents.values():
            subagent.cancel()
        self.active_subagents.clear()


class Subagent:
    """子代理 (简化版)"""
    
    def __init__(self, config: SubagentConfig):
        self.config = config
        self.status = SubagentStatus.PENDING
        self.messages: List[Dict[str, Any]] = []
    
    def cancel(self) -> None:
        """取消执行"""
        self.status = SubagentStatus.CANCELLED
