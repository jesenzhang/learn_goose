"""
Agent Memory Module - Load and manage AGENTS.md files.

This module provides functionality to load AGENTS.md files as agent context
and system prompt, similar to DeepAgents MemoryMiddleware.
"""

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Agent Memory Manager.

    Loads and manages AGENTS.md files as persistent agent context.
    AGENTS.md provides agent identity, instructions, and domain knowledge.
    """

    def __init__(self, memory_paths: Optional[List[str]] = None):
        """
        Initialize Agent Memory.

        Args:
            memory_paths: List of AGENTS.md file paths to load.
                         Can be absolute or relative paths.
        """
        self.memory_paths = [Path(p) for p in memory_paths or []]
        self._content: str = ""
        self._metadata: dict = {}

    def load(self) -> str:
        """
        Load all AGENTS.md files and concatenate their content.

        Files are loaded in order, with content joined by double newlines.

        Returns:
            Combined content of all AGENTS.md files.
        """
        parts = []

        for path in self.memory_paths:
            try:
                absolute_path = path if path.is_absolute() else Path.cwd() / path

                if not absolute_path.exists():
                    logger.warning(f"Memory file not found: {absolute_path}")
                    continue

                with open(absolute_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        parts.append(content)
                        logger.info(f"Loaded memory from: {absolute_path}")
                        # Extract metadata if available (frontmatter style)
                        self._metadata[str(absolute_path)] = self._extract_frontmatter(content)

            except Exception as e:
                logger.error(f"Error loading memory file {path}: {e}")

        self._content = '\n\n'.join(parts)
        return self._content

    def _extract_frontmatter(self, content: str) -> dict:
        """
        Extract YAML frontmatter from content.

        Args:
            content: File content

        Returns:
            Parsed frontmatter as dict, or empty dict if none found.
        """
        try:
            import frontmatter
            post = frontmatter.loads(content)
            return post.metadata
        except Exception:
            return {}

    def get_content(self) -> str:
        """Get loaded memory content."""
        return self._content

    def get_system_prompt(self) -> str:
        """
        Get system prompt from loaded memory.

        Returns:
            Memory content as system prompt.
        """
        return self._content

    def get_metadata(self, path: Optional[str] = None) -> dict:
        """
        Get metadata for a specific memory file.

        Args:
            path: File path. If None, returns all metadata.

        Returns:
            Metadata dict.
        """
        if path:
            return self._metadata.get(str(path), {})
        return self._metadata

    def reload(self) -> str:
        """
        Reload all memory files.

        Returns:
            Updated content.
        """
        return self.load()

    def is_loaded(self) -> bool:
        """Check if memory content has been loaded."""
        return bool(self._content)

    @property
    def content(self) -> str:
        """Property accessor for content."""
        return self._content


class MemoryMiddleware:
    """
    Memory Middleware for Agent.

    Injects AGENTS.md content into system prompts, similar to
    DeepAgents MemoryMiddleware pattern.
    """

    def __init__(self, memory_paths: Optional[List[str]] = None):
        """
        Initialize Memory Middleware.

        Args:
            memory_paths: List of AGENTS.md file paths.
        """
        self.memory = AgentMemory(memory_paths)

    def before_request(self, system_message: str) -> str:
        """
        Pre-process request by injecting memory content.

        Args:
            system_message: Current system message

        Returns:
            System message with memory content appended.
        """
        memory_content = self.memory.get_content()

        if memory_content:
            # Inject memory into system message
            if system_message:
                return f"{system_message}\n\n# Agent Memory\n\n{memory_content}"
            else:
                return f"# Agent Memory\n\n{memory_content}"

        return system_message

    def load(self) -> str:
        """Load memory files."""
        return self.memory.load()

    def reload(self) -> str:
        """Reload memory files."""
        return self.memory.reload()

    def get_metadata(self, path: Optional[str] = None) -> dict:
        """Get metadata for memory file."""
        return self.memory.get_metadata(path)
