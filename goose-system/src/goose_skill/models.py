"""
Data models for the Goose Skill System.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml

# Import extended MCP types
from .protocol_ext import Meta, Notification


@dataclass
class ToolAnnotations:
    """Tool annotation hints for the model."""
    title: str | None = None
    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.title is not None:
            result["title"] = self.title
        if self.read_only_hint is not None:
            result["readOnlyHint"] = self.read_only_hint
        if self.destructive_hint is not None:
            result["destructiveHint"] = self.destructive_hint
        if self.idempotent_hint is not None:
            result["idempotentHint"] = self.idempotent_hint
        if self.open_world_hint is not None:
            result["openWorldHint"] = self.open_world_hint
        return result


@dataclass
class Tool:
    """Represents an MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    annotations: ToolAnnotations | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations is not None:
            result.update(self.annotations.to_dict())
        return result


@dataclass
class ServerCapabilities:
    """MCP server capabilities."""
    tools: dict[str, Any] | None = None
    resources: dict[str, Any] | None = None
    prompts: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.tools is not None:
            result["tools"] = self.tools
        if self.resources is not None:
            result["resources"] = self.resources
        if self.prompts is not None:
            result["prompts"] = self.prompts
        return result


@dataclass
class Implementation:
    """Server implementation info."""
    name: str
    version: str = "1.0.0"
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
        }
        if self.title is not None:
            result["title"] = self.title
        return result


@dataclass
class InitializeResult:
    """MCP initialize result."""
    protocol_version: str = "2025-03-26"
    capabilities: ServerCapabilities = field(default_factory=ServerCapabilities)
    server_info: Implementation = field(default_factory=lambda: Implementation(name="skills"))
    instructions: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities.to_dict(),
            "serverInfo": self.server_info.to_dict(),
        }
        if self.instructions is not None:
            result["instructions"] = self.instructions
        return result


@dataclass
class Content:
    """Tool call result content."""
    content_type: str = "text"
    text: str = ""

    @classmethod
    def make_text(cls, content: str) -> "Content":
        return cls(content_type="text", text=content)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.content_type, "text": self.text}


@dataclass
class ToolCallResult:
    """Result of a tool call."""
    content: list[Content]
    is_error: bool = False

    @classmethod
    def success(cls, content: list[Content]) -> "ToolCallResult":
        return cls(content=content, is_error=False)

    @classmethod
    def error(cls, content: list[Content]) -> "ToolCallResult":
        return cls(content=content, is_error=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": [c.to_dict() for c in self.content],
            "isError": self.is_error,
        }


@dataclass
class ListToolsResult:
    """Result of listing tools."""
    tools: list[Tool]
    next_cursor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "tools": [t.to_dict() for t in self.tools],
        }
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        return result


@dataclass
class ListResourcesResult:
    """Result of listing resources."""
    resources: list[dict[str, Any]]
    next_cursor: str | None = None


@dataclass
class ListPromptsResult:
    """Result of listing prompts."""
    prompts: list[dict[str, Any]]
    next_cursor: str | None = None


@dataclass
class ReadResourceResult:
    """Result of reading a resource."""
    contents: list[dict[str, Any]]


@dataclass
class GetPromptResult:
    """Result of getting a prompt."""
    description: str
    name: str
    arguments: list[dict[str, Any]] | None = None
