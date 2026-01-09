import streamlit as st
import requests
import json
import uuid

# ================= 配置 =================
SERVER_URL = "http://localhost:8300"

# ================= 状态初始化 =================
if "session_id" not in st.session_state:
    st.session_state.session_id = f"user_{str(uuid.uuid4())[:8]}"

if "messages" not in st.session_state:
    st.session_state.messages = []

if "agent_context" not in st.session_state:
    st.session_state.agent_context = {"intent": None, "slots": {}, "plan": []}

if "pending_approval" not in st.session_state:
    st.session_state.pending_approval = None

# ================= 辅助函数：流式处理 =================
def process_stream(response, message_placeholder):
    """
    处理服务器的 SSE (Server-Sent Events) 流。
    解析不同的 event 类型并更新 UI。
    """
    full_response = ""
    tool_status = None # 用于显示工具执行状态的容器
    
    for line in response.iter_lines():
        if not line: continue
        
        try:
            # 解析 NDJSON
            data_str = line.decode('utf-8')
            payload = json.loads(data_str)
            event = payload.get("event")
            data = payload.get("data")

            # --- Case 1: 文本生成 (Token) ---
            if event == "token":
                full_response += data
                message_placeholder.markdown(full_response + "▌")

            # --- Case 2: 工具开始执行 ---
            elif event == "tool_start":
                # 创建一个可折叠的状态栏显示工具调用
                if tool_status is None:
                    tool_status = message_placeholder.status("正在调用工具...", expanded=True)
                tool_status.write(f"🔨 **调用**: `{data['name']}`")
                tool_status.write(f"⚙️ **参数**: `{json.dumps(data['args'], ensure_ascii=False)}`")

            # --- Case 3: 工具执行结束 ---
            elif event == "tool_end":
                if tool_status:
                    tool_status.write(f"✅ **结果**: `{str(data.get('result'))[:100]}...`")
                    tool_status.update(label="工具调用完成", state="complete", expanded=False)
                    tool_status = None # 重置

            # --- Case 4: 状态/意图更新 ---
            elif event == "state_update":
                st.session_state.agent_context = data
                # 强制刷新侧边栏（Streamlit特性）
                st.rerun()

            # --- Case 5: 需要人工审批 (HITL) ---
            elif event == "approval_required":
                st.session_state.pending_approval = data
                st.warning(f"⚠️ 需要审批: {data['tool']}")
                st.rerun() # 刷新以显示审批按钮

            # --- Case 6: 系统消息 ---
            elif event == "system":
                # 显示为灰色小字
                full_response += f"\n\n*System: {data}*\n\n"
                message_placeholder.markdown(full_response)
            
            # --- Case 7: 错误 ---
            elif event == "error":
                st.error(f"Server Error: {data}")

        except json.JSONDecodeError:
            pass

    message_placeholder.markdown(full_response)
    return full_response

# ================= UI 布局 =================

st.set_page_config(page_title="MicroAgent Client", layout="wide")

st.title("🤖 MicroAgent 通用客户端")

# --- 侧边栏：状态监控面板 ---
with st.sidebar:
    st.header("🧠 内部状态监控")
    
    # 会话 ID
    new_session = st.text_input("Session ID", value=st.session_state.session_id)
    if new_session != st.session_state.session_id:
        st.session_state.session_id = new_session
        st.session_state.messages = []
        st.session_state.agent_context = {"intent": None, "slots": {}, "plan": []}
        st.rerun()
    
    st.divider()
    
    # 意图与槽位 (Intent & Slots)
    st.subheader("当前意图 (Intent)")
    intent = st.session_state.agent_context.get('intent')
    if intent:
        st.info(f"🎯 {intent}")
    else:
        st.text("未知")

    st.subheader("提取槽位 (Slots)")
    slots = st.session_state.agent_context.get('slots', {})
    if slots:
        st.json(slots)
    else:
        st.caption("暂无槽位信息")

    # 执行计划 (Plan)
    st.subheader("执行计划 (Plan)")
    plan = st.session_state.agent_context.get('plan', [])
    if plan:
        for i, step in enumerate(plan):
            st.checkbox(step, value=False, key=f"plan_{i}", disabled=True)
    else:
        st.caption("无活跃计划")

# --- 主界面：聊天窗口 ---

# 1. 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 2. 审批区域 (Human in the Loop)
if st.session_state.pending_approval:
    with st.chat_message("assistant"):
        st.error("🛑 **操作暂停：请求人工审批**")
        tool_info = st.session_state.pending_approval
        st.code(f"Tool: {tool_info['tool']}\nArgs: {json.dumps(tool_info['args'], indent=2)}")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("✅ 批准执行", type="primary"):
                # 发送批准请求
                with st.spinner("正在执行..."):
                    try:
                        res = requests.post(f"{SERVER_URL}/agent/{st.session_state.session_id}/approve", stream=True)
                        st.session_state.pending_approval = None # 清除审批状态
                        
                        # 处理恢复后的流
                        with st.chat_message("assistant"):
                            placeholder = st.empty()
                            full_response = process_stream(res, placeholder)
                            st.session_state.messages.append({"role": "assistant", "content": full_response})
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))

# 3. 输入区域
if prompt := st.chat_input("输入你的指令 (例如: 给张三转账100元)"):
    # 只有当没有待审批任务时才允许输入
    if st.session_state.pending_approval:
        st.toast("请先处理当前的审批请求！", icon="🚫")
    else:
        # 显示用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 调用 API 并流式接收
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            try:
                response = requests.post(
                    f"{SERVER_URL}/agent/{st.session_state.session_id}/chat",
                    json={"message": prompt},
                    stream=True
                )
                
                # 处理流
                full_response = process_stream(response, message_placeholder)
                
                # 保存助手回复到历史
                if full_response:
                    st.session_state.messages.append({"role": "assistant", "content": full_response})
            
            except Exception as e:
                st.error(f"连接服务器失败: {e}")