"""
MicroAgent Core Module - Main agent execution logic.

This module handles:
- LLM interaction and streaming responses
- Tool execution with dependency injection
- Concurrent tool execution
- Human-in-the-loop approval workflow
- State management integration
"""

import os
import time
import json
import uuid
import asyncio
import logging
import inspect
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable

from openai import AsyncOpenAI

from ..skills.context import ServiceContext, create_context
from .events import EventManager, EventType
from .state import AgentState, AgentStatus
from ..db import get_db
from ..config.loader import ConfigLoader
from ..skills import SkillLoader

# Intent System
from ..intent.recognizer import IntentRecognizer
from ..intent.strategy import IntentExecutor, ExecutionMode, TerminationAction
from ..intent.config_loader import IntentConfigLoader

logger = logging.getLogger(__name__)


# Core control tools
def update_plan(steps: List[str], _ctx=None) -> str:
    """Update or create a step-by-step execution plan."""
    return f"PLAN_UPDATED:{json.dumps(steps)}"


def submit_intent(slots: Dict, _ctx=None) -> str:
    """Submit intent with filled slots."""
    return "SUBMITTED"


class MicroAgent:
    """
    Core LLM Agent with event streaming and tool execution.

    Features:
    - OpenAI-compatible LLM integration
    - Streaming response with real-time events
    - Concurrent tool execution
    - Human approval for sensitive actions
    - Skill/context switching
    - State persistence
    
    The orchestrator.
    Pipeline: Input -> [Intent Recognition] -> [Execution Strategy] -> [LLM Loop (Optional)]
    """

    def __init__(
        self,
        config: ConfigLoader,
        ai_services: Optional[Any] = None,
        skill_loader: Optional[SkillLoader] = None
    ):
        self.config = config
        self.events = EventManager()
        self.skill_loader: Optional[SkillLoader] = skill_loader
        self.ai_services: Optional[Any] = ai_services
        self.db = get_db()

        # Initialize OpenAI client with type-safe config access
        self.client = AsyncOpenAI(
            api_key=config.get_api_key(),
            base_url=config.provider.base_url
        )

        # Core tools (always available)
        self.core_tools = {
            "submit_intent": submit_intent,
            "update_plan": update_plan,
        }

        # Intent System Init
        self.intent_recognizer: Optional[IntentRecognizer] = None
        self.intent_executor: Optional[IntentExecutor] = None
        self._init_intents()

        logger.info("MicroAgent initialized")

    def _init_intents(self):
        """Load intent definitions and strategies from config."""
        # 1. Get definitions (for Recognizer)
        intent_definitions = self.config.get_intent_definitions() 
        
        if intent_definitions:
            self.intent_recognizer = IntentRecognizer(
                intents=intent_definitions,
                llm_client=self.client
            )
            
            # 2. Get strategies (for Executor)
            self.intent_executor = IntentExecutor(
                skill_loader=self.skill_loader,
                ai_services=self.ai_services
            )
            
            # Load raw yaml execution configs
            config_loader = IntentConfigLoader()
            config_loader.load_from_config(self.config.raw_data, self.intent_executor)
            
            logger.info(f"Intent system active: {len(intent_definitions)} intents loaded.")
    
    # =========================================================================
    # Phase 1: Intent Processing
    # =========================================================================

    async def _handle_intent_phase(self, user_input: str, state: AgentState) -> Optional[str]:
        """
        Analyze user input for intents.
        
        Returns:
            str: Final response (if intent handled directly/chain)
            None: If should proceed to LLM ReAct loop
        """
        if not self.intent_recognizer:
            return None

        # 1. Recognize (Stateless call, passing persistent session data)
        await self.events.emit(EventType.STATE_CHANGE, {"msg": "🤔 Analyzing intent..."})
        
        results, updated_session_data = await self.intent_recognizer.recognize(
            user_input=user_input,
            session_state=state.intent_session, # Load from DB
            background_info=f"Active Skill: {state.active_skill}"
        )
        
        # Save updated intent state immediately
        state.intent_session = updated_session_data
        self.db.save_state(state)

        # 2. Check Results
        if not results.intents:
            return None # No intent, fallback to LLM

        # If primary intent is incomplete, return the clarification question
        # (The Recognizer generates reply_to_user in this case)
        primary_intent_name = results.primary_intent or results.intents[0].intent
        primary_result = results.get_intent(primary_intent_name)
        
        if not primary_result:
            return None

        if primary_result.is_incomplete and primary_result.reply_to_user:
            # Short-circuit: ask user for missing slot
            return primary_result.reply_to_user

        if not primary_result.is_ready:
            return None # Not ready, fallback

        # 3. Execution Strategy
        logger.info(f"Executing Intent: {primary_result.intent}")
        await self.events.emit(EventType.STATE_CHANGE, {
            "msg": f"🎯 Intent: {primary_result.intent}",
            "slots": primary_result.entities
        })

        # Inject slots into shared memory
        for k, v in primary_result.entities.items():
            state.shared_memory[k] = v

        # Get Strategy Config
        exec_config = self.intent_executor.get_config(primary_result.intent)
        if not exec_config:
            # Default: LLM mode with no constraints
            return None

        # 4. Pre-Hook
        ctx = create_context(state.session_id, state=state, db=self.db, ai_services=self.ai_services)
        pre_res = await self.intent_executor.execute_pre_hook(
            primary_result.intent, primary_result.entities, ctx
        )
        if pre_res:
            return pre_res # Hook handled it

        # 5. Core Execution (Direct, Chain, Skill, LLM)
        final_response = None
        should_stop = False

        if exec_config.mode == ExecutionMode.DIRECT:
            res = await self.intent_executor.execute_direct(
                primary_result.intent, primary_result.entities, ctx
            )
            final_response = str(res)
            should_stop = True

        elif exec_config.mode == ExecutionMode.CHAIN:
            res = await self.intent_executor.execute_chain(
                primary_result.intent, primary_result.entities, ctx
            )
            final_response = str(res)
            should_stop = True

        elif exec_config.mode == ExecutionMode.SKILL:
            # Switch Context
            state.active_skill = exec_config.skill_name
            # Inject skill params
            state.shared_memory.update(exec_config.skill_params)
            
            await self.events.emit(EventType.STATE_CHANGE, {
                "msg": f"🔄 Switching Context: {exec_config.skill_name}"
            })
            # should_stop = False -> Continue to ReAct loop with new Skill Context
            should_stop = False

        elif exec_config.mode == ExecutionMode.LLM:
            # Lock tools for this turn
            allowed = self.intent_executor.get_allowed_tools(
                primary_result.intent, 
                self.skill_loader.get_available_skills_list() if self.skill_loader else []
            )
            state.shared_memory["_restricted_tools"] = allowed
            should_stop = False

        # 6. Post-Processing
        if exec_config.on_complete == TerminationAction.STOP:
            return final_response
        
        return final_response if should_stop else None
    
    
    # =========================================================================
    # Phase 2: Tool Execution & Dependency Injection
    # =========================================================================
    
    async def _exec_tool_func(
        self,
        tool_name: str,
        tool_args: Dict,
        state: AgentState
    ) -> str:
        """
        Execute a tool function with dependency injection.
        """
        # Find tool implementation
        func = self.core_tools.get(tool_name)
        if not func and self.skill_loader:
            func = self.skill_loader.get_tool_func(tool_name)

        if not func:
            return f"Error: Tool '{tool_name}' not found."

        # 2. Inspect Signature
        try:
            sig = inspect.signature(func)
        except ValueError:
            return func(**tool_args)

        call_args = tool_args.copy()

        # Check for **kwargs
        has_var_keyword = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

        # Check for explicitly typed ServiceContext
        needs_ctx = 'ctx' in sig.parameters and self._is_service_context_type(sig.parameters['ctx'].annotation)
        # 3. Create Context
        if needs_ctx or has_var_keyword:
            ctx = create_context(
                session_id=state.session_id,
                state=state,
                db=self.db,
                ai_services=self.ai_services
            )
            if needs_ctx or has_var_keyword:
                call_args['ctx'] = ctx
                
        # 4. Legacy Injection (state, db, ai)
        if has_var_keyword or '_state' in sig.parameters:
            call_args['_state'] = state
        if has_var_keyword or '_ctx' in sig.parameters:
            call_args['_ctx'] = {"session_id": state.session_id} # Legacy dict
        if self.db and (has_var_keyword or '_db' in sig.parameters):
            call_args['_db'] = self.db
        if self.ai_services and (has_var_keyword or '_ai' in sig.parameters):
            call_args['_ai'] = self.ai_services

        # 5. Execute
        try:
            if inspect.iscoroutinefunction(func):
                result = await func(**call_args)
            else:
                result = await asyncio.to_thread(func, **call_args)

            # 6. Handle Artifacts
            from agent_skills.types import CallToolResult
            if isinstance(result, CallToolResult):
                final_llm_text_parts = []
                for item in result.content:
                    if item.data is not None:
                        art_id = f"art_{uuid.uuid4().hex[:8]}"
                        state.shared_memory[art_id] = item.data

                        # Emit artifact event
                        await self.events.emit(EventType.TOOL_ARTIFACT, {
                            "id": art_id,
                            "type": item.type,
                            "title": f"Output from {tool_name}",
                            "view": item.text,
                            "data": item.data
                        })
                        
                        # [View Layer] Append ID reference
                        item_view = f"{item.text}\n[Artifact ID: {art_id}]"
                        final_llm_text_parts.append(item_view)
                    else:
                        final_llm_text_parts.append(item.text or "")
                return "\n\n".join(final_llm_text_parts)

            return str(result) if result is not None else ""

        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=e)
            return f"Error executing tool '{tool_name}': {str(e)}"

    def _is_service_context_type(self, annotation: Any) -> bool:
        """Check if parameter annotation is ServiceContext."""
        return "ServiceContext" in str(annotation)

    
    # =========================================================================
    # Phase 3: LLM Loop (ReAct)
    # =========================================================================
    
    
    def _get_tools_schema(self, state: AgentState) -> List[Dict]:
        """
        Build tool schemas for LLM function calling.

        Args:
            state: Current agent state

        Returns:
            List of tool schemas in OpenAI format
        """
        schemas = []

        # Plan management tool
        schemas.append({
            "type": "function",
            "function": {
                "name": "update_plan",
                "description": "Manage execution steps for complex tasks.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of execution steps"
                        }
                    },
                    "required": ["steps"]
                }
            }
        })

        if not self.skill_loader:
            return schemas
        
        # 2. Check for Intent-based Tool Restrictions
        restricted_list = state.shared_memory.get("_restricted_tools")
        if restricted_list:
            # Only allow tools explicitly permitted by the Intent Strategy
            # (Note: This requires SkillLoader to support filtering by name list, or we filter manually here)
            all_schemas = self.skill_loader.get_all_tools_schema(state.active_skill)
            filtered = [s for s in all_schemas if s['function']['name'] in restricted_list]
            schemas.extend(filtered)
        else:
            # 3. Standard Mode: Load tools based on Active Skill
            # (SkillLoader handles Global + Active Skill logic)
            schemas.extend(self.skill_loader.get_all_tools_schema(state.active_skill))

        return schemas

    def _needs_complex_protocol(self, state: AgentState) -> bool:
        if state.current_plan: return True
        if state.status == AgentStatus.WAITING_APPROVAL: return True
        if state.shared_memory.get("_restricted_tools"): return True
        return False
    
    def _build_system_prompt(self, state: AgentState) -> str:
        """
        Build dynamic system prompt from configuration and state.

        Args:
            state: Current agent state

        Returns:
            Complete system prompt string
        """
        # Base persona with type-safe config access
        base_template = self.config.agent.system_template
        try:
            static_prompt = base_template.format(name=self.config.agent.name)
        except KeyError:
            static_prompt = base_template

        # Concurrency protocol
        if self._needs_complex_protocol(state):
            concurrency_protocol = """
=== ⚡ CONCURRENCY & SAFETY RULES ===
1. **Parallel Execution**: You CAN call multiple tools in a single turn if they are independent (e.g., searching for two different things). This is encouraged for speed.
2. **Sequential Dependency**: If Tool B requires the output of Tool A, you MUST NOT call them in the same turn. Wait for Tool A's result, then call Tool B in the next turn.
3. **State Safety**: Do not read and write to the same memory key in the same turn.
4. **Routing**: If the user's request is out of scope, use skill switching tools immediately.
"""
            static_prompt += concurrency_protocol

        # Skill context
        if self.skill_loader:
            skill_prompt = self.skill_loader.get_context_prompt(state.active_skill)
            static_prompt += skill_prompt

        # Dynamic context
        now = datetime.now()
        dynamic_context = f"\n=== STATUS ===\n"
        dynamic_context += f"[Time]: {now.strftime('%Y-%m-%d %H:%M')}\n"
        dynamic_context += f"[Mode]: {state.active_skill or 'Router (Global)'}\n"

        # Shared memory preview
        # 智能内存预览：只显示非 Artifact 的短数据，长数据显示 ID
        if state.shared_memory:
            memory_view = []
            for k, v in state.shared_memory.items():
                val_str = str(v)
                # 过滤掉内部保留字段
                if k.startswith("_"): continue
                
                # 如果是 Artifact ID (art_) 或者数据太长，只显示引用
                if k.startswith("art_") or len(val_str) > 100:
                    memory_view.append(f"- {k}: <Complex Data, use tools to read>")
                else:
                    memory_view.append(f"- {k}: {val_str}")
            
            if memory_view:
                dynamic_context += "[Active Memory]:\n" + "\n".join(memory_view) + "\n"
        # Current plan
        if state.current_plan:
            dynamic_context += f"\n[Execution Plan]:\n{json.dumps(state.current_plan, ensure_ascii=False)}"

        return static_prompt + dynamic_context

    async def _execute_tools_concurrent(
        self,
        tool_buffer: List[Dict],
        state: AgentState
    ) -> Dict[int, Dict]:
        """
        Execute multiple tools concurrently with proper ordering.

        Args:
            tool_buffer: List of tool calls from LLM
            state: Current agent state

        Returns:
            Map of tool index to execution results
        """
        results_map = {}

        # Pre-flight sensitivity check
        for t in tool_buffer:
            name = t["name"]
            try:
                args = json.loads(t["args"])
            except json.JSONDecodeError:
                args = {}

            # Check if tool requires approval
            is_sensitive = self.config.is_sensitive(name)
            if not is_sensitive and self.skill_loader:
                is_sensitive = self.skill_loader.is_sensitive(name)

            if is_sensitive:
                state.status = AgentStatus.WAITING_APPROVAL
                state.pending_tool_call = {
                    "name": name,
                    "args": args,
                    "id": t["id"]
                }
                self.db.save_state(state)
                await self.events.emit(EventType.APPROVAL_REQ, {
                    "tool": name,
                    "args": args,
                    "reason": "Sensitive action"
                })
                return {}  # Abort execution

        # Wrapper for timing and metadata
        async def wrapper(tool_name: str, tool_args: Dict, current_state: AgentState):
            start_ts = time.time()
            start_str = time.strftime('%H:%M:%S', time.localtime(start_ts))
            
            result_str = await self._exec_tool_func(tool_name, tool_args, current_state)

            # Handle side effects
            if tool_name == "update_plan":
                steps = tool_args.get("steps", [])
                current_state.current_plan = steps
                await self.events.emit(EventType.STATE_CHANGE, {"plan": steps})

            duration = time.time() - start_ts
            return {
                "result": result_str,
                "meta": {
                    "tool": tool_name,
                    "args": tool_args,
                    "start_time": start_str,
                    "duration": f"{duration * 1000:.2f}ms"
                }
            }

        # Create tasks
        pending_tasks = []
        task_indices = []

        for i, t in enumerate(tool_buffer):
            name = t["name"]
            try:
                args = json.loads(t["args"])
            except json.JSONDecodeError:
                args = {}

            await self.events.emit(EventType.TOOL_START, {"name": name, "args": args})
            pending_tasks.append(wrapper(name, args, state))
            task_indices.append(i)

        # Execute concurrently
        if pending_tasks:
            task_outputs = await asyncio.gather(*pending_tasks, return_exceptions=True)

            for idx, output in enumerate(task_outputs):
                original_index = task_indices[idx]

                if isinstance(output, Exception):
                    logger.error(f"Task {original_index} failed: {output}", exc_info=output)
                    results_map[original_index] = {
                        "result": f"System Error: {str(output)}",
                        "meta": {"error": True}
                    }
                else:
                    results_map[original_index] = output
                    meta = output["meta"]
                    logger.debug(f"✅ [Done] {meta['tool']} | ⏳ {meta['duration']}")

        return results_map
    
    async def _process_approval(self, state: AgentState, approval_data: Dict) -> bool:
        """
        Process human approval for pending tool call.

        Args:
            state: Agent state with pending tool call
            approval_data: User's decision (approved/rejected, feedback)

        Returns:
            True if processing should continue
        """
        if state.status != AgentStatus.WAITING_APPROVAL or not state.pending_tool_call:
            await self.events.emit(EventType.ERROR, "Resume failed: No pending approval found.")
            return False

        tool_data = state.pending_tool_call
        is_approved = approval_data.get("approved", False)
        feedback = approval_data.get("feedback", "")

        if is_approved:
            await self.events.emit(EventType.STATE_CHANGE, {
                "msg": f"✅ Approved: {tool_data['name']}"
            })

            # Execute the approved tool
            try:
                res_str = await self._exec_tool_func(
                    tool_data['name'],
                    tool_data['args'],
                    state
                )
            except Exception as e:
                logger.error(f"Error executing approved tool: {e}", exc_info=e)
                res_str = f"Error executing approved tool: {e}"

            # Record result
            state.history.append({
                "role": "tool",
                "tool_call_id": tool_data['id'],
                "content": res_str
            })
            await self.events.emit(EventType.TOOL_END, {"result": res_str})
            state.status = AgentStatus.RUNNING
            state.pending_tool_call = None
            return True
        else:
            await self.events.emit(EventType.STATE_CHANGE, {
                "msg": f"❌ Rejected: {tool_data['name']}"
            })

            reject_msg = f"User denied permission to execute '{tool_data['name']}'. Reason: {feedback}"
            state.history.append({
                "role": "tool",
                "tool_call_id": tool_data['id'],
                "content": reject_msg
            })
            await self.events.emit(EventType.TOOL_END, {"result": reject_msg})
            state.status = AgentStatus.RUNNING
            state.pending_tool_call = None
            return True
        
    # =========================================================================
    # Main Entry Point
    # =========================================================================
    async def run_task(
        self,
        session_id: str,
        user_input: Optional[str] = None,
        resume: bool = False,
        approval_data: Optional[Dict] = None
    ):
        """
        Main agent execution loop.

        Args:
            session_id: Session identifier
            user_input: Optional user message
            resume: Whether resuming from approval
            approval_data: Approval decision if resuming
        """
        # Load state
        state = self.db.load_state(session_id)
        if not state:
            state = AgentState(session_id=session_id)

        # Auto-generate title for new sessions
        if user_input and state.title == "New Chat":
            clean_input = user_input.replace("\n", " ").strip()
            new_title = clean_input[:20] + ("..." if len(clean_input) > 20 else "")
            state.title = new_title
            self.db.save_state(state)

        # Handle approval resume
        if resume:
            if not await self._process_approval(state, approval_data or {}):
                return
        else:
            if user_input:
                state.status = AgentStatus.RUNNING
                state.history.append({"role": "user", "content": user_input})

            # --- INTENT PHASE ---
            direct_response = await self._handle_intent_phase(user_input, state)
            if direct_response:
                state.history.append({"role": "assistant", "content": direct_response})
                await self.events.emit(EventType.TOKEN, direct_response)
                self.db.save_state(state)
                return # Task complete via Direct/Chain strategy
                
        # Get model config with type-safe access
        model_name = self.config.provider.name
        temperature = self.config.provider.temperature

        # Main loop: Think -> Act -> Loop
        while state.status == AgentStatus.RUNNING:
            await asyncio.sleep(0.01)

            # Build system prompt
            full_sys_prompt = self._build_system_prompt(state)

            # Update history with latest system prompt
            if not state.history:
                state.history.append({"role": "system", "content": full_sys_prompt})
            elif state.history[0]['role'] == 'system':
                state.history[0]['content'] = full_sys_prompt
            else:
                state.history.insert(0, {"role": "system", "content": full_sys_prompt})

            # Get available tools
            tools = self._get_tools_schema(state)

            # LLM inference
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=state.history,
                    tools=tools if tools else None,
                    stream=True,
                    temperature=temperature
                )
            except Exception as e:
                await self.events.emit(EventType.ERROR, f"LLM API Error: {e}")
                logger.error(f"LLM API error: {e}", exc_info=e)
                break

            full_content = ""
            tool_buffer = []

            # Process stream
            async for chunk in response:
                delta = chunk.choices[0].delta

                if delta.content:
                    full_content += delta.content
                    await self.events.emit(EventType.TOKEN, delta.content)

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if len(tool_buffer) <= tc.index:
                            tool_buffer.append({"id": "", "name": "", "args": ""})

                        item = tool_buffer[tc.index]
                        if tc.id:
                            item["id"] += tc.id
                        if tc.function.name:
                            item["name"] += tc.function.name
                        if tc.function.arguments:
                            item["args"] += tc.function.arguments

            # Record assistant response
            if full_content:
                state.history.append({"role": "assistant", "content": full_content})

            # No tools? End of turn
            if not tool_buffer:
                self.db.save_state(state)
                break

            # Add tool calls to history (required by OpenAI format)
            state.history.append({
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": t["id"],
                        "type": "function",
                        "function": {"name": t["name"], "arguments": t["args"]}
                    }
                    for t in tool_buffer
                ]
            })

            # Execute tools
            results_map = await self._execute_tools_concurrent(tool_buffer, state)

            # Check for sensitivity abort
            if state.status == AgentStatus.WAITING_APPROVAL:
                return

            # Record results
            for i, t in enumerate(tool_buffer):
                execution_data = results_map.get(i, {"result": "Skipped", "meta": {}})
                res_str = execution_data["result"]
                meta_data = execution_data.get("meta", {})

                await self.events.emit(EventType.TOOL_END, {
                    "result": res_str,
                    "meta": meta_data
                })

                state.history.append({
                    "role": "tool",
                    "tool_call_id": t["id"],
                    "content": res_str
                })

            # Save state and continue loop
            self.db.save_state(state)

    def shutdown(self):
        """Cleanup resources."""
        if self.db:
            self.db.close()
        logger.info("MicroAgent shutdown complete")
