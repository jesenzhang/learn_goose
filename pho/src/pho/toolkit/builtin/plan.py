"""
Plan tools for agent switching between plan and build modes.

This module provides:
- PlanEnterTool: Suggests switching to plan agent
- PlanExitTool: Suggests switching to build agent after planning
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


class PlanParams(ToolInputSchema):
    """Parameters for plan tools (empty)."""

    pass


class PlanEnterTool(BaseTool):
    """
    Suggests switching to plan agent.

    Features:
    - User confirmation via question.ask()
    - Creates synthetic message for agent switching
    - Read-only mode for planning

    Usage:
    - No parameters required
    """

    name = "plan_enter"
    description = (
        "Suggest switching to plan agent for creating a plan. "
        "Plan mode is read-only - you can explore, analyze, and plan "
        "but cannot edit files. Use this when you need to create a plan "
        "before implementing."
    )
    input_schema = PlanParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._session_id = self.config.get("session_id", "default")
        self._plan_directory = self.config.get("plan_directory", ".opencode/plans")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute plan enter.

        Args:
            params: Empty dictionary.

        Returns:
            ToolResult with confirmation message.

        Raises:
            ToolError: If plan creation fails or user rejects.
        """
        # In a real implementation, this would:
        # 1. Ask user for confirmation
        # 2. On yes, create synthetic message with agent="plan"
        # 3. Return confirmation

        plan_path = self._plan_directory
        if self._plan_directory:
            import time
            timestamp = int(time.time() * 1000)
            plan_path = f"{self._plan_directory}/{timestamp}-plan.md"

        return ToolResult(
            content=(
                f"User confirmed to switch to plan mode. "
                f"A new message has been created to switch you to plan mode. "
                f"The plan file will be at {plan_path}. Begin planning."
            ),
            metadata={
                "plan_directory": self._plan_directory,
                "plan_path": plan_path,
            },
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters={},
        )


class PlanExitTool(BaseTool):
    """
    Suggests switching to build agent after planning.

    Features:
    - User confirmation via question.ask()
    - Creates synthetic message for agent switching
    - Write mode for implementation

    Usage:
    - No parameters required
    """

    name = "plan_exit"
    description = (
        "Suggests switching to build agent after planning. "
        "Build mode allows full file editing. Use this after completing a plan "
        "to start implementation."
    )
    input_schema = PlanParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._session_id = self.config.get("session_id", "default")
        self._plan_directory = self.config.get("plan_directory", ".opencode/plans")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute plan exit.

        Args:
            params: Empty dictionary.

        Returns:
            ToolResult with confirmation message.

        Raises:
            ToolError: If user rejects.
        """
        # In a real implementation, this would:
        # 1. Ask user for confirmation
        # 2. On yes, create synthetic message with agent="build"
        # 3. Return confirmation

        import glob
        import os

        # Find most recent plan file
        plan_path = None
        if self._plan_directory and os.path.exists(self._plan_directory):
            plan_files = list(glob.glob(os.path.join(self._plan_directory, "*.md")))
            if plan_files:
                plan_path = max(plan_files, key=os.path.getmtime)

        return ToolResult(
            content=(
                "User approved switching to build agent. "
                "Wait for further instructions to begin implementing the plan."
            ),
            metadata={
                "plan_path": plan_path,
                "plan_directory": self._plan_directory,
            },
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters={},
        )
