import streamlit as st
import requests
import json
import uuid
import time
from datetime import datetime, date

# ================= 1. 配置 =================
SERVER_URL = "http://localhost:8300"

st.set_page_config(
    page_title="UltraAgent Pro", 
    page_icon="🤖", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 2. CSS 美化 =================
st.markdown("""
<style>
    /* 聊天气泡优化 */
    .stChatMessage {
        padding: 1rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }
    /* 状态框美化 */
    .stStatusWidget {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: #f8f9fa;
        padding: 10px;
        margin-bottom: 10px;
    }
    /* 侧边栏按钮文字截断 */
    .stButton button p {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# ================= 3. 状态初始化 =================
if "session_id" not in st.session_state:
    st.session_state.session_id = f"user_{str(uuid.uuid4())[:6]}"

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "agent_state" not in st.session_state:
    st.session_state.agent_state = {}

# [关键] 增加持久化的审批状态，防止刷新后丢失
if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

# ================= 4. 核心逻辑函数 =================

def send_approval(approved: bool, feedback: str = ""):
    """发送决策回服务端"""
    try:
        url = f"{SERVER_URL}/agent/{st.session_state.session_id}/approval"
        
        # 清除本地挂起状态 (UI立即响应)
        st.session_state.pending_approval = None
        
        # 渲染占位符，准备接收恢复后的流
        with st.chat_message("assistant"):
            response_container = st.empty()
            
            # 发送请求并处理流式响应
            with requests.post(url, json={"approved": approved, "feedback": feedback}, stream=True) as response:
                process_stream_manus_style(response, response_container)
        
        # 处理完后刷新，更新历史记录
        st.rerun()
        
    except Exception as e:
        st.error(f"Failed to send approval: {e}")

def render_approval_box(data):
    """渲染审批请求卡片 (阻塞式 UI)"""
    tool_name = data.get("tool")
    args = data.get("args")
    
    # 使用 container 包裹，使其更醒目
    with st.container(border=True):
        st.warning(f"🛑 **需要人工审批 (Approval Required)**")
        st.markdown(f"Agent 请求执行敏感操作：**`{tool_name}`**")
        
        with st.expander("查看参数详情 (Arguments)", expanded=True):
            st.json(args)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ 批准执行 (Approve)", key="btn_approve_main", type="primary", use_container_width=True):
                send_approval(True)
        with col2:
            if st.button("❌ 拒绝 (Reject)", key="btn_reject_main", type="secondary", use_container_width=True):
                send_approval(False, "User rejected via UI.")

def process_stream_manus_style(response, msg_placeholder):
    """Manus 风格流处理器"""
    full_text = ""
    
    if response.status_code != 200:
        msg_placeholder.error(f"Server Error: {response.status_code}")
        return ""

    status_box = st.status("Thinking & Planning...", expanded=True)
    
    try:
        for line in response.iter_lines():
            if not line: continue
            try:
                data_str = line.decode('utf-8')
                payload = json.loads(data_str)
                event_type = payload.get("type") or payload.get("event")
                data = payload.get("data")
            except:
                continue

            # --- 事件处理 ---
            if event_type == "state_change":
                if "intent" in data and data["intent"]:
                    status_box.write(f"🎯 **Intent:** `{data['intent']}`")
                if "plan" in data:
                    status_box.write("📋 **Plan Updated**")

            elif event_type == "tool_start":
                status_box.write(f"🔨 **Call:** `{data['name']}`")

            elif event_type == "tool_end":
                res = str(data.get('result'))
                short_res = res[:80] + "..." if len(res) > 80 else res
                status_box.markdown(f"&nbsp;&nbsp;✅ {short_res}")

            elif event_type == "approval_req":
              # [优化] 防抖动：只有当 session_state 还没记录时才刷新
                # 避免重复收到事件导致界面疯狂重绘
                current_pending = st.session_state.get("pending_approval")
                
                # 简单对比一下 ID 或工具名，如果一样就不刷新了
                if current_pending and current_pending.get("tool") == data.get("tool"):
                    pass # 已经显示了，忽略
                else:
                    status_box.update(label="✋ Waiting for approval...", state="error", expanded=True)
                    st.session_state.pending_approval = data
                    st.rerun()
                
                return "" # 中断流
            elif event_type == "token":
                full_text += data
                msg_placeholder.markdown(full_text + "▌")
                
            elif event_type == "error":
                status_box.error(f"Error: {data}")

        status_box.update(label="Complete", state="complete", expanded=False)
        msg_placeholder.markdown(full_text)
        return full_text

    except Exception as e:
        status_box.error(f"Stream Error: {e}")
        return full_text

# ================= 5. API 交互 =================

@st.cache_data(ttl=5, show_spinner=False)
def fetch_sessions():
    """获取会话列表 (带缓存)"""
    try:
        res = requests.get(f"{SERVER_URL}/sessions", timeout=2) # 设置短超时
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, list): return data
            return data.get("sessions", [])
    except:
        pass
    return []

def load_history_from_server(sid):
    """加载历史"""
    st.session_state.chat_history = []
    st.session_state.pending_approval = None # 切换会话时清除审批状态
    try:
        res = requests.get(f"{SERVER_URL}/agent/{sid}/state")
        if res.status_code == 200:
            data = res.json()
            
            # 恢复消息
            server_history = data.get("history", [])
            for msg in server_history:
                if msg["role"] == "user":
                    st.session_state.chat_history.append(msg)
                elif msg["role"] == "assistant" and msg.get("content"):
                    st.session_state.chat_history.append(msg)
            
            # [关键] 检查服务端状态是否卡在 waiting_approval
            # 如果服务端也是 waiting，同步到前端
            if data.get("status") == "waiting_approval" and data.get("pending_tool_call"):
                tool_data = data.get("pending_tool_call")
                # 构造成前端需要的格式
                st.session_state.pending_approval = {
                    "tool": tool_data["name"],
                    "args": tool_data.get("args", {})
                }
    except Exception as e:
        st.error(f"Load error: {e}")

def create_new_session():
    st.session_state.session_id = f"user_{str(uuid.uuid4())[:6]}"
    st.session_state.chat_history = []
    st.session_state.pending_approval = None
    st.rerun()

# ================= 6. 侧边栏 (分组+折叠) =================

def render_sidebar():
    with st.sidebar:
        st.title("🗂️ UltraAgent")
        
        if st.button("➕ 新建会话 (New Chat)", use_container_width=True, type="primary"):
            create_new_session()
        
        st.divider()
        
        sessions = fetch_sessions()
        
        # 分组逻辑
        today_sess = []
        yesterday_sess = []
        older_sess = []
        
        today_date = date.today()
        
        for s in sessions:
            # [修复逻辑] 兼容处理：如果 s 是字符串(旧版服务端)，构造成字典
            if isinstance(s, str):
                s = {
                    "id": s,
                    "title": f"Session {s[-6:]}", # 使用 ID 后6位作为临时标题
                    "updated_at": 0 # 默认时间为0，会被分到 older
                }
            
            # 此时 s 必定是字典，安全访问
            try:
                # 假设服务端返回的是 timestamp (float)
                ts = s.get("updated_at", 0)
                # 处理可能的时间戳格式问题
                if ts == 0:
                    older_sess.append(s)
                    continue

                s_date = datetime.fromtimestamp(ts).date()
                
                if s_date == today_date:
                    today_sess.append(s)
                elif (today_date - s_date).days == 1:
                    yesterday_sess.append(s)
                else:
                    older_sess.append(s)
            except Exception as e:
                # 遇到解析错误，兜底放入 older
                older_sess.append(s)

        # 渲染分组的内部函数
        def render_session_list(sess_list):
            for s in sess_list:
                # 此时 s 肯定是字典
                sid = s.get('id')
                title = s.get('title', 'New Chat')
                
                # 截断过长标题
                if len(title) > 18: title = title[:18] + "..."
                
                is_active = (sid == st.session_state.session_id)
                icon = "🟢" if is_active else "💬"
                
                # key 必须唯一，使用 sid
                if st.button(f"{icon} {title}", key=f"sess_{sid}", help=s.get('title'), use_container_width=True):
                    st.session_state.session_id = sid
                    load_history_from_server(sid)
                    st.rerun()

        # 开始渲染
        if today_sess:
            with st.expander("📅 今天 (Today)", expanded=True):
                render_session_list(today_sess)
        
        if yesterday_sess:
            with st.expander("⏮️ 昨天 (Yesterday)", expanded=False):
                render_session_list(yesterday_sess)
                
        # 如果没有今天或昨天的会话，默认展开 older，否则折叠
        expand_older = (not today_sess and not yesterday_sess)
        if older_sess:
            with st.expander("🗄️ 更早 (Older)", expanded=expand_older):
                render_session_list(older_sess)

# 执行渲染
render_sidebar()

# ================= 7. 主界面逻辑 =================

st.header("UltraAgent Pro")

# 1. 渲染历史消息
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. 状态检查与互斥 UI
# 核心逻辑：如果有挂起的审批，显示审批框；否则显示输入框

if st.session_state.pending_approval:
    # --- 审批模式 ---
    render_approval_box(st.session_state.pending_approval)

else:
    # --- 正常对话模式 ---
    prompt = st.chat_input("输入指令...")
    
    if prompt:
        # 显示用户消息
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 请求后端
        with st.chat_message("assistant"):
            response_container = st.empty()
            try:
                payload = {"message": prompt}
                res = requests.post(f"{SERVER_URL}/chat/{st.session_state.session_id}", json=payload, stream=True)
                
                # 处理流 (如果遇到审批请求，函数内部会设置 pending_approval 并 rerun)
                final_text = process_stream_manus_style(res, response_container)
                
                if final_text:
                    st.session_state.chat_history.append({"role": "assistant", "content": final_text})
            
            except Exception as e:
                st.error(f"Error: {e}")