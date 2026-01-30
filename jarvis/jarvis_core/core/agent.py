"""
Agent - Pure state machine with event-driven behavior.

Agents are NOT threads, tasks, or coroutines.
Agents are state machines that produce effects.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, AsyncIterator, Callable
import uuid
import time

from .event import Event
from .state import AgentState, AgentStatus
from .effect import Effect, llm_generate_effect, llm_stream_effect, save_state_effect


class Agent(ABC):
    """
    Base Agent class - pure state machine.

    An Agent is defined by:
    1. State (AgentState)
    2. Reducer function (reduce() -> new_state + effects)

    Key design principles:
    - No side effects in reduce()
    - No async operations in reduce()
    - Only produce Effects
    """

    def __init__(
        self,
        id: Optional[str] = None,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.id = id or uuid.uuid4().hex
        self.name = name or self.__class__.__name__
        self.config = config or {}

    @abstractmethod
    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> tuple[AgentState, List[Effect]]:
        """
        The reducer function - pure transformation.

        Given current state and an event, compute:
        1. New state
        2. Effects to execute

        IMPORTANT: No side effects, no async, no external calls.
        Only compute and return.

        Returns:
            (new_state, effects)
        """
        pass

    def initialize(self, session_id: str, run_id: str) -> AgentState:
        """Create initial state for a new run."""
        from .state import create_initial_state
        return create_initial_state(
            agent_id=self.id,
            session_id=session_id,
            run_id=run_id,
            context=self.config.get("initial_context"),
        )


class SimpleChatAgent(Agent):
    """
    Simple chat agent - responds to messages with LLM generation.

    Example:
        agent = SimpleChatAgent(
            system_prompt="You are a helpful assistant.",
            model="gpt-3.5-turbo",
        )
    """

    def __init__(
        self,
        id: Optional[str] = None,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        system_prompt: str = "You are a helpful assistant.",
        model: str = "gpt-3.5-turbo",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        super().__init__(id, name, config)
        self.system_prompt = system_prompt
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> tuple[AgentState, List[Effect]]:
        """
        Handle events and produce effects.
        """
        effects: List[Effect] = []

        if event.type == "user_input":
            # Add user message to state
            new_messages = state.messages + [
                {"role": "user", "content": event.payload.get("message", "")}
            ]

            # Update state
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.RUNNING,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )

            # Create full conversation with system prompt
            full_messages = [
                {"role": "system", "content": self.system_prompt}
            ] + new_messages

            # Produce LLM generation effect
            llm_effect = llm_generate_effect(
                messages=full_messages,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            effects.append(llm_effect)

            # Add state save effect
            effects.append(save_state_effect(
                state=new_state.to_dict(),
                session_id=state.session_id,
            ))

            return new_state, effects

        elif event.type == "assistant_response":
            # Add assistant response to messages
            new_messages = state.messages + [
                {"role": "assistant", "content": event.payload.get("message", "")}
            ]

            # Update state
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.IDLE,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )

            return new_state, []

        elif event.type == "error":
            # Handle error
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=AgentStatus.FAILED,
                last_error=event.payload.get("error"),
                error_count=state.error_count + 1,
                messages=state.messages,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        # Default: no state change, no effects
        return state, []


class ToolUsingAgent(Agent):
    """
    Agent that can use tools.

    This agent:
    1. Generates responses with tool calls
    2. Executes tools
    3. Continues conversation with tool results
    """

    def __init__(
        self,
        id: Optional[str] = None,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        system_prompt: str = "You are a helpful assistant that can use tools.",
        model: str = "gpt-3.5-turbo",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        super().__init__(id, name, config)
        self.system_prompt = system_prompt
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.tools = tools or []

    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> tuple[AgentState, List[Effect]]:
        """
        Handle events and produce effects.
        """
        effects: List[Effect] = []

        if event.type == "user_input":
            # Add user message
            new_messages = state.messages + [
                {"role": "user", "content": event.payload.get("message", "")}
            ]

            # Update state
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.RUNNING,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )

            # Create full conversation
            full_messages = [
                {"role": "system", "content": self.system_prompt}
            ] + new_messages

            # Produce LLM generation effect with tools
            llm_effect = llm_stream_effect(
                messages=full_messages,
                tools=self.tools,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            effects.append(llm_effect)

            # Add state save effect
            effects.append(save_state_effect(
                state=new_state.to_dict(),
                session_id=state.session_id,
            ))

            return new_state, effects

        elif event.type == "tool_call":
            # Tool was called - update state
            tool_name = event.payload.get("tool_name")
            tool_args = event.payload.get("tool_args")

            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=state.status,
                context={
                    **state.context,
                    "last_tool": tool_name,
                    "last_tool_args": tool_args,
                },
                messages=state.messages,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed + 1,
                execution_time=state.execution_time,
            )
            return new_state, []

        elif event.type == "tool_result":
            # Tool result received - add to conversation
            tool_name = event.payload.get("tool_name")
            result = event.payload.get("result")
            is_error = event.payload.get("is_error", False)

            # Add tool result to messages
            new_messages = state.messages + [
                {
                    "role": "tool",
                    "name": tool_name,
                    "content": str(result),
                }
            ]

            # Continue generation
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.RUNNING,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )

            # Create full conversation and continue
            full_messages = [
                {"role": "system", "content": self.system_prompt}
            ] + new_messages

            llm_effect = llm_stream_effect(
                messages=full_messages,
                tools=self.tools,
                model=self.model,
                temperature=self.temperature,
            )
            effects.append(llm_effect)

            return new_state, effects

        elif event.type == "assistant_response":
            # Assistant response
            new_messages = state.messages + [
                {"role": "assistant", "content": event.payload.get("message", "")}
            ]

            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.IDLE,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        elif event.type == "error":
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=AgentStatus.FAILED,
                last_error=event.payload.get("error"),
                error_count=state.error_count + 1,
                messages=state.messages,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        return state, []


# Full Assistant Agent (with skills, intent recognition)
class FullAssistantAgent(Agent):
    """
    Full-featured assistant with:
    - Intent recognition
    - Skill activation
    - Tool execution
    - Approval workflow
    - Conversation management
    """

    def __init__(
        self,
        id: Optional[str] = None,
        name: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        skill_loader: Optional[Any] = None,
        intent_recognizer: Optional[Any] = None,
    ):
        super().__init__(id, name, config)
        self.skill_loader = skill_loader
        self.intent_recognizer = intent_recognizer

    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> tuple[AgentState, List[Effect]]:
        """
        Full-featured reducer with skill and intent support.
        """
        effects: List[Effect] = []

        if event.type == "user_input":
            # Process user input
            message = event.payload.get("message", "")

            # Recognize intent if available
            intent = None
            if self.intent_recognizer:
                # This would be async in real execution,
                # but here we just mark it for later
                intent = "unknown"

            # Update state
            new_messages = state.messages + [
                {"role": "user", "content": message}
            ]

            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.RUNNING,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )

            # Generate response
            system_prompt = self.config.get("system_prompt", "You are a helpful assistant.")
            full_messages = [
                {"role": "system", "content": system_prompt}
            ] + new_messages

            llm_effect = llm_stream_effect(
                messages=full_messages,
                tools=self.config.get("tools", []),
                model=self.config.get("model", "gpt-3.5-turbo"),
            )
            effects.append(llm_effect)

            return new_state, effects

        elif event.type == "skill_activate":
            # Activate a skill
            skill_name = event.payload.get("skill_name")

            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=AgentStatus.SKILL_ACTIVE,
                active_skill=skill_name,
                messages=state.messages,
                context=state.context,
                working_memory=state.working_memory,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        elif event.type == "skill_exit":
            # Exit current skill
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=AgentStatus.IDLE,
                active_skill=None,
                messages=state.messages,
                context=state.context,
                working_memory=state.working_memory,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        elif event.type == "assistant_response":
            # Assistant response
            new_messages = state.messages + [
                {"role": "assistant", "content": event.payload.get("message", "")}
            ]

            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                messages=new_messages,
                status=AgentStatus.IDLE,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                last_error=state.last_error,
                error_count=state.error_count,
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        elif event.type == "error":
            new_state = AgentState(
                agent_id=state.agent_id,
                session_id=state.session_id,
                run_id=state.run_id,
                status=AgentStatus.FAILED,
                last_error=event.payload.get("error"),
                error_count=state.error_count + 1,
                messages=state.messages,
                context=state.context,
                working_memory=state.working_memory,
                active_skill=state.active_skill,
                skill_state=state.skill_state,
                current_step=state.current_step,
                total_steps=state.total_steps,
                created_at=state.created_at,
                updated_at=time.time(),
                conversation_summary=state.conversation_summary,
                tokens_generated=state.tokens_generated,
                tools_executed=state.tools_executed,
                execution_time=state.execution_time,
            )
            return new_state, []

        return state, []
