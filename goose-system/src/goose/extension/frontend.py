"""
Frontend Tools

Manages frontend-displayed tools that require user approval.
Reference: goose-rs frontend_tool.rs

Features:
- Frontend tool definitions
- User approval workflow
- Tool instructions
- Display preferences
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum

logger = logging.getLogger("goose.frontend")


class FrontendToolType(str, Enum):
    """Frontend tool types."""
    BUTTON = "button"
    INPUT = "input"
    SELECT = "select"
    MULTISELECT = "multiselect"
    TEXTAREA = "textarea"
    FILE_UPLOAD = "file_upload"


@dataclass
class FrontendToolOption:
    """Select/multiselect option."""
    value: str
    label: str
    description: Optional[str] = None
    icon: Optional[str] = None


@dataclass
class FrontendTool:
    """
    Frontend tool definition.

    Reference: goose-rs FrontendTool
    """

    name: str
    type: FrontendToolType
    label: str
    description: str = ""
    instructions: str = ""
    options: List[FrontendToolOption] = field(default_factory=list)
    default_value: Optional[Any] = None
    placeholder: Optional[str] = None
    required: bool = False
    validate: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for frontend."""
        return {
            "name": self.name,
            "type": self.type.value,
            "label": self.label,
            "description": self.description,
            "instructions": self.instructions,
            "options": [opt.__dict__ for opt in self.options],
            "default": self.default_value,
            "placeholder": self.placeholder,
            "required": self.required,
            "validate": self.validate,
            "metadata": self.metadata
        }


@dataclass
class FrontendAction:
    """
    Frontend action/button definition.

    Reference: goose-rs FrontendAction
    """

    id: str
    label: str
    description: str = ""
    icon: Optional[str] = None
    variant: str = "primary"  # primary, secondary, danger
    requires_confirmation: bool = False
    confirmation_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FrontendDisplay:
    """
    Frontend display configuration.

    Reference: goose-rs FrontendDisplay
    """

    title: str
    icon: Optional[str] = None
    theme: str = "light"
    width: Optional[str] = None
    height: Optional[str] = None
    tools: List[FrontendTool] = field(default_factory=list)
    actions: List[FrontendAction] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FrontendManager:
    """
    Manages frontend tools and displays.

    Reference: goose-rs FrontendManager
    """

    def __init__(self):
        self._tools: Dict[str, FrontendTool] = {}
        self._actions: Dict[str, FrontendAction] = {}
        self._displays: Dict[str, FrontendDisplay] = {}
        self._lock_lock = None

    def register_tool(self, tool: FrontendTool) -> None:
        """Register a frontend tool."""
        self._tools[tool.name] = tool
        logger.info(f"Registered frontend tool: {tool.name}")

    def register_action(self, action: FrontendAction) -> None:
        """Register a frontend action."""
        self._actions[action.id] = action
        logger.info(f"Registered frontend action: {action.id}")

    def register_display(self, display: FrontendDisplay) -> None:
        """Register a frontend display."""
        self._displays[display.title] = display
        logger.info(f"Registered frontend display: {display.title}")

    def create_tool_from_tool(self, tool: 'Tool') -> FrontendTool:
        """
        Create a frontend tool from a regular tool.

        Args:
            tool: Regular tool definition

        Returns:
            FrontendTool instance
        """
        frontend_tool = FrontendTool(
            name=f"frontend_{tool.name}",
            type=FrontendToolType.INPUT,
            label=tool.name.replace("_", " ").title(),
            description=tool.description,
            instructions=f"Use the {tool.name} tool with the following parameters:"
        )
        return frontend_tool

    def get_tool(self, name: str) -> Optional[FrontendTool]:
        """Get a frontend tool by name."""
        return self._tools.get(name)

    def get_action(self, id: str) -> Optional[FrontendAction]:
        """Get a frontend action by ID."""
        return self._actions.get(id)

    def get_display(self, title: str) -> Optional[FrontendDisplay]:
        """Get a frontend display by title."""
        return self._displays.get(title)

    def list_tools(self) -> List[FrontendTool]:
        """List all registered frontend tools."""
        return list(self._tools.values())

    def list_actions(self) -> List[FrontendAction]:
        """List all registered frontend actions."""
        return list(self._actions.values())

    def for_display(self, display_title: str) -> FrontendDisplay:
        """Get display configuration with registered tools."""
        if display_title in self._displays:
            return self._displays[display_title]

        return FrontendDisplay(
            title=display_title,
            tools=list(self._tools.values())
        )

    def to_frontend_config(self) -> Dict[str, Any]:
        """Export configuration for frontend."""
        return {
            "tools": [tool.to_dict() for tool in self._tools.values()],
            "actions": [action.__dict__ for action in self._actions.values()],
            "displays": [
                {**display.__dict__, "tools": [t.to_dict() for t in display.tools]}
                for display in self._displays.values()
            ]
        }


# Forward reference for Tool
Tool = None
