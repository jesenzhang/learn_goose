"""
UltraClient - Streamlit client for skill_micro_agent

Optimized for modular agent architecture with:
- Artifact rendering (charts, tables, etc.)
- Tool execution metadata display
- Enhanced approval workflow
- Better error handling
"""

import streamlit as st
import requests
import json
import uuid
from datetime import datetime, date
from typing import Dict, Any, Optional

# ==================== Configuration ====================
SERVER_URL = "http://localhost:8300"

st.set_page_config(
    page_title="UltraClient",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==================== CSS Styling ====================
st.markdown("""
<style>
    /* Chat message styling */
    .stChatMessage {
        padding: 1rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }

    /* Status widget styling */
    .stStatusWidget {
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        background-color: #f8f9fa;
        padding: 10px;
        margin-bottom: 10px;
    }

    /* Button text truncation */
    .stButton button p {
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        display: block;
        width: 100%;
    }

    /* Artifact container */
    .artifact-container {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background-color: #fafafa;
    }

    /* Tool metadata */
    .tool-meta {
        font-size: 0.85em;
        color: #666;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# ==================== Session State Initialization ====================
def init_session_state():
    """Initialize session state variables."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"user_{uuid.uuid4().hex[:8]}"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "artifacts" not in st.session_state:
        st.session_state.artifacts = {}  # Store tool artifacts

    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

init_session_state()

# ==================== API Functions ====================
@st.cache_data(ttl=5, show_spinner=False)
def fetch_sessions() -> list:
    """Fetch list of sessions with metadata."""
    try:
        res = requests.get(f"{SERVER_URL}/sessions", timeout=2)
        if res.status_code == 200:
            data = res.json()
            return data.get("sessions", [])
    except Exception:
        pass
    return []


def load_session_state(session_id: str) -> Optional[Dict]:
    """Load complete state for a session."""
    try:
        res = requests.get(f"{SERVER_URL}/agent/{session_id}/state")
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        st.error(f"Failed to load session: {e}")
    return None


def load_history_from_server(session_id: str):
    """Load chat history and check for pending approvals."""
    st.session_state.chat_history = []
    st.session_state.pending_approval = None
    st.session_state.artifacts = {}

    state = load_session_state(session_id)
    if not state:
        return

    # Restore messages
    for msg in state.get("history", []):
        if msg["role"] in ("user", "assistant") and msg.get("content"):
            st.session_state.chat_history.append(msg)

    # Check for pending approval
    if state.get("status") == "waiting_approval" and state.get("pending_tool_call"):
        tool_data = state["pending_tool_call"]
        st.session_state.pending_approval = {
            "tool": tool_data["name"],
            "args": tool_data.get("args", {})
        }

    # Restore artifacts from shared memory
    for key, value in state.get("shared_memory", {}).items():
        if key.startswith("art_"):
            st.session_state.artifacts[key] = value


def create_new_session():
    """Create a new chat session."""
    st.session_state.session_id = f"user_{uuid.uuid4().hex[:8]}"
    st.session_state.chat_history = []
    st.session_state.artifacts = {}
    st.session_state.pending_approval = None
    st.rerun()

# ==================== Event Processing ====================
def render_artifact(artifact_data: Dict):
    """
    Render tool artifact (chart, table, etc.).

    Args:
        artifact_data: Dict containing id, type, title, view, data
    """
    artifact_type = artifact_data.get("type", "text")
    title = artifact_data.get("title", "Output")
    data = artifact_data.get("data")
    view_text = artifact_data.get("view", "")

    with st.container(border=True):
        st.markdown(f"**📊 {title}**")

        if artifact_type == "chart" and data:
            # Render chart using Plotly
            import plotly.express as px

            try:
                if isinstance(data, dict) and "fig" in data:
                    fig = data["fig"]
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.json(data)
            except Exception as e:
                st.error(f"Failed to render chart: {e}")

        elif artifact_type == "table" and data:
            # Render table
            try:
                import pandas as pd

                if isinstance(data, list):
                    df = pd.DataFrame(data)
                elif isinstance(data, dict):
                    df = pd.DataFrame([data])
                else:
                    df = pd.DataFrame(data)

                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.json(data)

        else:
            # Default: show as code/json
            if view_text:
                st.markdown(view_text)
            if data:
                st.json(data)


def process_stream(response, msg_placeholder, status_box):
    """
    处理流式响应，强制在 Status Box 中显示工具原始结果。
    """
    full_text = ""

    if response.status_code != 200:
        msg_placeholder.error(f"Server Error: {response.status_code}")
        return ""

    try:
        for line in response.iter_lines():
            if not line: continue

            try:
                data_str = line.decode('utf-8')
                payload = json.loads(data_str)
                event_type = payload.get("type")
                data = payload.get("data")
            except json.JSONDecodeError:
                continue

            # ================= 事件处理 =================

            # 1. 文本生成 (Token)
            if event_type == "token":
                full_text += data
                msg_placeholder.markdown(full_text + "▌")

            # 2. 工具开始 (Tool Start)
            elif event_type == "tool_start":
                tool_name = data.get("name", "unknown")
                # 打印一行日志到状态框
                status_box.write(f"🔨 Calling tool: **{tool_name}**...")

            # 3. 工具结束 (Tool End) - [核心修改]
            elif event_type == "tool_end":
                result = data.get("result", "")
                meta = data.get("meta", {})
                tool_name = meta.get("tool", "tool")
                
                # A. 打印完成状态
                status_box.markdown(f"✅ **{tool_name}** finished.")

                # B. [关键] 在状态框内渲染完整结果
                # 如果结果是字典/列表，用 st.json；如果是字符串，尝试解析或直接显示代码块
                if isinstance(result, (dict, list)):
                    status_box.json(result, expanded=False)
                else:
                    # 尝试判断是否为 JSON 字符串
                    try:
                        if isinstance(result, str) and (result.strip().startswith('{') or result.strip().startswith('[')):
                            parsed = json.loads(result)
                            status_box.json(parsed, expanded=False)
                        else:
                            # 普通文本，使用 code block 显示，防止 markdown 渲染混乱
                            # wrap_lines=True 让长文本自动换行
                            status_box.code(str(result), language="text", wrap_lines=True)
                    except:
                        status_box.code(str(result), language="text", wrap_lines=True)

            # 4. Artifact (图表/表格)
            elif event_type == "tool_artifact":
                art_id = data.get("id")
                # 存入 session 用于持久化
                st.session_state.artifacts[art_id] = data
                
                # 也在状态框里显示一份
                with status_box:
                    st.caption(f"📊 Generated Artifact: {data.get('title')}")
                    render_artifact(data)

            # 5. 状态变更 / 思考
            elif event_type == "state_change":
                if "intent" in data and data["intent"]:
                    status_box.info(f"🎯 Intent detected: **{data['intent']}**")
                if "msg" in data:
                    status_box.write(f"🧠 {data['msg']}")

            # 6. 审批请求
            elif event_type == "approval_req":
                # ... (保持原有的审批逻辑) ...
                tool_name = data.get("tool")
                args = data.get("args")
                current = st.session_state.get("pending_approval")
                if not current or current.get("tool") != tool_name:
                    status_box.update(label="✋ Waiting for approval...", state="error", expanded=True)
                    st.session_state.pending_approval = {"tool": tool_name, "args": args}
                    st.rerun()
                return ""

            # 7. 错误
            elif event_type == "error":
                status_box.error(f"❌ Error: {data}")

        # ================= 结束 =================
        # expanded=True 保持展开，让用户一眼能看到里面的工具结果
        status_box.update(label="✨ Task Complete", state="complete", expanded=True)
        msg_placeholder.markdown(full_text)
        return full_text

    except Exception as e:
        status_box.error(f"Stream error: {e}")
        return full_text
# ==================== Approval UI ====================
def render_approval_box(approval_data: Dict):
    """
    Render approval request UI.

    Args:
        approval_data: Dict with 'tool' and 'args'
    """
    tool_name = approval_data.get("tool", "unknown")
    args = approval_data.get("args", {})

    with st.container(border=True):
        st.warning("🛑 **需要人工审批 (Approval Required)**")
        st.markdown(f"Agent 请求执行敏感操作：**`{tool_name}`**")

        with st.expander("查看参数详情 (Arguments)", expanded=True):
            st.json(args)

        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button("✅ 批准执行 (Approve)", key="btn_approve", type="primary", use_container_width=True):
                send_approval(True)
        with col2:
            if st.button("❌ 拒绝 (Reject)", key="btn_reject", type="secondary", use_container_width=True):
                send_approval(False, "User rejected via UI")


def send_approval(approved: bool, feedback: str = ""):
    """Send approval decision to server."""
    try:
        url = f"{SERVER_URL}/agent/{st.session_state.session_id}/approval"

        # Clear pending state immediately
        st.session_state.pending_approval = None

        # Prepare to receive response stream
        with st.chat_message("assistant"):
            response_container = st.empty()

            with requests.post(
                url,
                json={"approved": approved, "feedback": feedback},
                stream=True
            ) as response:
                status_box = st.status("Processing approval...", expanded=True)
                process_stream(response, response_container, status_box)

        st.rerun()

    except Exception as e:
        st.error(f"Failed to send approval: {e}")

# ==================== Sidebar ====================
def render_sidebar():
    """Render sidebar with session list."""
    with st.sidebar:
        st.title("🗂️ UltraClient")

        if st.button("➕ 新建会话 (New Chat)", use_container_width=True, type="primary"):
            create_new_session()

        st.divider()

        sessions = fetch_sessions()

        # Group by time
        today_sess = []
        yesterday_sess = []
        older_sess = []

        today = date.today()

        for s in sessions:
            # Handle both string (old) and dict (new) formats
            if isinstance(s, str):
                s = {"id": s, "title": f"Session {s[-6:]}", "updated_at": 0}

            try:
                ts = s.get("updated_at", 0)
                if ts == 0:
                    older_sess.append(s)
                    continue

                s_date = datetime.fromtimestamp(ts).date()

                if s_date == today:
                    today_sess.append(s)
                elif (today - s_date).days == 1:
                    yesterday_sess.append(s)
                else:
                    older_sess.append(s)
            except Exception:
                older_sess.append(s)

        # Render session lists
        def render_session_list(sess_list):
            for s in sess_list:
                sid = s.get('id')
                title = s.get('title', 'New Chat')

                if len(title) > 18:
                    title = title[:18] + "..."

                is_active = (sid == st.session_state.session_id)
                icon = "🟢" if is_active else "💬"

                if st.button(
                    f"{icon} {title}",
                    key=f"sess_{sid}",
                    help=s.get('title'),
                    use_container_width=True
                ):
                    st.session_state.session_id = sid
                    load_history_from_server(sid)
                    st.rerun()

        if today_sess:
            with st.expander("📅 今天 (Today)", expanded=True):
                render_session_list(today_sess)

        if yesterday_sess:
            with st.expander("⏮️ 昨天 (Yesterday)", expanded=False):
                render_session_list(yesterday_sess)

        expand_older = (not today_sess and not yesterday_sess)
        if older_sess:
            with st.expander("🗄️ 更早 (Older)", expanded=expand_older):
                render_session_list(older_sess)


render_sidebar()

# ==================== Main Chat Interface ====================
st.header("UltraClient Pro")

# Render chat history
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Render stored artifacts
if st.session_state.artifacts:
    for art_id, art_data in st.session_state.artifacts.items():
        with st.expander(f"📊 {art_data.get('title', 'Artifact')}", expanded=False):
            render_artifact(art_data)

# Main interaction logic
if st.session_state.pending_approval:
    # --- Approval Mode ---
    render_approval_box(st.session_state.pending_approval)

else:
    # --- Normal Chat Mode ---
    prompt = st.chat_input("输入指令...")

    if prompt:
        # Display user message
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Send to agent
        with st.chat_message("assistant"):
            response_container = st.empty()
            try:
                payload = {"message": prompt}
                res = requests.post(
                    f"{SERVER_URL}/chat/{st.session_state.session_id}",
                    json=payload,
                    stream=True
                )

                status_box = st.status("Thinking & Planning...", expanded=True)
                final_text = process_stream(res, response_container, status_box)

                if final_text:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": final_text
                    })

            except requests.exceptions.ConnectionError:
                st.error("无法连接到服务器。请确保 agent 服务正在运行。")
            except Exception as e:
                st.error(f"Error: {e}")
