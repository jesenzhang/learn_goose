"""
SecurityInspector - Detect potentially dangerous tool calls.

This inspector checks for:
- Shell injection patterns
- Path traversal attempts
- Malformed arguments
- Suspicious input patterns
"""

import re
import logging
from typing import Dict, Any, Optional, Set, List
from .base import ToolInspector, InspectorResult, InspectorAction

logger = logging.getLogger(__name__)


class SecurityInspector(ToolInspector):
    """
    Inspector that checks for security issues in tool calls.

    Looks for common attack patterns:
    - Shell injection (command, ;, &, |, etc.)
    - Path traversal (../, ..\\, etc.)
    - Excessive input lengths
    - Suspicious characters
    """

    # Default dangerous patterns
    DEFAULT_PATTERNS = {
        "shell_injection": [
            r";\s*\w+",      # command followed by semicolon and word
            r"\|\s*\w+",     # pipe followed by word
            r"&&\s*\w+",     # AND followed by word
            r"\|\|\s*\w+",   # OR followed by word
            r"`[^`]*`",      # backtick commands
            r"\$[^a-zA-Z]",  # variable expansion
            r"\n\s*\w+",     # newline followed by command
            r"\r\s*\w+",     # carriage return followed by command
        ],
        "path_traversal": [
            r"\.\./",        # parent directory
            r"\.\.\\\\",     # parent directory (Windows)
            r"%2e%2e",       # URL encoded parent directory
            r"~/?\.\.",      # home directory parent
        ],
        "file_operations": [
            r">\s*/",        # redirect to root
            r"<\s*/dev/",    # read from device
        ]
    }

    # Tools that need extra scrutiny
    SENSITIVE_TOOLS: Set[str] = {
        "execute_command",
        "run_shell",
        "bash",
        "write_file",
        "read_file",
        "delete_file",
        "file_write",
        "file_read",
    }

    def __init__(
        self,
        priority: int = 10,
        enabled: bool = True,
        max_string_length: int = 10000,
        custom_patterns: Optional[Dict[str, List[str]]] = None,
        blocked_tools: Optional[Set[str]] = None,
        allow_list_tools: Optional[Set[str]] = None
    ):
        """
        Initialize SecurityInspector.

        Args:
            priority: Inspector priority (default 10, early in chain)
            enabled: Whether inspector is enabled
            max_string_length: Maximum allowed string argument length
            custom_patterns: Additional regex patterns to check
            blocked_tools: Set of tool names to completely block
            allow_list_tools: If set, only these tools are allowed
        """
        super().__init__(priority=priority)
        if not enabled:
            self.disable()

        self.max_string_length = max_string_length
        self.blocked_tools = blocked_tools or set()
        self.allow_list_tools = allow_list_tools

        # Compile regex patterns
        self.patterns = self.DEFAULT_PATTERNS.copy()
        if custom_patterns:
            for category, patterns in custom_patterns.items():
                if category not in self.patterns:
                    self.patterns[category] = []
                self.patterns[category].extend(patterns)

        self.compiled_patterns: Dict[str, List[re.Pattern]] = {}
        for category, patterns in self.patterns.items():
            self.compiled_patterns[category] = [re.compile(p, re.IGNORECASE) for p in patterns]

    async def inspect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> InspectorResult:
        """Inspect tool call for security issues"""

        # Check blocked tools
        if tool_name in self.blocked_tools:
            return InspectorResult.deny(
                reason=f"Tool '{tool_name}' is blocked by security policy",
                error_message=f"Tool '{tool_name}' is not allowed"
            )

        # Check allow list
        if self.allow_list_tools and tool_name not in self.allow_list_tools:
            return InspectorResult.deny(
                reason=f"Tool '{tool_name}' is not in allow list",
                error_message=f"Tool '{tool_name}' is not authorized"
            )

        # Check all string arguments
        for key, value in tool_args.items():
            if isinstance(value, str):
                # Check length
                if len(value) > self.max_string_length:
                    return InspectorResult.deny(
                        reason=f"Argument '{key}' exceeds maximum length of {self.max_string_length}",
                        error_message=f"Argument too long"
                    )

                # For sensitive tools, check patterns
                if tool_name in self.SENSITIVE_TOOLS:
                    security_result = self._check_string(value, key, tool_name)
                    if security_result:
                        return security_result

        return InspectorResult.allow(reason="No security issues detected")

    def _check_string(self, value: str, arg_name: str, tool_name: str) -> Optional[InspectorResult]:
        """Check a string value against security patterns"""
        for category, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(value):
                    logger.warning(
                        f"Security issue detected in tool '{tool_name}', "
                        f"argument '{arg_name}': {category} pattern matched"
                    )
                    return InspectorResult.deny(
                        reason=f"Security issue: {category} pattern detected in '{arg_name}'",
                        error_message=f"Potentially malicious input detected in '{arg_name}'"
                    )
        return None

    def add_blocked_tool(self, tool_name: str) -> None:
        """Add a tool to the blocked list"""
        self.blocked_tools.add(tool_name)

    def remove_blocked_tool(self, tool_name: str) -> None:
        """Remove a tool from the blocked list"""
        self.blocked_tools.discard(tool_name)

    def add_pattern(self, category: str, pattern: str) -> None:
        """Add a custom regex pattern to check"""
        if category not in self.patterns:
            self.patterns[category] = []
        self.patterns[category].append(pattern)
        self.compiled_patterns.setdefault(category, []).append(
            re.compile(pattern, re.IGNORECASE)
        )


__all__ = ["SecurityInspector"]
