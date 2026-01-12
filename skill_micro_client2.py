"""
UltraClient - Streamlit client for skill_micro_agent with multi-user support

Features:
- User registration and login
- Token-based authentication
- User session persistence
- Artifact rendering (charts, tables, etc.)
- Tool execution metadata display
- Enhanced approval workflow
- Better error handling
"""

import streamlit as st
import requests
import json
import uuid
import os
from datetime import datetime, date
from typing import Dict, Any, Optional

# ==================== Configuration ====================
SERVER_URL = os.getenv("ASSISTANT_SERVER", "http://localhost:8400")

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

    /* Auth container */
    .auth-container {
        max-width: 400px;
        margin: 0 auto;
        padding: 20px;
    }
</style>
""", unsafe_allow_html=True)

# ==================== Session State Initialization ====================
def init_session_state():
    """Initialize session state variables."""
    # User authentication state
    if "user_id" not in st.session_state:
        st.session_state.user_id = None
    if "username" not in st.session_state:
        st.session_state.username = None
    if "auth_token" not in st.session_state:
        st.session_state.auth_token = None
    if "is_logged_in" not in st.session_state:
        st.session_state.is_logged_in = False

    # Chat state
    if "session_id" not in st.session_state:
        st.session_state.session_id = f"user_{uuid.uuid4().hex[:8]}"

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    if "artifacts" not in st.session_state:
        st.session_state.artifacts = {}  # Store tool artifacts

    if "pending_approval" not in st.session_state:
        st.session_state.pending_approval = None

    # Stream format preference (ndjson or sse)
    if "stream_format" not in st.session_state:
        st.session_state.stream_format = "ndjson"

    # Debug log
    if "debug_log" not in st.session_state:
        st.session_state.debug_log = []

def log_debug(message: str):
    """Add debug message to log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.debug_log.append(f"[{timestamp}] {message}")
    # Keep only last 100 messages
    if len(st.session_state.debug_log) > 100:
        st.session_state.debug_log = st.session_state.debug_log[-100:]

init_session_state()

# ==================== Authentication Functions ====================
def get_auth_headers() -> Dict[str, str]:
    """Get authentication headers for API requests."""
    headers = {"Content-Type": "application/json"}
    if st.session_state.auth_token:
        headers["Authorization"] = f"Bearer {st.session_state.auth_token}"
    return headers


def register_user(username: str, password: str, email: str = None) -> bool:
    """Register a new user."""
    try:
        payload = {"username": username, "password": password}
        if email:
            payload["email"] = email

        res = requests.post(
            f"{SERVER_URL}/api/v1/auth/register",
            json=payload,
            timeout=10
        )

        if res.status_code == 200:
            data = res.json()
            st.session_state.auth_token = data.get("token")
            st.session_state.user_id = data.get("user_id")
            st.session_state.username = data.get("username")
            st.session_state.is_logged_in = True
            st.success(f"✅ 注册成功！欢迎，{data.get('username')}！")
            return True
        else:
            error = res.json().get("detail", "Registration failed")
            st.error(f"❌ 注册失败: {error}")
            return False

    except requests.exceptions.ConnectionError:
        st.error("❌ 无法连接到服务器")
        return False
    except Exception as e:
        st.error(f"❌ 注册失败: {e}")
        return False


def login_user(username: str, password: str) -> bool:
    """Login with username and password."""
    try:
        payload = {"username": username, "password": password}
        res = requests.post(
            f"{SERVER_URL}/api/v1/auth/login",
            json=payload,
            timeout=10
        )

        if res.status_code == 200:
            data = res.json()
            st.session_state.auth_token = data.get("token")
            st.session_state.user_id = data.get("user_id")
            st.session_state.username = data.get("username")
            st.session_state.is_logged_in = True
            st.success(f"✅ 登录成功！欢迎回来，{data.get('username')}！")
            st.rerun()
            return True
        else:
            error = res.json().get("detail", "Login failed")
            st.error(f"❌ 登录失败: {error}")
            return False

    except requests.exceptions.ConnectionError:
        st.error("❌ 无法连接到服务器")
        return False
    except Exception as e:
        st.error(f"❌ 登录失败: {e}")
        return False


def logout_user():
    """Logout current user."""
    st.session_state.auth_token = None
    st.session_state.user_id = None
    st.session_state.username = None
    st.session_state.is_logged_in = False
    st.session_state.chat_history = []
    st.session_state.artifacts = {}
    st.session_state.pending_approval = None
    st.success("✅ 已登出")
    st.rerun()


def refresh_token() -> bool:
    """Refresh authentication token."""
    if not st.session_state.auth_token:
        return False

    try:
        res = requests.post(
            f"{SERVER_URL}/api/v1/auth/refresh",
            headers=get_auth_headers(),
            timeout=10
        )

        if res.status_code == 200:
            data = res.json()
            st.session_state.auth_token = data.get("token")
            return True
        return False

    except Exception:
        return False


