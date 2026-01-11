"""
BaseEngine - Base execution engine for all agent implementations.

This module provides the foundation that specific engines (React, Streaming, etc.) will extend.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, AsyncIterator
from abc import ABC, abstractmethod

from ..core import (
    AgentEngine,
    AgentResponse,
    AgentStatus,
    AgentEvent,
    AgentEventType,
    Context,
    ExecutionMode,
    AgentStyle,
)
from pho.conversation import Message, Conversation
from pho.providers import BaseLLM

logger = logging.getLogger(__name__)


class BaseEngine(AgentEngine):
    """
    Base execution engine that provides common functionality.

    Specific engines (ReactEngine, StreamingEngine, etc.) extend this class.
    """

    def __init__(
        self,
        llm: BaseLLM,
        config: Any = None,
        tools: Dict[str, Any] = None
    ):
        """
        Initialize the base engine.

        Args:
            llm: LLM provider instance
            config: Agent configuration
            tools: Tool registry or dict of tools
        """
        self.llm = llm
        self.config = config
        self.tools = tools or {}
        self._event_handlers = []

    # ========================================================================
    # Abstract Methods (must be implemented by subclasses)
    # ========================================================================

    @abstractmethod
    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Execute the agent logic.

        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def get_mode(self) -> ExecutionMode:
        """Return the execution mode"""
        pass

    @abstractmethod
    def get_style(self) -> AgentStyle:
        """Return the agent style"""
        pass

    # ========================================================================
    # Common Utilities
    # ========================================================================

    async def execute_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """
        Default streaming implementation.

        Subclasses can override for more sophisticated streaming.
        """
        response = await self.execute(input, context)
        yield response

    def create_conversation(self, input: str, context: Context) -> Conversation:
        """
        Create initial conversation from input.
        """
        conversation = Conversation()

        # Add system prompt if configured
        if self.config and hasattr(self.config, 'system_prompt') and self.config.system_prompt:
            conversation.push(Message.system(self.config.system_prompt))

        # Add user input
        conversation.push(Message.user(input))

        return conversation

    async def call_llm(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> tuple[Message, Optional[Any]]:
        """
        Call the LLM with messages and optional tools.

        Returns:
            Tuple of (response_message, usage_info)
        """
        try:
            msg, usage = await self.llm.agenerate(messages, tools=tools)
            return msg, usage
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def call_llm_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> AsyncIterator[tuple[Message, Optional[Any]]]:
        """
        Call the LLM with streaming support.

        Yields:
            Tuples of (partial_message, usage_info)
        """
        try:
            async for msg, usage in self.llm.astream(messages, tools=tools):
                yield msg, usage
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise

    # ========================================================================
    # Event Handling
    # ========================================================================

    def on_event(self, event_type: str = "*"):
        """
        Decorator to register event handlers.

        Usage:
            @agent.on_event("tool_start")
            async def handle_tool_start(event):
                print(f"Tool started: {event.data}")
        """
        def decorator(func):
            self._event_handlers.append((event_type, func))
            return func
        return decorator

    async def emit_event(self, event: AgentEvent):
        """Emit an event to all registered handlers"""
        for event_pattern, handler in self._event_handlers:
            if event_pattern == "*" or event.type.value == event_pattern:
                try:
                    await handler(event)
                except Exception as e:
                    logger.error(f"Event handler failed: {e}")

    async def emit(self, event_type: AgentEventType, data: Dict[str, Any] = None):
        """Convenience method to emit events"""
        event = AgentEvent(
            type=event_type,
            data=data or {},
        )
        await self.emit_event(event)

    # ========================================================================
    # Tool Execution (stub - to be enhanced)
    # ========================================================================

    async def execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Context
    ) -> Any:
        """
        Execute a tool by name.

        Subclasses should override this to add:
        - Tool inspection/validation
        - Permission checks
        - Error handling
        - Result formatting
        """
        if tool_name not in self.tools:
            raise ValueError(f"Tool not found: {tool_name}")

        tool = self.tools[tool_name]

        # Execute tool (sync or async)
        if asyncio.iscoroutinefunction(tool):
            return await tool(**tool_args)
        else:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, tool, **tool_args)


__all__ = ["BaseEngine"]
