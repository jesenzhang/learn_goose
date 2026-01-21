"""
Agent State Management

状态管理，参考 Goose-Rs 的 SkillsState 设计。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import copy


class JumpTo(str, Enum):
    """控制流跳转目标"""
    TOOLS = "tools"
    MODEL = "model"
    END = "end"


@dataclass
class AgentState:
    """Agent 基础状态"""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    jump_to: Optional[str] = None
    structured_response: Optional[Any] = None
    
    def model_copy(self) -> "AgentState":
        """创建状态副本"""
        return AgentState(
            messages=copy.deepcopy(self.messages),
            jump_to=self.jump_to,
            structured_response=copy.deepcopy(self.structured_response)
        )
    
    def add_message(self, role: str, content: Any, **extra) -> None:
        """添加消息"""
        message = {"role": role, "content": content}
        message.update(extra)
        self.messages.append(message)
    
    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """获取最后一条消息"""
        return self.messages[-1] if self.messages else None
    
    def get_last_user_message(self) -> Optional[str]:
        """获取最后一条用户消息"""
        for msg in reversed(self.messages):
            if msg.get("role") == "user":
                return msg.get("content", "")
        return None


@dataclass
class SkillsState(AgentState):
    """支持 Skills 的状态"""
    skills_metadata: Optional[List[Dict[str, Any]]] = None
    active_skills: List[str] = field(default_factory=list)
    
    def model_copy(self) -> "SkillsState":
        """创建状态副本"""
        return SkillsState(
            messages=copy.deepcopy(self.messages),
            jump_to=self.jump_to,
            structured_response=copy.deepcopy(self.structured_response),
            skills_metadata=copy.deepcopy(self.skills_metadata),
            active_skills=copy.deepcopy(self.active_skills)
        )
    
    def add_skill_metadata(self, skill: Dict[str, Any]) -> None:
        """添加 skill 元数据"""
        if self.skills_metadata is None:
            self.skills_metadata = []
        self.skills_metadata.append(skill)
    
    def activate_skill(self, skill_name: str) -> None:
        """激活 skill"""
        if skill_name not in self.active_skills:
            self.active_skills.append(skill_name)
    
    def deactivate_skill(self, skill_name: str) -> None:
        """停用 skill"""
        if skill_name in self.active_skills:
            self.active_skills.remove(skill_name)


@dataclass
class ToolExecutionState:
    """工具执行状态"""
    tool_name: str
    arguments: Dict[str, Any]
    status: str = "pending"  # pending, running, approved, denied, completed, error
    result: Optional[Any] = None
    error: Optional[str] = None
    approval_requested: bool = False
    approval_received: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "approval_requested": self.approval_requested,
            "approval_received": self.approval_received,
        }


@dataclass
class SessionState:
    """会话状态"""
    session_id: str
    conversation_state: SkillsState = field(default_factory=SkillsState)
    tool_execution_queue: List[ToolExecutionState] = field(default_factory=list)
    turn_count: int = 0
    max_turns: int = 100
    compact_threshold: float = 0.8  # 压缩阈值
    compact_ratio: float = 0.5  # 压缩比例
    
    def can_continue(self) -> bool:
        """检查是否可以继续"""
        return self.turn_count < self.max_turns
    
    def increment_turn(self) -> None:
        """增加回合数"""
        self.turn_count += 1
    
    def should_compact(self, message_count: int, context_limit: int) -> bool:
        """检查是否需要压缩"""
        return (message_count / context_limit) > self.compact_threshold
    
    def queue_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """将工具加入执行队列"""
        execution = ToolExecutionState(
            tool_name=tool_name,
            arguments=arguments
        )
        self.tool_execution_queue.append(execution)
        return len(self.tool_execution_queue) - 1
    
    def get_pending_tools(self) -> List[ToolExecutionState]:
        """获取待执行的工具"""
        return [t for t in self.tool_execution_queue if t.status == "pending"]
    
    def update_tool_status(
        self,
        index: int,
        status: str,
        result: Any = None,
        error: str = None
    ) -> None:
        """更新工具状态"""
        if 0 <= index < len(self.tool_execution_queue):
            self.tool_execution_queue[index].status = status
            if result is not None:
                self.tool_execution_queue[index].result = result
            if error is not None:
                self.tool_execution_queue[index].error = error