def get_current_user_info() -> Optional[Dict]:
    """Get current user information."""
    if not st.session_state.auth_token:
        return None

    try:
        res = requests.get(
            f"{SERVER_URL}/api/v1/auth/me",
            headers=get_auth_headers(),
            timeout=10
        )

        if res.status_code == 200:
            return res.json()
        return None

    except Exception:
        return None


# ==================== Authentication UI ====================
def render_auth_page():
    """Render login/register page."""
    st.title("🤖 UltraClient - 用户认证")

    tab1, tab2 = st.tabs(["登录 (Login)", "注册 (Register)"])

    with tab1:
        st.subheader("登录到您的账户")
        username = st.text_input("用户名", key="login_username")
        password = st.text_input("密码", type="password", key="login_password")

        if st.button("登录", type="primary", use_container_width=True):
            if username and password:
                login_user(username, password)
            else:
                st.warning("请输入用户名和密码")

    with tab2:
        st.subheader("创建新账户")
        new_username = st.text_input("用户名", key="reg_username")
        new_password = st.text_input("密码", type="password", key="reg_password")
        confirm_password = st.text_input("确认密码", type="password", key="reg_confirm_password")
        email = st.text_input("邮箱 (可选)", key="reg_email")

        if st.button("注册", type="primary", use_container_width=True):
            if not new_username or not new_password:
                st.warning("请填写必填字段")
            elif new_password != confirm_password:
                st.error("密码不匹配")
            elif len(new_password) < 6:
                st.error("密码长度至少为6位")
            elif len(new_username) < 3:
                st.error("用户名长度至少为3位")
            else:
                register_user(new_username, new_password, email or None)

    # Guest mode (skip authentication)
    st.divider()
    st.markdown("---")
    if st.button("🚀 访客模式 (Guest Mode) - 无需登录"):
        st.session_state.user_id = "guest"
        st.session_state.username = "Guest"
        st.session_state.is_logged_in = True
        st.info("以访客模式进入，数据将不会被保存")
        st.rerun()


# ==================== API Functions ====================
@st.cache_data(ttl=5, show_spinner=False)
def fetch_sessions() -> list:
    """Fetch list of sessions with metadata."""
    try:
        url = f"{SERVER_URL}/sessions"

        # If logged in, use user-specific endpoint
        if st.session_state.is_logged_in and st.session_state.user_id:
            url = f"{SERVER_URL}/users/{st.session_state.user_id}/sessions"

        res = requests.get(url, headers=get_auth_headers(), timeout=5)

        if res.status_code == 200:
            data = res.json()
            return data.get("sessions", [])
    except Exception:
        pass
    return []


def load_session_state(session_id: str) -> Optional[Dict]:
    """Load complete state for a session."""
    try:
        res = requests.get(
            f"{SERVER_URL}/agent/{session_id}/state",
            headers=get_auth_headers()
        )
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

def parse_sse_event(buffer: str) -> tuple[Optional[str], Optional[Dict], str]:
    """
    尝试从缓冲区解析一个完整的 SSE 消息。
    返回: (event_type, json_data, remaining_buffer)
    """
    if "\n\n" not in buffer:
        return None, None, buffer

    # 分割出第一条完整的消息
    raw_msg, remaining = buffer.split("\n\n", 1)
    
    event_type = None
    data = None

    for line in raw_msg.split("\n"):
        line = line.strip()
        if not line: continue
        
        # 解析 event:
        if line.startswith("event:"):
            event_type = line[6:].strip()
        
        # 解析 data:
        elif line.startswith("data:"):
            content = line[5:].strip()
            try:
                # 尝试合并多行 data (虽然这里假设一行 data 就是完整 JSON)
                if data is None:
                    data = json.loads(content)
                else:
                    # 如果有多行 data，通常意味着文本拼接，但在 JSON 场景较少见
                    # 这里简化处理，以后面的为准或合并
                    pass 
            except json.JSONDecodeError:
                pass  # 忽略解析错误的行

    # 如果没指定 event，但有数据，尝试从数据里回填 type (兼容旧逻辑)
    if not event_type and isinstance(data, dict):
        event_type = data.get("type")

    return event_type, data, remaining


