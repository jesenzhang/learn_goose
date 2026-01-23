"""
Memory Platform Extension

Provides memory storage and retrieval capabilities:
- remember_memory: Store memories with categories and tags
- retrieve_memories: Retrieve memories by category
- remove_memory_category: Remove all memories in a category
- remove_specific_memory: Remove a specific memory

Reference: goose-rs/crates/goose-mcp/src/memory/mod.rs
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import shutil

from ...session import SessionManager


class MemoryPlatformExtension:
    """Memory Platform Extension for persistent storage"""

    EXTENSION_NAME = "memory"

    def __init__(self, session_manager: Optional[SessionManager] = None):
        self.session_manager = session_manager
        self._initialized = False

        self._global_memory_dir = self._get_global_memory_dir()
        self._local_memory_dir = self._get_local_memory_dir()

    def _get_global_memory_dir(self) -> Path:
        """Get global memory directory"""
        if os.name == "nt":
            base = Path(os.environ.get("APPDATA", ""))
            return base / "Block" / "goose" / "memory"
        else:
            base = Path.home() / ".config"
            return base / "goose" / "memory"

    def _get_local_memory_dir(self) -> Path:
        """Get local (project) memory directory"""
        cwd = Path.cwd()
        return cwd / ".goose" / "memory"

    def _get_memory_file(self, category: str, is_global: bool) -> Path:
        """Get memory file path for a category"""
        base_dir = self._global_memory_dir if is_global else self._local_memory_dir
        return base_dir / f"{category}.txt"

    async def initialize(self) -> Dict[str, Any]:
        """Initialize and load existing memories"""
        instructions = self._generate_instructions()
        self._initialized = True

        return {
            "name": self.EXTENSION_NAME,
            "version": "1.0.0",
            "description": "Store and retrieve categorized memories",
            "instructions": instructions,
        }

    def _generate_instructions(self) -> str:
        """Generate system instructions for memory usage"""
        return """This extension allows storage and retrieval of categorized information with tagging support.

Capabilities:
1. Store information in categories with optional tags
2. Search memories by content or category
3. List all available memory categories
4. Remove memories when no longer needed

When to call memory tools:
- User provides recurring preferences or project details
- User wants to remember important information
- User explicitly asks to remember something

Interaction Protocol:
1. Identify the important information
2. Ask the user if they'd like to store it
3. Suggest a relevant category
4. Store using remember_memory tool

