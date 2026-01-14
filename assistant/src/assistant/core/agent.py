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
from ..conversation import Message, Role, TextContent, ToolRequest, ToolResponse, CallToolResult, RawContent

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

# Intent Imports
from ..intent.recognizer import IntentRecognizer
from ..intent.strategy import IntentExecutor, ExecutionMode, TerminationAction
from ..intent.config_loader import IntentConfigLoader
from .watcher import ConfigWatcher
from .generation import AgentGeneration
from .context import RequestContext
from .hooks import HookManager, AgentHook, HookContext, HookAction
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
    
    
    async def add_message(self, session_id: int, msg: Message, state: Optional[AgentState] = None, metadata: Dict = None):
        if state:
            state.history.append(msg.model_dump())
        await self.db.add_message(session_id, msg.role, msg.content, metadata)
    
    # =========================================================================
    # Phase 1: Intent Processing (Unchanged logic, just context)
    # =========================================================================

    async def _handle_intent_phase(self, user_input: str, state: AgentState, gen: AgentGeneration) -> Optional[str]:
        if not gen.intent_recognizer:
            return None

        await self.events.emit(EventType.STATE_CHANGE, {"msg": "🤔 Analyzing intent..."})
        
        # Note: IntentRecognizer.recognize now accepts intent_session dict
        results, updated_session = await gen.intent_recognizer.recognize(
            user_input=user_input,
            session_state=state.intent_session,
            background_info=f"Active Skill: {state.active_skill}"
        )
        
        state.intent_session = updated_session
        await self.db.save_state(state.session_id, state.model_dump())

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

        config = gen.intent_executor.get_config(primary.intent)
        if not config: return None

        ctx = create_context(state.session_id, state=state, db=self.db, ai_services=gen.ai_services)
        pre_res = await gen.intent_executor.execute_pre_hook(primary.intent, primary.entities, ctx)
        if pre_res: return pre_res

        final_res = None
        should_stop = False

        if config.mode == ExecutionMode.DIRECT:
            res = await gen.intent_executor.execute_direct(primary.intent, primary.entities, ctx)
            final_res = str(res)
            should_stop = True
        elif config.mode == ExecutionMode.CHAIN:
            res = await gen.intent_executor.execute_chain(primary.intent, primary.entities, ctx)
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
                    if gen.intent_recognizer:
                        intent_def = gen.intent_recognizer._intent_map.get(primary.intent)
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
            allowed = gen.intent_executor.get_allowed_tools(
                primary.intent,
                gen.skill_loader.get_available_skills_list() if gen.skill_loader else []
            )
            state.shared_memory["_restricted_tools"] = allowed
            should_stop = False

        if config.on_complete == TerminationAction.STOP:
            return final_res
        
        return final_res if should_stop else None

    # =========================================================================
    # Phase 2: Tool Execution (Unchanged)
    # =========================================================================
    
    async def _exec_tool_func(self, tool_name: str, tool_args: Dict, state: AgentState, gen: AgentGeneration, req_ctx: RequestContext) -> str:
        # 使用 gen.core_tools 和 gen.skill_loader
        func = gen.core_tools.get(tool_name)
        if not func and gen.skill_loader:
            func = gen.skill_loader.get_tool_func(tool_name)
        
        if not func: return f"Error: Tool '{tool_name}' not found."

        # 2. 实例化执行器
        # 这里注入了当前会话的所有上下文资源
        executor = ToolExecutor(
            session_id=state.session_id,
            state=state,
            db=self.db,
            ai_services=gen.ai_services,
            request_context=req_ctx
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
        使用 ArtifactManager 存储数据以支持分层存储和自动清理。
        """
        parts = []

        # 检查是否启用 ArtifactManager
        artifact_mgr = get_manager()
        use_artifact_manager = artifact_mgr is not None and artifact_mgr.config.enabled

        for c in result.content:
            # 如果包含结构化数据 (Artifact)
            if c.data is not None:
                # 1. 生成唯一的 Artifact ID
                aid = f"art_{uuid.uuid4().hex[:8]}"

                if use_artifact_manager:
                    # 2. 使用 ArtifactManager 存储 (分层存储: 内存/文件/混合)
                    try:
                        ref = await artifact_mgr.store(
                            session_id=state.session_id,
                            artifact_id=aid,
                            artifact_type=c.type or "dataset",
                            data=c.data,
                            text=c.text or "",
                        )

                        # 3. 存储引用到 shared_memory (轻量级，只包含元数据)
                        state.shared_memory[aid] = ref.to_dict()

                        # 4. 触发 Artifact 事件 (前端收到后立即渲染图表/表格)
                        # 注意：不再发送完整 data，前端需要时通过 API 获取
                        artifact_payload = {
                            "id": aid,
                            "type": ref.type,
                            "text": ref.text,
                            "size": ref.size,
                            "storage_type": ref.storage_type.value,
                        }
                        await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                    except Exception as e:
                        logger.error(f"Failed to store artifact {aid} with ArtifactManager: {e}", exc_info=True)
                        # 回退到原始方式
                        artifact_payload = {
                            "id": aid,
                            "type": c.type or "dataset",
                            "data": c.data,
                            "text": c.text or "",
                        }
                        state.shared_memory[aid] = artifact_payload
                        await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                else:
                    # 回退到原始方式 (直接存入 shared_memory)
                    artifact_payload = {
                        "id": aid,
                        "type": c.type or "dataset",
                        "data": c.data,
                        "text": c.text or "",
                    }
                    state.shared_memory[aid] = artifact_payload
                    await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)

                # 5. 返回给 LLM 的只是一个引用，防止 Token 爆炸
                parts.append(f"{c.text or 'Generated Data'}\n[Artifact ID: {aid}]")
            else:
                # 纯文本部分
                parts.append(c.text or "")

        return "\n\n".join(parts)

    async def _emit_tool_artifacts(self, result: CallToolResult, state: AgentState) -> None:
        """
        只触发 TOOL_ARTIFACT 事件，不返回文本（用于 Hook 拦截场景）
        Hook 拦截时，用户看到的应该是纯文本响应，而 artifact 数据只用于前端渲染
        使用 ArtifactManager 存储数据以支持分层存储和自动清理。
        """
        artifact_count = 0

        # 检查是否启用 ArtifactManager
        artifact_mgr = get_manager()
        use_artifact_manager = artifact_mgr is not None and artifact_mgr.config.enabled

        for c in result.content:
            # 如果包含结构化数据 (Artifact)
            if c.data is not None:
                # 1. 生成唯一的 Artifact ID
                aid = f"art_{uuid.uuid4().hex[:8]}"

                if use_artifact_manager:
                    # 2. 使用 ArtifactManager 存储
                    try:
                        ref = await artifact_mgr.store(
                            session_id=state.session_id,
                            artifact_id=aid,
                            artifact_type=c.type or "dataset",
                            data=c.data,
                            text=c.text or "",
                        )

                        # 3. 存储引用到 shared_memory (轻量级)
                        state.shared_memory[aid] = ref.to_dict()

                        # 4. 触发 Artifact 事件（前端渲染）
                        artifact_payload = {
                            "id": aid,
                            "type": ref.type,
                            "text": ref.text,
                            "size": ref.size,
                            "storage_type": ref.storage_type.value,
                        }
                        logger.info(f"🎨 Emitting TOOL_ARTIFACT: {aid}, type={c.type}")
                        await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                        artifact_count += 1
                    except Exception as e:
                        logger.error(f"Failed to store artifact {aid} with ArtifactManager: {e}", exc_info=True)
                        # 回退到原始方式
                        artifact_payload = {
                            "id": aid,
                            "type": c.type or "dataset",
                            "data": c.data,
                            "text": c.text or "",
                        }
                        state.shared_memory[aid] = artifact_payload
                        await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                        artifact_count += 1
                else:
                    # 回退到原始方式 (直接存入 shared_memory)
                    artifact_payload = {
                        "id": aid,
                        "type": c.type or "dataset",
                        "data": c.data,
                        "text": c.text or "",
                    }
                    state.shared_memory[aid] = artifact_payload
                    logger.info(f"🎨 Emitting TOOL_ARTIFACT: {aid}, type={c.type}")
                    await self.events.emit(EventType.TOOL_ARTIFACT, artifact_payload)
                    artifact_count += 1

        if artifact_count > 1:
            logger.warning(f"⚠️ Multiple artifacts ({artifact_count}) emitted in single CallToolResult")

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
        
        # 响应 Deep Thinking 开关
        if req_ctx.deep_thinking:
            prompt += "\n\n🚀 **DEEP THINKING MODE ACTIVATED**\n"
            prompt += "You must think step-by-step. Break down the problem into atomic parts before answering.\n"
            prompt += "Use Chain-of-Thought reasoning."
            
            
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
        
        # 注入页面上下文 (让 Agent 知道用户正在看什么)
        if req_ctx.page_content:
            page_summary = str(req_ctx.page_content)[:1000] # 截断防止太长
            prompt += f"\n\nUser is currently viewing:\n{page_summary}...\n"
            
        return prompt

    async def _execute_tools_concurrent(self, tool_requests: List[ToolRequest], state: AgentState, gen: AgentGeneration, req_ctx: RequestContext) -> Dict:
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
                # 调用核心执行逻辑，传递 gen
                result_str = await self._exec_tool_func(name, args, state, gen, req_ctx)
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
            is_sens = gen.config.is_sensitive(name)
            if gen.skill_loader: is_sens |= gen.skill_loader.is_sensitive(name)
            
            if is_sens:
                state.status = AgentStatus.WAITING_APPROVAL
                state.pending_tool_call = {"name": name, "args": args, "id": call_id}
                await self.db.save_state(state.session_id, state.model_dump())
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
        # 如果是 resume，可能没有 request 数据，需要考虑是否从 state 恢复或使用默认值
        req_ctx = RequestContext()
        if input_data:
            if isinstance(input_data, dict):
                req_ctx = RequestContext(
                    token=input_data.get("token"),
                    server_type=input_data.get("server_type"),
                    file_path=input_data.get("file_path"),
                    page_content=input_data.get("page_content"),
                    deep_thinking=input_data.get("deep_thinking"),
                    is_deep_research=input_data.get("is_deep_research")
            )
            
        # 使用 context manager 自动管理计数
        async with current_gen_ref.context_scope() as gen:
            # 如果提供了 user_id，则加载该用户的会话
            if user_id:
                state_data = await self.db.load_state_for_user(user_id, session_id)
            else:
                state_data = await self.db.load_state(session_id)

            state = AgentState(**state_data) if state_data else AgentState(session_id=session_id)
            
            # [关键步骤 A]：处理上下文数据 (Input Context)
            # 如果有上传文件或页面内容，将其放入 Shared Memory，以便工具（如 read_file）可以访问
            if req_ctx.file_path:
                state.shared_memory["_current_file_path"] = req_ctx.file_path
                # 可选：生成一条系统消息告知 Agent
                # state.history.append({"role": "system", "content": f"User uploaded file: {req_ctx.file_path}"})
            
            if req_ctx.page_content:
                state.shared_memory["_page_context"] = req_ctx.page_content

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

                                # 如果 response_data 是 CallToolResult，需要发送 artifact 事件
                                # 但不使用 _format_and_emit_tool_result 的返回值（包含 artifact ID）
                                if hook_result.response_data and isinstance(hook_result.response_data, CallToolResult):
                                    await self._emit_tool_artifacts(hook_result.response_data, state)

                                await self.add_message(state.session_id, Message.assistant(final_response), state)
                                
                                
                                await self.events.emit(EventType.TOKEN, final_response)
                                await self.db.save_state(state.session_id, state.model_dump())

                                # 执行请求结束 Hooks
                                await self.hook_manager.on_request_end(hook_ctx, final_response)
                                return

                            elif hook_result.action == HookAction.MODIFY:
                                # Hook 修改了输入
                                user_input = hook_result.modified_input
                                hook_ctx.user_input = user_input

                    # 更新状态和历史
                    state.status = AgentStatus.RUNNING
                    state.history.append({"role": "user", "content": user_input})

                    # Intent Phase (传递 gen)
                    direct_res = await self._handle_intent_phase(user_input, state, gen)
                    if direct_res:
                        state.history.append({"role": "assistant", "content": direct_res})
                        await self.events.emit(EventType.TOKEN, direct_res)
                        await self.db.save_state(state.session_id, state.model_dump())

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
                input_messages = [Message.model_validate(h) for h in state.history]
                
                # 传递 gen
                tools = self._get_tools_schema(state, gen)
                logger.info(f"🔧 Available tools count: {len(tools) if tools else 0}, active_skill: {state.active_skill}")

                # 3. Call BaseLLM
                # ===============
                full_content_text = ""
                received_tool_requests: List[ToolRequest] = []
                
                try:
                    # Use astream instead of OpenAI specific create
                    # 传递 gen.llm
                    async for partial_msg, usage in gen.llm.astream(
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
                # Use by_alias=True to preserve camelCase aliases for proper deserialization
                state.history.append(assistant_msg.model_dump(exclude_none=True, by_alias=True))

                # 5. Handle Tools or Stop
                # =======================
                if not received_tool_requests:
                    await self.db.save_state(state.session_id, state.model_dump())
                    break # Turn complete

                # Execute Tools (传递 gen)
                results_map = await self._execute_tools_concurrent(received_tool_requests, state, gen, req_ctx)

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
                    
                    await self.add_message(state.session_id, "tool", res_str, state)

                await self.db.save_state(state.session_id, state.model_dump())


    async def _process_approval(self, state: AgentState, data: Dict, gen: AgentGeneration) -> bool:
        if state.status != AgentStatus.WAITING_APPROVAL or not state.pending_tool_call: return False
        tool = state.pending_tool_call
        if data.get("approved"):
            # 传递 gen
            res = await self._exec_tool_func(tool['name'], tool['args'], state, gen)
            # Add Tool Response
            state.history.append(Message.tool(text=res, tool_call_id=tool['id']).model_dump(exclude_none=True, by_alias=True))
        else:
            state.history.append(Message.tool(text=f"Rejected: {data.get('feedback')}", tool_call_id=tool['id']).model_dump(exclude_none=True, by_alias=True))

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