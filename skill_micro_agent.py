import os
# ================= ADD START =================
from dotenv import load_dotenv

# 加载当前目录下的 .env 文件
# override=True 表示如果系统环境变量里已有该值，优先使用 .env 里的覆盖
load_dotenv(override=True)
import time
import yaml
import json
import sqlite3
import importlib
import asyncio
import uuid
from typing import Dict, List, Any, Optional, Callable, Awaitable
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime
import logging
from fastapi import FastAPI, BackgroundTasks, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, create_model, ValidationError
from openai import AsyncOpenAI
from ai_services import BaseAIService,OpenAI_Service
from agent_skills.types import CallToolResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= 1. 事件驱动核心 (Event Bus) =================
# 这是本次升级的核心：将“发生什么”和“如何传输”解耦

class EventType(str, Enum):
    TOKEN = "token"                 # 流式文本
    TOOL_START = "tool_start"       # 工具开始
    TOOL_END = "tool_end"           # 工具结束
    TOOL_ARTIFACT = "tool_artifact"     # 工具输出
    STATE_CHANGE = "state_change"   # 状态变更 (Intent/Plan)
    APPROVAL_REQ = "approval_req"   # 需要审批
    ERROR = "error"                 # 错误

class Event(BaseModel):
    type: str
    data: Any
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp())

class EventManager:
    """简单的异步事件管理器"""
    def __init__(self):
        self._listeners: List[Callable[[Event], Awaitable[None]]] = []

    def subscribe(self, listener: Callable[[Event], Awaitable[None]]):
        self._listeners.append(listener)

    async def emit(self, event_type: EventType, data: Any):
        event = Event(type=event_type, data=data)
        for listener in self._listeners:
            await listener(event)

# ================= 2. 配置与状态 (Config & State) =================

class ConfigLoader:
    def __init__(self, path="agent_config.yaml"):
        # (同上一版，省略加载逻辑，保留动态模型构建)
        with open(path, 'r', encoding='utf-8') as f:
            self.raw = yaml.safe_load(f)
        self.system = self.raw.get('system', {})
        self.intents = self.raw.get('intents', {})
        self.tools_conf = self.raw.get('tools_config', {})
        self.intent_models = self._build_intent_models()
        self.security = self.raw.get('security', {})
        self.sensitive_tools = set(self.security.get('sensitive_tools', []))
        self.tool_func_map = {}
        self._load_all_tools()

    def _build_intent_models(self):
        models = {}
        for name, data in self.intents.items():
            fields = {k: (eval(v['type']) if v['type'] in ['str','int','float','bool'] else str, Field(v.get('default', ...), description=v.get('description'))) for k, v in data.get('slots', {}).items()}
            models[name] = create_model(f"Intent_{name}", **fields)
        return models

    def _load_all_tools(self):
        paths = set(self.raw.get('global_tools', []))
        for i in self.intents.values(): paths.update(i.get('allowed_tools', []))
        for path in paths:
            try:
                mod, func = path.rsplit('.', 1)
                self.tool_func_map[path] = getattr(importlib.import_module(mod), func)
            except: pass
    
    def is_sensitive(self, tool_name: str) -> bool:
        """检查工具是否敏感"""
        return tool_name in self.sensitive_tools

DB_PATH = "agent_ultra.db"

class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"

    
class AgentState(BaseModel):
    session_id: str
    status: AgentStatus = AgentStatus.IDLE
    history: List[Dict] = []
    current_intent: Optional[str] = None
    current_plan: List[str] = [] 
    pending_tool_call: Optional[Dict] = None
    title: str = "New Chat"
    shared_memory: Dict[str, Any] = {}
    
    # [新增] 最后一次活跃时间，方便前端展示
    updated_at: float = Field(default_factory=lambda: datetime.now().timestamp())
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_json(self): return self.model_dump_json()
    @classmethod
    def from_json(cls, j): return cls.model_validate_json(j)

