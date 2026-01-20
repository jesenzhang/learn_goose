"""
ThreePhaseAgent - Intent → LLM → Tools execution pattern.

This agent implements the three-phase execution pattern from skill_micro_agent:
- Phase 1: Intent Recognition (check if intent is ready to execute)
- Phase 2: LLM Generation (streaming response with tool calls)
- Phase 3: Tool Execution (execute tools with inspector chain)
"""

import logging
from typing import Optional, Dict, Any, List, AsyncIterator

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
from pho.conversation import Message, Conversation
from pho.providers import BaseLLM
from pho.skills import SkillLoader, SkillType
from pho.intent import IntentRecognizer, IntentDefinition, MultiIntentResult
from pho.toolkit import ToolExecutor, ExecutionContext
from pho.agent.inspectors import InspectorChain

logger = logging.getLogger(__name__)


class ThreePhaseAgentEngine(AgentEngine):
    """
    Three-phase agent engine implementation.

    Phase 1 - Intent Recognition:
        - Use IntentRecognizer to identify user intent
        - Check if intent is ready (all required slots filled)
        - If incomplete, return follow-up question

    Phase 2 - LLM Generation:
        - Generate response using available tools
        - Stream output tokens
        - Detect tool calls

    Phase 3 - Tool Execution:
        - Execute tools via ToolExecutor
        - Run through inspector chain
        - Return results
    """

    def __init__(
        self,
        llm: BaseLLM,
        config: Optional[AgentConfig] = None,
        tools: Optional[Dict[str, Any]] = None,
        skill_loader: Optional[SkillLoader] = None,
        intent_recognizer: Optional[IntentRecognizer] = None,
        inspector_chain: Optional[InspectorChain] = None,
    ):
        self.llm = llm
        self.config = config
        self.tools = tools or {}
        self.skill_loader = skill_loader
        self.intent_recognizer = intent_recognizer
        self.inspector_chain = inspector_chain or InspectorChain()

        # Create tool executor
        self.tool_executor = ToolExecutor(
            registry=self._create_registry(),
            inspector_chain=self.inspector_chain,
            enable_cache=True,
        )

        # Session state for intent tracking
        self._intent_sessions: Dict[str, Dict[str, Any]] = {}

    def _create_registry(self):
        """Create tool registry from skills and tools"""
        from pho.toolkit import ToolRegistry, ToolSourceType
        registry = ToolRegistry()

        # Register tools from skills if available
        if self.skill_loader:
            for skill_name, skill in self.skill_loader._skills.items():
                for tool_name, tool_meta in skill._tools.items():
                    registry.register(
                        name=tool_name,
                        func=tool_meta.handler,
                        description=tool_meta.description,
                        tool_type=ToolSourceType.SKILL,
                        category=skill_name,
                        source=skill_name,
                    )

        # Register direct tools
        for name, func in self.tools.items():
            registry.register(
                name=name,
                func=func,
                description=f"Tool: {name}",
                tool_type=ToolSourceType.DECORATOR,
            )

        return registry

    def get_mode(self) -> ExecutionMode:
        return ExecutionMode.THREE_PHASE

    def get_style(self) -> AgentStyle:
        return AgentStyle.SKILL_BASED

    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Execute the three-phase agent logic.

        Returns:
            AgentResponse with results
        """
        session_id = context.session_id or "default"

        # Phase 1: Intent Recognition
        if self.intent_recognizer:
            intent_result = await self._phase1_intent_recognition(input, context)
            if intent_result:
                # If intent is incomplete, return follow-up question
                if intent_result.incomplete_intents:
                    incomplete = intent_result.incomplete_intents[0]
                    return AgentResponse(
                        text=incomplete.reply_to_user or "I need more information.",
                        status=AgentStatus.COMPLETED,
                        events=[AgentEvent(
                            type=AgentEventType.THINKING,
                            data={"thought": incomplete.thought}
                        )],
                    )
                # If intent is ready, we can proceed to Phase 2
                # (Intent entities are merged into context variables)
                if intent_result.ready_intents:
                    ready = intent_result.ready_intents[0]
                    context.variables.update(ready.entities)

        # Phase 2: LLM Generation
        response_text, tool_calls = await self._phase2_llm_generation(input, context)

        # Phase 3: Tool Execution
        if tool_calls:
            tool_results = await self._phase3_tool_execution(tool_calls, context)
            if tool_results:
                # Generate final response with tool results
                response_text = await self._generate_final_response(
                    input, response_text, tool_results, context
                )

        return AgentResponse(
            text=response_text,
            status=AgentStatus.COMPLETED,
        )

    async def execute_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream execution with real-time updates"""
        # Emit start event
        yield AgentResponse(
            text="",
            status=AgentStatus.THINKING,
            events=[AgentEvent(type=AgentEventType.START, data={"input": input})]
        )

        # Phase 1: Intent Recognition
        if self.intent_recognizer:
            yield AgentResponse(
                text="",
                status=AgentStatus.THINKING,
                events=[AgentEvent(type=AgentEventType.THINKING, data={"phase": "intent_recognition"})]
            )

            intent_result = await self._phase1_intent_recognition(input, context)
            if intent_result and intent_result.incomplete_intents:
                incomplete = intent_result.incomplete_intents[0]
                yield AgentResponse(
                    text=incomplete.reply_to_user or "I need more information.",
                    status=AgentStatus.COMPLETED,
                )
                return

        # Phase 2: LLM Generation (streaming)
        response_text = ""
        tool_calls = []

        async for chunk in self._phase2_llm_generation_stream(input, context):
            if chunk.text:
                response_text += chunk.text
                yield AgentResponse(
                    text=chunk.text,
                    status=AgentStatus.STREAMING,
                )
            if chunk.tool_calls:
                tool_calls.extend(chunk.tool_calls)

        # Phase 3: Tool Execution
        if tool_calls:
            yield AgentResponse(
                text="",
                status=AgentStatus.TOOLING,
                events=[AgentEvent(type=AgentEventType.TOOL_START, data={"tools": [t.name for t in tool_calls]})]
            )

            tool_results = await self._phase3_tool_execution(tool_calls, context)

            for tool_name, result in tool_results.items():
                yield AgentResponse(
                    text=f"\n[Tool: {tool_name} Result: {result}]",
                    status=AgentStatus.STREAMING,
                )

            # Generate final response
            final_response = await self._generate_final_response(
                input, response_text, tool_results, context
            )
            yield AgentResponse(
                text=final_response,
                status=AgentStatus.COMPLETED,
            )
        else:
            yield AgentResponse(
                text=response_text,
                status=AgentStatus.COMPLETED,
            )

    async def _phase1_intent_recognition(
        self,
        input: str,
        context: Context
    ) -> Optional[MultiIntentResult]:
        """Phase 1: Recognize user intent"""
        session_id = context.session_id or "default"

        # Get or create session state
        if session_id not in self._intent_sessions:
            self._intent_sessions[session_id] = {
                "session_id": session_id,
                "current_intent": None,
                "collected_slots": {},
                "last_updated": 0,
            }

        session_state = self._intent_sessions[session_id]

        try:
            result, updated_state = await self.intent_recognizer.recognize(
                user_input=input,
                session_state=session_state,
                background_info=context.variables.get("background_info", ""),
            )
            self._intent_sessions[session_id] = updated_state
            return result
        except Exception as e:
            logger.error(f"Intent recognition failed: {e}")
            return None

    async def _phase2_llm_generation(
        self,
        input: str,
        context: Context
    ) -> tuple[str, List[Any]]:
        """Phase 2: Generate LLM response"""
        conversation = self.create_conversation(input, context)

        # Add skill context prompt if available
        if self.skill_loader:
            active_skill = context.variables.get("active_skill")
            skill_prompt = self.skill_loader.get_context_prompt(active_skill)
            if skill_prompt:
                system_msg = Message.system(skill_prompt)
                conversation.messages.insert(0, system_msg)

        # Get tools schema
        tools = None
        if self.tool_executor.registry:
            active_skill = context.variables.get("active_skill")
            tools = self.skill_loader.get_all_tools_schema(active_skill) if self.skill_loader else None

        # Call LLM
        response_msg, _ = await self.call_llm(
            conversation.agent_visible_messages(),
            tools=tools,
        )

        # Extract tool calls
        tool_calls = []
        if hasattr(response_msg, 'tool_requests') and response_msg.tool_requests:
            tool_calls = response_msg.tool_requests

        return response_msg.text or "", tool_calls

    async def _phase2_llm_generation_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Phase 2: Generate LLM response (streaming)"""
        conversation = self.create_conversation(input, context)

        # Add skill context prompt if available
        if self.skill_loader:
            active_skill = context.variables.get("active_skill")
            skill_prompt = self.skill_loader.get_context_prompt(active_skill)
            if skill_prompt:
                system_msg = Message.system(skill_prompt)
                conversation.messages.insert(0, system_msg)

        # Get tools schema
        tools = None
        if self.skill_loader:
            active_skill = context.variables.get("active_skill")
            tools = self.skill_loader.get_all_tools_schema(active_skill)

        # Stream LLM response
        full_text = ""
        async for msg, _ in self.call_llm_stream(
            conversation.agent_visible_messages(),
            tools=tools,
        ):
            if msg and msg.content:
                for item in msg.content:
                    if hasattr(item, 'text'):
                        full_text += item.text
                        yield AgentResponse(text=item.text)

        # Extract tool calls from final message
        tool_calls = []
        if msg and hasattr(msg, 'tool_requests') and msg.tool_requests:
            tool_calls = msg.tool_requests

        # Yield tool calls
        if tool_calls:
            yield AgentResponse(text="", tool_calls=tool_calls)

    async def _phase3_tool_execution(
        self,
        tool_calls: List[Any],
        context: Context
    ) -> Dict[str, Any]:
        """Phase 3: Execute tools"""
        results = {}

        # Create execution context
        exec_context = ExecutionContext(
            session_id=context.session_id,
            user_id=context.user_id,
            user_role=context.variables.get("user_role"),
            variables=context.variables,
        )

        for tool_call in tool_calls:
            tool_name = tool_call.name if hasattr(tool_call, 'name') else tool_call.get("name")
            tool_args = tool_call.arguments if hasattr(tool_call, 'arguments') else tool_call.get("arguments", {})

            try:
                result = await self.tool_executor.execute(tool_name, tool_args, exec_context)
                if result.is_success:
                    results[tool_name] = result.result
                else:
                    results[tool_name] = f"Error: {result.error}"
            except Exception as e:
                logger.error(f"Tool execution failed for {tool_name}: {e}")
                results[tool_name] = f"Error: {str(e)}"

        return results

    async def _generate_final_response(
        self,
        input: str,
        initial_response: str,
        tool_results: Dict[str, Any],
        context: Context
    ) -> str:
        """Generate final response incorporating tool results"""
        # For now, just append tool results
        # In production, you'd call LLM again to synthesize
        parts = [initial_response]

        if tool_results:
            parts.append("\n\nTool Results:")
            for tool_name, result in tool_results.items():
                parts.append(f"\n{tool_name}: {result}")

        return "".join(parts)

    # ========================================================================
    # Helper Methods (from BaseEngine)
    # ========================================================================

    def create_conversation(self, input: str, context: Context) -> Conversation:
        """Create initial conversation from input."""
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
        """Call the LLM with messages and optional tools."""
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
        """Call the LLM with streaming support."""
        try:
            async for msg, usage in self.llm.astream(messages, tools=tools):
                yield msg, usage
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise


__all__ = ["ThreePhaseAgentEngine"]
