"""
MCP (Model Context Protocol) 协议实现

参考: goose-rs/crates/goose/src/mcp_utils.rs
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, AsyncIterator, List
from dataclasses import dataclass, field
from enum import Enum
import asyncio
import json
import uuid


class MCPMessageType(str, Enum):
    """MCP 消息类型"""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"


class MCPMethod(str, Enum):
    """MCP 方法"""
    INITIALIZE = "initialize"
    LIST_TOOLS = "list_tools"
    CALL_TOOL = "call_tool"
    LIST_RESOURCES = "list_resources"
    READ_RESOURCE = "read_resource"
    SUBSCRIBE = "subscribe"


@dataclass
class MCPRequest:
    """MCP 请求"""
    method: MCPMethod
    params: Optional[Dict[str, Any]] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "method": self.method.value if isinstance(self.method, MCPMethod) else self.method,
            "params": self.params,
            "requestId": self.request_id,
            "type": "request"
        }


@dataclass
class MCPResponse:
    """MCP 响应"""
    request_id: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPResponse":
        return cls(
            request_id=data.get("requestId", ""),
            result=data.get("result"),
            error=data.get("error")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "requestId": self.request_id,
            "type": "response"
        }
        if self.result is not None:
            result["result"] = self.result
        if self.error is not None:
            result["error"] = self.error
        return result


@dataclass
class MCPNotification:
    """MCP 通知"""
    method: str
    params: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "method": self.method,
            "type": "notification"
        }
        if self.params is not None:
            result["params"] = self.params
        return result


@dataclass
class ToolDefinition:
    """工具定义 (MCP 格式)"""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolDefinition":
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            input_schema=data.get("inputSchema", {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema
        }


@dataclass
class ResourceDefinition:
    """资源定义 (MCP 格式)"""
    uri: str
    name: str
    mime_type: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ResourceDefinition":
        return cls(
            uri=data.get("uri", ""),
            name=data.get("name", ""),
            mime_type=data.get("mimeType")
        )
    
    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "uri": self.uri,
            "name": self.name
        }
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result


@dataclass
class InitializeResult:
    """初始化结果"""
    tools: List[ToolDefinition] = field(default_factory=list)
    resources: List[ResourceDefinition] = field(default_factory=list)
    instructions: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InitializeResult":
        tools = [
            ToolDefinition.from_dict(t) 
            for t in data.get("tools", [])
        ]
        resources = [
            ResourceDefinition.from_dict(r) 
            for r in data.get("resources", [])
        ]
        return cls(
            tools=tools,
            resources=resources,
            instructions=data.get("instructions")
        )


class MCPTransport(ABC):
    """MCP 传输层抽象"""
    
    @abstractmethod
    async def connect(self) -> None:
        """建立连接"""
        pass
    
    @abstractmethod
    async def send(self, message: Dict[str, Any]) -> None:
        """发送消息"""
        pass
    
    @abstractmethod
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        """接收消息流"""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """关闭连接"""
        pass


class StdioTransport(MCPTransport):
    """标准输入/输出传输"""
    
    def __init__(
        self,
        command: str,
        args: List[str],
        envs: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None
    ):
        self.command = command
        self.args = args
        self.envs = envs or {}
        self.working_dir = working_dir
        self.process: Optional[asyncio.subprocess.Process] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
    
    async def connect(self) -> None:
        """启动进程并建立连接"""
        import subprocess
        
        env = {**self.envs}
        
        self.process = await asyncio.create_subprocess_exec(
            self.command,
            *self.args,
            env=env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir
        )
        
        self._reader = self.process.stdout
        self._writer = self.process.stdin
    
    async def send(self, message: Dict[str, Any]) -> None:
        """发送 JSON 消息"""
        if self._writer is None:
            raise RuntimeError("Transport not connected")
        
        line = json.dumps(message) + "\n"
        self._writer.write(line.encode())
        await self._writer.drain()
    
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        """接收 JSON 消息流"""
        if self._reader is None:
            raise RuntimeError("Transport not connected")
        
        while True:
            try:
                line = await self._reader.readline()
                if not line:
                    break
                
                text = line.decode().strip()
                if not text:
                    continue
                
                message = json.loads(text)
                yield message
            except json.JSONDecodeError:
                continue
            except asyncio.CancelledError:
                break
    
    async def close(self) -> None:
        """关闭连接"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
            self.process = None
        
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
            self._writer = None
        
        self._reader = None


class HttpTransport(MCPTransport):
    """HTTP 传输 (StreamableHttp)"""
    
    def __init__(
        self,
        uri: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ):
        self.uri = uri
        self.headers = headers or {}
        self.timeout = timeout
        self.session: Optional[Any] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
    
    async def connect(self) -> None:
        """建立 HTTP 连接"""
        import aiohttp
        
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
    
    async def send(self, message: Dict[str, Any]) -> None:
        """发送消息到服务器"""
        if self.session is None:
            raise RuntimeError("Transport not connected")
        
        async with self.session.post(
            self.uri,
            json=message
        ) as response:
            await response.read()
    
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        """接收消息流"""
        self._running = True
        
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._message_queue.get(),
                    timeout=1.0
                )
                yield message
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
    
    async def close(self) -> None:
        """关闭连接"""
        self._running = False
        
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            self.session = None


class InMemoryTransport(MCPTransport):
    """内存传输 (用于测试)"""
    
    def __init__(self):
        self.input_queue: asyncio.Queue = asyncio.Queue()
        self.output_queue: asyncio.Queue = asyncio.Queue()
        self._connected = False
    
    async def connect(self) -> None:
        self._connected = True
    
    async def send(self, message: Dict[str, Any]) -> None:
        await self.output_queue.put(message)
    
    async def receive(self) -> AsyncIterator[Dict[str, Any]]:
        while self._connected:
            try:
                message = await asyncio.wait_for(
                    self.input_queue.get(),
                    timeout=0.1
                )
                yield message
            except asyncio.TimeoutError:
                continue
    
    async def close(self) -> None:
        self._connected = False