# (DB操作函数 init_db, db_ops 同上一版，此处省略以节省篇幅)
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        # [关键优化] 开启 WAL 模式，支持并发读写，大幅减少锁等待
        conn.execute("PRAGMA journal_mode=WAL;") 
        # [优化] 开启同步模式为 NORMAL，牺牲极小概率的数据安全性换取写入性能
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
# [升级] DB 操作：增加获取记忆列表的功能
def db_ops(op, **kwargs):
    with sqlite3.connect(DB_PATH) as conn:
        if op=="save": 
            # 更新 updated_at
            kwargs['state'].updated_at = datetime.now().timestamp()
            kwargs['state'].last_active = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT OR REPLACE INTO sessions (id, state) VALUES (?, ?)", (kwargs['state'].session_id, kwargs['state'].to_json()))
        elif op=="load": 
            row = conn.execute("SELECT state FROM sessions WHERE id = ?", (kwargs['id'],)).fetchone()
            return AgentState.from_json(row[0]) if row else AgentState(session_id=kwargs['id'])
        # --- 新增操作 ---
        elif op=="get_memories":
            c = conn.execute("SELECT id, content, created_at FROM memories WHERE user_id = ? ORDER BY created_at DESC", (kwargs['uid'],))
            return [{"id": r[0], "content": r[1], "created_at": r[2]} for r in c.fetchall()]
        elif op=="clear_history":
            conn.execute("DELETE FROM sessions WHERE id = ?", (kwargs['id'],))

        elif op == "list_sessions":
            # [修改] 返回完整的元数据列表，而不仅仅是 ID
            c = conn.execute("SELECT state FROM sessions")
            sessions = []
            for row in c.fetchall():
                try:
                    # 只解析关键字段以提高性能，或者完全解析
                    # 这里为了简单直接解析整个 state
                    state_dict = json.loads(row[0])
                    sessions.append({
                        "id": state_dict.get("session_id"),
                        "title": state_dict.get("title", "New Chat"),
                        "updated_at": state_dict.get("updated_at", 0)
                    })
                except:
                    pass
            # 按时间倒序排列 (最新的在最上面)
            sessions.sort(key=lambda x: x['updated_at'], reverse=True)
            return sessions
        
        
# ================= 3. 核心工具 (包括计划管理) =================
def switch_intent(intent_name: str, _ctx=None): return f"SWITCHED_TO:{intent_name}"
def submit_intent(slots: Dict, _ctx=None): return "SUBMITTED"

# [新增] 计划管理工具
def update_plan(steps: List[str], _ctx=None):
    """Update or create a step-by-step execution plan."""
    return f"PLAN_UPDATED:{json.dumps(steps)}"

# ================= 4. Ultra MicroAgent =================

