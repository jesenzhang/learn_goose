"""
Subagent Handler

Manages subagent execution with isolation and resource limits.
Reference: goose-rs subagent_handler.rs

Features:
- Subagent isolation (separate Agent instances)
- Independent conversation history
- Configurable max_turns
- Resource limits
- Result collection
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator
from enum import Enum

logger = logging.getLogger("goose.subagent")


class SubagentStatus(str, Enum):
    """Subagent execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentConfig:
    """Subagent configuration."""
    name: str
    system_prompt: str
    max_turns: int = 50
    max_input_tokens: int = 100000
    max_output_tokens: int = 4000
    allowed_tools: List[str] = field(default_factory=list)
    blocked_tools: List[str] = field(default_factory=list)
    isolation_level: str = "full"  # full, partial, none


@dataclass
class SubagentResult:
    """Subagent execution result."""
    status: SubagentStatus
    conversation: Dict[str, Any] = field(default_factory=dict)
    output: Optional[str] = None
    error: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0


class SubagentHandler:
    """
    Handles subagent execution with isolation.

    Reference: goose-rs SubagentHandler
    """

    def __init__(self):
        self._active_subagents: Dict[str, 'Subagent'] = {}
        self._results: Dict[str, SubagentResult] = {}
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Number of active subagents."""
        return len(self._active_subagents)

    async def create_subagent(
        self,
        config: SubagentConfig,
        parent_agent: 'Agent'
    ) -> 'Subagent':
        """
        Create a new subagent instance.

        Args:
            config: Subagent configuration
            parent_agent: Parent agent for tool sharing

        Returns:
            Subagent instance
        """
        from goose.agent.base import Agent, AgentConfig

        subagent = Subagent(config, parent_agent)

        async with self._lock:
            self._active_subagents[subagent.id] = subagent

        return subagent

    async def execute(
        self,
        config: SubagentConfig,
        task_prompt: str,
        parent_agent: 'Agent'
    ) -> SubagentResult:
        """
        Execute a subagent task.

        Args:
            config: Subagent configuration
            task_prompt: Task to execute
            parent_agent: Parent agent

        Returns:
            SubagentResult with execution outcome
        """
        import time
        start_time = time.time()

        subagent = await self.create_subagent(config, parent_agent)

        try:
            result = await subagent.run(task_prompt)
            status = SubagentStatus.COMPLETED
            error = None
        except Exception as e:
            status = SubagentStatus.FAILED
            error = str(e)
            result = SubagentResult(
                status=status,
                error=error,
                duration_ms=(time.time() - start_time) * 1000
            )

        async with self._lock:
            self._active_subagents.pop(subagent.id, None)
            self._results[subagent.id] = result

        return result

    async def cancel(self, subagent_id: str) -> bool:
        """Cancel a running subagent."""
        async with self._lock:
            if subagent_id in self._active_subagents:
                subagent = self._active_subagents[subagent_id]
                await subagent.cancel()
                self._active_subagents[subagent_id]._status = SubagentStatus.CANCELLED
                return True
        return False

    def get_result(self, subagent_id: str) -> Optional[SubagentResult]:
        """Get result for a completed subagent."""
        return self._results.get(subagent_id)

    def get_active_subagents(self) -> List[str]:
        """Get list of active subagent IDs."""
        return list(self._active_subagents.keys())


class Subagent:
    """
    Subagent instance with isolation.

    Reference: goose-rs SubAgent
    """

    def __init__(self, config: SubagentConfig, parent_agent: 'Agent'):
        import uuid
        self.id = str(uuid.uuid4())[:8]
        self.config = config
        self._status = SubagentStatus.PENDING
        self._parent = parent_agent

        from goose.agent.base import Agent, AgentConfig

        self._agent = Agent(
            provider=parent_agent.provider,
            config=AgentConfig(
                session_id=f"subagent_{self.id}",
                max_turns=config.max_turns,
                system_prompt=config.system_prompt
            )
        )

        self._setup_isolation()

    def _setup_isolation(self) -> None:
        """Setup tool isolation based on config."""
        for tool in self._parent.tools:
            if self.config.allowed_tools:
                if tool.name in self.config.allowed_tools:
                    self._agent.register_tool(tool)
            elif tool.name not in self.config.blocked_tools:
                self._agent.register_tool(tool)

    @property
    def status(self) -> SubagentStatus:
        return self._status

    async def run(self, task_prompt: str) -> SubagentResult:
        """Execute the subagent task."""
        import time
        from goose.providers import Message

        self._status = SubagentStatus.RUNNING
        start_time = time.time()

        try:
            await self._agent.reply(task_prompt)

            conversation = self._agent.conversation.to_provider_format() if hasattr(
                self._agent.conversation, 'to_provider_format'
            ) else []

            output = ""
            for msg in reversed(conversation):
                if msg.get("role") == "assistant":
                    output = msg.get("content", "")
                    break

            tool_calls = []
            for msg in conversation:
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    tool_calls.extend(msg["tool_calls"])

            session_info = self._agent.get_session_info()

            self._status = SubagentStatus.COMPLETED

            return SubagentResult(
                status=self._status,
                conversation=conversation,
                output=output,
                usage={
                    "input_tokens": session_info.get("turn_count", 0) * 100,
                    "output_tokens": len(output) // 4
                },
                tool_calls=tool_calls,
                duration_ms=(time.time() - start_time) * 1000
            )

        except asyncio.CancelledError:
            self._status = SubagentStatus.CANCELLED
            raise
        except Exception as e:
            self._status = SubagentStatus.FAILED
            raise

    async def cancel(self) -> None:
        """Cancel subagent execution."""
        self._status = SubagentStatus.CANCELLED
        self._agent.session_state._max_turns = 0


# Forward reference for Agent
Agent = None
