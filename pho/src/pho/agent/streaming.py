"""
StreamingAgent - Event-driven streaming agent.

This agent implements event-driven streaming with real-time updates:
- Stream tokens as they arrive
- Emit events for each stage
- Async-first architecture
- State machine for execution tracking

Inspired by goose-rs streaming agent pattern.
"""

import logging
from typing import Optional, Dict, Any, List, AsyncIterator
from enum import Enum
from dataclasses import dataclass, field

from .core import (
    AgentEngine,
    AgentResponse,
    AgentStatus,
    AgentEvent,
    AgentEventType,
    Context,
    ExecutionMode,
    AgentStyle,
    AgentConfig,
)
from pho.conversation import Message, Conversation, Role
from pho.providers import BaseLLM
from pho.toolkit import ToolExecutor, ExecutionContext
from pho.agent.inspectors import InspectorChain

logger = logging.getLogger(__name__)


class StreamingState(str, Enum):
    """States in streaming execution"""
    IDLE = "idle"
    STARTING = "starting"
    THINKING = "thinking"
    STREAMING = "streaming"
    TOOLING = "tooling"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class StreamingEvent:
    """Event emitted during streaming execution"""
    event_type: AgentEventType
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: 0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class StreamingAgentEngine(AgentEngine):
    """
    Event-driven streaming agent engine.

    Features:
    - Real-time token streaming
    - Event emission for all stages
    - Tool execution with streaming updates
    - Async-first design
    - State machine tracking

    Events emitted:
    - start: Execution started
    - thinking: Agent is thinking
    - token: Individual token (optional)
    - text: Text chunk
    - tool_start: Tool execution starting
    - tool_end: Tool execution complete
    - complete: Execution finished
    - error: Error occurred
    """

    def __init__(
        self,
        llm: BaseLLM,
        config: Optional[AgentConfig] = None,
        tools: Optional[Dict[str, Any]] = None,
        inspector_chain: Optional[InspectorChain] = None,
        emit_tokens: bool = False,
    ):
        self.llm = llm
        self.config = config
        self.tools = tools or {}
        self.inspector_chain = inspector_chain or InspectorChain()
        self.emit_tokens = emit_tokens

        # State
        self._state = StreamingState.IDLE

        # Event handlers
        self._event_handlers: List[callable] = []

        # Create tool executor
        from pho.toolkit import ToolRegistry
        registry = ToolRegistry()
        for name, func in self.tools.items():
            registry.register(name=name, func=func, description=f"Tool: {name}")

        self.tool_executor = ToolExecutor(
            registry=registry,
            inspector_chain=self.inspector_chain,
            enable_cache=True,
        )

    def get_mode(self) -> ExecutionMode:
        return ExecutionMode.STREAMING

    def get_style(self) -> AgentStyle:
        return AgentStyle.REACTIVE

    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """Execute and collect all events into final response"""
        full_text = ""
        events = []

        async for response in self.execute_stream(input, context):
            full_text += response.text or ""
            if response.events:
                events.extend(response.events)

        return AgentResponse(
            text=full_text,
            status=AgentStatus.COMPLETED,
            events=events,
        )

    async def execute_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream execution with events"""
        self._state = StreamingState.STARTING

        # Emit start event
        await self._emit_event(AgentEventType.START, {"input": input})
        yield AgentResponse(
            text="",
            status=AgentStatus.THINKING,
            events=[AgentEvent(AgentEventType.START, {"input": input})]
        )

        # Create conversation
        conversation = self.create_conversation(input, context)

        # Get tools schema
        tools_schema = None
        if self.tools:
            tools_schema = self.tool_executor.registry.to_openai_functions()

        try:
            # Enter thinking state
            self._state = StreamingState.THINKING
            await self._emit_event(AgentEventType.THINKING, {})

            yield AgentResponse(
                text="",
                status=AgentStatus.THINKING,
                events=[AgentEvent(AgentEventType.THINKING, {})]
            )

            # Stream LLM response
            self._state = StreamingState.STREAMING
            full_text = ""
            tool_calls = []

            async for msg, _ in self.call_llm_stream(
                conversation.agent_visible_messages(),
                tools=tools_schema,
            ):
                if msg and msg.content:
                    for item in msg.content:
                        if hasattr(item, 'text'):
                            chunk = item.text
                            full_text += chunk

                            # Emit text event
                            await self._emit_event(AgentEventType.TEXT, {
                                "chunk": chunk,
                                "full_length": len(full_text),
                            })

                            # Emit token event if enabled
                            if self.emit_tokens:
                                await self._emit_event(AgentEventType.TOKEN, {
                                    "token": chunk,
                                })

                            yield AgentResponse(
                                text=chunk,
                                status=AgentStatus.STREAMING,
                            )

                # Check for tool calls
                if msg and hasattr(msg, 'tool_requests') and msg.tool_requests:
                    tool_calls.extend(msg.tool_requests)

            # Execute tools if any
            if tool_calls:
                self._state = StreamingState.TOOLING

                for tool_call in tool_calls:
                    tool_name = tool_call.name
                    tool_args = tool_call.arguments

                    # Emit tool_start event
                    await self._emit_event(AgentEventType.TOOL_START, {
                        "tool": tool_name,
                        "args": tool_args,
                    })

                    yield AgentResponse(
                        text=f"\n[Using {tool_name}...]",
                        status=AgentStatus.TOOLING,
                        events=[AgentEvent(AgentEventType.TOOL_START, {
                            "tool": tool_name,
                            "args": tool_args,
                        })],
                    )

                    # Execute tool
                    exec_context = ExecutionContext(
                        session_id=context.session_id,
                        user_id=context.user_id,
                        variables=context.variables,
                    )

                    result = await self.tool_executor.execute(
                        tool_name, tool_args, exec_context
                    )

                    # Emit tool_end event
                    await self._emit_event(AgentEventType.TOOL_END, {
                        "tool": tool_name,
                        "result": str(result.result)[:200] if result.is_success else None,
                        "error": result.error if not result.is_success else None,
                    })

                    yield AgentResponse(
                        text=f"[{tool_name}: {result.result if result.is_success else result.error}]",
                        status=AgentStatus.TOOLING,
                        events=[AgentEvent(AgentEventType.TOOL_END, {
                            "tool": tool_name,
                            "result": str(result.result)[:200] if result.is_success else None,
                        })],
                    )

            # Complete
            self._state = StreamingState.COMPLETED
            await self._emit_event(AgentEventType.COMPLETE, {
                "text_length": len(full_text),
            })

            yield AgentResponse(
                text="",
                status=AgentStatus.COMPLETED,
                events=[AgentEvent(AgentEventType.COMPLETE, {})]
            )

        except Exception as e:
            self._state = StreamingState.ERROR
            logger.error(f"Streaming execution error: {e}")
            await self._emit_event(AgentEventType.ERROR, {"error": str(e)})

            yield AgentResponse(
                text=f"\nError: {str(e)}",
                status=AgentStatus.ERROR,
                events=[AgentEvent(AgentEventType.ERROR, {"error": str(e)})],
            )

        finally:
            self._state = StreamingState.IDLE

    def on_event(self, handler: callable) -> None:
        """Register an event handler"""
        self._event_handlers.append(handler)

    async def _emit_event(self, event_type: AgentEventType, data: Dict[str, Any]) -> None:
        """Emit event to all handlers"""
        event = StreamingEvent(event_type=event_type, data=data)

        for handler in self._event_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def create_conversation(self, input: str, context: Context) -> Conversation:
        """Create initial conversation from input."""
        conversation = Conversation()

        if self.config and hasattr(self.config, 'system_prompt') and self.config.system_prompt:
            conversation.push(Message.system(self.config.system_prompt))

        conversation.push(Message.user(input))
        return conversation

    async def call_llm_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> AsyncIterator[tuple[Message, Optional[Any]]]:
        """Call the LLM with streaming."""
        try:
            async for msg, usage in self.llm.astream(messages, tools=tools):
                yield msg, usage
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise

    def get_state(self) -> StreamingState:
        """Get current streaming state"""
        return self._state


__all__ = ["StreamingAgentEngine", "StreamingState", "StreamingEvent"]
