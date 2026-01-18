"""
Task tool for launching subagents.

This tool provides:
- Launch subagents for specialized tasks
- Create nested sessions with specific permissions
- Disable todo and task tools for subagents by default
- Stream tool execution progress via events
- Subagent session tracking
"""

import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult


# In-memory agent registry (in production, load from config)
_AGENTS = {
    "explore": {
        "name": "explore",
        "description": "Fast codebase exploration subagent for finding files and searching code",
        "mode": "subagent",
    },
    "general": {
        "name": "general",
        "description": "General purpose subagent for research and multi-step tasks",
        "mode": "subagent",
    },
    "compaction": {
        "name": "compaction",
        "description": "Hidden agent for conversation compaction",
        "mode": "primary",
        "hidden": True,
    },
}


class TaskParams(ToolInputSchema):
    """Parameters for the Task tool."""

    description: str = Field(
        ...,
        description="A short (3-5 words) description of the task",
    )
    prompt: str = Field(..., description="The task for the agent to perform")
    subagent_type: str = Field(
        ...,
        description="The type of specialized agent to use for this task",
    )
    session_id: Optional[str] = Field(
        None,
        description="Existing Task session to continue",
    )
    command: Optional[str] = Field(
        None,
        description="The command that triggered this task",
    )


class TaskTool(Tool):
    """
    Launch subagents for specialized tasks.

    Features:
    - Creates nested sessions with specific permissions
    - Disables todo and task tools for subagents by default
    - Subagent session tracking
    - Progress streaming via events

    Usage:
    - description (required): Short 3-5 word description
    - prompt (required): Task for the agent
    - subagent_type (required): Agent type (explore, general, etc.)
    - session_id (optional): Existing session to continue
    - command (optional): Trigger command
    """

    name = "task"
    description = (
        "Launch a subagent for specialized tasks. Creates a nested session with specific permissions. "
        "Available agent types: explore (fast codebase exploration, read-only tools), "
        "general (research and multi-step tasks). "
        "Subagents have todo and task tools disabled by default."
    )
    input_schema = TaskParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._session_id = self.config.get("session_id", "default")
        self._parent_session_id = self.config.get("parent_session_id")
        self._agents = _AGENTS.copy()

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the task by launching a subagent.

        Args:
            params: Dictionary containing 'description', 'prompt', 'subagent_type',
                     optional 'session_id', and 'command'.

        Returns:
            ToolResult with task result summary.

        Raises:
            ToolError: If agent type not found or task execution fails.
        """
        description = params["description"]
        prompt = params["prompt"]
        subagent_type = params["subagent_type"]
        session_id = params.get("session_id")
        command = params.get("command")

        # Validate agent type
        agent = self._agents.get(subagent_type)
        if not agent:
            available = ", ".join(self._agents.keys())
            raise ToolError(
                f"Unknown agent type: {subagent_type}. "
                f"Available types: {available}"
            )

        # In a real implementation, this would:
        # 1. Create a new nested session
        # 2. Set permissions (disable todo/task tools)
        # 3. Run the agent with the prompt
        # 4. Stream progress via events
        # 5. Return the summary

        # For now, simulate a result
        result_metadata = {
            "subagent_type": subagent_type,
            "description": description,
            "session_id": session_id or "new_session_id",
            "command": command,
        }

        return ToolResult(
            content=f"Task '{description}' delegated to {subagent_type} agent.\n\n"
                    f"The agent is processing: {prompt[:100]}...",
            metadata=result_metadata,
        )

    def register_agent(self, agent_info: Dict[str, Any]) -> None:
        """
        Register a custom agent type.

        Args:
            agent_info: Dictionary with agent configuration.
        """
        self._agents[agent_info["name"]] = agent_info

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        # Build agent list for description
        agent_descriptions = []
        for name, agent in self._agents.items():
            if not agent.get("hidden"):
                agent_descriptions.append(f"- {name}: {agent.get('description', '')}")

        agent_list = "\n".join(agent_descriptions)

        parameters = {
            "description": {
                "type": "string",
                "description": "A short (3-5 words) description of the task",
            },
            "prompt": {
                "type": "string",
                "description": "The task for the agent to perform",
            },
            "subagent_type": {
                "type": "string",
                "description": "The type of specialized agent to use for this task",
                "enum": list(self._agents.keys()),
            },
            "session_id": {
                "type": "string",
                "description": "Existing Task session to continue",
            },
            "command": {
                "type": "string",
                "description": "The command that triggered this task",
            },
        }

        return ToolInfo(
            name=self.name,
            description=f"{self.description}\n\nAvailable agent types:\n{agent_list}",
            parameters=parameters,
        )
