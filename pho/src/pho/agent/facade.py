"""
PhoAgent - Unified multi-style agent facade.

This is the main entry point for using agents in Pho.
It provides a unified interface that supports multiple execution styles.
"""

import logging
from typing import Optional, Dict, Any, AsyncIterator

from .core import (
    AgentEngine,
    AgentResponse,
    AgentStyle,
    AgentConfig,
    Context,
    ExecutionMode,
)
from .base import BaseAgent, BaseAgentEngine
from .three_phase import ThreePhaseAgentEngine
from .workflow import WorkflowAgentEngine
from .react import ReactAgentEngine
from .streaming import StreamingAgentEngine

logger = logging.getLogger(__name__)


class PhoAgent:
    """
    Unified Agent facade supporting multiple execution styles.

    Usage:
        # Default style (STREAMING)
        agent = PhoAgent()

        # Specify style
        agent = PhoAgent(style=AgentStyle.REASONING)

        # Run
        response = await agent.run("Hello, world!")
        print(response.text)

        # Stream
        async for chunk in agent.run_stream("Hello!"):
            print(chunk.text, end="")
    """

    def __init__(
        self,
        style: AgentStyle = AgentStyle.REACTIVE,
        config: Optional[AgentConfig] = None,
        llm=None,
        tools: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize PhoAgent.

        Args:
            style: Agent style (MINIMAL, REACTIVE, REASONING, SKILL_BASED, ORCHESTRATED)
            config: Agent configuration
            llm: LLM provider instance
            tools: Dictionary of tool functions
        """
        self.style = style
        self.config = config or AgentConfig(mode=self._style_to_mode(style))
        self.llm = llm
        self.tools = tools or {}

        # Create the appropriate engine based on style
        self.engine = self._create_engine(style, self.config)

    def _create_engine(self, style: AgentStyle, config: AgentConfig) -> AgentEngine:
        """Create the appropriate engine for the given style"""
        # For now, we only have BaseAgentEngine
        # More engines will be added as we implement them

        if style == AgentStyle.MINIMAL:
            return BaseAgentEngine(llm=self.llm, config=config, tools=self.tools)

        elif style == AgentStyle.REACTIVE:
            # Use StreamingAgentEngine
            return StreamingAgentEngine(llm=self.llm, config=config, tools=self.tools)

        elif style == AgentStyle.REASONING:
            # Use ReactAgentEngine
            return ReactAgentEngine(llm=self.llm, config=config, tools=self.tools)

        elif style == AgentStyle.SKILL_BASED:
            # Use ThreePhaseAgentEngine
            return ThreePhaseAgentEngine(llm=self.llm, config=config, tools=self.tools)

        elif style == AgentStyle.ORCHESTRATED:
            # Use WorkflowAgentEngine
            return WorkflowAgentEngine(llm=self.llm, config=config, tools=self.tools)

        else:
            raise ValueError(f"Unknown style: {style}")

    def _style_to_mode(self, style: AgentStyle) -> ExecutionMode:
        """Convert style to default execution mode"""
        mapping = {
            AgentStyle.MINIMAL: ExecutionMode.REACT,
            AgentStyle.REACTIVE: ExecutionMode.STREAMING,
            AgentStyle.REASONING: ExecutionMode.REACT,
            AgentStyle.SKILL_BASED: ExecutionMode.THREE_PHASE,
            AgentStyle.ORCHESTRATED: ExecutionMode.WORKFLOW,
        }
        return mapping.get(style, ExecutionMode.STREAMING)

    # ========================================================================
    # Public API
    # ========================================================================

    async def run(self, input: str, **kwargs) -> AgentResponse:
        """
        Run the agent with the given input.

        Args:
            input: User input or task description
            **kwargs: Additional context (session_id, user_id, variables, etc.)

        Returns:
            AgentResponse with results
        """
        context = Context(**kwargs)
        return await self.engine.execute(input, context)

    async def run_stream(self, input: str, **kwargs) -> AsyncIterator[AgentResponse]:
        """
        Run the agent with streaming output.

        Args:
            input: User input or task description
            **kwargs: Additional context

        Yields:
            Partial AgentResponse objects as events occur
        """
        context = Context(**kwargs)
        async for response in self.engine.execute_stream(input, context):
            yield response

    # ========================================================================
    # Convenience Methods
    # ========================================================================

    def on_event(self, event_type: str = "*"):
        """
        Register an event handler.

        Usage:
            @agent.on_event("tool_start")
            async def handle_tool_start(event):
                print(f"Tool started: {event.data}")
        """
        return self.engine.on_event(event_type)

    def get_style(self) -> AgentStyle:
        """Get the current agent style"""
        return self.style

    def get_config(self) -> AgentConfig:
        """Get the agent configuration"""
        return self.config


# ========================================================================
# Convenience Functions
# ========================================================================

def create_agent(
    style: AgentStyle = AgentStyle.REACTIVE,
    llm=None,
    tools: Optional[Dict[str, Any]] = None,
    **kwargs
) -> PhoAgent:
    """
    Convenience function to create an agent.

    Usage:
        from pho.agent import create_agent, AgentStyle
        from pho.providers import ProviderFactory, ModelConfig

        llm = ProviderFactory.create_llm("openai", ModelConfig())
        agent = create_agent(style=AgentStyle.MINIMAL, llm=llm)

        response = await agent.run("Hello!")
    """
    return PhoAgent(style=style, llm=llm, tools=tools, **kwargs)


__all__ = [
    "PhoAgent",
    "create_agent",
]
