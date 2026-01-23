"""
ACP (Agent Communication Protocol) Implementation for goose-system

Reference: goose-rs/crates/goose-acp/src/server.rs
"""

from typing import Any, Callable, Dict, List, Optional
from enum import Enum
import uuid
import json
import sys


class StopReason(Enum):
    END_TURN = "end_turn"
    CANCELLED = "cancelled"
    TOOL_CALLS = "tool_calls"


class ToolCallStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentCapabilities:
    def __init__(self, load_session: bool = False):
        self.load_session = load_session
    
    def to_dict(self) -> Dict[str, Any]:
        return {"loadSession": self.load_session}


class SessionId:
    def __init__(self, session_id: str):
        self._id = session_id
    
    @classmethod
    def from_str(cls, s: str) -> "SessionId":
        return cls(s)
    
    def __str__(self) -> str:
        return self._id


class ContentBlock:
    def __init__(self, text: str = ""):
        self.text = text
    
    def to_dict(self) -> Dict[str, Any]:
        return {"type": "text", "text": self.text}


class ToolCall:
    def __init__(self, id: str, name: str, status: ToolCallStatus = ToolCallStatus.PENDING):
        self.id = id
        self.name = name
        self.status = status
    
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "status": self.status.value}


class ToolCallUpdate:
    def __init__(self, id: str, status: ToolCallStatus, content: List[Dict[str, Any]] = None):
        self.id = id
        self.status = status
        self.content = content or []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "fields": {
                "status": self.status.value,
                "content": self.content,
            }
        }


class SessionUpdate:
    AGENT_MESSAGE = "agentMessageChunk"
    TOOL_CALL = "toolCall"
    TOOL_UPDATE = "toolCallUpdate"
    
    def __init__(self, update_type: str, data: Dict[str, Any]):
        self.update_type = update_type
        self.data = data
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.update_type}
        result.update(self.data)
        return result


class SessionNotification:
    def __init__(self, session_id: SessionId, update: SessionUpdate):
        self.session_id = session_id
        self.update = update
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessionId": str(self.session_id),
            "update": self.update.to_dict(),
        }


class InitializeRequest:
    def __init__(self, protocol_version: str = "1.0"):
        self.protocol_version = protocol_version


class InitializeResponse:
    def __init__(self, protocol_version: str, capabilities: Dict[str, Any]):
        self.protocol_version = protocol_version
        self.capabilities = capabilities
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": self.capabilities,
        }


class NewSessionRequest:
    def __init__(self, mcp_servers: List[Dict[str, Any]] = None):
        self.mcp_servers = mcp_servers or []


class NewSessionResponse:
    def __init__(self, session_id: SessionId):
        self.session_id = session_id
    
    def to_dict(self) -> Dict[str, Any]:
        return {"sessionId": str(self.session_id)}


class PromptRequest:
    def __init__(self, session_id: SessionId, prompt: List[Dict[str, Any]]):
        self.session_id = session_id
        self.prompt = prompt


class PromptResponse:
    def __init__(self, stop_reason: StopReason):
        self.stop_reason = stop_reason
    
    def to_dict(self) -> Dict[str, Any]:
        return {"stopReason": self.stop_reason.value}


class CancelNotification:
    def __init__(self, session_id: SessionId):
        self.session_id = session_id


class AuthenticateRequest:
    def __init__(self):
        pass


class AuthenticateResponse:
    def __init__(self):
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        return {}


