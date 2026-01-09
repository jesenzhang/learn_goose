"""
MicroAgent Core Module - Main agent execution logic.
Refactored to use BaseLLM abstraction.
"""

import json
import uuid
import asyncio
import logging
import inspect
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

# [NEW] Import Service Abstractions and Models
from ..providers.base import BaseLLM
from ..providers.factory import ProviderFactory
from ..conversation import Message, Role, TextContent, ToolRequest, ToolResponse, CallToolResult, RawContent

# Core Imports
from .events import EventManager, EventType
from .state import AgentState, AgentStatus
from ..db import get_db,DatabaseManager
from ..config.loader import ConfigLoader
from ..skills import SkillLoader
from ..skills.context import create_context,ServiceContext

from .executor import ToolExecutor

# Intent Imports
from ..intent.recognizer import IntentRecognizer
from ..intent.strategy import IntentExecutor, ExecutionMode, TerminationAction
from ..intent.config_loader import IntentConfigLoader
AgentContext = ServiceContext[AgentState, DatabaseManager]

logger = logging.getLogger(__name__)

# --- Core Tools ---
def update_plan(steps: List[str], _ctx=None) -> str:
    return f"PLAN_UPDATED:{json.dumps(steps)}"

def submit_intent(slots: Dict, _ctx=None) -> str:
    return "SUBMITTED"

