"""
Protocol interfaces for MCP-style tool calling.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from .models import (
    Content,
    GetPromptResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
    ReadResourceResult,
    ToolCallResult,
)


@dataclass
class McpMeta:
    """Metadata for MCP operations."""
    session_id: str = ""

    @classmethod
    def new(cls, session_id: str) -> "McpMeta":
        return cls(session_id=session_id)


class McpClientTrait(ABC):
    """Abstract base class for MCP clients."""

    @abstractmethod
    async def list_tools(
        self,
        next_cursor: str | None = None,
    ) -> ListToolsResult:
        """List available tools."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        meta: McpMeta | None = None,
    ) -> ToolCallResult:
        """Call a tool by name."""
        ...

    @abstractmethod
    def get_info(self) -> dict[str, Any]:
        """Get server information."""
        ...

    async def list_resources(
        self,
        next_cursor: str | None = None,
    ) -> ListResourcesResult:
        """List available resources."""
        return ListResourcesResult(resources=[])

    async def read_resource(
        self,
        uri: str,
    ) -> ReadResourceResult:
        """Read a resource."""
        return ReadResourceResult(contents=[])

    async def list_prompts(
        self,
        next_cursor: str | None = None,
    ) -> ListPromptsResult:
        """List available prompts."""
        return ListPromptsResult(prompts=[])

    async def get_prompt(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> GetPromptResult:
        """Get a prompt."""
        return GetPromptResult(name=name, description="")
