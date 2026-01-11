"""
BaseAgent - The simplest agent implementation.

This is a minimal agent that:
- Takes user input
- Calls LLM
- Optionally executes tools
- Returns response

No state management, no complex loops. Perfect for simple tasks.
"""

import logging
from typing import List, Dict, Any, Optional

from .core import (
    AgentEngine,
    AgentResponse,
    AgentStatus,
    AgentEventType,
    Context,
    ExecutionMode,
    AgentStyle,
)
from .engines.base import BaseEngine
from pho.conversation import Message

logger = logging.getLogger(__name__)


class BaseAgentEngine(BaseEngine):
    """
    Minimal agent engine - simplest possible implementation.

    Flow: Input → LLM → [Optional Tools] → Response
    """

    def get_mode(self) -> ExecutionMode:
        return ExecutionMode.REACT

    def get_style(self) -> AgentStyle:
        return AgentStyle.MINIMAL

    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Execute the minimal agent flow.
        """
        await self.emit(AgentEventType.START, {"input": input})

        try:
            # Create conversation
            conversation = self.create_conversation(input, context)

            # Prepare tools if available
            tools = None
            if self.tools:
                tools = self._prepare_tools()

            # Call LLM
            await self.emit(AgentEventType.THINKING)
            response_msg, usage = await self.call_llm(
                conversation.agent_visible_messages(),
                tools=tools
            )

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response_msg)

            if tool_calls:
                await self.emit(AgentEventType.TOOL_START, {"count": len(tool_calls)})

                # Parallel tool execution for independent tools
                tool_results = await self._execute_tools_parallel(tool_calls, context)

                await self.emit(AgentEventType.TOOL_END)
                # Optionally call LLM again with tool results
                # For minimal agent, we just return the results

            # Build response
            response = AgentResponse(
                text=response_msg.text,
                tool_calls=tool_calls,
                usage=self._format_usage(usage),
                status=AgentStatus.COMPLETED
            )

            await self.emit(AgentEventType.COMPLETE)
            return response

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            await self.emit(AgentEventType.ERROR, {"error": str(e)})

            return AgentResponse(
                text=f"Error: {str(e)}",
                status=AgentStatus.ERROR
            )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _prepare_tools(self) -> List[Dict[str, Any]]:
        """Prepare tool definitions for LLM"""
        # This is a simplified version
        # Full implementation would generate OpenAI-style tool schemas
        return []

    def _extract_tool_calls(self, message: Message) -> List[Dict[str, Any]]:
        """Extract tool calls from message"""
        tool_calls = []

        for content in message.content:
            if hasattr(content, 'tool_call') and content.tool_call:
                if content.tool_call.value:
                    tool_calls.append({
                        "name": content.tool_call.value.name,
                        "arguments": content.tool_call.value.arguments or {}
                    })

        return tool_calls

    def _format_usage(self, usage: Any) -> Optional[Dict[str, Any]]:
        """Format usage information"""
        if usage is None:
            return None

        if isinstance(usage, dict):
            return usage

        # Try to extract from object
        try:
            return {
                "input_tokens": getattr(usage, "input_tokens", 0),
                "output_tokens": getattr(usage, "output_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            }
        except Exception:
            return None

    async def _execute_tools_parallel(
        self,
        tool_calls: List[Dict[str, Any]],
        context: Context
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple tools in parallel.

        Args:
            tool_calls: List of tool call dictionaries
            context: Execution context

        Returns:
            List of tool results with name and result fields
        """
        import asyncio

        async def execute_single_tool(tool_call: Dict[str, Any]) -> Dict[str, Any]:
            """Execute a single tool and capture result"""
            try:
                result = await self.execute_tool(
                    tool_call["name"],
                    tool_call.get("arguments", {}),
                    context
                )
                return {
                    "name": tool_call["name"],
                    "result": str(result),
                    "success": True
                }
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                return {
                    "name": tool_call["name"],
                    "result": f"Error: {str(e)}",
                    "success": False
                }

        # Execute all tools in parallel
        tasks = [execute_single_tool(tc) for tc in tool_calls]
        tool_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any exceptions from gather
        results = []
        for i, item in enumerate(tool_results):
            if isinstance(item, Exception):
                results.append({
                    "name": tool_calls[i]["name"],
                    "result": f"Error: {str(item)}",
                    "success": False
                })
            else:
                results.append(item)

        return results


# Convenience class for direct usage
class BaseAgent:
    """
    Minimal Agent - simplest possible implementation.

    Usage:
        from pho.agent import BaseAgent
        from pho.providers import ProviderFactory, ModelConfig

        llm = ProviderFactory.create_llm("openai", ModelConfig())
        agent = BaseAgent(llm=llm)

        response = await agent.run("Hello, world!")
        print(response.text)
    """

    def __init__(
        self,
        llm,
        tools: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None
    ):
        """
        Initialize BaseAgent.

        Args:
            llm: LLM provider instance
            tools: Optional dict of tool functions
            system_prompt: Optional system prompt
        """
        self.llm = llm
        self.tools = tools or {}
        self.system_prompt = system_prompt

        # Create config
        from .core import AgentConfig
        self.config = AgentConfig(
            system_prompt=system_prompt
        )

        # Create engine
        self.engine = BaseAgentEngine(
            llm=llm,
            config=self.config,
            tools=tools
        )

    async def run(self, input: str, **kwargs) -> AgentResponse:
        """
        Run the agent.

        Args:
            input: User input or task
            **kwargs: Additional context variables

        Returns:
            AgentResponse with results
        """
        from .core import Context
        context = Context(**kwargs)
        return await self.engine.execute(input, context)

    def on_event(self, event_type: str = "*"):
        """Register event handler"""
        return self.engine.on_event(event_type)


__all__ = ["BaseAgentEngine", "BaseAgent"]