class MicroAgent:
    """
    Core Agent using BaseLLM abstraction.
    """

    def __init__(
        self,
        config: ConfigLoader,
        skill_loader: Optional[SkillLoader] = None
    ):
        self.config = config
        self.events = EventManager()
        self.skill_loader = skill_loader
        self.db = get_db()

        # [CHANGED] Initialize Services via Factory
        # MicroAgent now holds a generic BaseLLM, not AsyncOpenAI
        if self.config.provider.llm:
            self.llm: BaseLLM = ProviderFactory.create_llm(self.config.provider.llm.provider, self.config.provider.llm.config)
        
        self.ai_services = {}
        if self.config.provider.embedding:
            self.ai_services["embedding"] = ProviderFactory.create_embedding(self.config.provider.embedding.provider, self.config.provider.embedding.config)

        if self.config.provider.reranker:
            self.ai_services["reranker"] = ProviderFactory.create_reranker(self.config.provider.reranker.provider, self.config.provider.reranker.config)
            
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
        definitions = self.config.get_intent_definitions()
        
        if definitions:
            # [CHANGED] Pass abstract LLM to Recognizer
            self.intent_recognizer = IntentRecognizer(
                intents=definitions,
                llm=self.llm 
            )
            self.intent_executor = IntentExecutor(
                skill_loader=self.skill_loader,
                ai_services=self.ai_services
            )
           
            loader = IntentConfigLoader()
            loader.load_from_config(self.config.raw_data, self.intent_executor)
            logger.info(f"Intent system active: {len(definitions)} intents loaded.")

    # =========================================================================
    # Phase 1: Intent Processing (Unchanged logic, just context)
    # =========================================================================

    async def _handle_intent_phase(self, user_input: str, state: AgentState) -> Optional[str]:
        if not self.intent_recognizer:
            return None

        await self.events.emit(EventType.STATE_CHANGE, {"msg": "🤔 Analyzing intent..."})
        
        # Note: IntentRecognizer.recognize now accepts intent_session dict
        results, updated_session = await self.intent_recognizer.recognize(
            user_input=user_input,
            session_state=state.intent_session,
            background_info=f"Active Skill: {state.active_skill}"
        )
        
        state.intent_session = updated_session
        self.db.save_state(state)

        if not results.intents: return None

        primary_name = results.primary_intent or results.intents[0].intent
        primary = results.get_intent(primary_name)
        
        if not primary: return None

        if primary.is_incomplete and primary.reply_to_user:
            return primary.reply_to_user

        if not primary.is_ready: return None

        logger.info(f"Intent Triggered: {primary.intent}")
        await self.events.emit(EventType.STATE_CHANGE, {
            "msg": f"🎯 Intent: {primary.intent}", 
            "slots": primary.entities
        })

        for k, v in primary.entities.items():
            state.shared_memory[k] = v

        config = self.intent_executor.get_config(primary.intent)
        if not config: return None

        ctx = create_context(state.session_id, state=state, db=self.db, ai_services=self.ai_services)
        pre_res = await self.intent_executor.execute_pre_hook(primary.intent, primary.entities, ctx)
        if pre_res: return pre_res

        final_res = None
        should_stop = False

        if config.mode == ExecutionMode.DIRECT:
            res = await self.intent_executor.execute_direct(primary.intent, primary.entities, ctx)
            final_res = str(res)
            should_stop = True
        elif config.mode == ExecutionMode.CHAIN:
            res = await self.intent_executor.execute_chain(primary.intent, primary.entities, ctx)
            final_res = str(res)
            should_stop = True
        elif config.mode == ExecutionMode.SKILL:
            state.active_skill = config.skill_name
            state.shared_memory.update(config.skill_params)
            # [新增] 尝试构建初始指令
            template = config.skill_params.get("_instruction_template")
            if template:
                try:
                    # 1. 获取意图定义 (为了拿到 slots 的默认值)
                    intent_def = None
                    if self.intent_recognizer:
                        intent_def = self.intent_recognizer._intent_map.get(primary.intent)
                    # 2. 构建完整的参数字典
                    render_params = {}
                    # A. 先填入默认值
                    if intent_def:
                        for slot in intent_def.slots:
                            # 如果有默认值用默认值，没有则填 "未指定" 或空字符串，防止报错
                            val = slot.default
                            if val is None:
                                val = "无" # 或者 ""
                            render_params[slot.name] = val
                    # B. 用实际提取到的实体覆盖默认值
                    render_params.update(primary.entities)
                    
                    # 3. 渲染模板
                    instruction = template.format(**render_params)
                    state.history.append({
                        "role": "system", 
                        "content": f"[Intent Action] Context switched to {config.skill_name}. Execution Instruction:\n{instruction}"
                    })
                    logger.info(f"Generated Intent Instruction: {instruction}")
                    
                except Exception as e:
                    logger.warning(f"Failed to render instruction template: {e}")
                    
            await self.events.emit(EventType.STATE_CHANGE, {"msg": f"🔄 Switching to {config.skill_name}"})
            should_stop = False
            
        elif config.mode == ExecutionMode.LLM:
            allowed = self.intent_executor.get_allowed_tools(
                primary.intent,
                self.skill_loader.get_available_skills_list() if self.skill_loader else []
            )
            state.shared_memory["_restricted_tools"] = allowed
            should_stop = False

        if config.on_complete == TerminationAction.STOP:
            return final_res
        
        return final_res if should_stop else None

    # =========================================================================
    # Phase 2: Tool Execution (Unchanged)
    # =========================================================================
    
    async def _exec_tool_func(self, tool_name: str, tool_args: Dict, state: AgentState) -> str:
        func = self.core_tools.get(tool_name)
        if not func and self.skill_loader:
            func = self.skill_loader.get_tool_func(tool_name)
        
        if not func: return f"Error: Tool '{tool_name}' not found."

        # 2. 实例化执行器
        # 这里注入了当前会话的所有上下文资源
        executor = ToolExecutor(
            session_id=state.session_id,
            state=state,
            db=self.db,
            ai_services=self.ai_services, # 现在这是一个 AIServices 对象
            # 如果有额外服务，可以在这里传入
            # extra_services={"config": self.config} 
        )
        
        try:
            # 3. 执行
            result = await executor.execute(func, tool_args)
        
            if isinstance(result, CallToolResult):
                return await self._format_and_emit_tool_result(result, state, tool_name)
            
            return str(result) if result is not None else ""
        
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=e)
            return f"Error executing tool '{tool_name}': {str(e)}"

    async def _format_and_emit_tool_result(self, result: CallToolResult, state: AgentState, tool_name: str) -> str:
        """
        处理复杂返回值，触发 TOOL_ARTIFACT 事件。
        """
        parts = []
        for c in result.content:
            # 如果包含结构化数据 (Artifact)
            if c.data is not None:
                # 1. 生成唯一的 Artifact ID
                aid = f"art_{uuid.uuid4().hex[:8]}"
                
                # 2. 存入 Shared Memory (持久化，防止刷新丢失)
                # 前端可以通过 art_id 重新获取数据
                artifact_payload = {
                    "id": aid,
                    "type": c.type or "data", # e.g., 'chart', 'table', 'json'
                    "data": c.data,
                    "text": c.text # 可选的 Markdown 视图建议
                }
                state.shared_memory[aid] = artifact_payload
                
                # 3. 触发 Artifact 事件 (前端收到后立即渲染图表/表格)
                await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                
                # 4. 返回给 LLM 的只是一个引用，防止 Token 爆炸
                parts.append(f"{c.text or 'Generated Data'}\n[Artifact ID: {aid}]")
            else:
                # 纯文本部分
                parts.append(c.text or "")
        
        return "\n\n".join(parts)
    
    # =========================================================================
    # Phase 3: Prompt & Loop (REFACTORED for BaseLLM)
    # =========================================================================

    def _get_tools_schema(self, state: AgentState) -> List[Dict]:
        schemas = [{"type": "function", "function": {"name": "update_plan", "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "string"}}}, "required": ["steps"]}}}]
        if not self.skill_loader: return schemas
        restrict = state.shared_memory.get("_restricted_tools")
        all_tools = self.skill_loader.get_all_tools_schema(state.active_skill)
        if restrict:
            schemas.extend([t for t in all_tools if t['function']['name'] in restrict])
        else:
            schemas.extend(all_tools)
        return schemas
        
    def _needs_complex_protocol(self, state: AgentState) -> bool:
        if state.current_plan: return True
        if state.status == AgentStatus.WAITING_APPROVAL: return True
        if state.shared_memory.get("_restricted_tools"): return True
        return False

    def _build_system_prompt(self, state: AgentState) -> str:
        prompt = self.config.agent.system_template.format(name=self.config.agent.name)
        if self._needs_complex_protocol(state):
            prompt += "\n=== RULES ===\n1. Parallel tools allowed.\n2. Wait for dependencies.\n3. Safe memory RW.\n"
        if self.skill_loader:
            prompt += self.skill_loader.get_context_prompt(state.active_skill)
        now = datetime.now().strftime("%H:%M")
        prompt += f"\n=== STATUS ===\nTime: {now}\nContext: {state.active_skill or 'Global'}\n"
        if state.shared_memory:
            view = []
            for k, v in state.shared_memory.items():
                if k.startswith("_"): continue
                s = str(v)
                if k.startswith("art_") or len(s) > 100: view.append(f"- {k}: <Data>")
                else: view.append(f"- {k}: {s}")
            if view: prompt += "Memory:\n" + "\n".join(view)
        if state.current_plan: prompt += f"\nPlan: {json.dumps(state.current_plan)}"
        return prompt

    async def _execute_tools_concurrent(self, tool_requests: List[ToolRequest], state: AgentState) -> Dict:
        """
        [CHANGED] Input is now a list of fully formed ToolRequest objects from BaseLLM
        """
        tasks = []
        # 定义一个闭包 wrapper 来处理单个工具的完整生命周期
        async def _exec_wrapper(index: int, req: ToolRequest):
            call_param = req.tool_call.value
            name = call_param.name
            args = call_param.arguments or {}
            
            # 1. 触发工具开始事件 (前端可显示 "Running tool X...")
            await self.events.emit(EventType.TOOL_START, {"name": name, "args": args})
            
            start_time = time.time()
            result_str = ""
            is_error = False
            
            # 2. 执行工具逻辑
            try:
                # 调用核心执行逻辑
                result_str = await self._exec_tool_func(name, args, state)
            except Exception as e:
                is_error = True
                result_str = f"Error: {str(e)}"
                logger.error(f"Tool execution failed: {e}", exc_info=True)
            
            # 计算耗时
            duration = f"{time.time() - start_time:.2f}s"
            
            # 3. 触发工具结束事件 (前端可显示结果摘要、耗时)
            # result 字段包含文本结果，meta 包含元数据
            await self.events.emit(EventType.TOOL_END, {
                "name": name,
                "result": result_str, # 如果是 Artifact，这里可能是摘要
                "meta": {
                    "tool": name,
                    "duration": duration,
                    "start_time": datetime.fromtimestamp(start_time).strftime("%H:%M:%S"),
                    "status": "error" if is_error else "success"
                }
            })
            
            return index, {"result": result_str}
        
        for i, req in enumerate(tool_requests):
            # req is a ToolRequest(id=..., tool_call=ToolCall(...))
            if req.tool_call.is_error():
                logger.error(f"Skipping malformed tool call: {req.tool_call.error}")
                continue
                
            call_param = req.tool_call.value
            name = call_param.name
            args = call_param.arguments or {}
            call_id = req.id

            # Sensitivity Check
            is_sens = self.config.is_sensitive(name)
            if self.skill_loader: is_sens |= self.skill_loader.is_sensitive(name)
            
            if is_sens:
                state.status = AgentStatus.WAITING_APPROVAL
                state.pending_tool_call = {"name": name, "args": args, "id": call_id}
                self.db.save_state(state)
                await self.events.emit(EventType.APPROVAL_REQ, {"tool": name, "args": args})
                return {} # Halt

            # 添加包装后的任务
            tasks.append(_exec_wrapper(i, req))

        if not tasks: return {}
        
        # 并发执行所有 wrapper
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 组装返回结果 map
        results_map = {}
        for res in results:
            if isinstance(res, tuple):
                idx, val = res
                results_map[idx] = val
            elif isinstance(res, Exception):
                logger.error(f"Concurrent execution error: {res}")
                
        return results_map
    

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    async def run_task(self, session_id: str, user_input: str = None, resume: bool = False, approval_data: Dict = None):
        state = self.db.load_state(session_id) or AgentState(session_id=session_id)

        if resume:
            if state.status == AgentStatus.WAITING_APPROVAL:
                if not await self._process_approval(state, approval_data or {}): return
        else:
            if user_input:
                state.status = AgentStatus.RUNNING
                state.history.append({"role": "user", "content": user_input})
                
                # Intent Phase
                direct_res = await self._handle_intent_phase(user_input, state)
                if direct_res:
                    state.history.append({"role": "assistant", "content": direct_res})
                    await self.events.emit(EventType.TOKEN, direct_res)
                    self.db.save_state(state)
                    return

        while state.status == AgentStatus.RUNNING:
            await asyncio.sleep(0.01)
            
            # 1. Build Prompt & Sync History
            # ==============================
            prompt = self._build_system_prompt(state)
            
            # Ensure system prompt is always at the top
            if not state.history: 
                state.history.append({"role": "system", "content": prompt})
            elif state.history[0]['role'] == 'system': 
                state.history[0]['content'] = prompt
            else: 
                state.history.insert(0, {"role": "system", "content": prompt})

            # 2. Convert State History (Dict) to Messages (Pydantic)
            # ======================================================
            # This is crucial because BaseLLM expects Message objects
            input_messages = [Message.model_validate(h) for h in state.history]
            
            tools = self._get_tools_schema(state)

            # 3. Call BaseLLM
            # ===============
            full_content_text = ""
            received_tool_requests: List[ToolRequest] = []
            
            try:
                # Use astream instead of OpenAI specific create
                async for partial_msg, usage in self.llm.astream(
                    messages=input_messages,
                    tools=tools or None
                ):
                    if partial_msg:
                        # Handle Text Stream
                        if partial_msg.content:
                            for c in partial_msg.content:
                                if isinstance(c, TextContent):
                                    full_content_text += c.text
                                    await self.events.emit(EventType.TOKEN, c.text)
                                # Handle Tool Requests (Provider aggregates them)
                                elif isinstance(c, ToolRequest):
                                    received_tool_requests.append(c)
                                    
            except Exception as e:
                logger.error(f"LLM Error: {e}")
                await self.events.emit(EventType.ERROR, str(e))
                break

            # 4. Update History (Assistant Response)
            # ======================================
            assistant_content = []
            if full_content_text:
                assistant_content.append(TextContent(text=full_content_text))
            
            if received_tool_requests:
                assistant_content.extend(received_tool_requests)
                
            # Create the finalized assistant message and dump to dict for DB
            assistant_msg = Message(role=Role.ASSISTANT, content=assistant_content)
            # Use by_alias=True to preserve camelCase aliases for proper deserialization
            state.history.append(assistant_msg.model_dump(exclude_none=True, by_alias=True))

            # 5. Handle Tools or Stop
            # =======================
            if not received_tool_requests:
                self.db.save_state(state)
                break # Turn complete

            # Execute Tools
            results_map = await self._execute_tools_concurrent(received_tool_requests, state)
            
            if state.status == AgentStatus.WAITING_APPROVAL: 
                return # Pause execution

            # 6. Append Tool Results to History
            # =================================
            for i, req in enumerate(received_tool_requests):
                # result string from execution map
                res_str = results_map.get(i, {}).get("result", "Error")
                
                # Construct Tool Response Message using Goose models
                # Note: OpenAIProvider._prepare_messages will separate this into the correct format
                tool_msg = Message.tool(text=res_str, tool_call_id=req.id)
                state.history.append(tool_msg.model_dump(exclude_none=True, by_alias=True))
            
            self.db.save_state(state)

    async def _process_approval(self, state: AgentState, data: Dict) -> bool:
        if state.status != AgentStatus.WAITING_APPROVAL or not state.pending_tool_call: return False
        tool = state.pending_tool_call
        if data.get("approved"):
            res = await self._exec_tool_func(tool['name'], tool['args'], state)
            # Add Tool Response
            state.history.append(Message.tool(text=res, tool_call_id=tool['id']).model_dump(exclude_none=True, by_alias=True))
        else:
            state.history.append(Message.tool(text=f"Rejected: {data.get('feedback')}", tool_call_id=tool['id']).model_dump(exclude_none=True, by_alias=True))

        state.status = AgentStatus.RUNNING
        state.pending_tool_call = None
        return True

    def shutdown(self):
        if self.db: self.db.close()