Keywords that trigger memory tools:
- "remember", "forget", "memory", "save", "save memory"
- "remove memory", "clear memory", "search memory", "find memory"
"""

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self._initialized:
            await self.initialize()

        return [
            {
                "name": "remember_memory",
                "description": "Store a memory with optional tags in a specified category",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Category to store memory in"},
                        "data": {"type": "string", "description": "Data to remember"},
                        "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"},
                        "is_global": {"type": "boolean", "description": "Store globally or locally", "default": False},
                    },
                    "required": ["category", "data"],
                }
            },
            {
                "name": "retrieve_memories",
                "description": "Retrieve all memories from a specified category",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Category to retrieve (use '*' for all)"},
                        "is_global": {"type": "boolean", "description": "Retrieve from global or local storage", "default": False},
                    },
                    "required": ["category"],
                }
            },
            {
                "name": "remove_memory_category",
                "description": "Remove all memories within a specified category",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Category to remove (use '*' for all)"},
                        "is_global": {"type": "boolean", "description": "Remove from global or local storage", "default": False},
                    },
                    "required": ["category"],
                }
            },
            {
                "name": "remove_specific_memory",
                "description": "Remove a specific memory within a specified category",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "description": "Category containing the memory"},
                        "memory_content": {"type": "string", "description": "Content of the memory to remove"},
                        "is_global": {"type": "boolean", "description": "Remove from global or local storage", "default": False},
                    },
                    "required": ["category", "memory_content"],
                }
            },
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        if not self._initialized:
            await self.initialize()

        handlers = {
            "remember_memory": self._remember_memory,
            "retrieve_memories": self._retrieve_memories,
            "remove_memory_category": self._remove_memory_category,
            "remove_specific_memory": self._remove_specific_memory,
        }

        if name not in handlers:
            return {"error": f"Unknown tool: {name}"}

        try:
            return await handlers[name](arguments)
        except Exception as e:
            return {"error": str(e)}

    async def _remember_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Store a memory"""
        category = args.get("category", "")
        data = args.get("data", "")
        tags = args.get("tags", [])
        is_global = args.get("is_global", False)

        if not category:
            return {"error": "Missing 'category' parameter"}
        if not data:
            return {"error": "Missing 'data' parameter"}

        memory_file = self._get_memory_file(category, is_global)

        try:
            memory_file.parent.mkdir(parents=True, exist_ok=True)

            with open(memory_file, "a", encoding="utf-8") as f:
                if tags:
                    f.write(f"# {' '.join(tags)}\n")
                f.write(f"{data}\n\n")

            location = "global" if is_global else "local"
            return {"content": [{"type": "text", "text": f"Stored memory in category '{category}' ({location})"}]}
        except Exception as e:
            return {"error": f"Failed to store memory: {e}"}

    async def _retrieve_memories(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve memories"""
        category = args.get("category", "*")
        is_global = args.get("is_global", False)

        try:
            if category == "*":
                memories = self._retrieve_all(is_global)
            else:
                memories = self._retrieve(category, is_global)

            if not memories:
                return {"content": [{"type": "text", "text": "No memories found"}]}

            result = ["Retrieved memories:"]
            for cat, entries in memories.items():
                result.append(f"\n--- {cat} ---")
                for entry in entries:
                    result.append(f"- {entry}")

            return {"content": [{"type": "text", "text": "\n".join(result)}]}
        except Exception as e:
            return {"error": f"Failed to retrieve memories: {e}"}

    def _retrieve_all(self, is_global: bool) -> Dict[str, List[str]]:
        """Retrieve all memories"""
        base_dir = self._global_memory_dir if is_global else self._local_memory_dir
        memories = {}

        if not base_dir.exists():
            return memories

        for file in base_dir.glob("*.txt"):
            category = file.stem
            entries = self._read_entries(file)
            if entries:
                memories[category] = entries

        return memories

    def _retrieve(self, category: str, is_global: bool) -> Dict[str, List[str]]:
        """Retrieve memories for a specific category"""
        memory_file = self._get_memory_file(category, is_global)

        if not memory_file.exists():
            return {}

        entries = self._read_entries(memory_file)
        return {category: entries} if entries else {}

    def _read_entries(self, file_path: Path) -> List[str]:
        """Read memory entries from file"""
        entries = []
        if not file_path.exists():
            return entries

        content = file_path.read_text(encoding="utf-8")
        blocks = content.split("\n\n")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")
            if lines:
                first_line = lines[0]
                if first_line.startswith("#"):
                    entry_lines = lines[1:] if len(lines) > 1 else []
                else:
                    entry_lines = lines

                entries.append("\n".join(entry_lines))

        return entries

    async def _remove_memory_category(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Remove all memories in a category"""
        category = args.get("category", "*")
        is_global = args.get("is_global", False)

        try:
            if category == "*":
                base_dir = self._global_memory_dir if is_global else self._local_memory_dir
                if base_dir.exists():
                    shutil.rmtree(base_dir)
                    base_dir.mkdir(parents=True, exist_ok=True)
                return {"content": [{"type": "text", "text": f"Cleared all {('global' if is_global else 'local')} memories"}]}
            else:
                memory_file = self._get_memory_file(category, is_global)
                if memory_file.exists():
                    memory_file.unlink()
                return {"content": [{"type": "text", "text": f"Removed memories in category '{category}'"}]}
        except Exception as e:
            return {"error": f"Failed to remove memories: {e}"}

    async def _remove_specific_memory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Remove a specific memory"""
        category = args.get("category", "")
        memory_content = args.get("memory_content", "")
        is_global = args.get("is_global", False)

        if not category:
            return {"error": "Missing 'category' parameter"}
        if not memory_content:
            return {"error": "Missing 'memory_content' parameter"}

        memory_file = self._get_memory_file(category, is_global)

        try:
            if not memory_file.exists():
                return {"content": [{"type": "text", "text": "Memory not found"}]}

            content = memory_file.read_text(encoding="utf-8")
            blocks = content.split("\n\n")
            new_blocks = [b for b in blocks if memory_content not in b]

            memory_file.write_text("\n\n".join(new_blocks), encoding="utf-8")

            return {"content": [{"type": "text", "text": f"Removed specific memory from category '{category}'"}]}
        except Exception as e:
            return {"error": f"Failed to remove memory: {e}"}

    async def close(self) -> None:
        """Close extension"""
        self._initialized = False


def create_memory_extension() -> MemoryPlatformExtension:
    """Create Memory Platform Extension"""
    return MemoryPlatformExtension()
