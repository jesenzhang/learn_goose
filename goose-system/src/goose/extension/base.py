"""
Extension 基类和工厂

参考: goose-rs/crates/goose/src/agents/extension.rs
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, TYPE_CHECKING
import asyncio

from .config import (
    ExtensionConfig,
    StdioExtensionConfig,
    StreamableHttpExtensionConfig,
    BuiltinExtensionConfig,
    InlinePythonExtensionConfig,
    ExtensionType,
)

if TYPE_CHECKING:
    from ..tools.base import Tool


class Extension(ABC):
    """Extension 基类"""

    def __init__(self, config: ExtensionConfig):
        self.config = config
        self.name = config.name
        self.id = config.id
        self._tools: List["Tool"] = []
        self._initialized = False

    @property
    def tools(self) -> List["Tool"]:
        """获取工具列表"""
        return self._tools

    @property
    def initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @abstractmethod
    async def initialize(self) -> None:
        """初始化 Extension"""
        pass

    @abstractmethod
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """关闭 Extension"""
        pass

    async def __aenter__(self) -> "Extension":
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class StdioExtension(Extension):
    """标准输入/输出 Extension"""

    def __init__(self, config: StdioExtensionConfig):
        super().__init__(config)
        self.command = config.command
        self.args = config.args
        self.envs = config.envs
        self.working_dir = config.working_dir
        self._client: Optional[Any] = None

    async def initialize(self) -> None:
        """初始化 Stdio Extension"""
        from ..mcp.client import MCPClient

        self._client = MCPClient.create_stdio(
            self.name,
            self.command,
            self.args,
            self.envs,
            self.working_dir
        )
        await self._client.initialize()
        self._initialized = True

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具"""
        if self._client is None:
            raise RuntimeError("Extension not initialized")

        result = await self._client.call_tool(tool_name, arguments)
        return {
            "content": result.content,
            "isError": result.is_error
        }

    async def close(self) -> None:
        """关闭 Extension"""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False


class HttpExtension(Extension):
    """HTTP Extension"""

    def __init__(self, config: StreamableHttpExtensionConfig):
        super().__init__(config)
        self.uri = config.uri
        self.headers = config.headers
        self.timeout = config.timeout
        self._client: Optional[Any] = None

    async def initialize(self) -> None:
        """初始化 HTTP Extension"""
        from ..mcp.client import MCPClient

        self._client = MCPClient.create_http(
            self.name,
            self.uri,
            self.headers,
            self.timeout
        )
        await self._client.initialize()
        self._initialized = True

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具"""
        if self._client is None:
            raise RuntimeError("Extension not initialized")

        result = await self._client.call_tool(tool_name, arguments)
        return {
            "content": result.content,
            "isError": result.is_error
        }

    async def close(self) -> None:
        """关闭 Extension"""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False


class BuiltinExtension(Extension):
    """内置 Extension"""

    def __init__(self, config: BuiltinExtensionConfig):
        super().__init__(config)
        self.module = config.module
        self.class_name = config.class_name
        self.config = config.config
        self._instance: Optional[Any] = None

    async def initialize(self) -> None:
        """初始化内置 Extension"""
        import importlib

        module = importlib.import_module(self.module)
        cls = getattr(module, self.class_name)
        self._instance = cls(**self.config)
        self._initialized = True

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用工具"""
        if self._instance is None:
            raise RuntimeError("Extension not initialized")

        if hasattr(self._instance, tool_name):
            func = getattr(self._instance, tool_name)
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            return {"content": [{"type": "text", "text": str(result)}]}

        raise ValueError(f"Tool not found: {tool_name}")

    async def close(self) -> None:
        """关闭 Extension"""
        self._instance = None
        self._initialized = False


class InlinePythonExtension(Extension):
    """内联 Python Extension"""

    def __init__(self, config: InlinePythonExtensionConfig):
        super().__init__(config)
        self.code = config.code
        self.dependencies = config.dependencies
        self.env = config.env
        self._namespace: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """初始化内联 Python"""
        self._namespace = {"__name__": "extension"}

        for dep in self.dependencies:
            self._namespace[dep] = __import__(dep)

        exec(self.code, self._namespace)
        self._initialized = True

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """调用内联 Python 工具"""
        if tool_name not in self._namespace:
            raise ValueError(f"Tool not found: {tool_name}")

        func = self._namespace[tool_name]
        result = func(**arguments)

        if asyncio.iscoroutine(result):
            result = await result

        return {"content": [{"type": "text", "text": str(result)}]}

    async def close(self) -> None:
        """关闭 Extension"""
        self._namespace.clear()
        self._initialized = False


class ExtensionFactory:
    """Extension 工厂"""

    @staticmethod
    def create(config: ExtensionConfig) -> Extension:
        """
        根据配置类型创建对应的 Extension

        ExtensionConfig::Stdio { cmd, args, ... } → StdioExtension
        ExtensionConfig::StreamableHttp { uri, ... } → HttpExtension
        ExtensionConfig::Builtin { name, ... } → BuiltinExtension
        ExtensionConfig::InlinePython { code, ... } → InlinePythonExtension
        """
        if isinstance(config, StdioExtensionConfig):
            return StdioExtension(config)
        elif isinstance(config, StreamableHttpExtensionConfig):
            return HttpExtension(config)
        elif isinstance(config, BuiltinExtensionConfig):
            return BuiltinExtension(config)
        elif isinstance(config, InlinePythonExtensionConfig):
            return InlinePythonExtension(config)
        else:
            raise ValueError(f"Unknown extension config type: {type(config)}")

    @staticmethod
    async def create_and_initialize(config: ExtensionConfig) -> Extension:
        """创建并初始化 Extension"""
        extension = ExtensionFactory.create(config)
        await extension.initialize()
        return extension
