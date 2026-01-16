"""
MicroAgent Core Module - Main agent execution logic.
Refactored to use BaseLLM abstraction and Generation-based Hot Reloading.
"""

from email import message
import json
import uuid
import asyncio
import logging
import inspect
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

from pydantic import BaseModel

# [NEW] Import Service Abstractions and Models
from ..providers.base import BaseLLM
from ..providers.factory import ProviderFactory
from ..conversation import (Message, Role, TextContent,
                            ToolRequest, ToolResponse, CallToolResult, RawContent,
                            ThinkingContent, RedactedThinkingContent)

# Core Imports
from .events import EventManager, EventType
from .state import AgentState, AgentStatus
from ..db import get_db, DatabaseManager
from ..config.loader import ConfigLoader
from ..skills import SkillLoader
from ..skills.context import create_context, ServiceContext

from .executor import ToolExecutor
# Artifact Storage Import
from .artifact_storage import init_manager, get_manager

    # 需要引入的依赖 (放在文件头部)
from ..intent.models import IntentResult
from ..intent.recognizer import IntentRecognizer
from ..intent.strategy import IntentExecutor, ExecutionMode, TerminationAction 
from ..intent.config_loader import IntentConfigLoader
from .watcher import ConfigWatcher
from .generation import AgentGeneration
from .context import RequestContext
from .hooks import HookManager, AgentHook, HookContext, HookAction
# [NEW] 导入 contextvars 用于获取中间件注入的 token
from ..utils.ctx_vars import get_auth_token
AgentContext = ServiceContext[AgentState, DatabaseManager]

logger = logging.getLogger(__name__)

# --- Core Tools ---
def update_plan(steps: List[str], _ctx=None) -> str:
    return f"PLAN_UPDATED:{json.dumps(steps)}"

def submit_intent(slots: Dict, _ctx=None) -> str:
    return "SUBMITTED"

