"""
Todo tools for task list management.

This module provides:
- TodoWriteTool: Update the todo list
- TodoReadTool: Read the todo list
"""

import json
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from ..tool import Tool, ToolError, ToolInfo, ToolInputSchema, ToolResult


class TodoItem(BaseModel):
    """A single todo item."""

    content: str = Field(..., description="Brief description of task")
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        "pending",
        description="Task status: pending, in_progress, completed, or cancelled",
    )
    priority: Literal["high", "medium", "low"] = Field(
        "medium",
        description="Task priority: high, medium, or low",
    )
    id: str = Field(..., description="Unique identifier for the todo item")


# In-memory storage for todos (in production, use a proper storage backend)
_todos: Dict[str, List[Dict[str, Any]]] = {}


class TodoWriteParams(ToolInputSchema):
    """Parameters for the TodoWrite tool."""

    todos: List[Dict[str, Any]] = Field(
        ...,
        description="The updated todo list (array of todo items)",
    )


class TodoReadParams(ToolInputSchema):
    """Parameters for the TodoRead tool (empty)."""

    pass


class TodoWriteTool(Tool):
    """
    Update the todo list.

    Features:
    - Replace entire todo list
    - Track task status and priority
    - Stored per session

    Usage:
    - todos (required): Array of todo items with content, status, priority, id
    """

    name = "todowrite"
    description = (
        "Update the todo list. Replaces the entire list with the provided todos. "
        "Each todo has content (description), status (pending/in_progress/completed/cancelled), "
        "priority (high/medium/low), and id (unique identifier). "
        "The todo list is stored per session."
    )
    input_schema = TodoWriteParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._session_id = self.config.get("session_id", "default")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Update the todo list.

        Args:
            params: Dictionary containing 'todos' array.

        Returns:
            ToolResult with updated todo list.

        Raises:
            ToolError: If update fails.
        """
        todos = params["todos"]

        # Validate todos
        for todo in todos:
            if not todo.get("id"):
                raise ToolError("Each todo must have an 'id' field")
            if not todo.get("content"):
                raise ToolError("Each todo must have a 'content' field")

        # Store todos (in production, use proper storage)
        _todos[self._session_id] = todos

        # Count incomplete todos
        incomplete_count = sum(1 for t in todos if t.get("status") != "completed")

        return ToolResult(
            content=json.dumps(todos, indent=2),
            metadata={
                "todos": todos,
                "incomplete_count": incomplete_count,
            },
        )

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "todos": {
                "type": "array",
                "description": "The updated todo list (array of todo items)",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Brief description of task",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed", "cancelled"],
                            "description": "Task status",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                            "description": "Task priority",
                        },
                        "id": {
                            "type": "string",
                            "description": "Unique identifier for the todo item",
                        },
                    },
                },
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )


class TodoReadTool(Tool):
    """
    Read the todo list.

    Features:
    - Read the current todo list
    - Per-session storage

    Usage:
    - No parameters required
    """

    name = "todoread"
    description = (
        "Read the current todo list. Returns all todos stored for the current session."
    )
    input_schema = TodoReadParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._session_id = self.config.get("session_id", "default")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Read the todo list.

        Args:
            params: Empty dictionary.

        Returns:
            ToolResult with todo list.
        """
        # Get todos (in production, use proper storage)
        todos = _todos.get(self._session_id, [])

        # Count incomplete todos
        incomplete_count = sum(1 for t in todos if t.get("status") != "completed")

        return ToolResult(
            content=json.dumps(todos, indent=2),
            metadata={
                "todos": todos,
                "incomplete_count": incomplete_count,
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
