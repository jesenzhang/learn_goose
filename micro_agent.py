import asyncio
import json
import sqlite3
import inspect
import time
from typing import List, Dict, Any, Optional, Callable, AsyncGenerator
from enum import Enum
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import AsyncOpenAI

# ================= Configuration =================
API_KEY = "vllm"  # 替换为你的 OpenAI API Key
MODEL_NAME = "qwen3_vl"
BASE_URL = 'http://192.168.10.180:8088/v1/'    
DB_PATH = "agent_service.db"
            
           
# ================= 1. Persistence Layer (SQLite) =================
class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    WAITING_USER = "waiting_user" 

class AgentState(BaseModel):
    session_id: str
    status: AgentStatus = AgentStatus.IDLE
    history: List[Dict[str, Any]] = []
    # 上下文/槽位/意图
    context: Dict[str, Any] = {"intent": None, "slots": {}, "plan": []}
    # 挂起的工具调用 (HITL)
    pending_tool: Optional[Dict] = None 

    def to_json(self): return self.model_dump_json()
    @classmethod
    def from_json(cls, j): return cls.model_validate_json(j)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, state TEXT)")

def save_state(state: AgentState):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO sessions (id, state) VALUES (?, ?)", 
                     (state.session_id, state.to_json()))

def load_state(session_id: str) -> AgentState:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT state FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        return AgentState.from_json(row[0]) if row else AgentState(session_id=session_id)

# ================= 2. Tools & Capabilities =================

# --- 意图与槽位管理工具 (Intent & Slot Filling) ---
def update_context(intent: str, slots: Dict[str, Any], confidence: float):
    """
    Call this tool to update the user's intent and extracted slots.
    Use this whenever the user clarifies their goal or provides new entities.
    """
    return f"Context Updated: Intent={intent}, Slots={slots}"

# --- 计划执行模式工具 (Plan & Execute) ---
def create_plan(steps: List[str]):
    """
    Create a step-by-step execution plan for complex tasks.
    """
    return f"Plan Created with {len(steps)} steps: {steps}"

# --- 敏感操作 (Human in the Loop) ---
def transfer_money(amount: int, to_account: str):
    """
    Transfer money to an account. THIS IS A SENSITIVE ACTION requiring approval.
    """
    return f"Successfully transferred ${amount} to {to_account}"

# --- 普通工具 ---
def get_weather(city: str):
    """Get current weather for a city."""
    return f"Weather in {city}: Sunny, 25°C"

TOOL_LIST = [update_context, create_plan, transfer_money, get_weather]

# ================= 3. MicroAgent Logic =================

