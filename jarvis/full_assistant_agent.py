"""
Full Assistant Agent - A complete feature-rich agent example.

This agent replicates the functionality of the original assistant project:
- Intent recognition and planning
- Skill system integration
- Tool execution with concurrent support
- LLM streaming with deep thinking
- Event sourcing and replay
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple

# Import Jarvis core
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])

from jarvis_core import (
    Agent, AgentState, AgentStatus, Event, EventType,
    Effect, EffectType,
    llm_generate_effect, llm_stream_effect,
    tool_call_effect, tool_batch_effect,
    save_state_effect,
    request_approval_effect,
    activate_skill_effect, exit_skill_effect,
)

logger = logging.getLogger(__name__)


class FullAssistantAgent(Agent):
    """
    Full-featured Assistant Agent.

    This agent supports:
    1. Intent recognition and planning
    2. Skill activation/context switching
    3. Tool execution with concurrency
    4. LLM streaming with thinking support
    5. Approval workflow for sensitive operations
    6. Artifact storage
    7. Deep thinking mode
    """

    def __init__(
        self,
        system_prompt: str = "You are a helpful assistant.",
        skills_loader: Optional[Any] = None,
        intent_recognizer: Optional[Any] = None,
        max_history: int = 100,
        enable_deep_thinking: bool = True,
    ):
        self.system_prompt = system_prompt
        self._skills_loader = skills_loader
        self._intent_recognizer = intent_recognizer
        self._max_history = max_history
        self._enable_deep_thinking = enable_deep_thinking

    def reduce(
        self,
        state: AgentState,
        event: Event,
    ) -> Tuple[AgentState, List[Effect]]:
        """
        Main reducer - handles all event types.

        This is the heart of the agent's decision logic.
        """
        effects: List[Effect] = []

        # ============================================================
        # 1. User Input - Entry point for all user interactions
        # ============================================================
        if event.type == "user_input":
            return self._handle_user_input(state, event)

        # ============================================================
        # 2. LLM Events - Responses and tool calls
        # ============================================================
        elif event.type == "llm_response":
            return self._handle_llm_response(state, event)

        elif event.type == "llm_tool_call":
            return self._handle_llm_tool_call(state, event)

        elif event.type == "llm_thinking":
            # Thinking content - pass through
            return state, []

        # ============================================================
        # 3. Tool Events - Execution results
        # ============================================================
        elif event.type == "tool_result":
            return self._handle_tool_result(state, event)

        elif event.type == "tool_error":
            return self._handle_tool_error(state, event)

        # ============================================================
        # 4. Approval Events - Human-in-the-loop
        # ============================================================
        elif event.type == "approval_granted":
            return self._handle_approval_granted(state, event)

        elif event.type == "approval_denied":
            return self._handle_approval_denied(state, event)

        # ============================================================
        # 5. Skill Events - Context switching
        # ============================================================
        elif event.type == "skill_activated":
            return self._handle_skill_activated(state, event)

        elif event.type == "skill_exited":
            return self._handle_skill_exited(state, event)

        # ============================================================
        # 6. Intent Events - Planning and coordination
        # ============================================================
        elif event.type == "intent_recognized":
            return self._handle_intent_recognized(state, event)

        elif event.type == "intent_step_complete":
            return self._handle_intent_step_complete(state, event)

        # ============================================================
        # 7. State Management Events
        # ============================================================
        elif event.type == "save_state":
            # Save state effect - handled externally
            return state, []

        # ============================================================
        # 8. Error Handling
        # ============================================================
        elif event.type == "error":
            return self._handle_error(state, event)

        # ============================================================
        # Default: No state change, no effects
        # ============================================================
        return state, []

    # =========================================================================
    # Input Handlers
    # =========================================================================

    def _handle_user_input(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle user input event."""
        user_message = event.payload.get("message", "")
        context = event.payload.get("context", {})

        # Create new state with user message in history
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=state.history + [
                {
                    "role": "user",
                    "content": user_message,
                    "timestamp": event.timestamp,
                    "context": context,
                }
            ],
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        effects: List[Effect] = []

        # Phase 1: Intent Recognition (if configured)
        if self._intent_recognizer:
            effects.append(
                Effect(
                    type=EffectType.CUSTOM,
                    payload={
                        "effect_type": "recognize_intent",
                        "message": user_message,
                        "context": context,
                    },
                )
            )
            return new_state, effects

        # Phase 2: Prepare LLM call
        messages = self._prepare_messages_for_llm(new_state)

        # Check if deep thinking is enabled
        deep_thinking = (
            self._enable_deep_thinking and
            event.payload.get("deep_thinking", False)
        )

        # Add LLM stream effect
        llm_effect = llm_stream_effect(
            messages=messages,
            temperature=0.7,
        )

        if deep_thinking:
            llm_effect.metadata["deep_thinking"] = True

        effects.append(llm_effect)

        return new_state, effects

    def _prepare_messages_for_llm(self, state: AgentState) -> List[Dict[str, Any]]:
        """Prepare messages for LLM from state."""
        messages = []

        # System prompt
        if self._enable_deep_thinking:
            system_prompt = self.system_prompt + """

=== DEEP THINKING PROTOCOL ===
You MUST start your response with a <thinking> block where you:
1. Analyze the user's request
2. Consider what tools to use
3. Plan your step-by-step approach

After your thinking, provide your final response.
"""
        else:
            system_prompt = self.system_prompt

        messages.append({"role": "system", "content": system_prompt})

        # Add skill context if active
        if state.active_skill and self._skills_loader:
            skill_prompt = self._get_active_skill_prompt(state)
            if skill_prompt:
                messages.append({
                    "role": "system",
                    "content": skill_prompt,
                })

        # Add conversation history (limited)
        history_to_include = state.history[-self._max_history:]

        for msg in history_to_include:
            if msg["role"] == "user":
                content = [{"type": "text", "text": msg["content"]}]
                messages.append({"role": "user", "content": content})

            elif msg["role"] == "assistant":
                # Assistant might have text and tool calls
                content = []
                if msg.get("text"):
                    content.append({"type": "text", "text": msg["text"]})

                if msg.get("tool_calls"):
                    content.extend(msg["tool_calls"])

                messages.append({"role": "assistant", "content": content})

            elif msg["role"] == "tool":
                # Tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": msg["tool_call_id"],
                    "content": msg.get("result", ""),
                })

        return messages

    # =========================================================================
    # LLM Response Handlers
    # =========================================================================

    def _handle_llm_response(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle LLM text response."""
        response_text = event.payload.get("response", "")

        # Update history with assistant response
        new_history = state.history.copy()

        # Update last assistant message or create new one
        if new_history and new_history[-1]["role"] == "assistant":
            new_history[-1]["text"] = response_text
        else:
            new_history.append({
                "role": "assistant",
                "text": response_text,
                "timestamp": event.timestamp,
            })

        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.IDLE,
            history=new_history,
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        # Emit save state effect
        return new_state, [save_state_effect(
            state=new_state.to_dict(),
            session_id=state.session_id,
        )]

    def _handle_llm_tool_call(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle LLM tool request."""
        tool_calls = event.payload.get("tool_calls", [])

        effects: List[Effect] = []

        # Check for sensitive tools
        sensitive_calls = []
        regular_calls = []

        if self._skills_loader:
            for call in tool_calls:
                tool_name = call.get("name", "")
                if self._is_sensitive_tool(tool_name):
                    sensitive_calls.append(call)
                else:
                    regular_calls.append(call)
        else:
            regular_calls = tool_calls

        # Update history with tool calls
        new_history = state.history.copy()

        if new_history and new_history[-1]["role"] == "assistant":
            new_history[-1]["tool_calls"] = tool_calls
        else:
            new_history.append({
                "role": "assistant",
                "tool_calls": tool_calls,
                "timestamp": event.timestamp,
            })

        # Create pending state
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=new_history,
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata={
                **state.metadata,
                "pending_tools": tool_calls,
            },
        )

        # Handle sensitive tools (require approval)
        if sensitive_calls:
            for call in sensitive_calls:
                effects.append(
                    request_approval_effect(
                        tool_name=call["name"],
                        tool_args=call.get("args", {}),
                        reason=f"Sensitive tool: {call['name']} requires human approval",
                    )
                )
            return new_state, effects

        # Execute regular tools concurrently
        if regular_calls:
            if len(regular_calls) == 1:
                # Single tool call
                call = regular_calls[0]
                effects.append(
                    tool_call_effect(
                        tool_name=call["name"],
                        tool_args=call.get("args", {}),
                    )
                )
            else:
                # Batch tool calls
                effects.append(
                    tool_batch_effect(tool_calls=regular_calls)
                )

        return new_state, effects

    # =========================================================================
    # Tool Result Handlers
    # =========================================================================

    def _handle_tool_result(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle successful tool execution."""
        tool_name = event.payload.get("tool_name")
        tool_result = event.payload.get("result")

        # Update history with tool result
        new_history = state.history.copy()
        new_history.append({
            "role": "tool",
            "tool_call_id": tool_name,
            "result": tool_result,
            "timestamp": event.timestamp,
        })

        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=new_history,
            intent_queue=state.intent_queuequeue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        effects: List[Effect] = []

        # Check if there are pending tool calls
        pending_tools = state.metadata.get("pending_tools", [])

        if len(pending_tools) > 1:
            # More tools to execute, continue with next
            return new_state, effects

        # All tools done, continue with LLM
        messages = self._prepare_messages_for_llm(new_state)
        effects.append(llm_stream_effect(messages=messages))

        return new_state, effects

    def _handle_tool_error(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle tool execution error."""
        tool_name = event.payload.get("tool_name")
        error = event.payload.get("error")

        # Update history with error
        new_history = state.history.copy()
        new_history.append({
            "role": "tool",
            "tool_call_id": tool_name,
            "result": f"Error: {error}",
            "error": error,
            "timestamp": event.timestamp,
        })

        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=new_history,
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        # Continue with LLM to handle the error
        messages = self._prepare_messages_for_llm(new_state)
        effects = [llm_stream_effect(messages=messages)]

        return new_state, effects

    # =========================================================================
    # Approval Handlers
    # =========================================================================

    def _handle_approval_granted(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle granted approval."""
        tool_name = event.payload.get("tool_name")
        tool_args = event.payload.get("tool_args")

        # Execute the tool
        effects = [
            tool_call_effect(tool_name=tool_name, tool_args=tool_args),
        ]

        # Update state to running
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=state.history.copy(),
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        return new_state, effects

    def _handle_approval_denied(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle denied approval."""
        reason = event.payload.get("reason")

        # Update history with denial
        new_history = state.history.copy()
        new_history.append({
            "role": "system",
            "content": f"Tool approval denied: {reason}",
            "timestamp": event.timestamp,
        })

        # Return to idle state
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.IDLE,
            history=new_history,
            intent_queue=[],
            intent_session={},
            active_skill=None,
            shared_memory=state.shared_memory.copy(),
            current_plan=None,
            metadata=state.metadata.copy(),
        )

        return new_state, []

    # =========================================================================
    # Skill Handlers
    # =========================================================================

    def _handle_skill_activated(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle skill activation."""
        skill_name = event.payload.get("skill_name")

        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=state.history.copy(),
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=skill_name,
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        return new_state, []

    def _handle_skill_exited(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle skill exit."""
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=state.history.copy(),
            intent_queue=state.intent_queue.copy(),
            intent_session=state.intent_session.copy(),
            active_skill=None,
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        return new_state, []

    # =========================================================================
    # Intent Handlers
    # =========================================================================

    def _handle_intent_recognized(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle intent recognition result."""
        intents = event.payload.get("intents", [])

        if not intents:
            # No intent matched, proceed to LLM
            messages = self._prepare_messages_for_llm(state)
            effects = [llm_stream_effect(messages=messages)]
            return state, effects

        # Add to intent queue
        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.RUNNING,
            history=state.history.copy(),
            intent_queue=intents,
            intent_session=state.intent_session.copy(),
            active_skill=state.get("active_skill"),
            shared_memory=state.shared_memory.copy(),
            current_plan=state.current_plan,
            metadata=state.metadata.copy(),
        )

        # Execute first intent
        return self._execute_intent_step(new_state, intents[0])

    def _handle_intent_step_complete(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle intent step completion."""
        # Move to next intent in queue
        if not state.intent_queue:
            # All intents done, go to LLM
            messages = self._prepare_messages_for_llm(state)
            effects = [llm_stream_effect(messages=messages)]
            return state, effects

        # Execute next intent
        next_intent = state.intent_queue[0]
        return self._execute_intent_step(state, next_intent)

    def _execute_intent_step(
        self, state: AgentState, intent: Dict[str, Any]
    ) -> Tuple[AgentState, List[Effect]]:
        """Execute a single intent step."""
        intent_type = intent.get("type")
        intent_name = intent.get("name")
        intent_data = intent.get("data", {})

        effects: List[Effect] = []

        if intent_type == "activate_skill":
            effects.append(
                activate_skill_effect(skill_name=intent_name)
            )

        elif intent_type == "tool_call":
            effects.append(
                tool_call_effect(
                    tool_name=intent_name,
                    tool_args=intent_data,
                )
            )

        elif intent_type == "llm_generate":
            messages = intent_data.get("messages", [])
            effects.append(
                llm_stream_effect(messages=messages)
            )

        return state, effects

    # =========================================================================
    # Error Handler
    # =========================================================================

    def _handle_error(
        self, state: AgentState, event: Event
    ) -> Tuple[AgentState, List[Effect]]:
        """Handle error event."""
        error_msg = event.payload.get("error", "")
        error_type = event.payload.get("error_type", "Exception")

        new_state = AgentState(
            session_id=state.session_id,
            user_id=state.user_id,
            status=AgentStatus.ERROR,
            history=state.history.copy(),
            intent_queue=[],
            intent_session={},
            active_skill=None,
            shared_memory=state.shared_memory.copy(),
            current_plan=None,
            metadata={
                **state.metadata,
                "error": error_msg,
                "error_type": error_type,
            },
        )

        return new_state, []

    # =========================================================================
    # Helpers
    # =========================================================================

    def _is_sensitive_tool(self, tool_name: str) -> bool:
        """Check if a tool is sensitive."""
        sensitive_tools = [
            "write_file",
            "delete_file",
            "execute_code",
            "bash",
        ]
        return tool_name in sensitive_tools

    def _get_active_skill_prompt(self, state: AgentState) -> Optional[str]:
        """Get prompt for active skill."""
        if not state.active_skill or not self._skills_loader:
            return None

        # Try to get skill prompt from loader
        try:
            skill = self._skills_loader.get_skill(state.active_skill)
            if skill and hasattr(skill, "get_system_prompt"):
                return skill.get_system_prompt()
        except Exception:
            pass

        return None
