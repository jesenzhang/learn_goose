"""
Extension Manager

Manages extensions (plugins) for the agent, including MCP servers.
Reference: goose-rs extension_manager.rs

Features:
- Extension lifecycle management (load/unload)
- Tool aggregation and caching using MCP client
- MCP protocol communication
- Resource and prompt template management
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, AsyncGenerator
from enum import Enum
from abc import ABC, abstractmethod
from pathlib import Path
import uuid

from goose.mcp import (
    StdioTransport,
    HttpTransport,
    ToolDefinition,
    ResourceDefinition,
)
from goose.mcp.client import (
    MCPClient,
    MCPClientPool,
)

logger = logging.getLogger("goose.extension")


class ExtensionType(str, Enum):
    """Extension types."""
    STDIO = "stdio"
    HTTP = "http"
    BUILTIN = "builtin"
    INLINE = "inline"


class ExtensionState(str, Enum):
    """Extension lifecycle states."""
    LOADING = "loading"
    READY = "ready"
    DISCONNECTED = "disconnected"
    ERROR = "error"


@dataclass
class ExtensionConfig:
    """Extension configuration."""
    name: str
    type: ExtensionType
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    envs: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    timeout: float = 30.0
    enabled: bool = True

    @classmethod
    def create_stdio(
        cls,
        name: str,
        command: str,
        args: Optional[List[str]] = None,
        envs: Optional[Dict[str, str]] = None
    ) -> "ExtensionConfig":
        """Create stdio extension config."""
        return cls(
            name=name,
            type=ExtensionType.STDIO,
            command=command,
            args=args or [],
            envs=envs or {}
        )

    @classmethod
    def create_http(
        cls,
        name: str,
        url: str,
        timeout: float = 30.0
    ) -> "ExtensionConfig":
        """Create HTTP extension config."""
        return cls(
            name=name,
            type=ExtensionType.HTTP,
            url=url,
            timeout=timeout
        )


@dataclass
class ExtensionTool:
    """Tool definition from extension."""
    name: str
    description: str
    input_schema: Dict[str, Any]
    extension_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mcp(cls, tool: ToolDefinition, extension_name: str) -> "ExtensionTool":
        """Create from MCP ToolDefinition."""
        return cls(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            extension_name=extension_name
        )


@dataclass
class ExtensionResource:
    """Resource from extension."""
    uri: str
    name: str
    mime_type: Optional[str] = None
    extension_name: str = ""

    @classmethod
    def from_mcp(cls, resource: ResourceDefinition, extension_name: str) -> "ExtensionResource":
        """Create from MCP ResourceDefinition."""
        return cls(
            uri=resource.uri,
            name=resource.name,
            mime_type=resource.mime_type,
            extension_name=extension_name
        )


@dataclass
class ExtensionInfo:
    """Extension information."""
    name: str
    version: str
    publisher: str
    description: Optional[str] = None
    tools: List[ExtensionTool] = field(default_factory=list)
    resources: List[ExtensionResource] = field(default_factory=list)
    instructions: Optional[str] = None


class Extension:
    """
    Extension wrapper with state management.

    Reference: goose-rs Extension struct
    """

    def __init__(self, config: ExtensionConfig):
        self.config = config
        self.id = str(uuid.uuid4())
        self.state = ExtensionState.LOADING
        self.info: Optional[ExtensionInfo] = None
        self.client: Optional[MCPClient] = None
        self._tools_cache: List[ExtensionTool] = []
        self._resources_cache: List[ExtensionResource] = []
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def tools(self) -> List[ExtensionTool]:
        return self._tools_cache.copy()

    @property
    def resources(self) -> List[ExtensionResource]:
        return self._resources_cache.copy()

    @property
    def is_connected(self) -> bool:
        return self.state == ExtensionState.READY

    async def load(self) -> None:
        """Load and initialize extension."""
        try:
            self.client = self._create_client()
            await self.client.initialize()

            self.state = ExtensionState.READY
            await self._sync_resources()

            logger.info(f"Extension loaded: {self.name}")
        except Exception as e:
            self.state = ExtensionState.ERROR
            logger.error(f"Failed to load extension {self.name}: {e}")
            raise

    def _create_client(self) -> MCPClient:
        """Create MCP client based on extension type."""
        if self.config.type == ExtensionType.STDIO:
            if not self.config.command:
                raise ValueError(f"Extension {self.name}: command is required for stdio type")
            return MCPClient.create_stdio(
                name=self.name,
                command=self.config.command,
                args=self.config.args,
                envs=self.config.envs
            )
        elif self.config.type == ExtensionType.HTTP:
            if not self.config.url:
                raise ValueError(f"Extension {self.name}: url is required for http type")
            return MCPClient.create_http(
                name=self.name,
                uri=self.config.url,
                timeout=self.config.timeout
            )
        else:
            raise ValueError(f"Unsupported extension type: {self.config.type}")

    async def _sync_resources(self) -> None:
        """Sync resources from MCP client."""
        if not self.client:
            return

        async with self._lock:
            mcp_tools = await self.client.list_tools()
            self._tools_cache = [
                ExtensionTool.from_mcp(t, self.name)
                for t in mcp_tools
            ]

            mcp_resources = await self.client.list_resources()
            self._resources_cache = [
                ExtensionResource.from_mcp(r, self.name)
                for r in mcp_resources
            ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on this extension."""
        if not self.client:
            raise RuntimeError(f"Extension {self.name} not connected")

        result = await self.client.call_tool(name, arguments)
        return {
            "content": result.content,
            "is_error": result.is_error,
            "error": result.error_message
        }

    async def unload(self) -> None:
        """Unload extension."""
        if self.client:
            await self.client.close()
            self.client = None
        self.state = ExtensionState.DISCONNECTED
        logger.info(f"Extension unloaded: {self.name}")


