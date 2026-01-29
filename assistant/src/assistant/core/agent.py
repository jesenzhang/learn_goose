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
from contextlib import asynccontextmanager
from pydantic import BaseModel

# [NEW] Import Service Abstractions and Models
from ..providers.base import BaseLLM
from ..providers.factory import ProviderFactory
from ..conversation import (Message, Role, TextContent,
                            ToolRequest, ToolResponse, CallToolResult, RawContent,
                            ThinkingContent, RedactedThinkingContent, Conversation)

# Core Imports
from ..events import MemoryEventBus, AsyncEventStore, StreamerFactory,BaseStreamer
from ..events.legacy import EventType
from .state import AgentState, AgentStatus
from ..db import get_db, DatabaseManager
from ..config.loader import ConfigLoader
from ..skills import SkillLoader
from ..skills.context import create_context, ServiceContext

from .executor import ToolExecutor
# Artifact Storage Import
from .artifact_storage import init_manager, get_manager



# [NEW] 导入 Truncation 和 ChatRecall 模块
from ..truncation import TruncationManager
from ..chatrecall import ChatRecall

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


class TaskHandle:
    """
    任务句柄 - 跟踪运行中的任务状态
    """
    def __init__(self, task: asyncio.Task, created_at: float, task_id: str, start_signal: asyncio.Event, input_data: Any = None):
        self.task = task
        self.created_at = created_at
        self.task_id = task_id  # 注入 task_id
        self.input_data = input_data
        self._start_signal = start_signal
        
    def start(self):
        """放行 Agent 逻辑"""
        self._start_signal.set()
        
    @property
    def is_running(self) -> bool:
        """任务是否正在运行"""
        return not self.task.done()

    @property
    def is_done(self) -> bool:
        """任务是否已完成（无异常）"""
        return self.task.done() and not self.task.exception()

    @property
    def is_failed(self) -> bool:
        """任务是否失败"""
        return self.task.done() and self.task.exception() is not None

    def get_exception(self) -> Optional[Exception]:
        """获取任务异常"""
        if self.is_failed:
            return self.task.exception()
        return None

class ThinkingTracker:
    def __init__(self, emit):
        self.emit = emit
        self.active = False

    async def start(self):
        if not self.active:
            await self.emit(EventType.THINKING_START, {})
            self.active = True

    async def token(self, text: str):
        if self.active and text:
            await self.emit(EventType.THINKING_TOKEN, text)

    async def end(self):
        if self.active:
            await self.emit(EventType.THINKING_END, {})
            self.active = False

