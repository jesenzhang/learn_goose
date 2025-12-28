import asyncio
import json
import logging
import os
from typing import Dict, Any, List, Optional
from asyncio import Future
from dataclasses import dataclass

logger = logging.getLogger("goose.mcp")

@dataclass
class McpToolDef:
    name: str
    description: str
    input_schema: Dict[str, Any]

class McpClient:
    def __init__(self, command: str, args: List[str], env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = args
        self.env = env or os.environ.copy()
        
        self.process: Optional[asyncio.subprocess.Process] = None
        self._msg_id = 0
        self._pending_requests: Dict[int, Future] = {}
        self._read_loop_task: Optional[asyncio.Task] = None
        
        # MCP Protocol Version
        self.version = "2024-11-05" 

    async def connect(self):
        """启动子进程并初始化 MCP 连接"""
        logger.info(f"🔌 Starting MCP Server: {self.command} {self.args}")
        
        self.process = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, # 捕获 stderr 防止污染输出
            env=self.env
        )
        
        # 启动后台读取循环
        self._read_loop_task = asyncio.create_task(self._read_loop())
        
        # 启动 stderr 监控 (可选，方便调试)
        asyncio.create_task(self._monitor_stderr())

        # --- MCP Handshake (Initialize) ---
        init_result = await self.request("initialize", {
            "protocolVersion": self.version,
            "capabilities": {
                "tools": {},
                "resources": {}
            },
            "clientInfo": {
                "name": "goose-py",
                "version": "0.1.0"
            }
        })
        
        # Send initialized notification
        await self.notify("notifications/initialized", {})
        
        logger.info(f"✅ MCP Connected. Server: {init_result.get('serverInfo', {}).get('name')}")

    async def list_tools(self) -> List[McpToolDef]:
        """获取 MCP Server 提供的工具列表"""
        response = await self.request("tools/list", {})
        tools = []
        for t in response.get("tools", []):
            tools.append(McpToolDef(
                name=t["name"],
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {})
            ))
        return tools

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        """调用工具"""
        result = await self.request("tools/call", {
            "name": name,
            "arguments": arguments
        })
        
        # MCP tool call result structure: { "content": [ { "type": "text", "text": "..." } ], "isError": bool }
        # 我们需要返回这个原始结构，交给 Adapter 去适配 Goose 的 ToolCallResult
        return result

    async def close(self):
        """关闭连接"""
        if self._read_loop_task:
            self._read_loop_task.cancel()
        
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
        logger.info("🔌 MCP Connection closed.")

    # --- JSON-RPC Internal ---

    async def request(self, method: str, params: Optional[Dict] = None) -> Any:
        self._msg_id += 1
        msg_id = self._msg_id
        
        payload = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params or {}
        }
        
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[msg_id] = future
        
        await self._send_json(payload)
        
        # Wait for response
        return await future

    async def notify(self, method: str, params: Optional[Dict] = None):
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        }
        await self._send_json(payload)

    async def _send_json(self, data: Dict):
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP process not connected")
        
        json_str = json.dumps(data)
        self.process.stdin.write(f"{json_str}\n".encode())
        await self.process.stdin.drain()

    async def _read_loop(self):
        """从 stdout 读取 JSON-RPC 响应"""
        if not self.process or not self.process.stdout:
            return

        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                
                line_str = line.decode().strip()
                if not line_str:
                    continue
                    
                try:
                    message = json.loads(line_str)
                    self._handle_message(message)
                except json.JSONDecodeError:
                    logger.warning(f"MCP Malformed JSON: {line_str}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"MCP Read Loop Error: {e}")

    async def _monitor_stderr(self):
        if not self.process or not self.process.stderr:
            return
        while True:
            line = await self.process.stderr.readline()
            if not line: break
            # 这里的日志可以设为 debug，或者是 info
            logger.debug(f"[MCP STDERR] {line.decode().strip()}")

    def _handle_message(self, message: Dict):
        # Handle Response
        if "id" in message and message["id"] in self._pending_requests:
            future = self._pending_requests.pop(message["id"])
            if "error" in message:
                future.set_exception(Exception(f"MCP Error: {message['error']}"))
            else:
                future.set_result(message.get("result"))
        
        # Handle Notification (Optional)
        # elif "method" in message: ...