class MicroAgent:
    """
    Core Agent using BaseLLM abstraction and Generation-based Hot Reloading.
    """

    def __init__(
        self,
        config_path: str
    ):
        self.config_path = config_path
        self.events = EventManager()
        self.db = get_db()

        # 当前活跃的"一代"
        self.current_generation: Optional[AgentGeneration] = None

        # Initialize Artifact Manager
        self.artifact_manager = init_manager(config_path=self.config_path)

        # 状态保存管理器 - 延迟批量保存
        self._pending_state_save = False
        self._state_save_task: Optional[asyncio.Task] = None
        self._pending_save_state: Optional[AgentState] = None  # 待保存的 state 引用

        # 1. 初始构建
        initial_config = ConfigLoader(config_path)
        first_gen = self._build_generation(initial_config)
        self.current_generation = first_gen

        # 启动监听
        self.watcher = ConfigWatcher(config_path, self.reload_config)
        self.watcher.start()

        # 初始化 Hook Manager 并加载配置的 Hooks
        self.hook_manager = HookManager()
        self._init_hooks(initial_config)

        logger.info("MicroAgent initialized")

    async def _flush_state_save(self, session_id: int):
        """立即执行待保存的状态"""
        if self._pending_state_save and self._pending_save_state:
            try:
                await self.db.save_state(session_id, self._pending_save_state.model_dump(exclude_none=True))
                self._pending_state_save = False
                self._pending_save_state = None
            except Exception as e:
                logger.error(f"Failed to flush state save: {e}", exc_info=True)

    def _schedule_state_save(self, session_id: int, state: AgentState, delay: float = 0.5):
        """
        调度状态保存，延迟执行以减少数据库写入次数

        Args:
            session_id: 会话 ID
            state: 要保存的 AgentState 对象
            delay: 延迟时间（秒），默认 0.5 秒
        """
        self._pending_state_save = True
        self._pending_save_state = state

        # 取消之前的任务（如果存在）
        if self._state_save_task and not self._state_save_task.done():
            self._state_save_task.cancel()

        # 创建新的延迟保存任务
        async def save_delayed():
            await asyncio.sleep(delay)
            await self._flush_state_save(session_id)

        self._state_save_task = asyncio.create_task(save_delayed())

    async def _ensure_state_saved(self, session_id: int, state: AgentState):
        """确保所有待保存的状态都已保存"""
        # 先保存当前 state
        self._pending_state_save = True
        self._pending_save_state = state
        await self._flush_state_save(session_id)

    def _build_generation(self, config: ConfigLoader) -> AgentGeneration:
        """构建新一代资源"""
        logger.debug("Building agent components...")
        # 提取 SkillsConfig (它是 Pydantic 对象)
        skills_cfg = config.skills_config
        skill_loader = SkillLoader(
            skills_dir="agent_skills",
            skills_config=skills_cfg, # 传入完整配置对象
            global_sensitive_tools=set(config.security.sensitive_tools)
        )
        logger.info("Skill loader initialized")
        
        # 1. LLM
        llm = None
        if config.provider.llm:
            llm = ProviderFactory.create_llm(
                config.provider.llm.provider, 
                config.provider.llm.config
            )
            
        # 2. AI Services
        ai_services = {}
        if config.provider.embedding:
            ai_services["embedding"] = ProviderFactory.create_embedding(
                config.provider.embedding.provider, 
                config.provider.embedding.config
            )
        if config.provider.reranker:
            ai_services["reranker"] = ProviderFactory.create_reranker(
                config.provider.reranker.provider, 
                config.provider.reranker.config
            )
            
        # 3. Intent System
        intent_recognizer = None
        intent_executor = None
        definitions = config.get_intent_definitions()
        
        if definitions:
            # 注入新的 LLM
            intent_recognizer = IntentRecognizer(intents=definitions, llm=llm)
            intent_executor = IntentExecutor(skill_loader=skill_loader, ai_services=ai_services)
            
            # 加载 Intent Execution Config
            loader = IntentConfigLoader()
            loader.load_from_config(config.raw_data, intent_executor)

        # 4. Core Tools (如果工具逻辑依赖配置，也在这里重新生成)
        core_tools = {
            "submit_intent": submit_intent,
            "update_plan": update_plan,
        }
        
        return AgentGeneration(
            version=uuid.uuid4().hex[:8],
            config=config,
            llm=llm,
            ai_services=ai_services,
            intent_recognizer=intent_recognizer,
            intent_executor=intent_executor,
            core_tools=core_tools,
            skill_loader=skill_loader # 传递 skill_loader
        )
    
    async def reload_config(self):
        """热重载"""
        logger.info("♻️ Reloading...")
        try:
            # 1. 准备新一代 (耗时)
            new_config = ConfigLoader(self.config_path)
            new_gen = self._build_generation(new_config)
            
            # 2. 原子切换
            # 捕获旧的一代
            old_gen = self.current_generation
            # 替换为新一代 (后续 run_task 将使用 new_gen)
            self.current_generation = new_gen
            
            # 3. 优雅退役旧一代 (后台任务)
            if old_gen:
                # 关键：这里不再 sleep(60)，而是等待真正的 drain
                asyncio.create_task(old_gen.drain_and_close())
                
            logger.info(f"✅ Swapped to generation {new_gen.version}")
            await self.events.emit(EventType.STATE_CHANGE, {"msg": "⚙️ Configuration reloaded"})
            
        except Exception as e:
            logger.error(f"Reload failed: {e}")
    

    async def add_message(self, session_id: int, msg: Message, state: Optional[AgentState] = None):
        state.history.append(msg.model_dump(exclude_none=True, by_alias=True))
        await self.db.add_message(session_id, msg.role, msg.content_json, msg.metadata)

    async def _emit_event_with_persistence(self, event_type: EventType, data: Any, session_id: int):
        """
        发送事件并持久化到数据库

        Args:
            event_type: 事件类型
            data: 事件数据
            session_id: 会话 ID，用于持久化
        """
        # 发送事件到监听器
        await self.events.emit(event_type, data)

        # 持久化事件到数据库（异步，不阻塞主流程）
        try:
            from .events import Event
            event = Event(type=event_type, data=data)
            await self.db.save_event(session_id, event.model_dump())
        except Exception as e:
            # 持久化失败不影响主流程，只记录日志
            logger.warning(f"Failed to persist event {event_type.value}: {e}")
            # 注意：save_event 现在会抛出异常，但这里是在异步任务中捕获
            # 如果需要发送错误事件，可以在上层统一处理

    # =========================================================================
    # Phase 1: Intent Processing (Unchanged logic, just context)
    # =========================================================================

    # core/agent.py

    
    async def _handle_intent_phase(self, user_input: str, state: AgentState, gen: AgentGeneration) -> Optional[str]:
        """
        [Hybrid Planning Engine]
        处理意图识别与执行规划。
        
        流程：
        1. 检查队列：如果队列为空，调用 Recognizer 生成多步计划 (Plan)。
        2. 调度任务：从队列头部取出一个意图 (Pop)。
        3. 分发执行：
           - Case A (Ad-hoc): 内置通用任务 -> 构造 System Prompt -> 交给 LLM 生成。
           - Case B (Configured): YAML 定义任务 -> 调用 Skill/Tool -> 获取结果。
        """
        
        # =========================================================================
        # Phase 1: 规划 (Planning)
        # 如果当前没有待执行的任务，则分析用户输入生成新计划
        # =========================================================================
        if not state.intent_queue:
            # 如果没有识别器，直接跳过 (回退到通用聊天)
            if not gen.intent_recognizer:
                return None

            await self.events.emit(EventType.STATE_CHANGE, {"msg": "🤔 Analyzing & Planning..."})
            
            # 1.1 调用识别器 (Recognizer now acts as a Planner)
            results, updated_session = await gen.intent_recognizer.recognize(
                user_input=user_input,
                session_state=state.intent_session,
                background_info=f"Active Skill: {state.active_skill}"
            )
            state.intent_session = updated_session

            # 1.2 如果生成了计划，压入队列
            if results.intents:
                # 将 Pydantic 对象转为 Dict 存入队列
                state.intent_queue = [i.model_dump() for i in results.intents]
                
                # 记录日志与事件
                plan_desc = [f"{i.intent}" for i in results.intents]
                logger.info(f"📋 Plan generated: {plan_desc}")
                
                await self.events.emit(EventType.STATE_CHANGE, {
                    "msg": "📋 Plan Formulated", 
                    "plan": plan_desc
                })
                
                # 立即保存状态，防止崩溃丢失计划
                await self.db.save_state(state.session_id, state.model_dump())

        # =========================================================================
        # Phase 2: 调度 (Scheduling)
        # =========================================================================
        
        # 如果队列依然为空，说明识别器认为这是 General Chat (无特定意图)
        if not state.intent_queue:
            return None

        # --- 从队列头部取出下一个任务 ---
        current_intent_data = state.intent_queue.pop(0)
        
        # 还原为 IntentResult 对象以便操作
        primary = IntentResult(**current_intent_data)

        logger.info(f"▶️ Executing Plan Step: {primary.intent}")
        await self.events.emit(EventType.STATE_CHANGE, {
            "msg": f"🚀 Executing: {primary.intent}",
            "slots": primary.entities
        })

        # 2.1 检查参数完整性 (Slot Filling Check)
        if primary.is_incomplete and primary.reply_to_user:
            # 如果缺少必要参数，且有追问语句 -> 清空队列(中断计划) -> 直接返回追问
            logger.info(f"Intent {primary.intent} incomplete. Asking user.")
            state.intent_queue = [] 
            return primary.reply_to_user

        # 2.2 上下文注入 (Context Injection)
        # 将提取到的实体写入 Shared Memory，供 Tool 使用
        for k, v in primary.entities.items():
            state.shared_memory[k] = v

        # =========================================================================
        # Phase 3: 执行 (Execution)
        # =========================================================================

        # --- Branch A: 处理内置意图 (System Native Capabilities) ---
        # 对应 "自主执行" / "Ad-hoc" 任务 (写作、总结、分析)
        if primary.intent == "adhoc_execution":
            instruction = primary.entities.get("instruction", "")
            context_source = primary.entities.get("context_source", "conversation_history")
            
            # 构造一条 System Instruction 插入历史记录
            # 作用：在下一轮 Loop 中，LLM 会看到这条指令 + 之前的 Tool 结果，从而进行生成
            system_instruction = f"""
[SYSTEM INSTRUCTION: AD-HOC TASK]
The user's plan requires you to perform the following task.

**Context Source**: {context_source} (Review previous messages/tool outputs).

**Resource Usage Guide**:
1. **Artifacts (IDs starting with 'art_')**: These are currently stored in your `shared_memory`.
   - To read them: Use the `read_from_clipboard` tool.
   - Do NOT pass 'art_' IDs to external search tools like `lookup_doc_content`.
2. **Real Documents**: If you need full document content, find the real `file_id` inside the Artifact first, then use `lookup_doc_content`.


**TASK**: "{instruction}"

**ACTION REQUIRED**:
Execute this task immediately. Do not ask for clarification unless impossible.
Generate the content/response now.
"""
            # 存入 History
            state.history.append(Message.system(system_instruction).model_dump(by_alias=True))
            
            # 【关键】返回 None
            # 这意味着不直接返回结果给用户，而是让 Agent 继续运行，进入 "Phase 3: LLM Loop"
            return None 

        # --- Branch B: 处理配置意图 (Configured Intents) ---
        # 对应 YAML 中定义的 search/view 任务
        config = gen.intent_executor.get_config(primary.intent)
        
        # 如果配置丢失 (鲁棒性处理)
        if not config: 
            logger.warning(f"⚠️ Intent '{primary.intent}' has no config. Fallback to adhoc.")
            fallback_msg = f"[SYSTEM] Intent '{primary.intent}' triggered but no tool config found. Handle: {user_input}"
            state.history.append(Message.system(fallback_msg).model_dump(by_alias=True))
            return None

        # 准备执行上下文
        ctx = create_context(state.session_id, state=state, db=self.db, ai_services=gen.ai_services)
        
        # 3.1 执行 Pre-hook (前置拦截)
        pre_res = await gen.intent_executor.execute_pre_hook(primary.intent, primary.entities, ctx)
        if pre_res: return pre_res

        final_res = None
        should_stop = False

        # 3.2 根据模式执行策略
        if config.mode == ExecutionMode.DIRECT:
            # 直接调用函数，不经过 LLM
            res = await gen.intent_executor.execute_direct(primary.intent, primary.entities, ctx)
            final_res = str(res)
            should_stop = True 
            
        elif config.mode == ExecutionMode.SKILL:
            # 切换技能模式
            state.active_skill = config.skill_name
            state.shared_memory.update(config.skill_params)
            
            # [关键修复] 模板渲染逻辑增强：自动填充默认值
            template = config.skill_params.get("_instruction_template")
            if template:
                try:
                    # 1. 准备渲染参数，先放入 Skill 的静态参数
                    render_params = config.skill_params.copy()
                    
                    # 2. 获取意图定义，填充 Slot 默认值 (Crucial Fix!)
                    if gen.intent_recognizer:
                        intent_def = gen.intent_recognizer._intent_map.get(primary.intent)
                        if intent_def:
                            for slot in intent_def.slots:
                                # 如果 entities 里没有这个值，尝试使用 default
                                if slot.name not in primary.entities:
                                    default_val = slot.default
                                    # 处理 default 为 None 的情况，转为空字符串防止 KeyError
                                    if default_val is None:
                                        default_val = "无" if slot.data_type == str else []
                                    render_params[slot.name] = default_val

                    # 3. 用实际提取到的实体覆盖默认值
                    render_params.update(primary.entities)
                    
                    # 4. 渲染模板
                    instruction = template.format(**render_params)
                    
                    # 5. 注入历史记录
                    state.history.append(Message.system(instruction).model_dump(by_alias=True))
                    logger.info(f"✅ Injected Skill Instruction for {primary.intent}")
                    
                except Exception as e:
                    logger.error(f"❌ Template render failed for {primary.intent}: {e}")
                    # 兜底：如果模板渲染挂了，至少发一个通用指令，防止 LLM 发呆
                    fallback = f"[SYSTEM] User intent: {primary.intent}. Entities: {primary.entities}. Please use appropriate tools."
                    state.history.append(Message.system(fallback).model_dump(by_alias=True))
            
            should_stop = False # Skill 模式进入 LLM Loop

        elif config.mode == ExecutionMode.LLM:
            # 仅限制工具，不做其他操作
            allowed = gen.intent_executor.get_allowed_tools(
                primary.intent, 
                gen.skill_loader.get_available_skills_list() if gen.skill_loader else []
            )
            state.shared_memory["_restricted_tools"] = allowed
            should_stop = False

        # 3.3 处理终止逻辑 (Termination)
        if config.on_complete == TerminationAction.STOP:
            # 如果队列里还有后续任务 (例如：Search -> [Write])
            # 我们不能直接 return final_res (这会结束整个 run_task)
            # 而是应该把结果存入 History，然后 return None 继续循环
            if state.intent_queue:
                # 模拟一个 Tool Output 存入历史，供下一步使用
                logger.info(f"Step {primary.intent} finished via STOP. Saving context for next step.")
                state.history.append(
                    Message.tool(text=final_res, tool_call_id=f"intent_{primary.intent}").model_dump(by_alias=True)
                )
                return None 
            
            return final_res
        
        return final_res if should_stop else None

    # =========================================================================
    # Phase 2: Tool Execution (Unchanged)
    # =========================================================================
    
    # =========================================================================
    # 工具执行相关方法 - 职责清晰化重构
    # =========================================================================

    async def _exec_tool_func(self, tool_name: str, tool_args: Dict, state: AgentState, gen: AgentGeneration, req_ctx: RequestContext) -> Any:
        """
        执行单个工具函数

        Args:
            tool_name: 工具名称
            tool_args: 工具参数
            state: Agent 状态
            gen: 当前 Generation 对象
            req_ctx: 请求上下文

        Returns:
            工具执行结果（可能是 str, CallToolResult, 或其他类型）
        """
        # 使用 gen.core_tools 和 gen.skill_loader
        func = gen.core_tools.get(tool_name)
        if not func and gen.skill_loader:
            func = gen.skill_loader.get_tool_func(tool_name)

        if not func:
            return f"Error: Tool '{tool_name}' not found."

        # 实例化执行器
        executor = ToolExecutor(
            session_id=state.session_id,
            state=state,
            db=self.db,
            ai_services=gen.ai_services,
            request_context=req_ctx
        )

        try:
            result = await executor.execute(func, tool_args)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=e)
            return f"Error executing tool '{tool_name}': {str(e)}"

    def _extract_artifacts_from_result(self, result: CallToolResult, tool_name: str) -> List[RawContent]:
        """
        从 CallToolResult 中提取 artifact 信息

        职责：仅提取 artifact 元数据，不涉及存储或事件发送

        Args:
            result: 工具执行结果
            tool_name: 工具名称

        Returns:
            artifact 信息列表，每个 artifact 包含: id, type, text, data, tool_name
        """
        artifacts = []

        for c in result.content:
            if c.data is not None:
                c.id = c.id or f"art_{uuid.uuid4().hex[:8]}"
                c.title = c.title or f"Artifact from {tool_name}"
                c.metadata = c.metadata or {}
                c.metadata["tool_name"] = tool_name
                artifacts.append(c)

        if len(artifacts) > 1:
            logger.warning(f"Multiple artifacts ({len(artifacts)}) in single CallToolResult from tool '{tool_name}'")

        return artifacts

    async def _store_artifacts_to_manager(self, artifacts: List[RawContent], state: AgentState) -> None:
        """
        将 artifact 存储到 ArtifactManager

        职责：仅负责存储 artifact 到管理器，更新 shared_memory

        Args:
            artifacts: artifact 信息列表
            state: Agent 状态
        """
        artifact_mgr = get_manager()
        if not artifact_mgr or not artifact_mgr.config.enabled:
            return

        for artifact in artifacts:
            try:
                ref = await artifact_mgr.store(
                    session_id=state.session_id,
                    artifact_id=artifact.id or f"art_{uuid.uuid4().hex[:8]}",
                    artifact_type=artifact.type,
                    data=artifact.data,
                    text=artifact.text,
                    metadata = {
                        "mime_type": artifact.mime_type,
                        **(artifact.metadata or {})
                    }
                )
                state.shared_memory[artifact.id] = ref.to_dict()
                artifact.metadata.update({
                    "size": ref.size,
                    "storage_type": ref.storage_type.value,
                })
            except Exception as e:
                logger.error(f"Failed to store artifact {artifact.id}: {e}", exc_info=True)

    def _format_tool_result_for_llm(self, result: CallToolResult) -> str:
        """
        格式化工具结果为 LLM 可读的文本

        职责：仅生成文本摘要，不涉及 artifact 处理或事件发送

        Args:
            result: 工具执行结果

        Returns:
            返回给 LLM 的文本摘要
        """
        parts = []

        for c in result.content:
            if c.data is None:
                # 纯文本部分直接返回
                parts.append(c.text or "")
            else:
                # Artifact 类型：只返回文本引用，完整数据由 TOOL_END 事件传递
                aid = c.id or f"art_{uuid.uuid4().hex[:8]}"
                parts.append(f"{c.text or 'Generated Data'}\n[Artifact ID: {aid}]")

        return "\n\n".join(parts)

    # =========================================================================
    # =========================================================================
    # Phase 3: Prompt & Loop (REFACTORED for BaseLLM)
    # =========================================================================

    def _get_tools_schema(self, state: AgentState, gen: AgentGeneration) -> List[Dict]:
        # 原始 schemas
        schemas = [{"type": "function", "function": {"name": "update_plan", "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "string"}}}, "required": ["steps"]}}}]
        if not gen.skill_loader: return schemas
        restrict = state.shared_memory.get("_restricted_tools")
        all_tools = gen.skill_loader.get_all_tools_schema(state.active_skill)
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

    def _build_system_prompt(self, state: AgentState, gen: AgentGeneration, req_ctx: RequestContext) -> str:
        # 使用 gen.config
        prompt = gen.config.agent.system_template.format(name=gen.config.agent.name)
        
        if self._needs_complex_protocol(state):
            concurrency_protocol = """
                \n=== ⚡ CONCURRENCY & SAFETY RULES ===
                1. **Parallel Execution**: You CAN call multiple tools in a single turn if they are independent (e.g., searching for two different things). This is encouraged for speed.
                2. **Sequential Dependency**: If Tool B requires the output of Tool A, you MUST NOT call them in the same turn. Wait for Tool A's result, then call Tool B in the next turn.
                3. **State Safety**: Do not read and write to the same `clipboard` key in the same turn.
                4. **Routing**: If the user's request is out of scope, use `activate_skill` immediately.\n
            """
            # "\n=== RULES ===\n1. Parallel tools allowed.\n2. Wait for dependencies.\n3. Safe memory RW.\n"
            prompt += concurrency_protocol 
            
        if gen.skill_loader:
            prompt += gen.skill_loader.get_context_prompt(state.active_skill)
            
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
        
        # # 注入页面上下文 (让 Agent 知道用户正在看什么)
        # if req_ctx.page_content:
        #     page_summary = str(req_ctx.page_content)[:1000] # 截断防止太长
        #     prompt += f"\n\nUser is currently viewing:\n{page_summary}...\n"
        
        
        return prompt

    async def _execute_tools_concurrent(self, tool_requests: List[ToolRequest], state: AgentState, gen: AgentGeneration, req_ctx: RequestContext) -> List[ToolResponse]:
        """
        并发执行多个工具请求

        职责：
        1. 协调工具执行流程
        2. 发送 TOOL_START 和 TOOL_END 事件
        3. 统一处理 artifacts 提取、存储和事件发送
        4. 返回结果映射和 artifact 列表

        Args:
            tool_requests: ToolRequest 对象列表
            state: Agent 状态
            gen: 当前 Generation 对象
            req_ctx: 请求上下文

        Returns:
            List[Dict] 包含:
            - tool_end_event: {
                "name": name,
                "text":result_str,
                "data":tool_artifacts,
                "status": "error" if is_error else "success",
                "meta": {
                    "duration": duration,
                    "start_time": datetime.fromtimestamp(start_time).strftime("%H:%M:%S")
                }
            }
        """
        tasks = []

        # 定义单个工具执行 wrapper
        async def _exec_wrapper(index: int, req: ToolRequest) -> tuple:
            call_param = req.tool_call.value
            name = call_param.name
            args = call_param.arguments or {}
            
            # 获取工具的中文显示名称（label）
            tool_label = None
            if gen.skill_loader:
                tool_metadata = gen.skill_loader.get_tool_metadata(name)
                if tool_metadata and tool_metadata.label:
                    tool_label = tool_metadata.label
                    
            # 1. 触发工具开始事件
            await self.events.emit(EventType.TOOL_START, {"name": name, 
                                                          "args": args, 
                                                          "label": tool_label})

            start_time = time.time()
            result_str = ""
            is_error = False
            tool_artifacts = []

            # 2. 执行工具逻辑
            try:
                tool_result = await self._exec_tool_func(name, args, state, gen, req_ctx)

                if isinstance(tool_result, CallToolResult):
                    # 提取 artifacts
                    tool_artifacts = self._extract_artifacts_from_result(tool_result, name)

                    # 存储 artifacts 到 ArtifactManager
                    await self._store_artifacts_to_manager(tool_artifacts, state)

                    # 格式化返回给 LLM 的文本
                    result_str = self._format_tool_result_for_llm(tool_result)
                else:
                    result_str = str(tool_result) if tool_result is not None else ""

            except Exception as e:
                is_error = True
                result_str = f"Error: {str(e)}"
                logger.error(f"Tool execution failed for '{name}': {e}", exc_info=True)

            # 3. 触发工具结束事件
            duration = f"{time.time() - start_time:.2f}s"

            

            tool_end_event = {
                "name": name,
                "label": tool_label,  # 中文显示名称
                "artifacts": [t.model_dump() for t in tool_artifacts],
                "status": "error" if is_error else "success",
                "meta": {
                    "duration": duration,
                    "start_time": datetime.fromtimestamp(start_time).strftime("%H:%M:%S"),
                    "label": tool_label,  # 在 meta 中也包含 label
                }
            }
            tool_response = ToolResponse(
                id = f"{uuid.uuid4().hex[:8]}",
                toolResult=CallToolResult(
                    content=[RawContent(text=result_str), *tool_artifacts],
                    isError=is_error,
                    meta={
                        "tool_name": name,
                        "duration": duration,
                        "start_time": datetime.fromtimestamp(start_time).strftime("%H:%M:%S"),
                        "label": tool_label,  # 在 ToolResponse 的 meta 中也包含 label
                    }
                )
            )

            await self.events.emit(EventType.TOOL_END, tool_end_event)

            return index, tool_response

        # 处理敏感工具检查和任务创建
        for i, req in enumerate(tool_requests):
            if req.tool_call.is_error():
                logger.error(f"Skipping malformed tool call: {req.tool_call.error}")
                continue

            call_param = req.tool_call.value
            name = call_param.name
            args = call_param.arguments or {}
            call_id = req.id

            # 敏感工具检查
            is_sens = gen.config.is_sensitive(name)
            if gen.skill_loader:
                is_sens |= gen.skill_loader.is_sensitive(name)

            if is_sens:
                state.status = AgentStatus.WAITING_APPROVAL
                state.pending_tool_call = {"name": name, "args": args, "id": call_id}
                # 使用 try-except 捕获 save_state 异常
                try:
                    await self.db.save_state(state.session_id, state.model_dump())
                except Exception as e:
                    logger.error(f"Failed to save state for approval: {e}")
                    # 发送错误事件
                    await self.events.emit(EventType.ERROR, {
                        "error": f"保存状态失败: {str(e)}",
                        "error_type": type(e).__name__
                    })
                    return []
                await self.events.emit(EventType.APPROVAL_REQ, {"tool": name, "args": args})
                return []

            tasks.append(_exec_wrapper(i, req))

        if not tasks:
            return []

        # 并发执行所有工具
        results = await asyncio.gather(*tasks, return_exceptions=True)
        results.sort(key=lambda x: x[0])  # 按原始顺序排序

        return [r[1] for r in results]
    

    # =========================================================================
    # Hook Initialization
    # =========================================================================

    def _init_hooks(self, config: ConfigLoader) -> None:
        """
        从配置文件初始化 Hooks

        初始化流程：
        1. 注册内置 Hooks（使用配置文件中的设置覆盖默认值）
        2. 从配置文件加载自定义 Hooks
        """
        from .hooks import HookConfigLoader, FAQHook, SensitiveWordHook, PromptInjectionHook
        from .hooks import RequestLoggerHook, InputValidatorHook, StatisticsCollectorHook
        from .hooks.base import HookConfig

        # 获取 hooks 配置
        hooks_config = config.hooks

        # 定义内置 Hook 类映射
        builtin_hooks = {
            "faq_interceptor": FAQHook,
            "sensitive_word_filter": SensitiveWordHook,
            "prompt_injection_detector": PromptInjectionHook,
            "input_validator": InputValidatorHook,
            "request_logger": RequestLoggerHook,
            "statistics_collector": StatisticsCollectorHook,
        }

        # 1. 注册内置 Hooks（支持配置覆盖）
        for hook_name, hook_class in builtin_hooks.items():
            # 如果配置文件中有此 Hook 的配置，使用配置创建
            if hook_name in hooks_config:
                cfg = hooks_config[hook_name]
                if isinstance(cfg, BaseModel):
                    cfg = cfg.model_dump()
                if isinstance(cfg, dict):
                    hook_config = HookConfig(
                        name=hook_name,
                        enabled=cfg.get("enabled", True),
                        priority=cfg.get("priority", 100),
                        hook_type=cfg.get("hook_type", "filter"),
                        conditions=cfg.get("conditions", {}),
                        params=cfg.get("params", {}),
                        fail_on_error=cfg.get("fail_on_error", False),
                        error_message=cfg.get("error_message")
                    )
                elif isinstance(cfg, HookConfig):
                    hook_config = cfg
                else:
                    raise TypeError(f"Invalid hook config for {hook_name}: {cfg}")
                
                hook = hook_class(hook_config)
                logger.info(f"🪝 Loaded builtin hook '{hook_name}' with config")
            else:
                # 使用默认配置
                hook = hook_class()
                logger.debug(f"🪝 Registered builtin hook '{hook_name}' with defaults")

            self.hook_manager.register(hook)

        # 2. 从配置文件加载自定义 Hooks（排除已注册的内置 Hooks）
        custom_hooks = {
            name: cfg for name, cfg in hooks_config.items()
            if name not in builtin_hooks
        }

        if custom_hooks:
            hook_configs = HookConfigLoader.from_dict(custom_hooks)
            loaded = self.hook_manager.load_from_config(hook_configs)
            logger.info(f"🪝 Loaded {loaded} custom hooks from config")

    # =========================================================================
    # Main Entry Point
    # =========================================================================

    async def run_task(self, session_id: int, input_data: Dict|str = None, resume: bool = False, approval_data: Dict = None, user_id: Optional[int] = None):
        # 1. 捕获当前时刻的 Generation (快照)
        # 此时必须立即 acquire，防止它在下一行代码还没执行时就被 drain 了
        current_gen_ref = self.current_generation
        if not current_gen_ref:
            raise RuntimeError("Agent not initialized")

        # 2. 构建 RequestContext
        # Token 由中间件通过 contextvars 自动注入，从 get_auth_token() 获取
        # 其他参数从 input_data 中获取
        auth_token = get_auth_token()
        req_ctx = RequestContext(token=auth_token)

        if input_data and isinstance(input_data, dict):
            req_ctx = RequestContext(
                token=auth_token,  # 从 contextvars 获取
                server_type=input_data.get("server_type", "show"),
                file_path=input_data.get("file_path"),
                page_content=input_data.get("page_content"),
                deep_thinking=input_data.get("deep_thinking", False),
                is_deep_research=input_data.get("is_deep_research", False)
            )
            
        # 使用 context manager 自动管理计数
        async with current_gen_ref.context_scope() as gen:
            # 如果提供了 user_id，则加载该用户的会话
            state_data = None
            try:
                if user_id:
                    state_data = await self.db.load_state_for_user(user_id, session_id)
                else:
                    state_data = await self.db.load_state(session_id)
            except Exception as e:
                # 统一异常处理：提取错误信息发送给客户端
                error_msg = str(e)
                error_type = type(e).__name__
                error_detail = None

                # 尝试提取更多信息（可选）
                if hasattr(e, 'response'):
                    error_detail = getattr(e, 'response')

                logger.error(f"Error in run_task [{error_type}]: {error_msg}")
                await self.events.emit(EventType.ERROR, {
                    "error": error_msg,
                    "error_type": error_type,
                    "error_detail": str(error_detail) if error_detail else None
                })
                await self.events.emit(EventType.DONE, {
                    "session_id": session_id
                })
                return

            if state_data is None:
                logger.error(f"Loaded state for session {session_id} Failed.")
                await self.events.emit(EventType.ERROR, {
                    "error": f"Failed to load state for session {session_id}"
                })
                await self.events.emit(EventType.DONE, {
                    "session_id": session_id
                })
                return

            state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)
            
            # [关键步骤 A]：处理上下文数据 (Input Context)
            # 如果有上传文件或页面内容，将其放入 Shared Memory，以便工具（如 read_file）可以访问
            # if req_ctx.file_path:
            #     state.shared_memory["_current_file_path"] = req_ctx.file_path
            #     # 可选：生成一条系统消息告知 Agent
            #     # state.history.append({"role": "system", "content": f"User uploaded file: {req_ctx.file_path}"})
            
            # if req_ctx.page_content:
            #     state.shared_memory["_page_content"] = req_ctx.page_content

            # [关键步骤 B]：处理配置标志 (Config)
            # 将 Deep Thinking 标志存入 State (如果需要在多轮对话中保持)
            # 或者仅在本次 run_task 中生效
            state.run_config["deep_thinking"] = req_ctx.deep_thinking
            state.run_config["is_deep_research"] = req_ctx.is_deep_research
            
            if input_data :
                if isinstance(input_data, dict):
                    user_input = input_data.get("message")
                elif isinstance(input_data, str):
                    user_input = input_data
                    
            # 设置 user_id 到 state
            if user_id:
                state.user_id = user_id

            if resume:
                if state.status == AgentStatus.WAITING_APPROVAL:
                    # 传递 gen
                    if not await self._process_approval(state, approval_data or {}, gen): return
            else:
                await self.events.emit(EventType.RUN_START, {
                    "session_id": session_id
                })
                if user_input:
                    # 清理上一次请求的 FAQ 标记（如果存在）
                    state.shared_memory.pop("_faq_already_queried", None)

                    # ==================== Hook Pipeline: User Input ====================
                    # 创建 Hook Context
                    hook_ctx = HookContext(
                        user_input=user_input,
                        state=state,
                        gen=gen,
                        req_ctx=req_ctx
                    )

                    # [关键] 执行用户输入 Hooks - FAQ、敏感词过滤等
                    if self.hook_manager:
                        hook_result = await self.hook_manager.on_user_input(hook_ctx)

                        if hook_result:
                            logger.info(f"🪝 Hook result: action={hook_result.action}, response={hook_result.response[:50] if hook_result.response else None}...")
                            # 处理 Hook 结果
                            if str(hook_result.action) == "intercept" or hook_result.action == HookAction.INTERCEPT:
                                # Hook 拦截了，直接返回响应
                                final_response = hook_result.response or ""

                                # 如果 response_data 是 CallToolResult，提取 artifact 信息
                                # 发送 TOOL_END 事件来传递 artifact 数据
                                if hook_result.response_data and isinstance(hook_result.response_data, CallToolResult):
                                    # 提取 artifacts
                                    artifacts = self._extract_artifacts_from_result(hook_result.response_data, "hook_response")

                                    # 存储 artifacts 到 ArtifactManager
                                    await self._store_artifacts_to_manager(artifacts, state)

                                    if artifacts:
                                        await self.events.emit(EventType.TOOL_END, {
                                            "name": "hook_response",
                                            "result": final_response,
                                            "meta": {"artifacts": artifacts}
                                        })

                                await self.add_message(state.session_id, Message.assistant(final_response), state)

                                await self.events.emit(EventType.TOKEN, final_response)
                                self._schedule_state_save(state.session_id, state)

                                # 执行请求结束 Hooks
                                await self.hook_manager.on_request_end(hook_ctx, final_response)
                                return

                            elif hook_result.action == HookAction.MODIFY:
                                # Hook 修改了输入
                                user_input = hook_result.modified_input
                                hook_ctx.user_input = user_input

                    # 更新状态和历史
                    state.status = AgentStatus.RUNNING
                    # 存入数据库
                    await self.add_message(state.session_id, Message.user(user_input), state)
                    state.history.append({"role": "user", "content": user_input})

                    # Intent Phase (传递 gen)
                    direct_res = await self._handle_intent_phase(user_input, state, gen)
                    if direct_res:
                        # 存入数据库
                        await self.add_message(state.session_id, Message.assistant(direct_res), state)
                        state.history.append({"role": "assistant", "content": direct_res})
                        await self.events.emit(EventType.TOKEN, direct_res)
                        self._schedule_state_save(state.session_id, state)

                        # 执行请求结束 Hooks
                        if self.hook_manager:
                            await self.hook_manager.on_request_end(hook_ctx, direct_res)
                        return

            while state.status == AgentStatus.RUNNING:
                await asyncio.sleep(0.01)
                
                # 1. Build Prompt & Sync History
                # ==============================
                # 传递 gen
                prompt = self._build_system_prompt(state, gen,req_ctx)
                
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
                input_messages = []
                for h in state.history:
                    msg = Message.model_validate(h)
                    # 注意：不再重新发送 TOOL_ARTIFACT 事件，artifact 数据已在消息历史中保存
                    input_messages.append(msg)
                
                # 响应 Deep Thinking 开关
                if req_ctx.deep_thinking:
                    deep_thinking_instruction = """
\n\n
--- SYSTEM OVERRIDE: DEEP THINKING PROTOCOL ---
You must strictly follow this two-phase output format, regardless of any previous constraints about "JSON only" or "conciseness":

**PHASE 1: REASONING (Internal Monologue)**
- You MUST start your response with a `<thinking>` block.
- Explain your reasoning step-by-step inside this block.
- This phase is MANDATORY and acts as a scratchpad.

**PHASE 2: FINAL RESPONSE (User Fulfillment)**
- After closing the `</thinking>` tag, proceed to answer the user's request.
- IN THIS PHASE, you must strictly adhere to the user's original formatting requirements (e.g., JSON only, Python code only, short answer).
- Do NOT output the thinking block if it violates the user's format; instead, output it *before* the user's format content.

**Example Structure:**
<thinking>
... analysis ...
</thinking>
{ "result": "This is the JSON the user asked for" }
"""
                    # 策略 A: 追加到最后一条 User 消息的内容里 (效果最强)
                    if input_messages and input_messages[-1].role == Role.USER:
                        last_msg = input_messages[-1]
                        # 这是一个临时修改，不保存到数据库，只影响本次推理
                        # 注意：需要处理多模态 Content 的情况，这里简化为处理文本
                        original_text = last_msg.text
                        new_text = f"{original_text}{deep_thinking_instruction}"
                        
                        # 替换最后一条消息用于本次推理
                        input_messages[-1] = Message(role=Role.USER, content=[TextContent(text=new_text)])
                    
                # 传递 gen
                tools = self._get_tools_schema(state, gen)
                logger.info(f"🔧 Available tools count: {len(tools) if tools else 0}, active_skill: {state.active_skill}")

                # 3. Call BaseLLM
                # ===============
                # 发送 TOKEN_START 事件（LLM 开始生成）
                await self.events.emit(EventType.TOKEN_START, {})

                full_content_text = ""
                received_tool_requests: List[ToolRequest] = []
                # [NEW] 思考过程状态追踪
                is_thinking = False
                # [解析器变量] 用于解析 Prompt 模式下的 <thinking> 标签
                parse_state = "normal" # normal, check_open, thinking, check_close
                tag_buffer = ""        # 缓存标签字符 (如 "<thi")

                try:
                    async for partial_msg, usage in gen.llm.astream(
                        messages=input_messages,
                        tools=tools or None
                    ):
                        if partial_msg and partial_msg.content:
                            for c in partial_msg.content:
                                # =================================================
                                # Case A: 模型原生支持思考 (DeepSeek R1 / Native)
                                # =================================================
                                if isinstance(c, (ThinkingContent, RedactedThinkingContent)):
                                    if not is_thinking:
                                        await self.events.emit(EventType.THINKING_START, {})
                                        is_thinking = True
                                    
                                    content = c.thinking if isinstance(c, ThinkingContent) else ""
                                    if content:
                                        await self.events.emit(EventType.THINKING_TOKEN, content)

                                # =================================================
                                # Case B: 普通文本 (需处理 Prompt 模式下的标签)
                                # =================================================
                                elif isinstance(c, TextContent):
                                    text_chunk = c.text
                                    
                                    # 1. 如果没开 deep_thinking，直接作为普通文本发送
                                    if not req_ctx.deep_thinking:
                                        # 如果之前是 Native Thinking 状态，先结束
                                        if is_thinking and not isinstance(c, ThinkingContent): 
                                            await self.events.emit(EventType.THINKING_END, {})
                                            is_thinking = False
                                            
                                        full_content_text += text_chunk
                                        await self.events.emit(EventType.TOKEN, text_chunk)
                                        continue

                                    # 2. 开启了 deep_thinking，启动状态机解析
                                    for char in text_chunk:
                                        # --- 状态 1: 正常文本 ---
                                        if parse_state == "normal":
                                            if char == "<":
                                                parse_state = "check_open"
                                                tag_buffer = "<"
                                            else:
                                                full_content_text += char
                                                await self.events.emit(EventType.TOKEN, char)
                                        
                                        # --- 状态 2: 检查开始标签 <thinking> ---
                                        elif parse_state == "check_open":
                                            tag_buffer += char
                                            if tag_buffer == "<thinking>":
                                                # 命中开始！
                                                if not is_thinking:
                                                    await self.events.emit(EventType.THINKING_START, {})
                                                    is_thinking = True
                                                parse_state = "thinking"
                                                tag_buffer = ""
                                            elif not "<thinking>".startswith(tag_buffer):
                                                # 匹配失败，原样吐出缓存
                                                full_content_text += tag_buffer
                                                await self.events.emit(EventType.TOKEN, tag_buffer)
                                                parse_state = "normal"
                                                tag_buffer = ""
                                        
                                        # --- 状态 3: 思考内容中 ---
                                        elif parse_state == "thinking":
                                            if char == "<":
                                                parse_state = "check_close"
                                                tag_buffer = "<"
                                            else:
                                                # 发送思考 Token
                                                await self.events.emit(EventType.THINKING_TOKEN, char)
                                        
                                        # --- 状态 4: 检查结束标签 </thinking> ---
                                        elif parse_state == "check_close":
                                            tag_buffer += char
                                            if tag_buffer == "</thinking>":
                                                # 命中结束！
                                                if is_thinking:
                                                    await self.events.emit(EventType.THINKING_END, {})
                                                    is_thinking = False
                                                parse_state = "normal"
                                                tag_buffer = ""
                                            elif not "</thinking>".startswith(tag_buffer):
                                                # 匹配失败（可能是思考内容里的 < 符号）
                                                await self.events.emit(EventType.THINKING_TOKEN, tag_buffer)
                                                parse_state = "thinking" # 回到思考状态
                                                tag_buffer = ""

                                # =================================================
                                # Case C: 工具请求
                                # =================================================
                                elif isinstance(c, ToolRequest):
                                    # 遇到工具调用，强制结束思考
                                    if is_thinking:
                                        await self.events.emit(EventType.THINKING_END, {})
                                        is_thinking = False
                                        # 重置解析器状态
                                        parse_state = "normal"
                                        tag_buffer = ""
                                    
                                    received_tool_requests.append(c)
                                        
                                        
                except Exception as e:
                    # 统一异常处理格式
                    error_msg = str(e)
                    error_type = type(e).__name__
                    logger.error(f"LLM Error [{error_type}]: {error_msg}")
                    await self.events.emit(EventType.ERROR, {
                        "error": error_msg,
                        "error_type": error_type
                    })
                    break
                
                # 兜底：如果循环结束还在 is_thinking 状态，强制结束
                if is_thinking:
                    await self.events.emit(EventType.THINKING_END, {})

                # 如果解析器卡在 buffer 里（例如流中断导致只输出了 "<think"），把残余发出来
                if tag_buffer:
                    if parse_state in ["check_open", "normal"]:
                        await self.events.emit(EventType.TOKEN, tag_buffer)
                        full_content_text += tag_buffer
                    elif parse_state in ["thinking", "check_close"]:
                        await self.events.emit(EventType.THINKING_TOKEN, tag_buffer)

                # 发送 TOKEN_END 事件（LLM 生成结束）
                await self.events.emit(EventType.TOKEN_END, {})
                        
                logger.info(f"📊 LLM returned: text_len={len(full_content_text)}, tool_requests={len(received_tool_requests)}")
                if received_tool_requests:
                    for req in received_tool_requests:
                        name = req.tool_call.value.name if req.tool_call and req.tool_call.value else "unknown"
                        logger.info(f"   Tool request: {req.id} -> {name}")

                # 4. Update History (Assistant Response)
                # ======================================
                assistant_content = []
                if full_content_text:
                    assistant_content.append(TextContent(text=full_content_text))
                
                if received_tool_requests:
                    assistant_content.extend(received_tool_requests)
                    
                # Create the finalized assistant message and dump to dict for DB
                assistant_msg = Message(role=Role.ASSISTANT, content=assistant_content)
                await self.add_message(state.session_id, assistant_msg,state)
                
                # 5. Handle Tools or Stop
                # =======================
                if not received_tool_requests:
                    self._schedule_state_save(state.session_id, state)
                    break # Turn complete

                # Execute Tools (传递 gen)
                exec_results = await self._execute_tools_concurrent(received_tool_requests, state, gen, req_ctx)

                if state.status == AgentStatus.WAITING_APPROVAL:
                    return # Pause execution
 

                # 创建带有 artifact 信息的消息 metadata
                message_metadata = {}
                for i, (req,resp) in enumerate(zip(received_tool_requests,exec_results)):
 
                    # Construct Tool Response Message using Goose models
                    # Note: OpenAIProvider._prepare_messages will separate this into the correct format
                    tool_msg = Message.tool_response(resp)
                    
                    # 存入数据库
                    await self.add_message(state.session_id, tool_msg, state)
                    state.history.append(tool_msg.model_dump(exclude_none=True, by_alias=True))

                self._schedule_state_save(state.session_id, state)

            # 确保最终状态被保存（延迟保存的最后一次刷新）
            await self._ensure_state_saved(session_id, state)


            await self.events.emit(EventType.DONE, {
                    "session_id": session_id
                })

    async def _process_approval(self, state: AgentState, data: Dict, gen: AgentGeneration) -> bool:
        if state.status != AgentStatus.WAITING_APPROVAL or not state.pending_tool_call: return False
        tool = state.pending_tool_call
        if data.get("approved"):
            # 传递 gen
            res = await self._exec_tool_func(tool['name'], tool['args'], state, gen)
            # Add Tool Response
            tool_msg = Message.tool(text=res, tool_call_id=tool['id'])
            # 存入数据库
            await self.add_message(state.session_id, tool_msg, state)
            state.history.append(tool_msg.model_dump(exclude_none=True, by_alias=True))
        else:
            tool_msg = Message.tool(text=f"Rejected: {data.get('feedback')}", tool_call_id=tool['id'])
            # 存入数据库
            await self.add_message(state.session_id, tool_msg, state)
            state.history.append(tool_msg.model_dump(exclude_none=True, by_alias=True))

        state.status = AgentStatus.RUNNING
        state.pending_tool_call = None
        return True

    async def cleanup_session(self, session_id: int) -> int:
        """
        清理会话的所有 artifacts

        Args:
            session_id: 会话 ID

        Returns:
            清理的数量
        """
        if self.artifact_manager is None:
            return 0

        try:
            count = await self.artifact_manager.cleanup_session(session_id=session_id)
            logger.info(f"Cleaned up {count} artifacts for session {session_id}")
            return count
        except Exception as e:
            logger.error(f"Failed to cleanup artifacts for session {session_id}: {e}", exc_info=True)
            return 0

    def shutdown(self):
        """同步关闭方法（向后兼容）"""
        if self.watcher:
            self.watcher.stop()

        # 尝试关闭当前 generation
        if self.current_generation:
            asyncio.create_task(self.current_generation.drain_and_close())

        logger.info("Agent shut down gracefully.")

    async def shutdown_async(self):
        """异步关闭方法"""
        if self.watcher:
            self.watcher.stop()

        # 关闭 Artifact Manager
        if self.artifact_manager:
            await self.artifact_manager.shutdown()
            logger.info("Artifact Manager shut down.")

        # 关闭数据库连接
        if self.db:
            await self.db.close()

        # 关闭当前 generation
        if self.current_generation:
            await self.current_generation.drain_and_close()

        logger.info("Agent shut down gracefully.")