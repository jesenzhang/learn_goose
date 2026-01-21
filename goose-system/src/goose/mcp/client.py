"""
MCP Client 实现

参考: goose-rs/crates/goose/src/agents/mcp_client.rs
"""

from typing import Dict, Any, Optional, List, AsyncIterator
from dataclasses import dataclass, field
import asyncio
import uuid

from . import (
    MCPTransport,
    StdioTransport,
    HttpTransport,
    InMemoryTransport,
    MCPRequest,
    MCPResponse,
    MCPNotification,
    MCPMethod,
    ToolDefinition,
    ResourceDefinition,
    InitializeResult,
)


@dataclass
class ToolResult:
    """工具调用结果"""
    content: List[Dict[str, Any]] = field(default_factory=list)
    is_error: bool = False
    error_message: Optional[str] = None


class MCPClient:
    """MCP 客户端"""
    
    def __init__(
        self,
        name: str,
        transport: MCPTransport,
        client_info: Optional[Dict[str, str]] = None
    ):
        self.name = name
        self.transport = transport
        self.client_info = client_info or {
            "name": "goose-system",
            "version": "0.1.0"
        }
        self.tools: List[ToolDefinition] = []
        self.resources: List[ResourceDefinition] = []
        self.instructions: Optional[str] = None
        self._request_id_counter = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    @classmethod
    def create_stdio(
        cls,
        name: str,
        command: str,
        args: List[str],
        envs: Optional[Dict[str, str]] = None,
        working_dir: Optional[str] = None
    ) -> "MCPClient":
        """创建 Stdio MCP Client"""
        transport = StdioTransport(command, args, envs, working_dir)
        return cls(name, transport)
    
    @classmethod
    def create_http(
        cls,
        name: str,
        uri: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0
    ) -> "MCPClient":
        """创建 HTTP MCP Client"""
        transport = HttpTransport(uri, headers, timeout)
        return cls(name, transport)
    
    @classmethod
    def create_in_memory(cls, name: str) -> "MCPClient":
        """创建内存 MCP Client (用于测试)"""
        transport = InMemoryTransport()
        return cls(name, transport)
    
    async def initialize(self) -> InitializeResult:
        """初始化连接"""
        await self.transport.connect()
        
        request = MCPRequest(
            method=MCPMethod.INITIALIZE,
            params={
                "clientInfo": self.client_info
            }
        )
        
        response = await self._send_request(request)
        
        result = InitializeResult.from_dict(response.result or {})
        self.tools = result.tools
        self.resources = result.resources
        self.instructions = result.instructions
        
        return result
    
    async def list_tools(self) -> List[ToolDefinition]:
        """列出可用工具"""
        return self.tools
    
    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> ToolResult:
        """调用工具"""
        request = MCPRequest(
            method=MCPMethod.CALL_TOOL,
            params={
                "name": name,
                "arguments": arguments
            }
        )
        
        response = await self._send_request(request)
        
        result_data = response.result or {}
        return ToolResult(
            content=result_data.get("content", []),
            is_error=result_data.get("isError", False),
            error_message=result_data.get("error")
        )
    
    async def list_resources(self) -> List[ResourceDefinition]:
        """列出可用资源"""
        return self.resources
    
    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """读取资源"""
        request = MCPRequest(
            method=MCPMethod.READ_RESOURCE,
            params={"uri": uri}
        )
        
        response = await self._send_request(request)
        
        return response.result or {}
    
    async def subscribe(self, uri: str) -> bool:
        """订阅资源变化"""
        request = MCPRequest(
            method=MCPMethod.SUBSCRIBE,
            params={"uri": uri}
        )
        
        response = await self._send_request(request)
        return response.error is None
    
    async def close(self) -> None:
        """关闭连接"""
        await self.transport.close()
    
    async def _send_request(self, request: MCPRequest) -> MCPResponse:
        """发送请求并等待响应"""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_requests[request.request_id] = future
        
        try:
            await self.transport.send(request.to_dict())
            response = await future
            return response
        finally:
            self._pending_requests.pop(request.request_id, None)
    
    async def _handle_messages(self) -> None:
        """处理接收到的消息"""
        async for message in self.transport.receive():
            msg_type = message.get("type")
            
            if msg_type == "response":
                request_id = message.get("requestId")
                future = self._pending_requests.pop(request_id, None)
                if future and not future.done():
                    response = MCPResponse.from_dict(message)
                    future.set_result(response)
            
            elif msg_type == "notification":
                await self._handle_notification(message)
    
    async def _handle_notification(self, message: Dict[str, Any]) -> None:
        """处理通知"""
        method = message.get("method")
        params = message.get("params", {})
        
        if method == "notifications/resources/updated":
            await self._handle_resource_updated(params)
        elif method == "notifications/tools/list_changed":
            await self._handle_tools_changed()
    
    async def _handle_resource_updated(self, params: Dict[str, Any]) -> None:
        """处理资源更新通知"""
        uri = params.get("uri")
        # 更新资源缓存或触发回调
        pass
    
    async def _handle_tools_changed(self) -> None:
        """处理工具列表变化通知"""
        # 重新加载工具列表
        pass
    
    async def __aenter__(self) -> "MCPClient":
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()


class MCPClientPool:
    """MCP 客户端池 (管理多个 Extension)"""
    
    def __init__(self):
        self.clients: Dict[str, MCPClient] = {}
    
    async def add_client(self, name: str, client: MCPClient) -> None:
        """添加客户端"""
        await client.initialize()
        self.clients[name] = client
    
    async def remove_client(self, name: str) -> None:
        """移除客户端"""
        if name in self.clients:
            await self.clients[name].close()
            del self.clients[name]
    
    async def get_tools(self) -> List[ToolDefinition]:
        """获取所有工具"""
        all_tools = []
        for client in self.clients.values():
            all_tools.extend(await client.list_tools())
        return all_tools
    
    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> ToolResult:
        """调用工具 (自动路由到正确的客户端)"""
        # 从工具名解析客户端名
        # 格式: {client_name}/{tool_name}
        if "/" in tool_name:
            client_name, actual_tool_name = tool_name.split("/", 1)
            if client_name in self.clients:
                client = self.clients[client_name]
                return await client.call_tool(actual_tool_name, arguments)
        
        # 遍历所有客户端查找工具
        for client in self.clients.values():
            tools = await client.list_tools()
            for tool in tools:
                if tool.name == tool_name:
                    return await client.call_tool(tool_name, arguments)
        
        raise ValueError(f"Tool not found: {tool_name}")
    
    async def close_all(self) -> None:
        """关闭所有客户端"""
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
