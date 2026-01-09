import os
# ================= ADD START =================
from dotenv import load_dotenv

# 加载当前目录下的 .env 文件
# override=True 表示如果系统环境变量里已有该值，优先使用 .env 里的覆盖
load_dotenv(override=True)

import yaml
import json
import sqlite3
import importlib
import asyncio
from typing import Dict, List, Any, Optional, Callable, Awaitable
from enum import Enum
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, BackgroundTasks, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, create_model, ValidationError
from openai import AsyncOpenAI

# ================= 1. 事件驱动核心 (Event Bus) =================
# 这是本次升级的核心：将“发生什么”和“如何传输”解耦

class EventType(str, Enum):
    TOKEN = "token"                 # 流式文本
    TOOL_START = "tool_start"       # 工具开始
    TOOL_END = "tool_end"           # 工具结束
    STATE_CHANGE = "state_change"   # 状态变更 (Intent/Plan)
    APPROVAL_REQ = "approval_req"   # 需要审批
    ERROR = "error"                 # 错误

class Event(BaseModel):
    type: EventType
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
    
    def is_sensitive(self, tool_name): return self.tools_conf.get(tool_name, {}).get('sensitive', False)

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
    
    # [新增] 最后一次活跃时间，方便前端展示
    last_active: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_json(self): return self.model_dump_json()
    @classmethod
    def from_json(cls, j): return cls.model_validate_json(j)

# (DB操作函数 init_db, db_ops 同上一版，此处省略以节省篇幅)
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        # 1. 创建会话表
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT)")
        
        # 2. [关键修复] 创建记忆表
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit() # 确保提交
        