def parse_sse_line(line: str) -> tuple:
    """
    解析 SSE 格式的一行或多行。

    Args:
        line: SSE 数据行

    Returns:
        (event_type, data) 元组，如果解析失败则返回 (None, None)

    Note:
        服务端 SSE 格式为:
        event: token
        data: {"type": "token", "data": "hello"}

        我们返回 (event_type, data_json)，其中 data_json 是完整的 {"type": "token", "data": "hello"} 对象
    """
    if not line.strip():
        return None, None

    # SSE 格式: "data: {...}" 或 "event: xxx\ndata: {...}"
    event_type = None
    data_json = None

    for part in line.split('\n'):
        part = part.strip()
        if part.startswith('event:'):
            event_type = part[6:].strip()
        elif part.startswith('data:'):
            data_str = part[5:].strip()
            try:
                data_json = json.loads(data_str)
            except json.JSONDecodeError:
                continue

    if data_json:
        # 返回完整的 data_json 对象，让调用者根据需要提取字段
        return event_type or data_json.get("type"), data_json
    return None, None



def process_stream(response, msg_placeholder, status_box, stream_format: str = "ndjson"):
    """
    处理流式响应，支持 NDJSON 和 SSE 格式。

    Args:
        response: 响应对象
        msg_placeholder: 消息占位符
        status_box: 状态框
        stream_format: 流式格式 - "ndjson" 或 "sse"
    """
    full_text = ""  # 使用字符串变量累积文本

    if response.status_code != 200:
        msg_placeholder.error(f"Server Error: {response.status_code}")
        return ""

    try:
        # 生成事件迭代器
        def event_iterator():
            if stream_format == "sse":
                # SSE 格式解析
                buffer = ""
                # 使用 iter_content 确保不遗漏任何字符（包括空行）
                for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                    if not chunk: continue
                    buffer += chunk
                    
                    while "\n\n" in buffer:
                        evt_type, evt_data, buffer = parse_sse_event(buffer)
                        if evt_data:
                            # 构造统一格式供下游消费
                            # 如果 parse_sse_event 没解析出 type，尝试默认值
                            final_type = evt_type or evt_data.get("type") or "unknown"
                            yield final_type, evt_data
            else:
                # NDJSON 格式解析
                for line in response.iter_lines():
                    if not line: continue

                    try:
                        data_str = line.decode('utf-8')
                        payload = json.loads(data_str)
                        event_type = payload.get("type")
                        if event_type:
                            yield event_type, payload  # 返回完整的 payload 对象
                    except json.JSONDecodeError:
                        continue

        # 处理所有事件
        event_count = 0
        log_debug(f"📡 Starting event processing (format={stream_format})...")
        for event_type, data in event_iterator():
            event_count += 1
            # ================= 事件处理 =================
            # data 现在是完整的 JSON 对象，例如: {"type": "token", "data": "hello"}
            # 需要从中提取实际的数据

            # 获取实际数据内容（兼容两种格式）
            # 兼容性处理：data 可能是 payload 可能是完整信封
            actual_data = data.get("data") if isinstance(data, dict) and "data" in data else data

            # 记录事件
            log_debug(f"📨 Event #{event_count}: {event_type}")

            # 调试信息
            if stream_format == "sse" and event_count <= 3:
                status_box.write(f"🔍 SSE Event #{event_count}: type={event_type}, data={str(actual_data)[:50]}...")

            # 1. 文本生成 (Token)
            if event_type == "token":
                full_text += actual_data
                msg_placeholder.markdown(full_text + "▌")

            # 2. 工具开始 (Tool Start)
            elif event_type == "tool_start":
                tool_name = actual_data.get("name", "unknown")
                status_box.write(f"🔨 Calling tool: **{tool_name}**...")

            # 3. 工具结束 (Tool End)
            elif event_type == "tool_end":
                result = actual_data.get("result", "")
                meta = actual_data.get("meta", {})
                tool_name = meta.get("tool", "tool")

                status_box.markdown(f"✅ **{tool_name}** finished.")

                if isinstance(result, (dict, list)):
                    status_box.json(result, expanded=False)
                else:
                    try:
                        if isinstance(result, str) and (result.strip().startswith('{') or result.strip().startswith('[')):
                            parsed = json.loads(result)
                            status_box.json(parsed, expanded=False)
                        else:
                            status_box.code(str(result), language="text", wrap_lines=True)
                    except:
                        status_box.code(str(result), language="text", wrap_lines=True)

            # 4. Artifact (图表/表格)
            elif event_type == "tool_artifact":
                art_id = actual_data.get("id")
                st.session_state.artifacts[art_id] = actual_data

                with status_box:
                    st.caption(f"📊 Generated Artifact: {actual_data.get('title')}")
                    render_artifact(actual_data)

            # 5. 状态变更 / 思考
            elif event_type == "state_change":
                if "intent" in actual_data and actual_data["intent"]:
                    status_box.info(f"🎯 Intent detected: **{actual_data['intent']}**")
                if "msg" in actual_data:
                    status_box.write(f"🧠 {actual_data['msg']}")

            # 6. 审批请求
            elif event_type == "approval_req":
                tool_name = actual_data.get("tool")
                args = actual_data.get("args")
                current = st.session_state.get("pending_approval")
                if not current or current.get("tool") != tool_name:
                    status_box.update(label="✋ Waiting for approval...", state="error", expanded=True)
                    st.session_state.pending_approval = {"tool": tool_name, "args": args}
                    st.rerun()
                return ""

            # 7. 错误
            elif event_type == "error":
                status_box.error(f"❌ Error: {actual_data}")

            # 8. 其他未知事件类型（调试用）
            else:
                status_box.write(f"🔔 Unknown event type: {event_type}")

        status_box.update(label="✨ Task Complete", state="complete", expanded=True)
        msg_placeholder.markdown(full_text)
        return full_text

    except Exception as e:
        status_box.error(f"Stream error: {e}")
        return full_text


