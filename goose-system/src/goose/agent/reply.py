"""
Agent Reply Core

核心回复流程，参考 Goose-Rs 的 agent.rs 实现。
支持上下文压缩管理。
"""

from typing import Dict, Any, List, Optional, AsyncGenerator
from dataclasses import dataclass
import asyncio

from .state import AgentState, SkillsState, SessionState, JumpTo
from .event import AgentEvent, AgentEventType, EventStream
from ..conversation import Conversation, Message
from ..tools import Tool, ToolRequest, ToolExecutor, InspectionManager, InspectionResult
from ..providers import Provider
from ..truncation import TruncationManager


@dataclass
class ReplyConfig:
    """回复配置"""
    max_turns: int = 100
    max_iterations: int = 1000
    compact_threshold: float = 0.8
    compact_ratio: float = 0.5
    chat_mode: bool = False


class ReplyContext:
    """回复上下文"""
    
    def __init__(
        self,
        conversation: Conversation,
        tools: List[Tool],
        system_prompt: str,
        config: ReplyConfig
    ):
        self.conversation = conversation
        self.tools = tools
        self.system_prompt = system_prompt
        self.config = config
        self.tool_executor = ToolExecutor()
        self.tool_inspector = InspectionManager()


class AgentReply:
    """Agent 回复处理器"""
    
    def __init__(
        self,
        provider: Provider,
        context: ReplyContext,
        event_stream: Optional[EventStream] = None,
        truncation_manager: Optional[TruncationManager] = None,
    ):
        self.provider = provider
        self.context = context
        self.event_stream = event_stream or EventStream()
        self.session_state = SessionState(
            session_id="default",
            conversation_state=SkillsState()
        )
        self.truncation_manager = truncation_manager
    
    def set_truncation_manager(self, manager: TruncationManager) -> None:
        """Set truncation manager after initialization"""
        self.truncation_manager = manager
    
    def _get_tool_calls(self, message: Message) -> List[ToolRequest]:
        """从消息中提取工具调用"""
        from ..conversation.message import ToolRequestContent
        tool_calls = []
        for content in message.content:
            if isinstance(content, ToolRequestContent):
                value = content.tool_call_value
                if value:
                    tool_calls.append(ToolRequest(
                        id=content.id,
                        name=value.name,
                        arguments=value.arguments
                    ))
        return tool_calls
    
    async def run(self) -> AgentState:
        """执行回复循环"""
        state = self.session_state.conversation_state
        
        while self.session_state.can_continue():
            if self._should_compact():
                await self._compact_conversation()
            
            response = await self._generate_response()
            
            state.add_message("assistant", response.text)
            
            await self._emit_message(response)
            
            tool_calls = self._get_tool_calls(response)
            if not tool_calls:
                break
            
            frontend_requests, backend_requests = self._categorize_tools(tool_calls)
            
            for request in frontend_requests:
                await self._handle_frontend_tool(request)
            
            for request in backend_requests:
                await self._handle_backend_tool(request)
            
            self.session_state.increment_turn()
        
        return state
    
    async def run_stream(self) -> AsyncGenerator[AgentEvent, None]:
        """流式执行回复循环"""
        state = self.session_state.conversation_state
        turn = 0
        
        while self.session_state.can_continue():
            turn += 1
            yield AgentEvent.message(f"--- Turn {turn} ---")
            
            if self._should_compact():
                yield AgentEvent(
                    type=AgentEventType.COMPACTION_STARTED,
                    data={"reason": "context_limit_exceeded"}
                )
                await self._compact_conversation()
                yield AgentEvent(
                    type=AgentEventType.COMPACTION_COMPLETED,
                    data={"message_count": len(state.messages)}
                )
            
            async for chunk in self._stream_response():
                yield chunk
            
            response = self._get_last_response()
            if response is None:
                break
            
            yield AgentEvent.message(response.text)
            
            tool_calls = self._get_tool_calls(response)
            if tool_calls:
                frontend, backend = self._categorize_tools(tool_calls)
                
                for request in frontend:
                    yield AgentEvent.tool_start(request.name, request.arguments or {})
                    yield AgentEvent(
                        type=AgentEventType.APPROVAL_REQUIRED,
                        data={
                            "tool_name": request.name,
                            "arguments": request.arguments or {}
                        }
                    )
                
                for request in backend:
                    result = await self._execute_tool(request)
                    yield AgentEvent.tool_end(request.name, result)
            
            if not tool_calls:
                break
        
        yield AgentEvent(type=AgentEventType.DONE, data={"turns": turn})
    
    async def _generate_response(self) -> Message:
        """生成模型响应"""
        messages = self.context.conversation.to_provider_format()
        
        result, usage = await self.provider.agenerate(
            messages=messages,
            tools=[t.to_dict() for t in self.context.tools]
        )
        
        return result
    
    async def _stream_response(self) -> AsyncGenerator[AgentEvent, None]:
        """流式生成响应"""
        messages = self.context.conversation.to_provider_format()
        
        async for chunk in self.provider.astream(
            messages=messages,
            tools=[t.to_dict() for t in self.context.tools]
        ):
            message, usage = chunk
            if message.text:
                yield AgentEvent.message(message.text)
    
    def _get_last_response(self) -> Optional[Message]:
        """获取最后一条响应"""
        messages = self.context.conversation.messages
        for msg in reversed(messages):
            if msg.role.value == "assistant":
                return msg
        return None
    
    def _categorize_tools(
        self,
        tool_requests: List[ToolRequest]
    ) -> tuple[List[ToolRequest], List[ToolRequest]]:
        """分类工具请求：前端 vs 后端"""
        frontend = []
        backend = []
        
        tool_names = {t.name: t for t in self.context.tools}
        
        for request in tool_requests:
            tool_name = request.name
            if tool_name in tool_names:
                tool = tool_names[tool_name]
                if tool.metadata.get("frontend", False):
                    frontend.append(request)
                else:
                    backend.append(request)
            else:
                backend.append(request)
        
        return frontend, backend
    
    async def _handle_frontend_tool(self, request: ToolRequest) -> None:
        """处理前端工具"""
        await self.event_stream.push(AgentEvent(
            type=AgentEventType.APPROVAL_REQUIRED,
            data={
                "tool_name": request.name,
                "arguments": request.arguments or {}
            }
        ))
    
    async def _handle_backend_tool(self, request: ToolRequest) -> Dict[str, Any]:
        """处理后端工具"""
        await self.event_stream.push(AgentEvent.tool_start(
            request.name,
            request.arguments or {}
        ))
        
        results = await self.context.tool_inspector.inspect(
            request,
            [m.to_dict() for m in self.context.conversation.messages]
        )
        
        approved, needs_approval, denied = self.context.tool_inspector.process_results(results)
        
        if denied:
            await self.event_stream.push(AgentEvent(
                type=AgentEventType.TOOL_DENIED,
                data={
                    "tool_name": request.name,
                    "reason": denied[0].message if denied else "Denied by security policy"
                }
            ))
            return {"error": "Tool denied"}
        
        if needs_approval:
            await self.event_stream.push(AgentEvent.approval_required(
                request.name,
                request.arguments or {},
                needs_approval[0].message or "需要用户确认"
            ))
            await asyncio.sleep(0.1)
        
        tool_result = await self._execute_tool(request)
        
        await self.event_stream.push(AgentEvent.tool_end(
            request.name,
            tool_result
        ))
        
        self.context.conversation.add_tool_result(
            request.id,
            request.name,
            tool_result
        )
        
        return tool_result
    
    async def _execute_tool(self, request: ToolRequest) -> Dict[str, Any]:
        """执行工具"""
        tool_name = request.name
        arguments = request.arguments or {}
        
        tool = None
        for t in self.context.tools:
            if t.name == tool_name:
                tool = t
                break
        
        if tool is None:
            return {"error": f"Tool not found: {tool_name}"}
        
        return await self.context.tool_executor.execute(tool, arguments)
    
    def _should_compact(self) -> bool:
        """检查是否需要压缩"""
        if not self.truncation_manager:
            message_count = len(self.session_state.conversation_state.messages)
            context_limit = self.provider.get_model_config().context_limit
            return self.session_state.should_compact(message_count, context_limit)
        return False
    
    async def _compact_conversation(self) -> None:
        """压缩对话"""
        if not self.truncation_manager:
            await self._simple_compact()
            return
        
        messages = self.session_state.conversation_state.messages
        system_prompt = self.context.system_prompt
        
        compacted, usage = await self.truncation_manager.check_and_compact(
            messages, system_prompt
        )
        
        if compacted:
            self.session_state.conversation_state.messages = messages
            await self.event_stream.push(AgentEvent(
                type=AgentEventType.COMPACTION_COMPLETED,
                data={
                    "message_count": len(messages),
                    "tokens_saved": usage.get("tokens_saved", 0),
                }
            ))
    
    async def _simple_compact(self) -> None:
        """简单的压缩（保留最近的消息）"""
        keep_messages = 10
        current_messages = self.session_state.conversation_state.messages
        
        if len(current_messages) <= keep_messages:
            return
        
        system_messages = [m for m in current_messages if m.get("role") == "system"]
        recent_messages = current_messages[-keep_messages:]
        
        new_messages = system_messages + recent_messages
        self.session_state.conversation_state.messages = new_messages
        
        await self.event_stream.push(AgentEvent.history_replaced(len(new_messages)))
    
    async def _emit_message(self, message: Message) -> None:
        """发送消息事件"""
        await self.event_stream.push(AgentEvent.message(message.text or ""))
