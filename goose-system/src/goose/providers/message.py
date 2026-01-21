"""
Provider Message Types

Message types for provider communication.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
import uuid


class Role(str, Enum):
    """Message role."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class TextContent:
    """Text content."""
    text: str = ""


@dataclass
class ToolCall:
    """Tool call information."""
    name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolRequest:
    """Tool request content."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    arguments: Optional[Dict[str, Any]] = None


@dataclass
class ToolResponse:
    """Tool response content."""
    id: str = ""
    result: Any = None
    is_error: bool = False


@dataclass
class Message:
    """
    Message for provider communication.

    Reference: goose-rs Message struct
    """
    role: Role
    content: List[Any] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: Optional[str] = None

    @property
    def text(self) -> str:
        """Get text content."""
        parts = []
        for c in self.content:
            if isinstance(c, TextContent):
                parts.append(c.text)
            elif isinstance(c, ToolResponse) and c.result:
                parts.append(str(c.result))
        return "\n".join(parts)

    @classmethod
    def system(cls, text: str) -> 'Message':
        return cls(role=Role.SYSTEM, content=[TextContent(text)])

    @classmethod
    def user(cls, text: str) -> 'Message':
        return cls(role=Role.USER, content=[TextContent(text)])

    @classmethod
    def assistant(cls, text: str = "") -> 'Message':
        return cls(role=Role.ASSISTANT, content=[TextContent(text)])

    @classmethod
    def tool_result(cls, tool_call_id: str, result: Any, is_error: bool = False) -> 'Message':
        return cls(
            role=Role.TOOL,
            content=[ToolResponse(id=tool_call_id, result=result, is_error=is_error)]
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "id": self.id,
            "role": self.role.value,
            "content": []
        }
        for c in self.content:
            if isinstance(c, TextContent):
                result["content"].append({"type": "text", "text": c.text})
            elif isinstance(c, ToolRequest):
                result["content"].append({
                    "type": "tool_request",
                    "id": c.id,
                    "name": c.name,
                    "arguments": c.arguments or {}
                })
            elif isinstance(c, ToolResponse):
                result["content"].append({
                    "type": "tool_response",
                    "id": c.id,
                    "result": c.result,
                    "is_error": c.is_error
                })
        return result