class MicroAgent:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=API_KEY,base_url=BASE_URL)
        self.tools_map = {f.__name__: f for f in TOOL_LIST}
        self.tools_schema = [self._func_to_schema(f) for f in TOOL_LIST]

    def _func_to_schema(self, func) -> dict:
        # 简化版 Schema 生成，实际项目建议用 pydantic TypeAdapter
        return {
            "type": "function",
            "function": {
                "name": func.__name__,
                "description": func.__doc__ or "",
                "parameters": {
                    "type": "object", 
                    "properties": {"steps": {"type": "array", "items": {"type": "string"}}} if func.__name__ == "create_plan" else {}, 
                    "additionalProperties": True # 偷懒允许任意参数，生产环境需严格定义
                }
            }
        }

    async def run_loop(self, session_id: str, user_input: str = None, resume: bool = False) -> AsyncGenerator[str, None]:
        state = load_state(session_id)
        
        # --- 恢复或初始化 ---
        if resume:
            if state.status != AgentStatus.WAITING_USER or not state.pending_tool:
                yield self._msg("error", "No pending action to resume.")
                return
            
            # 执行挂起的工具
            tool_call = state.pending_tool
            yield self._msg("system", f"Approving action: {tool_call['name']}")
            result = self._exec_tool_func(tool_call["name"], tool_call["args"])
            
            # 记录结果
            state.history.append({
                "role": "tool", 
                "tool_call_id": tool_call["id"], 
                "content": str(result)
            })
            state.pending_tool = None
            state.status = AgentStatus.RUNNING
        
        else:
            # 新的用户输入
            if not state.history:
                # System Prompt 配置
                state.history.append({
                    "role": "system", 
                    "content": "You are a helpful Agent. Use 'update_context' to track intents. Use 'create_plan' for complex tasks. 'transfer_money' requires approval."
                })
            
            state.history.append({"role": "user", "content": user_input})
            state.status = AgentStatus.RUNNING

        save_state(state)

        # --- 主循环 ---
        while state.status == AgentStatus.RUNNING:
            try:
                # 1. 调用 LLM
                stream = await self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=state.history,
                    tools=self.tools_schema,
                    stream=True
                )

                full_content = ""
                tool_calls_buffer = []

                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    
                    # 流式文本输出
                    if delta.content:
                        full_content += delta.content
                        yield self._msg("token", delta.content)
                    
                    # 收集工具调用
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            if len(tool_calls_buffer) <= tc.index:
                                tool_calls_buffer.append({"id": "", "func": {"name": "", "args": ""}})
                            if tc.id: tool_calls_buffer[tc.index]["id"] += tc.id
                            if tc.function.name: tool_calls_buffer[tc.index]["func"]["name"] += tc.function.name
                            if tc.function.arguments: tool_calls_buffer[tc.index]["func"]["args"] += tc.function.arguments

                if full_content:
                    state.history.append({"role": "assistant", "content": full_content})

                # 2. 处理工具
                if tool_calls_buffer:
                    # 记录 Assistant 的 Tool Calls
                    state.history.append({
                        "role": "assistant",
                        "tool_calls": [{
                            "id": t["id"],
                            "type": "function",
                            "function": {"name": t["func"]["name"], "arguments": t["func"]["args"]}
                        } for t in tool_calls_buffer]
                    })

                    for tc in tool_calls_buffer:
                        func_name = tc["func"]["name"]
                        args_str = tc["func"]["args"]
                        tool_id = tc["id"]
                        
                        try:
                            args = json.loads(args_str)
                        except:
                            args = {}

                        # === Human in the Loop Check ===
                        if func_name == "transfer_money":
                            state.status = AgentStatus.WAITING_USER
                            state.pending_tool = {"name": func_name, "args": args, "id": tool_id}
                            save_state(state)
                            yield self._msg("approval_required", {"tool": func_name, "args": args})
                            return # 中断循环，等待 API 调用 /approve

                        # === 特殊逻辑: 更新状态上下文 ===
                        if func_name == "update_context":
                            state.context["intent"] = args.get("intent")
                            state.context["slots"].update(args.get("slots", {}))
                            yield self._msg("state_update", state.context)

                        # 执行工具
                        yield self._msg("tool_start", {"name": func_name, "args": args})
                        result = self._exec_tool_func(func_name, args)
                        yield self._msg("tool_end", {"result": result})

                        state.history.append({
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": str(result)
                        })

                else:
                    # 无工具调用，结束本轮
                    state.status = AgentStatus.IDLE
                
                save_state(state)

            except Exception as e:
                yield self._msg("error", str(e))
                return

    def _exec_tool_func(self, name, args):
        func = self.tools_map.get(name)
        if func:
            return func(**args)
        return "Error: Tool not found"

    def _msg(self, event_type: str, data: Any):
        """格式化为 JSON 行数据，方便前端解析"""
        return json.dumps({"event": event_type, "data": data}, ensure_ascii=False) + "\n"

# ================= 4. FastAPI Service =================

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(lifespan=lifespan)
agent = MicroAgent()

class ChatRequest(BaseModel):
    message: str

@app.post("/agent/{session_id}/chat")
async def chat_endpoint(session_id: str, req: ChatRequest):
    """通用对话接口：支持流式输出、意图识别、自动执行"""
    return StreamingResponse(
        agent.run_loop(session_id, user_input=req.message),
        media_type="application/x-ndjson"
    )

@app.post("/agent/{session_id}/approve")
async def approve_endpoint(session_id: str):
    """HITL 接口：用户确认后，恢复挂起的任务"""
    return StreamingResponse(
        agent.run_loop(session_id, resume=True),
        media_type="application/x-ndjson"
    )

@app.get("/agent/{session_id}")
async def get_state(session_id: str):
    """获取当前的会话状态（持久化数据）"""
    return load_state(session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8300)