class ExtensionManager:
    """
    Extension manager for the agent.

    Reference: goose-rs ExtensionManager

    Responsibilities:
    - Plugin lifecycle management
    - Tool aggregation and caching
    - MCP protocol communication
    - Resource/prompt template management
    """

    def __init__(self):
        self._extensions: Dict[str, Extension] = {}
        self._tools_cache: Dict[str, ExtensionTool] = {}
        self._resources: Dict[str, ExtensionResource] = {}
        self._lock = asyncio.Lock()

    @property
    def extensions(self) -> Dict[str, Extension]:
        return self._extensions.copy()

    @property
    def all_tools(self) -> List[ExtensionTool]:
        return list(self._tools_cache.values())

    @property
    def all_resources(self) -> List[ExtensionResource]:
        return list(self._resources.values())

    def register_extension(self, config: ExtensionConfig) -> None:
        """Register an extension configuration."""
        self._extensions[config.name] = Extension(config)
        logger.info(f"Registered extension: {config.name}")

    async def load_extension(self, name: str) -> Extension:
        """Load and initialize an extension."""
        if name not in self._extensions:
            raise ValueError(f"Extension not registered: {name}")

        extension = self._extensions[name]
        await extension.load()

        async with self._lock:
            for tool in extension.tools:
                self._tools_cache[tool.name] = tool

            for resource in extension.resources:
                self._resources[resource.uri] = resource

        return extension

    async def unload_extension(self, name: str) -> None:
        """Unload an extension."""
        if name not in self._extensions:
            return

        extension = self._extensions[name]
        await extension.unload()

        async with self._lock:
            for tool in extension.tools:
                self._tools_cache.pop(tool.name, None)

        logger.info(f"Unloaded extension: {name}")

    async def call_tool(
        self,
        extension_name: str,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool on a specific extension."""
        if extension_name not in self._extensions:
            raise ValueError(f"Extension not loaded: {extension_name}")

        extension = self._extensions[extension_name]
        return await extension.call_tool(tool_name, arguments)

    async def call_tool_by_name(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call a tool by name, auto-discovering the extension."""
        if tool_name not in self._tools_cache:
            raise ValueError(f"Tool not found: {tool_name}")

        tool = self._tools_cache[tool_name]
        return await self.call_tool(tool.extension_name, tool_name, arguments)

    def get_tool(self, name: str) -> Optional[ExtensionTool]:
        """Get a tool by name."""
        return self._tools_cache.get(name)

    def get_resource(self, uri: str) -> Optional[ExtensionResource]:
        """Get a resource by URI."""
        return self._resources.get(uri)

    async def load_all(self) -> None:
        """Load all registered extensions."""
        for name, extension in list(self._extensions.items()):
            if extension.config.enabled and extension.state != ExtensionState.READY:
                try:
                    await self.load_extension(name)
                except Exception as e:
                    logger.error(f"Failed to load extension {name}: {e}")

    async def unload_all(self) -> None:
        """Unload all extensions."""
        for name in list(self._extensions.keys()):
            await self.unload_extension(name)