# [升级] DB 操作：增加获取记忆列表的功能
def db_ops(op, **kwargs):
    with sqlite3.connect(DB_PATH) as conn:
        if op=="save": 
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
        
        # ================= FIX START =================
        # 1. 获取模型配置段
        model_conf = self.config.raw.get('model', {})
        
        # 2. 动态获取 API Key (根据配置文件指定的环境变量名)
        env_var_name = model_conf.get('api_key_env', 'OPENAI_API_KEY')
        api_key = os.getenv(env_var_name)
        
        if not api_key:
            print(f"⚠️ Warning: Environment variable '{env_var_name}' is not set.")

        # 3. 初始化客户端 (应用 base_url)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=model_conf.get('base_url') # 如果 YAML 没配，默认为 None (官方地址)
        )
        # ================= FIX END =================

        # 核心工具集
        self.core_tools = {
            "switch_intent": switch_intent,
            "submit_intent": submit_intent,
            "update_plan": update_plan,
            "cancel_intent": None # 占位，逻辑在 run_task 里处理
        }

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
        根据当前 Agent 状态 (Idle/Locked) 动态构建可见的工具列表
        """
        schemas = []
        
        # =========================================================
        # 1. 记忆相关工具 (全局生效，如果配置开启)
        # =========================================================
        if self.config.system.get('memory_enabled', False):
            # 假设这两个函数已在 __init__ 中注册到 self.core_tools 或 self.config.tool_func_map
            # 这里直接使用硬编码的 Schema 以确保准确性
            schemas.append({
                "type": "function", "function": {
                    "name": "save_memory",
                    "description": "Save important information to long-term memory.",
                    "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]}
                }
            })
            schemas.append({
                "type": "function", "function": {
                    "name": "search_memory",
                    "description": "Search long-term memory for information.",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
                }
            })

        # =========================================================
        # 2. 状态分支逻辑
        # =========================================================
        
        # --- A. IDLE 模式 (路由模式) ---
        if not state.current_intent:
            
            # [Core] switch_intent
            schemas.append({
                "type": "function",
                "function": {
                    "name": "switch_intent",
                    "description": f"Switch context to a specific intent. Available: {list(self.config.intents.keys())}",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "intent_name": {
                                "type": "string", 
                                "enum": list(self.config.intents.keys())
                            }
                        },
                        "required": ["intent_name"]
                    }
                }
            })

            # [Configured] 加载 Global Tools
            # 只有在 Idle 模式下，才能看到全局工具 (取决于你的业务设计，也可设为始终可见)
            for path in self.config.raw.get('global_tools', []):
                if path in self.config.tool_func_map:
                    schemas.append(self._func_to_schema(self.config.tool_func_map[path], path))

        # --- B. LOCKED 模式 (意图锁定) ---
        else:
            # [Core] update_plan (计划执行模式)
            schemas.append({
                "type": "function",
                "function": {
                    "name": "update_plan",
                    "description": "Update execution plan steps when the task is complex.",
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

            # [Core] cancel_intent (退出机制)
            schemas.append({
                "type": "function",
                "function": {
                    "name": "cancel_intent",
                    "description": "Exit the current intent/task and return to idle mode.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            })

            # [Core] submit_intent (动态生成严格校验 Schema)
            # 从 ConfigLoader 预编译的 Pydantic 模型中提取 Schema
            intent_model = self.config.intent_models.get(state.current_intent)
            if intent_model:
                # 获取 Pydantic 生成的 JSON Schema
                model_schema = intent_model.model_json_schema()
                properties = model_schema.get("properties", {})
                required = model_schema.get("required", [])

                schemas.append({
                    "type": "function",
                    "function": {
                        "name": "submit_intent",
                        "description": f"Submit the fully collected data for intent '{state.current_intent}'.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "slots": {
                                    "type": "object",
                                    "description": "The extracted slot data",
                                    "properties": properties, # 注入 Pydantic 字段定义
                                    "required": required
                                }
                            },
                            "required": ["slots"]
                        }
                    }
                })

            # [Configured] 加载 Intent 专属工具
            # 只有在 allowed_tools 列表里的工具才会被 LLM 看到
            current_intent_conf = self.config.intents.get(state.current_intent, {})
            allowed_tools = current_intent_conf.get('allowed_tools', [])
            
            for path in allowed_tools:
                if path in self.config.tool_func_map:
                    schemas.append(self._func_to_schema(self.config.tool_func_map[path], path))

            # [Optional] 如果你希望 Global Tools 在锁定模式下也能用 (如 get_current_time)
            # 可以取消下面代码的注释：
            for path in self.config.raw.get('global_tools', []):
                if path in self.config.tool_func_map:
                    schemas.append(self._func_to_schema(self.config.tool_func_map[path], path))

        return schemas

    def _simple_schema(self, func, name):
        return {"type": "function", "function": {"name": name, "parameters": {"type": "object", "properties": {"a":{"type":"string"}}}}}

    # --- 核心运行逻辑 ---
    async def run_task(self, session_id: str, user_input: str = None, resume: bool = False):
        """
        核心运行逻辑：思考 -> 执行 -> 循环
        支持：流式输出、事件驱动、HITL恢复、动态Prompt、配置读取
        """
        # 1. 加载状态
        state = db_ops("load", id=session_id)
        
        # 2. 处理“恢复执行”逻辑 (Human-in-the-Loop Resume)
        if resume:
            if state.status == AgentStatus.WAITING_APPROVAL and state.pending_tool_call:
                # 用户已批准，取出挂起的工具调用
                tool_data = state.pending_tool_call
                
                # 发送系统通知事件
                await self.events.emit(EventType.STATE_CHANGE, {"msg": f"Resuming approved action: {tool_data['name']}"})
                
                # 执行工具
                # 注意：这里需要传入 session_id，因为某些工具（如 save_memory）可能需要它
                res = self._exec_tool_func(tool_data['name'], tool_data['args'], session_id)
                
                # 记录工具执行结果
                await self.events.emit(EventType.TOOL_END, {"id": tool_data['id'], "result": str(res)})
                state.history.append({
                    "role": "tool", 
                    "tool_call_id": tool_data['id'], 
                    "content": str(res)
                })
                
                # 清除挂起状态，恢复运行
                state.pending_tool_call = None
                state.status = AgentStatus.RUNNING
            else:
                # 异常情况：请求恢复但没有挂起的任务
                await self.events.emit(EventType.ERROR, "Resume failed: No pending approval found.")
                return
        else:
            # 正常对话流程
            state.status = AgentStatus.RUNNING
            if user_input:
                state.history.append({"role": "user", "content": user_input})

        # 3. 读取模型配置 (确保每次都使用最新的配置)
        model_conf = self.config.raw.get('model', {})
        model_name = model_conf.get('name', 'gpt-4o')
        temperature = model_conf.get('temperature', 0.5)
        max_tokens = model_conf.get('max_tokens', 2000)

        # 4. 主循环 (Think -> Act -> Loop)
        while state.status == AgentStatus.RUNNING:
            
            # ============================================================
            # A. 动态构建 System Prompt (关键：必须在循环内构建)
            # ============================================================
            
            # A.1 准备计划信息
            plan_str = ""
            if state.current_plan:
                # 将列表格式化为易读的文本
                steps_text = "\n".join([f"- {step}" for step in state.current_plan])
                plan_str = f"\n\n【当前执行计划 (Current Plan)】\n{steps_text}"
            else:
                plan_str = "\n\n【当前执行计划】\n(暂无计划，如任务复杂请使用 update_plan 工具)"

            # A.2 准备状态描述
            if state.current_intent:
                # 如果锁定意图，提示 LLM 当前的专注领域
                intent_desc = self.config.intents[state.current_intent].get('description', '')
                status_str = f"LOCKED MODE (Intent: {state.current_intent})\nTask: {intent_desc}"
            else:
                status_str = "IDLE MODE (Routing)\nPlease identify user intent and use 'switch_intent'."

            # A.3 准备记忆上下文 (此处可扩展为向量检索)
            # 简单实现：从 DB 取最近 3 条记忆
            recent_mems = db_ops("get_memories", uid=session_id)
            if recent_mems:
                mem_text = "\n".join([f"- {m['content']}" for m in recent_mems[:3]])
                memories_str = f"\n\n【相关记忆 (Memories)】\n{mem_text}"
            else:
                memories_str = ""

            # A.4 组装完整 Prompt
            try:
                sys_template = self.config.raw['agent']['system_template']
                full_sys_prompt = sys_template.format(
                    name=self.config.raw['agent']['name'],
                    status=status_str,
                    memories=memories_str
                ) + plan_str
            except KeyError as e:
                # 防止配置文件缺少 key 导致崩溃
                full_sys_prompt = f"System Error: Config template missing key {e}"

            # A.5 更新 History 中的 System Message
            # 确保 System Message 永远在 history 的第 0 位
            if not state.history:
                state.history.append({"role": "system", "content": full_sys_prompt})
            elif state.history[0]['role'] == 'system':
                state.history[0]['content'] = full_sys_prompt
            else:
                state.history.insert(0, {"role": "system", "content": full_sys_prompt})

            # ============================================================
            # B. 获取当前上下文允许的工具
            # ============================================================
            active_tools = self._get_tools_schema(state)

            # ============================================================
            # C. 调用 LLM
            # ============================================================
            try:
                response = await self.client.chat.completions.create(
                    model=model_name,
                    messages=state.history,
                    tools=active_tools if active_tools else None,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
            except Exception as e:
                await self.events.emit(EventType.ERROR, f"OpenAI API Error: {str(e)}")
                # 遇到 LLM 错误，停止当前任务
                break

            # ============================================================
            # D. 处理流式响应
            # ============================================================
            full_content = ""
            tool_buffer = []

            async for chunk in response:
                delta = chunk.choices[0].delta
                
                # D.1 文本流
                if delta.content:
                    full_content += delta.content
                    await self.events.emit(EventType.TOKEN, delta.content)
                
                # D.2 工具调用流 (OpenAI 返回的是片段，需要拼接)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        # 扩展 buffer 大小
                        if len(tool_buffer) <= tc.index:
                            tool_buffer.append({"id": "", "name": "", "args": ""})
                        
                        item = tool_buffer[tc.index]
                        if tc.id: item["id"] += tc.id
                        if tc.function.name: item["name"] += tc.function.name
                        if tc.function.arguments: item["args"] += tc.function.arguments

            # 将完整的 Assistant 回复（无论是否有工具调用）加入历史
            if full_content:
                state.history.append({"role": "assistant", "content": full_content})

            # 如果本轮没有工具调用，说明 LLM 认为任务暂停或等待用户输入 -> 结束循环
            if not tool_buffer:
                db_ops("save", state=state)
                break

            # ============================================================
            # E. 执行工具调用
            # ============================================================
            
            # 首先将 Assistant 的 tool_calls 消息加入历史 (这是 OpenAI 协议要求的)
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

            # 遍历并执行每一个工具
            for t in tool_buffer:
                func_name = t["name"]
                call_id = t["id"]
                args_str = t["args"]
                
                # E.1 解析参数
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    args = {} # 参数解析失败，传空字典或记录错误

                # 发送工具开始事件
                await self.events.emit(EventType.TOOL_START, {"name": func_name, "args": args})
                
                tool_result = None

                # E.2 特殊工具处理逻辑

                # --- 意图切换 (Switch Intent) ---
                if func_name == "switch_intent":
                    new_intent = args.get("intent_name")
                    if new_intent in self.config.intents:
                        state.current_intent = new_intent
                        await self.events.emit(EventType.STATE_CHANGE, {"intent": new_intent})
                        tool_result = f"System: Context successfully switched to '{new_intent}'. System Prompt updated."
                    else:
                        tool_result = f"Error: Intent '{new_intent}' is not defined in configuration."

                # --- 意图提交 (Submit Intent - 严格校验) ---
                elif func_name == "submit_intent":
                    if not state.current_intent:
                        tool_result = "Error: No active intent to submit."
                    else:
                        # 动态获取 Pydantic 模型进行校验
                        model_cls = self.config.intent_models.get(state.current_intent)
                        if model_cls:
                            try:
                                # 校验 args['slots']
                                slots_data = args.get('slots', {})
                                valid_data = model_cls(**slots_data)
                                
                                # 校验成功
                                tool_result = f"Intent '{state.current_intent}' submitted successfully. Data: {valid_data.model_dump_json()}"
                                await self.events.emit(EventType.STATE_CHANGE, {"intent": None}) # 提交后重置意图
                                state.current_intent = None 
                            except ValidationError as ve:
                                # 校验失败，返回详细错误给 LLM
                                tool_result = f"Slot Validation Error: {ve}. Please ask user for missing info."
                        else:
                            tool_result = "System Error: Intent model not found."

                elif func_name == "cancel_intent":
                    state.current_intent = None
                    # 发送状态变更事件，通知前端
                    await self.events.emit(EventType.STATE_CHANGE, {"intent": None})
                    tool_result = "System: Current intent cancelled. Returned to Idle mode."
                    
                # --- 计划更新 (Update Plan) ---
                elif func_name == "update_plan":
                    new_steps = args.get('steps', [])
                    state.current_plan = new_steps
                    await self.events.emit(EventType.STATE_CHANGE, {"plan": new_steps})
                    tool_result = f"System: Plan updated with {len(new_steps)} steps."

                # E.3 敏感操作拦截 (HITL)
                elif self.config.is_sensitive(func_name):
                    # 1. 改变状态
                    state.status = AgentStatus.WAITING_APPROVAL
                    # 2. 挂起当前调用
                    state.pending_tool_call = {
                        "name": func_name, 
                        "args": args, 
                        "id": call_id
                    }
                    # 3. 保存状态
                    db_ops("save", state=state)
                    # 4. 发送审批请求事件
                    await self.events.emit(EventType.APPROVAL_REQ, {"tool": func_name, "args": args})
                    
                    # 5. 【关键】直接退出函数，不再执行后续逻辑，等待 resume
                    return 

                # E.4 普通/全局工具执行
                else:
                    tool_result = self._exec_tool_func(func_name, args, session_id)

                # E.5 发送结果事件并记录历史
                result_str = str(tool_result)
                await self.events.emit(EventType.TOOL_END, {"id": call_id, "result": result_str})
                
                state.history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result_str
                })

            # E.6 保存本轮状态
            db_ops("save", state=state)
            
            # 循环继续... 下一轮开头会重新生成 System Prompt
    def _exec_tool_func(self, name, args, sid):
        # 执行具体函数
        func = self.config.tool_func_map.get(name)
        return func(**args) if func else "Tool not found"

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
    
# [新增] 状态响应模型
class AgentStateResponse(BaseModel):
    session_id: str
    status: str
    current_intent: Optional[str]
    current_plan: List[str]
    history_len: int
    pending_approval: bool

@app.get("/agent/{session_id}/state", response_model=AgentStateResponse)
async def get_state(session_id: str):
    """获取 Agent 的实时内部状态"""
    state = db_ops("load", id=session_id)
    return {
        "session_id": state.session_id,
        "status": state.status,
        "current_intent": state.current_intent,
        "current_plan": state.current_plan,
        "history_len": len(state.history),
        "pending_approval": (state.status == AgentStatus.WAITING_APPROVAL)
    }

@app.get("/agent/{session_id}/memories")
async def get_memories(session_id: str):
    """获取 Agent 关于该用户的长期记忆"""
    return db_ops("get_memories", uid=session_id)

@app.delete("/agent/{session_id}")
async def reset_session(session_id: str):
    """重置会话（清空短期记忆，保留长期记忆）"""
    db_ops("clear_history", id=session_id)
    return {"status": "success", "msg": "Session reset"}


async def event_generator(session_id: str, input_text: str = None, resume: bool = False):
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
    task = asyncio.create_task(agent.run_task(session_id, input_text, resume))

    try:
        while True:
            # 设定一个短超时，防止死锁
            try:
                # 优先处理队列里的消息
                event = await asyncio.wait_for(q.get(), timeout=0.1)
                print(f"DEBUG: Yielding event -> {event.type}") # 打印发送的事件类型
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