class MicroAgent:
    def __init__(self, config: ConfigLoader):
        self.config = config
        self.events = EventManager()
        
        # [NEW] 初始化符合 Anthropic 标准的技能加载器
        # 确保你已经有了上一轮提供的 skill_loader.py
        
        # 从配置中读取白名单
        enabled_list = self.config.raw.get('agent', {}).get('enabled_skills', None)
        
        self.ai_services = OpenAI_Service()
        
        from skill_loader import AnthropicSkillLoader
        
        self.skill_loader = AnthropicSkillLoader(skills_dir="agent_skills",ai_services=self.ai_services,sensitive_tools=config.sensitive_tools, enabled_skills=enabled_list)
        
        # 初始化 OpenAI 客户端
        model_conf = self.config.raw.get('model', {})
        env_var_name = model_conf.get('api_key_env', 'OPENAI_API_KEY')
        api_key = os.getenv(env_var_name)
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=model_conf.get('base_url')
        )
        
        # [NEW] 核心控制工具集
        # 我们保留 update_plan (作为通用能力)，但替换了 intent 相关工具
        self.core_tools = {
            "submit_intent":submit_intent,
            "update_plan": update_plan             # 保留：计划能力
        }

    
    async def _exec_tool_func(self, tool_name: str, tool_args: Dict, state: AgentState):
        """
        执行工具函数，支持依赖注入 (State Injection)
        """
        # 1. 查找工具实现
        func = self.core_tools.get(tool_name)
        if not func:
            # [Refactored] 使用 Loader 提供的接口查找
            func = self.skill_loader.get_tool_func(tool_name)
        
        if not func:
            return f"Error: Tool '{tool_name}' not found."

        # 2. [关键] 依赖注入
        # 使用 inspect 检查函数签名，看它是否需要 _state 或 _ctx
        import inspect
        try:
            sig = inspect.signature(func)
        except ValueError:
            # 如果是内置 C 函数等无法签名的，直接调用
            return func(**tool_args)

        call_args = tool_args.copy()

        # 如果函数定义了 '_state' 参数，注入当前 AgentState
        if '_state' in sig.parameters:
            call_args['_state'] = state
        
        # 如果函数定义了 '_ctx' 参数，注入上下文 (如 session_id)
        if '_ctx' in sig.parameters:
            call_args['_ctx'] = {"session_id": state.session_id}

        # 2. 注入 AI 服务 (Embedding/Rerank)
        if "_ai" in sig.parameters:
            call_args["_ai"] = self.skill_loader.ai_services
            
        # 3. [核心修改] 执行逻辑
        try:
            if inspect.iscoroutinefunction(func):
                # A. 如果是异步函数 (async def)，直接 await
                # 这样可以利用 EventLoop 的并发能力
                result = await func(**call_args)
            else:
                # B. 如果是同步函数 (def)，放入线程池执行
                # 这一点至关重要！如果直接运行同步的 time.sleep 或 requests，
                # 会卡死整个 Server，导致其他用户的请求无法响应。
                result = await asyncio.to_thread(func, **call_args)
            
            # === 适配 CallToolResult ===
            if isinstance(result, CallToolResult):
                final_llm_text_parts = []
                for item in result.content:
                    # 1. 处理 Artifact 数据
                    if item.data is not None:
                        # 生成 ID
                        art_id = f"art_{uuid.uuid4().hex[:8]}"
                        # 存入 Shared Memory (Artifact Store)
                        state.shared_memory[art_id] = item.data
                        # 发送前端事件 (用于渲染图表/表格)
                        await self.events.emit(EventType.TOOL_ARTIFACT, {
                            "id": art_id,
                            "type": item.type,
                            "title": f"Output from {tool_name}",
                            "view": item.text,
                            "data": item.data
                        })
                        item_view = f"{item.text}\n[Artifact ID: {art_id}]"
                        final_llm_text_parts.append(item_view)
                    else:
                        # 纯文本
                        final_llm_text_parts.append(item.text or "")
                return "\n\n".join(final_llm_text_parts)
            return result
        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {str(e)}")
            return f"Error executing tool '{tool_name}': {str(e)}"
        
    # --- 辅助方法：生成 Schema ---
    def _func_to_schema(self, func, name_override=None):
        """
        辅助函数：将 Python 函数转换为 OpenAI Tool Schema
        """
        name = name_override or func.__name__
        doc = func.__doc__ or ""
        
        # 简单解析 docstring (生产环境推荐使用 inspect 库做更深度的解析)
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": doc.strip(),
                "parameters": {
                    "type": "object", 
                    # 这里为了简化，默认允许任意参数，或者你可以集成 pydantic.TypeAdapter
                    # 如果 ConfigLoader 里已经解析了参数类型，也可以从那里读取
                    "properties": {}, 
                    "additionalProperties": True 
                }
            }
        }

    def _get_tools_schema(self, state: AgentState) -> List[Dict]:
        """
        构建工具列表：
        1. 始终包含：activate_skill (路由), update_plan (计划), clipboard (记忆)
        2. 根据状态包含：当前 Skill 的专用工具
        """
        schemas = []
        
        # 3. 计划工具
        schemas.append({
            "type": "function", "function": {
                "name": "update_plan",
                "description": "Manage execution steps for complex tasks.",
                "parameters": {"type": "object", "properties": {"steps": {"type": "array", "items": {"type": "string"}}}, "required": ["steps"]}
            }
        })
        
        # 2. Skill 专用工具 (委托给 Loader)
        # [Refactored] Loader 知道当前 Intent 下该显示什么工具
        skill_schemas = self.skill_loader.get_all_tools_schema(state.current_intent)
        schemas.extend(skill_schemas)

        return schemas
    
    def _simple_schema(self, func, name):
        return {"type": "function", "function": {"name": name, "parameters": {"type": "object", "properties": {"a":{"type":"string"}}}}}

    async def process_approve(self,state:AgentState, approval_data: Dict = None):
        if state.status == AgentStatus.WAITING_APPROVAL and state.pending_tool_call:
            tool_data = state.pending_tool_call
            is_approved = approval_data.get("approved", False)
            feedback = approval_data.get("feedback", "")

            if is_approved:
                # ✅ 用户批准：执行被挂起的工具
                await self.events.emit(EventType.STATE_CHANGE, {"msg": f"✅ Approved: {tool_data['name']}"})
                
                # 执行工具
                try:
                    res_str = await self._exec_tool_func(tool_data['name'], tool_data['args'], state)
                except Exception as e:
                    res_str = f"Error executing approved tool: {e}"

                # 记录结果
                state.history.append({
                    "role": "tool", 
                    "tool_call_id": tool_data['id'], 
                    "content": res_str
                })
                # 发送事件通知前端显示结果
                await self.events.emit(EventType.TOOL_END, {"result": res_str})

            else:
                # ❌ 用户拒绝：生成一个拒绝的 Tool Output
                await self.events.emit(EventType.STATE_CHANGE, {"msg": f"❌ Rejected: {tool_data['name']}"})
                
                reject_msg = f"User denied permission to execute '{tool_data['name']}'. Reason: {feedback}"
                
                state.history.append({
                    "role": "tool", 
                    "tool_call_id": tool_data['id'], 
                    "content": reject_msg
                })
                # 即使拒绝，也要发一个 END 事件让前端 loading 停下来
                await self.events.emit(EventType.TOOL_END, {"result": reject_msg})

            # 清除挂起状态，恢复为 RUNNING，继续进入 Phase 2 循环
            state.pending_tool_call = None
            state.status = AgentStatus.RUNNING
            return True
        else:
            await self.events.emit(EventType.ERROR, "Resume failed: No pending approval found.")
            return False
    
    async def run_task(self, session_id: str, user_input: str = None, resume: bool = False, approval_data: Dict = None):
        """
        核心运行循环：负责状态管理、Prompt构建、LLM交互、工具分发与执行。
        """
        # 1. 加载或初始化状态
        state = db_ops("load", id=session_id)
        
        # [新增] 自动标题生成逻辑
        # 如果是新会话(默认标题) 且 有用户输入，则截取输入作为标题
        if user_input and state.title == "New Chat":
            # 截取前 20 个字符，去掉换行
            clean_input = user_input.replace("\n", " ").strip()
            new_title = clean_input[:20] + ("..." if len(clean_input) > 20 else "")
            state.title = new_title
            # 立即保存一次，确保列表刷新能看到
            db_ops("save", state=state)
            
        # =========================================================================
        # Phase 1: 恢复逻辑 (Human-in-the-Loop Resume)
        # =========================================================================
        if resume:
            if not await self.process_approve(state,approval_data):
                return
        else:
            # 正常流程：接收用户输入
            state.status = AgentStatus.RUNNING
            if user_input:
                state.history.append({"role": "user", "content": user_input})

        # 获取模型配置
        model_conf = self.config.raw.get('model', {})
        model_name = model_conf.get('name', 'gpt-4o')
        temperature = model_conf.get('temperature', 0.1)

        # =========================================================================
        # Phase 2: 主循环 (Think -> Act -> Loop)
        # =========================================================================
        while state.status == AgentStatus.RUNNING:
            await asyncio.sleep(0.01)
            # ---------------------------------------------------------------------
            # A. 动态构建 System Prompt (Context Injection)
            # ---------------------------------------------------------------------
            # --- A. Prompt Building (大大简化) ---
            
            # 1. 基础人设
            base_template = self.config.raw['agent']['system_template']
            try:
                static_prompt = base_template.format(name=self.config.raw['agent']['name'])
            except:
                static_prompt = base_template
            
             # [关键] 并发安全协议
            concurrency_protocol = """
                \n=== ⚡ CONCURRENCY & SAFETY RULES ===
                1. **Parallel Execution**: You CAN call multiple tools in a single turn if they are independent (e.g., searching for two different things). This is encouraged for speed.
                2. **Sequential Dependency**: If Tool B requires the output of Tool A, you MUST NOT call them in the same turn. Wait for Tool A's result, then call Tool B in the next turn.
                3. **State Safety**: Do not read and write to the same `clipboard` key in the same turn.
                4. **Routing**: If the user's request is out of scope, use `activate_skill` immediately.
            """
            
            static_prompt += concurrency_protocol
            
              # 2. [Refactored] 技能上下文 + 路由协议 (由 Loader 接管)
            skill_prompt = self.skill_loader.get_context_prompt(state.current_intent)
            
            
            #  获取当前时间 (精确到秒，包含星期)
            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d %H:%M %A")
            dynamic_context = f"""
                \n=== 🔴 DYNAMIC CONTEXT ===
                [System Time]: {time_str}
                [Status]: Intent={state.current_intent or 'Idle'}
            """
            # 4. 记忆与计划 (保留在 Agent 层，因为数据在 state 里)
            memory_str = ""
            if state.shared_memory:
                # 仅展示 Key 和简略值，防止 Token 溢出
                preview = {k: str(v)[:60] + ("..." if len(str(v))>60 else "") for k, v in state.shared_memory.items()}
                memory_str = f"\n\n=== 📋 SHARED CLIPBOARD (Memory) ===\nKeys Available: {list(preview.keys())}\nPreview: {preview}\n(Use `read_from_clipboard` to get full content.)"

            # A.5 当前计划 (Plan)
            plan_str = f"\n\n[Current Plan]: {state.current_plan}" if state.current_plan else ""
            
            dynamic_context += memory_str + plan_str
            
            full_sys_prompt = static_prompt + skill_prompt +dynamic_context
 

            # A.7 更新 History 中的 System Message
            # 始终确保 System Prompt 是第一条，且是最新的
            if not state.history:
                state.history.append({"role": "system", "content": full_sys_prompt})
            elif state.history[0]['role'] == 'system':
                state.history[0]['content'] = full_sys_prompt
            else:
                state.history.insert(0, {"role": "system", "content": full_sys_prompt})

            # ---------------------------------------------------------------------
            # B. 获取可见工具 Schema
            # ---------------------------------------------------------------------
            tools = self._get_tools_schema(state)
            
            # ---------------------------------------------------------------------
            # C. LLM 推理与流式响应
            # ---------------------------------------------------------------------
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=state.history,
                    tools=tools if tools else None,
                    stream=True,
                    temperature=temperature
                )
            except Exception as e:
                await self.events.emit(EventType.ERROR, f"OpenAI API Error: {str(e)}")
                # 遇到 LLM 报错，中断循环，等待用户重试
                break

            full_content = ""
            tool_buffer = []

            # C.1 处理流 (Token & Tool Chunks)
            async for chunk in response:
                delta = chunk.choices[0].delta
                
                # 文本部分
                if delta.content:
                    full_content += delta.content
                    await self.events.emit(EventType.TOKEN, delta.content)
                
                # 工具调用部分
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        if len(tool_buffer) <= tc.index: 
                            tool_buffer.append({"id": "", "name": "", "args": ""})
                        
                        item = tool_buffer[tc.index]
                        if tc.id: item["id"] += tc.id
                        if tc.function.name: item["name"] += tc.function.name
                        if tc.function.arguments: item["args"] += tc.function.arguments

            # C.2 记录 Assistant 回复
            if full_content:
                state.history.append({"role": "assistant", "content": full_content})

            # 如果没有工具调用，说明 LLM 认为该回合结束 (等待用户输入)
            if not tool_buffer:
                db_ops("save", state=state)
                break

            # ---------------------------------------------------------------------
            # D. 工具执行与分发
            # ---------------------------------------------------------------------
            
            # D.1 先将 tool_calls 消息加入历史 (OpenAI 协议要求)
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
            # 3.1 Pre-flight Check: Sensitivity Block
            for t in tool_buffer:
                name = t["name"]
                args_preview = {}
                try: args_preview = json.loads(t["args"])
                except: pass

                is_sensitive = False
                if hasattr(self.skill_loader, 'is_sensitive') and self.skill_loader.is_sensitive(name): is_sensitive = True
                elif self.config.is_sensitive(name): is_sensitive = True

                if is_sensitive:
                    state.status = AgentStatus.WAITING_APPROVAL
                    state.pending_tool_call = {"name": name, "args": args_preview, "id": t["id"]}
                    db_ops("save", state=state)
                    await self.events.emit(EventType.APPROVAL_REQ, {"tool": name, "args": args_preview, "reason": "Sensitive action"})
                    # 🚀 立即中断循环，释放资源，等待 API 再次唤醒
                    return
            
            # 3.2 Task Creation with Wrapper
            async def _concurrency_wrapper(tool_name, tool_args, current_state):
                """Wrapper to capture timing and metadata"""
                start_ts = time.time()
                start_str = time.strftime('%H:%M:%S', time.localtime(start_ts))
                
                # Execute tool (async or sync -> threadpool handled in _exec_tool_func)
                result_str = await self._exec_tool_func(tool_name, tool_args, current_state)
                
                # Check for state changes (side-effects)
                if tool_name == "activate_skill":
                    args_obj = tool_args if isinstance(tool_args, dict) else {}
                    new_skill = args_obj.get("skill_name")
                    if new_skill:
                        current_state.current_intent = new_skill
                        await self.events.emit(EventType.STATE_CHANGE, {"intent": new_skill})
                elif tool_name == "exit_skill":
                    current_state.current_intent = None
                    await self.events.emit(EventType.STATE_CHANGE, {"intent": None})
                elif tool_name == "update_plan":
                    args_obj = tool_args if isinstance(tool_args, dict) else {}
                    steps = args_obj.get("steps", [])
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
            
            pending_tasks = []
            task_indices = []

            for i, t in enumerate(tool_buffer):
                name = t["name"]
                try: args = json.loads(t["args"])
                except: args = {}
                
                await self.events.emit(EventType.TOOL_START, {"name": name, "args": args})

                # Create Coroutine
                coro = _concurrency_wrapper(name, args, state)
                pending_tasks.append(coro)
                task_indices.append(i)

            # 3.3 Launch Concurrent Execution
            results_map = {}
            if pending_tasks:
                # 
                # This gathers all tasks effectively running independent tools in parallel
                task_outputs = await asyncio.gather(*pending_tasks, return_exceptions=True)
                
                for idx, output in enumerate(task_outputs):
                    original_index = task_indices[idx]
                    
                    if isinstance(output, Exception):
                        print(f"❌ System Error in Task {original_index}: {output}")
                        results_map[original_index] = {
                            "result": f"System Error: {str(output)}",
                            "meta": {"error": True}
                        }
                    else:
                        results_map[original_index] = output
                        meta = output["meta"]
                        print(f"✅ [Done] {meta['tool']} | ⏳ {meta['duration']}")

            # 3.4 Process Results & Order Integrity
            for i, t in enumerate(tool_buffer):
                execution_data = results_map.get(i, {"result": "Skipped", "meta": {}})
                
                res_str = execution_data["result"]
                meta_data = execution_data.get("meta", {})

                await self.events.emit(EventType.TOOL_END, {"result": res_str, "meta": meta_data})
                
                state.history.append({
                    "role": "tool",
                    "tool_call_id": t["id"],
                    "content": res_str
                })
                
            # # D.2 遍历执行工具
            # for t in tool_buffer:
            #     name = t["name"]
            #     tid = t["id"]
            #     args_str = t["args"]
                
            #     # 解析 JSON 参数
            #     try:
            #         args = json.loads(args_str)
            #     except json.JSONDecodeError:
            #         args = {} 
            #         await self.events.emit(EventType.ERROR, f"Invalid JSON args for {name}")

            #     # 发送开始事件
            #     await self.events.emit(EventType.TOOL_START, {"name": name, "args": args})
                
            #     tool_result = None

            #     # === 分支 D-1: 核心路由控制 ===
            #     if name == "activate_skill":
            #         new_skill = args.get("skill_name")
            #         state.current_intent = new_skill
                    
            #         # 发送状态变更事件 (前端可用于刷新 UI)
            #         await self.events.emit(EventType.STATE_CHANGE, {"intent": new_skill})
                    
            #         # 返回给 LLM 的观察结果
            #         tool_result = f"SYSTEM: Successfully switched context to Skill '{new_skill}'. Instructions updated."

            #     elif name == "exit_skill":
            #         state.current_intent = None
            #         await self.events.emit(EventType.STATE_CHANGE, {"intent": None})
            #         tool_result = "SYSTEM: Exited skill. Returned to Idle routing mode."

            #     elif name == "update_plan":
            #         state.current_plan = args.get("steps", [])
            #         await self.events.emit(EventType.STATE_CHANGE, {"plan": state.current_plan})
            #         tool_result = f"SYSTEM: Plan updated ({len(state.current_plan)} steps)."

            #     # === 分支 D-2: 业务/通用工具 ===
            #     else:
            #         # 检查敏感性 (HITL)
            #         # 从 SkillLoader 或 Config 判断该工具是否敏感
            #         is_sensitive = False
            #         # 检查 skill.json/yaml 中的属性
            #         if name in self.skill_loader.global_tools:
            #             # 这里假设 skill_loader 有个 helper 方法，或者直接查配置
            #             # 简单起见，这里演示逻辑：
            #             # is_sensitive = self.skill_loader.is_sensitive(name)
            #             pass 
                    
            #         # 另外检查 agent_final.yaml 里的旧配置
            #         if self.config.is_sensitive(name):
            #             is_sensitive = True

            #         if is_sensitive:
            #             # --- HITL 拦截逻辑 ---
            #             state.status = AgentStatus.WAITING_APPROVAL
            #             state.pending_tool_call = {
            #                 "name": name, 
            #                 "args": args, 
            #                 "id": tid
            #             }
            #             db_ops("save", state=state)
            #             await self.events.emit(EventType.APPROVAL_REQ, {"tool": name, "args": args})
                        
            #             # 【重要】必须立即从函数返回，中断后续的所有执行
            #             return 

            #         # --- 正常执行 ---
            #         # 调用 _exec_tool_func，它会自动处理 state 注入 (用于 clipboard)
            #         tool_result = await self._exec_tool_func(name, args, state)

            #     # D.3 记录结果与事件
            #     result_str = str(tool_result)
            #     await self.events.emit(EventType.TOOL_END, {"result": result_str})
                
            #     state.history.append({
            #         "role": "tool",
            #         "tool_call_id": tid,
            #         "content": result_str
            #     })

            # D.4 保存本轮状态
            db_ops("save", state=state)
            
            # 循环继续 -> 回到开头，重新构建 System Prompt (包含新技能指令或剪贴板数据) -> LLM