# ==================== Approval UI ====================
def render_approval_box(approval_data: Dict):
    """Render approval request UI."""
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
        params = {"format": st.session_state.stream_format}

        st.session_state.pending_approval = None

        with st.chat_message("assistant"):
            response_container = st.empty()

            with requests.post(
                url,
                params=params,
                json={"approved": approved, "feedback": feedback},
                headers=get_auth_headers(),
                stream=True
            ) as response:
                status_box = st.status("Processing approval...", expanded=True)
                process_stream(response, response_container, status_box, st.session_state.stream_format)

        st.rerun()

    except Exception as e:
        st.error(f"Failed to send approval: {e}")


# ==================== Sidebar ====================
def render_sidebar():
    """Render sidebar with user info and session list."""
    with st.sidebar:
        st.title("🗂️ UltraClient")

        # User info section
        if st.session_state.is_logged_in:
            user_info_col1, user_info_col2 = st.columns([3, 1])
            with user_info_col1:
                st.markdown(f"👤 **{st.session_state.username}**")
                if st.session_state.user_id == "guest":
                    st.caption("访客模式")
            with user_info_col2:
                if st.button("🚪", key="btn_logout", help="登出"):
                    logout_user()
        else:
            st.info("请登录以保存数据")

        st.divider()

        # Stream format selector
        st.caption("📡 流式格式 / Stream Format")
        format_col1, format_col2 = st.columns([1, 1])
        with format_col1:
            if st.button("NDJSON", use_container_width=True, type="primary" if st.session_state.stream_format == "ndjson" else "secondary"):
                st.session_state.stream_format = "ndjson"
                st.rerun()
        with format_col2:
            if st.button("SSE", use_container_width=True, type="primary" if st.session_state.stream_format == "sse" else "secondary"):
                st.session_state.stream_format = "sse"
                st.rerun()

        st.divider()

        if st.button("➕ 新建会话 (New Chat)", use_container_width=True, type="primary"):
            create_new_session()

        st.divider()

        # Debug log section
        with st.expander("🔍 调试日志 / Debug Log", expanded=False):
            if st.button("清空日志", key="clear_debug_log"):
                st.session_state.debug_log = []
                st.rerun()

            # Show logs
            for log_entry in reversed(st.session_state.debug_log):
                st.text(log_entry)

            # Log count
            st.caption(f"共 {len(st.session_state.debug_log)} 条日志")

        st.divider()

        sessions = fetch_sessions()

        # Group by time
        today_sess = []
        yesterday_sess = []
        older_sess = []

        today = date.today()

        for s in sessions:
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


# ==================== Main Application ====================

# Check authentication first
if not st.session_state.is_logged_in:
    render_auth_page()
else:
    # Authenticated - show main interface
    render_sidebar()

    # Main Chat Interface
    st.header(f"UltraClient Pro - {st.session_state.username}")

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
        # Approval Mode
        render_approval_box(st.session_state.pending_approval)

    else:
        # Normal Chat Mode
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
                    params = {"format": st.session_state.stream_format}

                    # Use user-specific endpoint if logged in
                    if st.session_state.user_id and st.session_state.user_id != "guest":
                        url = f"{SERVER_URL}/users/{st.session_state.user_id}/chat/{st.session_state.session_id}"
                    else:
                        url = f"{SERVER_URL}/chat/{st.session_state.session_id}"

                    log_debug(f"🌐 Request: {url}?format={st.session_state.stream_format}")

                    res = requests.post(
                        url,
                        params=params,
                        json=payload,
                        headers=get_auth_headers(),
                        stream=True
                    )

                    log_debug(f"📊 Response status: {res.status_code}, Content-Type: {res.headers.get('Content-Type', 'N/A')}")

                    status_box = st.status("Thinking & Planning...", expanded=True)
                    final_text = process_stream(res, response_container, status_box, st.session_state.stream_format)

                    if final_text:
                        st.session_state.chat_history.append({
                            "role": "assistant",
                            "content": final_text
                        })

                except requests.exceptions.ConnectionError:
                    st.error("无法连接到服务器。请确保 agent 服务正在运行。")
                except Exception as e:
                    st.error(f"Error: {e}")
