"""
MCP Protocol data structures for Goose Skill System.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json


@dataclass
class Meta:
    """MCP metadata for session tracking."""
    session_id: str

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id}


@dataclass
class Resource:
    """MCP resource definition."""
    uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"uri": self.uri}
        if self.name is not None:
            result["name"] = self.name
        if self.description is not None:
            result["description"] = self.description
        if self.mime_type is not None:
            result["mimeType"] = self.mime_type
        return result


@dataclass
class Prompt:
    """MCP prompt definition."""
    name: str
    description: str | None = None
    arguments: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.description is not None:
            result["description"] = self.description
        if self.arguments is not None:
            result["arguments"] = self.arguments
        return result


# Result types for MCP operations

@dataclass
class ListResourcesResult:
    """Result of listing resources."""
    resources: list[Resource]
    next_cursor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resources": [r.to_dict() for r in self.resources]
        }
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        return result


@dataclass
class ReadResourceResult:
    """Result of reading a resource."""
    contents: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"contents": self.contents}


@dataclass
class ListPromptsResult:
    """Result of listing prompts."""
    prompts: list[Prompt]
    next_cursor: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "prompts": [p.to_dict() for p in self.prompts]
        }
        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor
        return result


@dataclass
class GetPromptResult:
    """Result of getting a prompt."""
    name: str
    description: str
    arguments: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        if self.arguments is not None:
            result["arguments"] = self.arguments
        return result


@dataclass
class Notification:
    """Server notification."""
    method: str
    params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "params": self.params
        }