# ================= 5. FastAPI 适配层 (Bridge) =================

agent = None # Startup 时初始化

@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = MicroAgent(ConfigLoader())
    init_db()
    yield

app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str


class ApprovalRequest(BaseModel):
    approved: bool
    feedback: Optional[str] = "" 

async def event_generator(session_id: str, input_text: str = None, resume: bool = False, approval_data: Optional[ApprovalRequest] = None):
    """
    带调试日志的事件生成器
    """
    print(f"DEBUG: Starting event stream for {session_id}") # 调试日志
    q = asyncio.Queue()

    async def listener(event: Event):
        await q.put(event)

    # 订阅
    agent.events.subscribe(listener)

    # 启动后台任务
    task = asyncio.create_task(agent.run_task(session_id, input_text, resume, approval_data))

    try:
        while True:
            # 设定一个短超时，防止死锁
            try:
                # 优先处理队列里的消息
                event = await asyncio.wait_for(q.get(), timeout=0.05)
                yield json.dumps(event.model_dump(), ensure_ascii=False) + "\n"
                q.task_done()
                continue # 继续取下一个
            except asyncio.TimeoutError:
                # 队列暂时为空，检查任务状态
                pass
            
            # 如果队列空了，且任务结束了，则退出循环
            if q.empty() and task.done():
                if task.exception():
                    print(f"DEBUG: Task failed with {task.exception()}")
                    yield json.dumps({"event": "error", "data": str(task.exception())}) + "\n"
                else:
                    print("DEBUG: Task finished successfully.")
                break
            
            # 稍微让出一下 CPU
            await asyncio.sleep(0.01)

    except Exception as e:
        print(f"DEBUG: Generator Error: {e}")
        yield json.dumps({"event": "error", "data": str(e)}) + "\n"


