"""
Tutorial Platform Extension

Provides tutorial loading functionality:
- load_tutorial: Load and display tutorials

Reference: goose-rs/crates/goose-mcp/src/tutorial/mod.rs
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...session import SessionManager


class TutorialPlatformExtension:
    """Tutorial Platform Extension"""

    EXTENSION_NAME = "tutorial"

    def __init__(self, session_manager: Optional[SessionManager] = None):
        self.session_manager = session_manager
        self._initialized = False
        self.tutorials_dir = self._get_tutorials_dir()

    def _get_tutorials_dir(self) -> Path:
        """Get tutorials directory"""
        return Path(__file__).parent / "tutorials"

    def _get_available_tutorials(self) -> List[Dict[str, str]]:
        """Get list of available tutorials"""
        tutorials = []

        if not self.tutorials_dir.exists():
            return tutorials

        for file in sorted(self.tutorials_dir.glob("*.md")):
            content = file.read_text(encoding="utf-8")
            first_line = content.split("\n")[0].strip().lstrip("#").strip()
            tutorials.append({
                "name": file.stem,
                "title": first_line or file.stem,
                "path": str(file),
            })

        return tutorials

    def _generate_instructions(self) -> str:
        """Generate instructions with available tutorials"""
        tutorials = self._get_available_tutorials()

        if not tutorials:
            return """Because the tutorial extension is enabled, you can help users by loading tutorials.
However, no tutorials are currently available."""

        tutorial_list = "\n".join(f"- {t['name']}: {t['title']}" for t in tutorials)

        return f"""Because the tutorial extension is enabled, be aware that the user may be new to using goose
or looking for help with specific features. Proactively offer relevant tutorials when appropriate.

Available tutorials:
{tutorial_list}

The specific content of the tutorial can be loaded using load_tutorial.
To run through a tutorial, make sure to be interactive with the user. Don't run more than
a few related tool calls in a row. Make sure to prompt the user for understanding and participation.

Important: Provide guidance or info before running commands."""

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the extension"""
        instructions = self._generate_instructions()
        self._initialized = True

        return {
            "name": self.EXTENSION_NAME,
            "version": "1.0.0",
            "description": "Tutorial guidance and learning resources",
            "instructions": instructions,
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self._initialized:
            await self.initialize()

        return [
            {
                "name": "load_tutorial",
                "description": "Load a specific tutorial by name. Returns markdown content with step by step instructions.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Tutorial name (e.g., 'getting-started', 'developer-mcp')"},
                    },
                    "required": ["name"],
                }
            },
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        if not self._initialized:
            await self.initialize()

        if name == "load_tutorial":
            return self._load_tutorial(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    def _load_tutorial(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Load a tutorial"""
        name = args.get("name", "")

        if not name:
            return {"error": "Missing 'name' parameter"}

        if not name.endswith(".md"):
            tutorial_path = self.tutorials_dir / f"{name}.md"
        else:
            tutorial_path = self.tutorials_dir / name

        if not tutorial_path.exists():
            available = [t["name"] for t in self._get_available_tutorials()]
            return {
                "error": f"Could not locate tutorial '{name}'",
                "available_tutorials": available,
            }

        try:
            content = tutorial_path.read_text(encoding="utf-8")
            return {"content": [{"type": "text", "text": content, "role": "assistant"}]}
        except Exception as e:
            return {"error": f"Failed to load tutorial: {e}"}

    async def close(self) -> None:
        """Close extension"""
        self._initialized = False


def create_tutorial_extension() -> TutorialPlatformExtension:
    """Create Tutorial Platform Extension"""
    return TutorialPlatformExtension()
