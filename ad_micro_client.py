import streamlit as st
import requests
import json
import uuid
import time

# ================= 1. 配置 =================
SERVER_URL = "http://localhost:8300"

st.set_page_config(
    page_title="UltraAgent Dashboard", 
    page_icon="🧠", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 2. 状态初始化 =================
if "session_id" not in st.session_state:
    st.session_state.session_id = f"user_{str(uuid.uuid4())[:6]}"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "agent_state" not in st.session_state:
    st.session_state.agent_state = {
        "current_intent": None,
        "current_plan": [],
        "pending_approval": False,
        "status": "idle"
    }

# ================= 3. 核心辅助函数 (提前定义) =================

def process_stream(response, container):
    """
    [修复版] 处理 SSE 流，兼容服务端的新 Event 模型
    """
    full_text = ""
    tool_status = None
    
    if response.status_code != 200:
        container.error(f"Server Error: {response.status_code}")
        return ""

    for line in response.iter_lines():
        if not line: continue
        try:
            data_str = line.decode('utf-8')
            payload = json.loads(data_str)
            
            # ================= 修复点开始 =================
            # 服务端现在发送的是 {"type": "...", "data": ...}
            # 为了兼容性，我们同时尝试获取 'type' 和 'event'
            event_type = payload.get("type") or payload.get("event")
            data = payload.get("data")
            # ================= 修复点结束 =================

            # --- 事件处理分支 ---
            
            if event_type == "token":
                full_text += data
                container.markdown(full_text + "▌")
            
            elif event_type == "tool_start":
                tool_status = st.status(f"🔧 Tool: {data['name']}", expanded=True)
                tool_status.write(f"Args: `{json.dumps(data['args'], ensure_ascii=False)}`")
            
            elif event_type == "tool_end":
                if tool_status:
                    result_str = str(data.get('result'))
                    display_res = result_str[:200] + "..." if len(result_str) > 200 else result_str
                    tool_status.write(f"Result: {display_res}")
                    tool_status.update(label=f"✅ Tool Finished", state="complete", expanded=False)
                    tool_status = None
            
            elif event_type == "state_change":
                if "plan" in data:
                    st.toast(f"📋 Plan Updated: {len(data['plan'])} steps")
                    st.session_state.agent_state["current_plan"] = data["plan"]
            
            elif event_type == "approval_req":
                st.session_state.agent_state["pending_approval"] = True
                st.toast("⚠️ Approval Required!", icon="🛑")
                break
            
            elif event_type == "error":
                st.error(f"Error: {data}")

        except Exception as e:
            print(f"Stream Error: {e}")
            pass
    
    container.markdown(full_text)
    return full_text

# ================= 4. API 封装 =================
def fetch_agent_state():
    """从服务端拉取最新状态"""
    try:
        sid = st.session_state.session_id
        res = requests.get(f"{SERVER_URL}/agent/{sid}/state")
        if res.status_code == 200:
            st.session_state.agent_state = res.json()
    except Exception:
        pass # 忽略连接错误，避免刷屏

def fetch_memories():
    """从服务端拉取记忆"""
    try:
        sid = st.session_state.session_id
        res = requests.get(f"{SERVER_URL}/agent/{sid}/memories")
        return res.json() if res.status_code == 200 else []
    except Exception:
        return []

def reset_session():
    try:
        requests.delete(f"{SERVER_URL}/agent/{st.session_state.session_id}")
        st.session_state.chat_history = []
        st.session_state.agent_state = {"current_intent": None, "current_plan": [], "pending_approval": False}
        st.rerun()
    except Exception as e:
        st.error(f"Failed to reset: {e}")

# ================= 5. 侧边栏布局 =================
with st.sidebar:
    st.title("🛡️ Control Center")
    
    # 1. 会话控制
    col1, col2 = st.columns([3, 1])
    with col1:
        new_sid = st.text_input("Session ID", value=st.session_state.session_id, label_visibility="collapsed")
    with col2:
        if st.button("🔄", help="Reset Session"):
            reset_session()
    
    if new_sid != st.session_state.session_id:
        st.session_state.session_id = new_sid
        st.rerun()

    st.divider()

    # 2. 状态监控 (Status Monitor)
    st.subheader("📡 Status Monitor")
    
    # 每次刷新页面都拉取一次最新状态
    fetch_agent_state()
    
    status = st.session_state.agent_state.get("status", "idle")
    intent = st.session_state.agent_state.get("current_intent")
    
    if status == "waiting_approval":
        st.error("🔴 WAITING APPROVAL")
    elif status == "running":
        st.success("🟢 RUNNING")
    else:
        st.info("⚪ IDLE")

    st.caption("Current Intent")
    if intent:
        st.code(intent, language="text")
    else:
        st.markdown("*No active intent*")

    # 3. 计划追踪 (Plan Tracker)
    plan = st.session_state.agent_state.get("current_plan", [])
    if plan:
        st.divider()
        st.subheader("📋 Execution Plan")
        for i, step in enumerate(plan):
            st.checkbox(step, value=False, key=f"plan_{i}", disabled=True)
    
    # 4. 记忆库 (Memory Bank)
    st.divider()
    st.subheader("🧠 Memory Bank")
    with st.expander("Show Long-term Memories"):
        memories = fetch_memories()
        if memories:
            for mem in memories:
                st.markdown(f"- <small>{mem['content']}</small>", unsafe_allow_html=True)
        else:
            st.caption("No memories yet.")

# ================= 6. 主界面交互区域 =================

st.header("💬 Agent Interaction")

# 1. 渲染历史消息
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. 审批卡片 (HITL 核心交互)
# 如果后端状态是 waiting_approval，前端就显示审批卡片
if st.session_state.agent_state.get("pending_approval") or st.session_state.agent_state.get("status") == "waiting_approval":
    with st.container(border=True):
        st.warning("⚠️ **Sensitive Action Detected**")
        st.markdown("The agent is requesting permission to execute a sensitive tool.")
        
        col_a, col_b = st.columns([1, 5])
        with col_a:
            if st.button("✅ Approve", type="primary"):
                # 记录一条“我同意了”的消息
                st.session_state.chat_history.append({"role": "user", "content": "✅ Approved action."})
                
                # 发送请求并处理流式响应
                with st.chat_message("assistant"):
                    response_container = st.empty()
                    try:
                        res = requests.post(f"{SERVER_URL}/approve/{st.session_state.session_id}", stream=True)
                        process_stream(res, response_container)
                    except Exception as e:
                        st.error(f"Approval failed: {e}")
                
                # 审批后刷新状态
                fetch_agent_state()
                st.rerun()

# 3. 输入框逻辑
# 如果正在等待审批，禁用输入框
is_locked = st.session_state.agent_state.get("pending_approval") or st.session_state.agent_state.get("status") == "waiting_approval"

if prompt := st.chat_input("Input your instruction...", disabled=is_locked):
    
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_container = st.empty()
        
        try:
            # 发起聊天请求
            payload = {"message": prompt}
            res = requests.post(f"{SERVER_URL}/chat/{st.session_state.session_id}", json=payload, stream=True)
            
            # 调用流处理函数 (现在它在上面已经定义好了，不会报错了)
            full_text = process_stream(res, response_container)
            
            if full_text:
                st.session_state.chat_history.append({"role": "assistant", "content": full_text})
        
        except Exception as e:
            st.error(f"Connection Error: {e}")
        
        # 结束后刷新状态
        fetch_agent_state()
        st.rerun()