@app.get("/agent/{session_id}/state")
async def get_agent_state(session_id: str):
    """
    客户端切换会话时，调用此接口获取完整的历史状态 (History, Plan, Intent)
    """
    try:
        # 复用 db_ops 加载状态
        state = db_ops("load", id=session_id)
        # 转换为字典返回
        return state.model_dump() # Pydantic v2
        # 如果是 Pydantic v1 使用: return state.dict()
    except Exception as e:
        # 如果找不到会话或出错，返回 404
        raise HTTPException(status_code=404, detail=str(e))
    
@app.get("/sessions")
async def get_sessions():
    """获取所有会话ID列表"""
    sessions = db_ops("list_sessions")
    # 倒序排列，模拟最近的在前面
    return {"sessions": sessions}

@app.get("/agent/{session_id}/memories")
async def get_agent_memories(session_id: str):
    """
    获取当前会话的长期记忆 (Clipboard / Shared Memory)
    """
    try:
        state = db_ops("load", id=session_id)
        
        # 将 shared_memory 转换为前端可读的列表格式
        memories = []
        if state.shared_memory:
            for key, val in state.shared_memory.items():
                # 截取过长的内容，避免前端显示臃肿
                preview = str(val)[:100] + "..." if len(str(val)) > 100 else str(val)
                memories.append({"content": f"**{key}**: {preview}"})
        
        return memories
    except Exception as e:
        return []

@app.delete("/agent/{session_id}")
async def reset_session(session_id: str):
    """重置会话（清空短期记忆，保留长期记忆）"""
    db_ops("clear_history", id=session_id)
    return {"status": "success", "msg": "Session reset"}


@app.post("/agent/{session_id}/approval")
async def handle_approval(session_id: str, req: ApprovalRequest):
    """
    接收前端的审批结果 (批准/拒绝) 并恢复 Agent 运行
    """
    print(f"🔔 Approval received for {session_id}: {req.approved}")
    
    # 使用 resume=True 重新启动 run_task
    # 并传入用户的决策数据
    return StreamingResponse(
        event_generator(session_id, resume=True, approval_data=req.model_dump()), 
        media_type="application/x-ndjson"
    )


@app.post("/chat/{session_id}")
async def chat(session_id: str, req: ChatRequest):
    # 注意这里变成了 req.message
    return StreamingResponse(
        event_generator(session_id, input_text=req.message), 
        media_type="application/x-ndjson"
    )
    
@app.post("/approve/{session_id}")
async def approve(session_id: str):
    return StreamingResponse(event_generator(session_id, resume=True), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Agent Server running on http://0.0.0.0:8300")
    uvicorn.run(app, host="0.0.0.0", port=8300)