class AcpSession:
    """State for an ACP session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Dict[str, Any]] = []


class GooseAcpAgent:
    """ACP Agent wrapper"""
    
    def __init__(self):
        self.sessions: Dict[str, AcpSession] = {}
        self.capabilities = AgentCapabilities(load_session=True)
    
    async def on_initialize(self, request: InitializeRequest) -> InitializeResponse:
        return InitializeResponse(
            protocol_version=request.protocol_version,
            capabilities=self.capabilities.to_dict(),
        )
    
    async def on_authenticate(self, request: AuthenticateRequest) -> AuthenticateResponse:
        return AuthenticateResponse()
    
    async def on_new_session(self, request: NewSessionRequest) -> NewSessionResponse:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = AcpSession(session_id)
        return NewSessionResponse(SessionId(session_id))
    
    async def on_prompt(
        self,
        request: PromptRequest,
        send_notification: Callable[[Dict[str, Any]], None],
    ) -> PromptResponse:
        session_id = str(request.session_id)
        
        if session_id not in self.sessions:
            self.sessions[session_id] = AcpSession(session_id)
        
        text = ""
        for block in request.prompt:
            if block.get("type") == "text":
                text = block.get("text", "")
        
        await send_notification({
            "sessionId": session_id,
            "update": {
                "type": "agentMessageChunk",
                "chunk": {"content": [{"type": "text", "text": f"Received: {text[:50]}..."}]}
            }
        })
        
        return PromptResponse(StopReason.END_TURN)
    
    async def on_cancel(self, notification: CancelNotification):
        pass


def create_acp_agent() -> GooseAcpAgent:
    """Create an ACP agent"""
    return GooseAcpAgent()


class AcpHandler:
    """ACP Message Handler"""
    
    def __init__(self, agent: GooseAcpAgent):
        self.agent = agent
    
    async def handle(
        self,
        message: Dict[str, Any],
        send_notification: Callable[[Dict[str, Any]], None],
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        msg_id = message.get("id")
        
        try:
            if msg_type == "initialize":
                request = InitializeRequest()
                response = await self.agent.on_initialize(request)
                return {"jsonrpc": "2.0", "id": msg_id, "result": response.to_dict()}
            
            elif msg_type == "authenticate":
                request = AuthenticateRequest()
                response = await self.agent.on_authenticate(request)
                return {"jsonrpc": "2.0", "id": msg_id, "result": response.to_dict()}
            
            elif msg_type == "newSession":
                request = NewSessionRequest(message.get("params", {}))
                response = await self.agent.on_new_session(request)
                return {"jsonrpc": "2.0", "id": msg_id, "result": response.to_dict()}
            
            elif msg_type == "prompt":
                params = message.get("params", {})
                request = PromptRequest(
                    SessionId.from_str(params.get("sessionId", "")),
                    params.get("prompt", [])
                )
                response = await self.agent.on_prompt(request, send_notification)
                return {"jsonrpc": "2.0", "id": msg_id, "result": response.to_dict()}
            
            elif msg_type == "cancel":
                params = message.get("params", {})
                await self.agent.on_cancel(CancelNotification(
                    SessionId.from_str(params.get("sessionId", ""))
                ))
                return None
            
            return None
        except Exception as e:
            return {"jsonrpc": "2.0", "id": msg_id, "error": {"error": str(e)}}


class StdioTransport:
    """ACP Transport using stdin/stdout"""
    
    async def receive(self) -> Optional[Dict[str, Any]]:
        line = sys.stdin.readline()
        if not line:
            return None
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            return None
    
    async def send(self, message: Dict[str, Any]) -> None:
        print(json.dumps(message), flush=True)


async def run_server():
    """Run the ACP server with stdio transport"""
    agent = create_acp_agent()
    handler = AcpHandler(agent)
    transport = StdioTransport()
    
    while True:
        message = await transport.receive()
        if message is None:
            break
        
        async def send_notification(notif: Dict[str, Any]):
            await transport.send(notif)
        
        response = await handler.handle(message, send_notification)
        if response:
            await transport.send(response)


__all__ = [
    "StopReason",
    "ToolCallStatus",
    "AgentCapabilities",
    "SessionId",
    "ContentBlock",
    "ToolCall",
    "ToolCallUpdate",
    "SessionUpdate",
    "SessionNotification",
    "InitializeRequest",
    "InitializeResponse",
    "NewSessionRequest",
    "NewSessionResponse",
    "PromptRequest",
    "PromptResponse",
    "CancelNotification",
    "AuthenticateRequest",
    "AuthenticateResponse",
    "GooseAcpAgent",
    "create_acp_agent",
    "AcpHandler",
    "StdioTransport",
    "run_server",
]
