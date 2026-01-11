"""
ReactAgent - Thought → Action → Observation loop pattern.

This agent implements the ReAct pattern (Reasoning + Acting):
- Thought: Explicit reasoning about what to do
- Action: Choose a tool to use or formulate answer
- Observation: Result from tool execution
- Loop until answer is ready

Inspired by Claude Code's agent design.
"""

import logging
from typing import Optional, Dict, Any, List, AsyncIterator
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


@dataclass
class Thought:
    """A reasoning step in the ReAct loop"""
    content: str
    step_number: int
    should_use_tool: bool = False
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    is_final: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "thought": self.content,
            "tool": self.tool_name,
            "args": self.tool_args,
            "final": self.is_final,
        }


@dataclass
class Observation:
    """Result from tool execution"""
    tool_name: str
    result: Any
    error: Optional[str] = None
    step_number: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "tool": self.tool_name,
            "result": str(self.result)[:200] if self.result else None,
            "error": self.error,
        }


class ReactAgentEngine(AgentEngine):
    """
    ReAct pattern agent engine.

    Implements the Thought → Action → Observation loop:
    1. Thought: Agent thinks about what to do
    2. Action: Agent chooses a tool or gives final answer
    3. Observation: Tool result is returned
    4. Loop continues until final answer

    Features:
    - Explicit reasoning output
    - Tool calling with observation
    - Configurable max iterations
    - Streaming support
    """

    def __init__(
        self,
        llm: BaseLLM,
        config: Optional[AgentConfig] = None,
        tools: Optional[Dict[str, Any]] = None,
        inspector_chain: Optional[InspectorChain] = None,
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.config = config
        self.tools = tools or {}
        self.inspector_chain = inspector_chain or InspectorChain()
        self.max_iterations = max_iterations

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
        return ExecutionMode.REACT

    def get_style(self) -> AgentStyle:
        return AgentStyle.REASONING

    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """Execute ReAct loop"""
        max_iter = self.max_iterations
        if self.config and hasattr(self.config, 'max_iterations'):
            max_iter = self.config.max_iterations

        conversation = self.create_conversation(input, context)
        thoughts: List[Thought] = []
        observations: List[Observation] = []

        for iteration in range(max_iter):
            # Generate thought
            thought = await self._generate_thought(conversation, iteration + 1)
            thoughts.append(thought)

            # Emit thinking event
            await self.emit(AgentEventType.THINKING, {
                "thought": thought.content,
                "step": thought.step_number,
            })

            # Check if final answer
            if thought.is_final:
                return AgentResponse(
                    text=thought.content,
                    status=AgentStatus.COMPLETED,
                    events=[
                        AgentEvent(AgentEventType.THINKING, {"thought": t.to_dict()})
                        for t in thoughts
                    ] + [
                        AgentEvent(AgentEventType.TOOL_END, {"observation": o.to_dict()})
                        for o in observations
                    ],
                )

            # Execute tool if needed
            if thought.should_use_tool and thought.tool_name:
                observation = await self._execute_tool(thought, context)
                observations.append(observation)

                # Add observation to conversation
                obs_text = f"Tool '{thought.tool_name}' returned: {observation.result}"
                if observation.error:
                    obs_text = f"Tool '{thought.tool_name}' error: {observation.error}"

                conversation.push(Message.system(obs_text))
            else:
                # No tool but not marked as final - this is unusual
                logger.warning(f"Thought {iteration + 1}: Not using tool and not final")

        # Max iterations reached
        return AgentResponse(
            text=f"Reached maximum iterations ({max_iter}) without final answer",
            status=AgentStatus.ERROR,
        )

    async def execute_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream ReAct loop with real-time updates"""
        max_iter = self.max_iterations
        if self.config and hasattr(self.config, 'max_iterations'):
            max_iter = self.config.max_iterations

        conversation = self.create_conversation(input, context)

        yield AgentResponse(
            text="",
            status=AgentStatus.THINKING,
            events=[AgentEvent(type=AgentEventType.START, data={"input": input})]
        )

        for iteration in range(max_iter):
            # Emit step indicator
            yield AgentResponse(
                text=f"\n[Step {iteration + 1}/{max_iter}] ",
                status=AgentStatus.THINKING,
            )

            # Generate thought
            thought = await self._generate_thought(conversation, iteration + 1)

            # Stream thought content
            yield AgentResponse(
                text=f"Thinking: {thought.content}",
                status=AgentStatus.THINKING,
            )

            if thought.is_final:
                yield AgentResponse(
                    text=f"\n\nAnswer: {thought.content}",
                    status=AgentStatus.COMPLETED,
                )
                return

            # Execute tool
            if thought.should_use_tool and thought.tool_name:
                yield AgentResponse(
                    text=f"\n  → Action: Use {thought.tool_name}",
                    status=AgentStatus.TOOLING,
                )

                observation = await self._execute_tool(thought, context)

                obs_text = f"Result: {observation.result}"
                if observation.error:
                    obs_text = f"Error: {observation.error}"

                yield AgentResponse(
                    text=f"  ← Observation: {obs_text}",
                    status=AgentStatus.TOOLING,
                )

                # Add to conversation
                conversation.push(Message.system(obs_text))
            else:
                # No tool - shouldn't happen if not final
                yield AgentResponse(
                    text="\n  → No action taken",
                    status=AgentStatus.THINKING,
                )

        yield AgentResponse(
            text=f"\n\nReached maximum iterations ({max_iter})",
            status=AgentStatus.ERROR,
        )

    async def _generate_thought(
        self,
        conversation: Conversation,
        step_number: int
    ) -> Thought:
        """Generate a thought using LLM"""
        # Build prompt for reasoning
        system_prompt = self._build_react_prompt()

        # Temporarily replace system prompt
        original_messages = conversation.messages[:]
        if conversation.messages and conversation.messages[0].role == Role.SYSTEM:
            conversation.messages[0] = Message.system(system_prompt)
        else:
            conversation.messages.insert(0, Message.system(system_prompt))

        try:
            # Get tool schemas
            tools_schema = None
            if self.tools:
                tools_schema = self.tool_executor.registry.to_openai_functions()

            # Call LLM
            response_msg, _ = await self.call_llm(
                conversation.agent_visible_messages(),
                tools=tools_schema,
            )

            # Parse response
            return self._parse_thought(response_msg, step_number)

        finally:
            # Restore original messages
            conversation.messages = original_messages

    def _build_react_prompt(self) -> str:
        """Build the ReAct system prompt"""
        base_prompt = "You are a helpful assistant with access to tools."

        if self.config and hasattr(self.config, 'system_prompt') and self.config.system_prompt:
            base_prompt = self.config.system_prompt

        return f"""{base_prompt}

Think step-by-step about what you need to do. For each step:

1. **Thought**: Explain your reasoning about what to do next
2. **Action**: Either:
   - Use a tool by calling it, OR
   - Provide your final answer if you have enough information

Available tools:
{', '.join(self.tools.keys()) if self.tools else 'None'}

When using a tool, follow this format:
Thought: <your reasoning>
Action: use_tool(tool_name, arg1=value1, arg2=value2)

When giving final answer:
Thought: <your reasoning>
Answer: <your final answer>

IMPORTANT:
- Always start with "Thought:"
- Use tools when you need information
- Provide "Answer:" when you have the final response
- Keep thoughts concise and actionable"""

    def _parse_thought(self, response_msg: Message, step_number: int) -> Thought:
        """Parse LLM response into a Thought object"""
        content = response_msg.text or ""

        # Check if it's a final answer
        if "Answer:" in content or "FINAL:" in content or "final answer" in content.lower():
            # Extract answer
            answer = content
            for prefix in ["Answer:", "FINAL:", "Final Answer:", "answer:"]:
                if prefix in content:
                    answer = content.split(prefix, 1)[1].strip()
                    break

            return Thought(
                content=answer,
                step_number=step_number,
                is_final=True,
            )

        # Check for tool call
        if hasattr(response_msg, 'tool_requests') and response_msg.tool_requests:
            tool_request = response_msg.tool_requests[0]
            return Thought(
                content=content,
                step_number=step_number,
                should_use_tool=True,
                tool_name=tool_request.name,
                tool_args=tool_request.arguments,
            )

        # Default: treat as thought without tool
        return Thought(
            content=content,
            step_number=step_number,
            should_use_tool=False,
        )

    async def _execute_tool(
        self,
        thought: Thought,
        context: Context
    ) -> Observation:
        """Execute a tool based on thought"""
        exec_context = ExecutionContext(
            session_id=context.session_id,
            user_id=context.user_id,
            user_role=context.variables.get("user_role"),
            variables=context.variables,
        )

        try:
            result = await self.tool_executor.execute(
                thought.tool_name,
                thought.tool_args or {},
                exec_context
            )

            if result.is_success:
                return Observation(
                    tool_name=thought.tool_name,
                    result=result.result,
                    step_number=thought.step_number,
                )
            else:
                return Observation(
                    tool_name=thought.tool_name,
                    result=None,
                    error=result.error,
                    step_number=thought.step_number,
                )

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return Observation(
                tool_name=thought.tool_name,
                result=None,
                error=str(e),
                step_number=thought.step_number,
            )

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

    async def call_llm(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> tuple[Message, Optional[Any]]:
        """Call the LLM with messages."""
        try:
            msg, usage = await self.llm.agenerate(messages, tools=tools)
            return msg, usage
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def emit(self, event_type: AgentEventType, data: Dict[str, Any]) -> None:
        """Emit an event (no-op for now, can be connected to event bus later)"""
        pass


__all__ = ["ReactAgentEngine", "Thought", "Observation"]