class MicroAgent:
    """
    Core Agent using BaseLLM abstraction and Generation-based Hot Reloading.
    """

    def __init__(
        self,
        config_path: str
    ):
        self.config_path = config_path
        self.db = get_db()

        # 创建事件总线、存储和工厂
        self._bus = MemoryEventBus(buffer_size=1000, ttl=3600)
        self._store = AsyncEventStore(self.db)
        self._factory = StreamerFactory(bus=self._bus, store=self._store)
        self._current_session_id: Optional[int] = None

        # 当前活跃的"一代"
        self.current_generation: Optional[AgentGeneration] = None

        # Initialize Artifact Manager
        self.artifact_manager = init_manager(config_path=self.config_path)

        # Initialize Truncation Manager
        self.truncation_manager: Optional[TruncationManager] = None

        # Initialize ChatRecall
        self.chat_recall: Optional[ChatRecall] = None

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

        self._streamers = {}

        # 任务管理：session_id -> TaskHandle
        self._running_tasks: Dict[int, TaskHandle] = {}

        logger.info("MicroAgent initialized")

    def get_streamer(self, session_id: int, run_id: str) -> "BaseStreamer":
        """获取指定会话的事件流"""
        if session_id not in self._streamers:
            self._streamers[session_id] ={}
        
        if run_id not in self._streamers[session_id]:
            self._streamers[session_id][run_id] = self._factory.create(session_id, str(run_id))
            
        return self._streamers[session_id][run_id]

    def get_task_handle(self, session_id: int) -> Optional[TaskHandle]:
        """
        获取会话的任务句柄

        Args:
            session_id: 会话 ID

        Returns:
            TaskHandle 对象，如果会话没有运行中的任务则返回 None
        """
        return self._running_tasks.get(session_id)

    async def cancel_running_task(self, session_id: int) -> bool:
        """
        取消运行中的任务

        Args:
            session_id: 会话 ID

        Returns:
            是否成功取消
        """
        handle = self._running_tasks.get(session_id)
        if handle and handle.is_running:
            handle.task.cancel()
            del self._running_tasks[session_id]
            logger.info(f"Cancelled running task for session {session_id}")
            return True
        return False

    async def _emit_event(self, event_type, data: Any, session_id: Optional[int] = None):
        """
        发送事件到总线和存储。

        Args:
            event_type: 事件类型
            data: 事件数据
            session_id: 会话 ID，如果为 None 则使用当前会话 ID
        """
        if session_id is None:
            session_id = self._current_session_id

        if session_id is None:
            logger.warning("Cannot emit event: no session_id set")
            return
        
        # 尝试从运行中的句柄获取当前的 task_id 和 user_id
        handle = self.get_task_handle(session_id)
        run_id = handle.task_id if handle else "system"
        
        user_id = getattr(self, "_active_user_id", "unknown")
        metadata = {
            "user_id": user_id,
        }
        streamer = self.get_streamer(session_id,run_id)
        await streamer.emit(event_type, data, **metadata)

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

        # Initialize Truncation Manager
        if config.provider.llm:
            # 直接使用 config.truncation 属性获取 dataclass 配置
            truncation_config = config.truncation
            # 使用 LLM provider 创建 Truncation Manager
            llm_provider = ProviderFactory.create_llm(
                config.provider.llm.provider,
                config.provider.llm.config
            )
            self.truncation_manager = TruncationManager(
                provider=llm_provider,
                config=truncation_config
            )
            logger.info("Truncation Manager initialized")
        else:
            self.truncation_manager = None

        # Initialize ChatRecall
        # 直接使用 config.chatrecall 属性获取 dataclass 配置
        chat_recall_config = config.chatrecall

        # 定义会话查询函数
        async def session_query_func(**kwargs) -> Dict[str, Any]:
            """查询会话数据的函数"""
            if kwargs.get("session_id"):
                # 加载单个会话
                session_data = await self.db.load_state(kwargs["session_id"])
                if session_data:
                    return {
                        "messages": session_data.get("history", []),
                        "created_at": session_data.get("created_at"),
                        "updated_at": session_data.get("updated_at"),
                        "system_prompt": session_data.get("system_prompt"),
                    }
            else:
                # 加载所有会话
                all_sessions = await self.db.list_sessions()
                return {sid: {"messages": data.get("history", [])} for sid, data in all_sessions.items()}

        self.chat_recall = ChatRecall(
            session_query_func=session_query_func,
            config=chat_recall_config
        )
        logger.info("ChatRecall initialized")

        # 提取 SkillsConfig (它是 Pydantic 对象)
        skills_cfg = config.skills_config
        skill_loader = SkillLoader(
            skills_dir= config.skills_directory or "agent_skills",
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
            await self._emit_event(EventType.STATE_CHANGE, {"msg": "⚙️ Configuration reloaded"})
            
        except Exception as e:
            logger.error(f"Reload failed: {e}")
    

    def _get_conversation(self, state: AgentState) -> Conversation:
        """获取或初始化 Conversation 对象"""
        if not hasattr(state, '_conversation') or state._conversation is None:
            messages = [Message.model_validate(h) for h in state.history] if state.history else []
            messages.reverse()
            messages.sort(key=lambda x: x.created_at)
            state._conversation = Conversation(messages=messages)

        # 设置 Truncation Manager（如果已初始化）
        if self.truncation_manager and hasattr(state._conversation, 'set_truncation_manager'):
            if state._conversation.get_truncation_manager() is None:
                state._conversation.set_truncation_manager(self.truncation_manager)

        return state._conversation

    def _sync_history_from_conversation(self, state: AgentState):
        """从 Conversation 同步到 history(保持向后兼容）"""
        if hasattr(state, '_conversation') and state._conversation is not None:
            state.history = [m.model_dump(exclude_none=True, by_alias=True) for m in state._conversation.messages]

    async def add_message(self, session_id: int, msg: Message, state: Optional[AgentState] = None, ephemeral: bool = False):
        """
        添加消息到会话

        Args:
            session_id: 会话 ID
            msg: 消息对象
            state: Agent 状态
            ephemeral: 是否为临时消息(不保存到数据库）
        """
        if state is None:
            raise ValueError("state is required for add_message")

        # 使用 Conversation 来管理消息
        msg.session_id = session_id
        conv = self._get_conversation(state)
        conv.push(msg, ephemeral=ephemeral)

        # 仅对持久化消息同步到 history 和保存到数据库
        if not ephemeral:
            self._sync_history_from_conversation(state)
            await self.db.add_message(session_id, msg.role, msg.content_json, msg.meta_json)

    async def save_new_messages(self, session_id: int, state: AgentState, start_count: int):
        """
        保存从某个点之后新增的消息到数据库

        Args:
            session_id: 会话 ID
            state: Agent 状态
            start_count: 起始消息数量，仅保存此数量之后的消息
        """
        conv = self._get_conversation(state)
        new_messages = conv.messages[start_count:]

        for msg in new_messages:
            await self.db.add_message(session_id, msg.role, msg.content_json, msg.meta_json)

        # 更新 history
        self._sync_history_from_conversation(state)

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

            await self._emit_event(EventType.STATE_CHANGE, {
                "msg": "🤔 Planning...",
                "label": "计划中",
            })

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
                
                await self._emit_event(EventType.STATE_CHANGE, {
                    "msg": "📋 Plan Formulated", 
                    "plan": plan_desc,
                    "label": "计划已生成",
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
        await self._emit_event(EventType.STATE_CHANGE, {
            "msg": f"🚀 Executing: {primary.intent}",
            "slots": primary.entities,
            "label": f"执行中:{primary.label}",
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

            # 构造一条 System Instruction 插入临时消息流
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
            # 使用 Conversation 存入临时消息流（不保存到数据库，仅用于内部推理）
            conv = self._get_conversation(state)
            conv.push(Message.system(system_instruction).with_visibility(user_visible=False, agent_visible=True), ephemeral=True)

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
            conv = self._get_conversation(state)
            conv.push(Message.system(fallback_msg), ephemeral=True)
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

                    # 5. 注入历史记录（使用临时消息流，不保存到数据库）
                    conv = self._get_conversation(state)
                    conv.push(Message.system(instruction).with_visibility(user_visible=False, agent_visible=True), ephemeral=True)
                    logger.info(f"✅ Injected Skill Instruction for {primary.intent}")

                except Exception as e:
                    logger.error(f"❌ Template render failed for {primary.intent}: {e}")
                    # 兜底：如果模板渲染挂了，至少发一个通用指令，防止 LLM 发呆
                    fallback = f"[SYSTEM] User intent: {primary.intent}. Entities: {primary.entities}. Please use appropriate tools."
                    conv = self._get_conversation(state)
                    conv.push(Message.system(fallback).with_visibility(user_visible=False, agent_visible=True), ephemeral=True)
            
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
                conv = self._get_conversation(state)
                conv.push(Message.tool(text=final_res or "", tool_call_id=f"intent_{primary.intent}"), ephemeral=True)
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
            await self._emit_event(EventType.TOOL_START, {"name": name,
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

            await self._emit_event(EventType.TOOL_END, tool_end_event)

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
                    await self._emit_event(EventType.ERROR, {
                        "error": f"保存状态失败: {str(e)}",
                        "error_type": type(e).__name__
                    })
                    return []
                await self._emit_event(EventType.APPROVAL_REQ, {"tool": name, "args": args})
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

    @asynccontextmanager
    async def event_scope(self, start_evt: EventType, end_evt: EventType, payload=None):
        await self._emit_event(start_evt, payload or {})
        try:
            yield
        finally:
            await self._emit_event(end_evt, {})
        
    # =========================================================================
    # Main Entry Point
    # =========================================================================
    async def run_task(self, session_id: int, input_data: Dict|str = None, resume: bool = False, approval_data: Dict = None, user_id: Optional[int] = None):
        """
        入口方法：负责任务调度逻辑
        """
        start_signal = asyncio.Event() # 创建一个事件锁
        self._current_session_id = session_id
        current_run_id = None

        # 1. 先从数据库拿到最实时的状态
        state_data = await self.db.load_state(session_id)
        state = AgentState(**state_data) if state_data else None

        # 2. 判断是否真的可以 Resume
        # 只有当状态是 WAITING_APPROVAL 时，复用 run_id 才有意义
        can_resume = (
            resume and 
            state and 
            state.status == AgentStatus.WAITING_APPROVAL
        )

        if can_resume:
            current_run_id = state.current_run_id
            logger.info(f"♻️ Resuming approval-locked task: {current_run_id}")
        else:
            # 如果任务已完成、已取消，或者用户没要求 resume
            # 开启一个全新的 RunID，这标志着一次新的交互轮次
            current_run_id = f"task_{uuid.uuid4().hex[:12]}"
            logger.info(f"🚀 Starting a new interaction round: {current_run_id}")
            
        # 1. 优先检查当前内存中是否已有任务运行（最高优先级，防止重复创建）
        handle = self.get_task_handle(session_id)
        if handle and handle.is_running:
            logger.info(f"Task for session {session_id} is already running [RunID: {handle.task_id}]")
            return handle


        # 3. 异步启动包装器（不阻塞当前 API 请求，立即返回句柄）
        # 我们不再 await _task_wrapper，而是让它在后台跑，run_task 立即返回 handle
        task = asyncio.create_task(self._task_wrapper(
            session_id=session_id,
            task_id=current_run_id,
            input_data=input_data, 
            resume=resume, 
            approval_data=approval_data, 
            user_id=user_id,
            start_signal=start_signal # 新增参数
        ))
        
        # 4. 手动构造并注册 handle，确保 run_task 返回时，管理字典里已经有它了
        handle = TaskHandle(task, time.time(), current_run_id, start_signal, input_data)
        self._running_tasks[session_id] = handle
        
        # # 如果你想立即启动，但要确保顺序：
        # loop = asyncio.get_running_loop()
        # loop.call_soon(start_signal.set) # 在下一个事件循环周期启动，给返回 handle 留出时间
        
        return handle
    
    async def _task_wrapper(
        self,
        session_id: int,
        task_id: str,
        input_data: Dict | str = None,
        resume: bool = False,
        approval_data: Dict = None,
        user_id: Optional[int] = None,
        start_signal: asyncio.Event = None,
    ):
        """
        任务包装函数 - 任务级生命周期唯一入口
        """

        await self._emit_event(
            EventType.RUN_START,
            {"session_id": session_id, "run_id": task_id},
            session_id=session_id,
        )

        try:
            await self._run_task_body(
                session_id,
                task_id,
                input_data,
                resume,
                approval_data,
                user_id,
                start_signal,
            )

        except asyncio.CancelledError:
            logger.info(f"Task for session {session_id} was cancelled.")
            await self._emit_event(
                EventType.CANCELLED,
                {"msg": "Task cancelled"},
                session_id=session_id,
            )
            raise

        except Exception as e:
            logger.error(
                f"Task execution failed for session {session_id}: {e}",
                exc_info=True,
            )
            await self._emit_event(
                EventType.ERROR,
                {"error": str(e), "type": type(e).__name__},
                session_id=session_id,
            )

        finally:
            # DONE 永远只在 wrapper 发
            await self._emit_event(
                EventType.DONE,
                {"session_id": session_id, "run_id": task_id},
                session_id=session_id,
            )
            self._running_tasks.pop(session_id, None)


    async def _run_deepresearch(self, session_id: int, task_id: str, req_ctx: RequestContext, user_input: str, start_signal: asyncio.Event = None, state: AgentState = None):
        from ai4search import DeepResearchAgent,DeepResearchConfig
        # 创建配置
        config = DeepResearchConfig(
            llm_config={
                "model": "qwen2",
                "api_key": "api_key",
                "base_url": "http://192.168.10.137:8086/v1"
            },
            rerank_url="http://192.168.10.137:8079/rerank",
            enable_local_doc=True,
            enable_exhibits=True,
            enable_online_search=False,
            max_depth=3,
            max_steps=3,
            max_concurrent=1,
        )
        # 创建 agent
        deepresearch_agent = DeepResearchAgent(config=config)
        streamer = self.get_streamer(session_id,task_id)
        # 执行任务
        query = user_input
        background_info = ''
        
        result = await deepresearch_agent.research(
            query=query,
            background_info=background_info,
            enable_write=True,
            streamer=streamer  # ← 传入自定义 streamer
        )
        ## 重要信息
        markdown = result["write"]["markdown_content"]
        search_conclusion = result["search"]["notebook"]
        
        await self.add_message(state.session_id, Message.user(user_input), state)
        await self.add_message(state.session_id, Message.assistant(markdown), state)
        
        return
    
    async def _run_task_body(self, session_id: int, task_id: str, input_data: Dict|str = None, resume: bool = False, approval_data: Dict = None, user_id: Optional[int] = None,start_signal: asyncio.Event = None):
        """
        核心执行逻辑 (从原 run_task 迁移过来的主体)
        """
        # 先等待信号，确保外界已经准备好接收事件了
        if start_signal:
            await start_signal.wait()
        
        current_gen_ref = self.current_generation
        if not current_gen_ref:
            raise RuntimeError("Agent not initialized")

        async with current_gen_ref.context_scope() as gen:
            try:
                # 1. 加载状态
                state_data = await self.db.load_state_for_user(user_id, session_id) if user_id else await self.db.load_state(session_id)
                state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)
                
                # 关键：将 task_id 存入 state 并在 metadata 中透传
                state.current_run_id = task_id
                state.user_id = user_id
                
                # 2. 预处理：Deep Thinking 等配置注入
                auth_token = get_auth_token()
                req_ctx = RequestContext(token=auth_token)
                
                if isinstance(input_data, dict):
                    req_ctx.server_type = input_data.get("server_type", "show")
                    req_ctx.file_path = input_data.get("file_path"),
                    req_ctx.page_content = input_data.get("page_content"),
                    req_ctx.deep_thinking = input_data.get("deep_thinking", False),
                    req_ctx.is_deep_research=input_data.get("is_deep_research", False)
                    user_input = input_data.get("message")
                else:
                    user_input = input_data

                if req_ctx.is_deep_research:
                    await self._run_deepresearch(session_id, task_id, req_ctx, user_input, start_signal, state)
                    return
                
                # 3. 处理审批恢复 (Resume Logic)
                if resume and state.status == AgentStatus.WAITING_APPROVAL:
                    logger.info(f"Resuming session {session_id} from approval...")
                    approved = await self._process_approval(state, approval_data or {}, gen)
                    if not approved: return # 依然没通过或需要继续等待

                # 4. 如果是新输入，处理 Hook 和 意图
                elif user_input:
                    # --- Hook Pipeline ---
                    hook_ctx = HookContext(user_input=user_input, state=state, gen=gen, req_ctx=req_ctx)
                    if self.hook_manager:
                        hook_res = await self.hook_manager.on_user_input(hook_ctx)
                        if hook_res and hook_res.action == HookAction.INTERCEPT:
                            await self.add_message(session_id, Message.assistant(hook_res.response), state)
                            await self._emit_event(EventType.TOKEN, hook_res.response)
                            state.status = AgentStatus.IDLE
                            return

                    # --- Intent Analysis ---
                    state.status = AgentStatus.RUNNING
                    direct_res = await self._handle_intent_phase(user_input, state, gen)
                    await self.add_message(session_id, Message.user(user_input), state)

                    if direct_res:
                        await self.add_message(session_id, Message.assistant(direct_res), state)
                        await self._emit_event(EventType.TOKEN, direct_res)
                        state.status = AgentStatus.IDLE
                        return

                # 5. 主循环：LLM + Tool Execution
                while state.status == AgentStatus.RUNNING:
                    await asyncio.sleep(0.01)

                    # ==============================
                    # [Truncation Integration] 检查并应用消息压缩
                    # ==============================
                    conv = self._get_conversation(state)
                    if self.truncation_manager and hasattr(conv, 'check_and_apply_truncation'):
                        # 构建 system prompt 用于 Truncation 估算
                        system_prompt = self._build_system_prompt(state, gen, req_ctx)
                        tools = self._get_tools_schema(state, gen)

                        # 执行 Truncation 检查
                        truncated = await conv.check_and_apply_truncation(
                            system_prompt=system_prompt,
                            tools=tools
                        )

                        if truncated:
                            # 如果执行了压缩，更新 history
                            self._sync_history_from_conversation(state)
                            logger.info("✅ Truncation applied and conversation compacted")

                    # 1. Build System Prompt & Update Conversation
                    # ==============================================
                    prompt = self._build_system_prompt(state, gen, req_ctx)
                    
                    # 使用 Conversation 的 update_system_prompt 方法更新系统提示词（临时消息）
                    conv = self._get_conversation(state)
                    conv.update_system_prompt(prompt)
                    
                    # 2. 准备 LLM 推理消息
                    # ==============================
                    # Deep Thinking 指令定义
                    deep_thinking_instruction = """
                    \n\n--- SYSTEM OVERRIDE: DEEP THINKING PROTOCOL ---
                    You must strictly follow this two-phase output format, regardless of any previous constraints about "JSON only" or "conciseness":

                    **PHASE 1: REASONING (Internal Monologue)**
                    - You MUST start your response with a `<thinking>` block.
                    - Explain your reasoning step-by-step inside this block.
                    - This phase is MANDATORY and acts as a scratchpad.

                    **PHASE 2: FINAL RESPONSE (User Fulfillment)**
                    - After closing `</thinking>` tag, proceed to answer user's request.
                    - IN THIS PHASE, you must strictly adhere to user's original formatting requirements (e.g., JSON only, Python code only, short answer).
                    - Do NOT output thinking block if it violates user's format; instead, output it *before* user's format content.

                    **Example Structure:**
                    <thinking>
                    ... analysis ...
                    </thinking>
                    { "result": "This is JSON that user asked for" }
                    """ if req_ctx.deep_thinking else None

                    # 使用 Conversation 的 for_llm 方法生成用于 LLM 的消息列表
                    input_messages = conv.for_llm(
                        deep_thinking=req_ctx.deep_thinking,
                        deep_thinking_instruction=deep_thinking_instruction
                    )
                    
                    # 3. 获取工具 schema
                    # ==============================
                    tools = self._get_tools_schema(state, gen)
                    logger.info(f"🔧 Available tools count: {len(tools) if tools else 0}, active_skill: {state.active_skill}")
                    
                    # 4. Call BaseLLM
                    # ===============
                    # 发送 TOKEN_START 事件(LLM 开始生成)
                    # await self._emit_event(EventType.TOKEN_START, {})

                    full_content_text = ""
                    received_tool_requests: List[ToolRequest] = []
                    # [解析器变量] 用于解析 Prompt 模式下的 <thinking> 标签
                    parse_state = "normal" # normal, check_open, thinking, check_close
                    tag_buffer = ""        # 缓存标签字符 (如 "<thi")

                    thinking = ThinkingTracker(self._emit_event)
                    async with self.event_scope(EventType.TOKEN_START, EventType.TOKEN_END):
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
                                            await thinking.start()
                                            await thinking.token(c.thinking)

                                        # =================================================
                                        # Case B: 普通文本 (需处理 Prompt 模式下的标签)
                                        # =================================================
                                        elif isinstance(c, TextContent):
                                            text_chunk = c.text
                                            
                                            # 1. 如果没开 deep_thinking，直接作为普通文本发送
                                            if not req_ctx.deep_thinking:
                                                await thinking.end()
                                                await self._emit_event(EventType.TOKEN, c.text)
                                                full_content_text += c.text
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
                                                        await self._emit_event(EventType.TOKEN, char)
                                                
                                                # --- 状态 2: 检查开始标签 <thinking> ---
                                                elif parse_state == "check_open":
                                                    tag_buffer += char
                                                    if tag_buffer == "<thinking>":
                                                        await thinking.start()
                                                        parse_state = "thinking"
                                                        tag_buffer = ""
                                                    elif not "<thinking>".startswith(tag_buffer):
                                                        await thinking.end()
                                                        full_content_text += tag_buffer
                                                        await self._emit_event(EventType.TOKEN, tag_buffer)
                                                        parse_state = "normal"
                                                        tag_buffer = ""
                                                
                                                # --- 状态 3: 思考内容中 ---
                                                elif parse_state == "thinking":
                                                    if char == "<":
                                                        parse_state = "check_close"
                                                        tag_buffer = "<"
                                                    else:
                                                        await thinking.token(char)
                                                
                                                # --- 状态 4: 检查结束标签 </thinking> ---
                                                elif parse_state == "check_close":
                                                    tag_buffer += char
                                                    if tag_buffer == "</thinking>":
                                                        await thinking.end()
                                                        parse_state = "normal"
                                                        tag_buffer = ""
                                                    elif not "</thinking>".startswith(tag_buffer):
                                                        await thinking.token(tag_buffer)
                                                        parse_state = "thinking" # 回到思考状态
                                                        tag_buffer = ""

                                        # =================================================
                                        # Case C: 工具请求
                                        # =================================================
                                        elif isinstance(c, ToolRequest):
                                            await thinking.end()
                                            received_tool_requests.append(c)
                        finally:
                            # 无论何种退出路径
                            await thinking.end()                        
                    

                    # 如果解析器卡在 buffer 里（例如流中断导致只输出了 "<think"），把残余发出来
                    if tag_buffer:
                        if parse_state in ["check_open", "normal"]:
                            full_content_text += tag_buffer
                            await self._emit_event(EventType.TOKEN, tag_buffer)
                        else:
                            await thinking.token(tag_buffer)

                    # # 发送 TOKEN_END 事件（LLM 生成结束）
                    # await self._emit_event(EventType.TOKEN_END, {})
                            
                    logger.info(f"📊 LLM returned: text_len={len(full_content_text)}, tool_requests={len(received_tool_requests)}")
                    
                    if received_tool_requests:
                        # 将工具请求序列化存储到回合结构化信息中
                        if "tool_requests" not in state.turn_structured_info:
                            state.turn_structured_info["tool_requests"] = []
                            
                        for req in received_tool_requests:
                            state.turn_structured_info["tool_requests"].append(req)

                        assistant_content = []
                        if full_content_text:
                            assistant_content.append(TextContent(text=full_content_text))
                        assistant_content.extend(received_tool_requests)
                        await self.add_message(state.session_id, Message(role=Role.ASSISTANT, content=assistant_content).only_agent_visible(), state)
                    
                        
                    # Create the finalized assistant message and dump to dict for DB
                    # assistant_msg = Message(role=Role.ASSISTANT, content=assistant_content)
                    # await self.add_message(state.session_id, assistant_msg,state)
                    
                    # 5. Handle Tools or Stop
                    # =======================
                    if not received_tool_requests:
                        assistant_content = []
                        if full_content_text:
                            assistant_content.append(TextContent(text=full_content_text))
                        
                        # 将工具请求序列化存储到回合结构化信息中
                        if "tool_responses" not in state.turn_structured_info:
                            state.turn_structured_info["tool_responses"] = []
                            
                        if state and state.turn_structured_info and state.turn_structured_info["tool_responses"]:
                            assistant_content.extend(state.turn_structured_info["tool_responses"])
                        
                        await self.add_message(state.session_id, Message(role=Role.ASSISTANT, content=assistant_content), state)
                        state.status = AgentStatus.IDLE
                        self._schedule_state_save(state.session_id, state)
                        break # Turn complete

                    # Execute Tools (传递 gen)
                    exec_results = await self._execute_tools_concurrent(received_tool_requests, state, gen, req_ctx)

                    if state.status == AgentStatus.WAITING_APPROVAL:
                        # 这种情况下，我们需要保留 WAITING 状态并退出 Task
                        logger.info("Task suspended for approval.")
                        return # Pause execution
    

                    # 创建带有 artifact 信息的消息 metadata
                    # 初始化工具响应列表
                    if "tool_responses" not in state.turn_structured_info:
                        state.turn_structured_info["tool_responses"] = []

                    for i, (req, resp) in enumerate(zip(received_tool_requests, exec_results)):
                        # Construct Tool Response Message using Goose models
                        # Note: OpenAIProvider._prepare_messages will separate this into the correct format
                        tool_msg = Message.tool_response(resp)

                        # 存入数据库（add_message 会自动同步到 history）
                        await self.add_message(state.session_id, tool_msg, state)


                        state.turn_structured_info["tool_responses"].append(resp)
                        
                    self._schedule_state_save(state.session_id, state)

                
            except Exception as e:
                    # 统一异常处理格式
                    error_msg = str(e)
                    error_type = type(e).__name__
                    logger.error(f"LLM Error [{error_type}]: {error_msg}")
                    await self._emit_event(EventType.ERROR, {
                        "error": error_msg,
                        "error_type": error_type
                    })
                    state.status = AgentStatus.ERROR
                    raise
            finally:
                await self._ensure_state_saved(session_id, state)


    async def _process_approval(self, state: AgentState, data: Dict, gen: AgentGeneration) -> bool:
        if state.status != AgentStatus.WAITING_APPROVAL or not state.pending_tool_call: return False
        tool = state.pending_tool_call
        if data.get("approved"):
            # 传递 gen
            res = await self._exec_tool_func(tool['name'], tool['args'], state, gen)
            # Add Tool Response
            tool_msg = Message.tool(text=res or "", tool_call_id=tool['id'])
            # 存入数据库（add_message 会自动同步到 history）
            await self.add_message(state.session_id, tool_msg, state)
        else:
            tool_msg = Message.tool(text=f"Rejected: {data.get('feedback')}", tool_call_id=tool['id'])
            # 存入数据库（add_message 会自动同步到 history）
            await self.add_message(state.session_id, tool_msg, state)
        
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
        """同步关闭方法(向后兼容)"""
        if self.watcher:
            self.watcher.stop()

        # 尝试关闭当前 generation
        if self.current_generation:
            asyncio.create_task(self.current_generation.drain_and_close())

        logger.info("Agent shut down gracefully.")

    async def cancel_task(self, session_id: int) -> bool:
        """
        取消指定会话的任务。

        Args:
            session_id: 会话 ID

        Returns:
            是否成功取消
        """
        try:
            # 1. 加载会话状态
            state_data = await self.db.load_state(session_id)
            if not state_data:
                logger.warning(f"Session {session_id} not found for cancellation")
                return False

            state = AgentState(**state_data)

            # 2. 检查会话是否正在运行
            if state.status != AgentStatus.RUNNING:
                logger.info(f"Session {session_id} is not running (status: {state.status}), cannot cancel")
                return False

            # 3. 设置取消状态
            state.status = AgentStatus.CANCELLED

            # 4. 清空意图队列
            state.intent_queue = []

            # 5. 保存状态
            await self.db.save_state(session_id, state.model_dump(exclude_none=True))

            # 6. 发送取消事件
            await self._emit_event(EventType.CANCELLED, {
                "msg": "Task cancelled by user",
                "session_id": session_id
            }, session_id=session_id)

            logger.info(f"Task cancelled for session {session_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel task for session {session_id}: {e}", exc_info=True)
            return False

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