"""Legacy event types for backward compatibility."""
from enum import Enum


class EventType(str, Enum):
    """Event types for agent lifecycle and tool execution."""

    # === 1. 任务生命周期 (Lifecycle) ===
    RUN_START = "run_start"         # [新增] 整个任务开始（前端用于重置 UI、显示 Loading）
    DONE = "done"                   # 任务完全结束（流结束信号）
    ERROR = "error"                 # 全局致命错误

    # === 2. LLM 内容生成 (Content Generation) ===
    TOKEN_START = "token_start"     # LLM 开始生成（首字延迟统计）
    TOKEN = "token"                 # 标准文本 Token
    TOKEN_END = "token_end"         # LLM 生成结束

    # [新增] 深度思考/推理 Token (适配 DeepSeek-R1, o1 等模型)
    # 允许前端将"思考过程"折叠显示，与最终答案区分开
    THINKING_START = "thinking_start"
    THINKING_TOKEN = "thinking_token"
    THINKING_END = "thinking_end"

    # === 3. 工具与执行 (Tools & Actions) ===
    STATE_CHANGE = "state_change"   # 状态变更 (Intent 确认 / Plan 更新 / 步骤切换)
    TOOL_START = "tool_start"       # 工具开始调用 (包含 input 参数)
    TOOL_END = "tool_end"           # 工具调用结束 (包含 output 结果，meta 中包含 artifacts)

    # === 4. 人机交互与控制 (Interaction) ===
    APPROVAL_REQ = "approval_req"   # 需要人工审批

    # [新增] 协议保活 (Keep-Alive)
    # NDJSON 模式下，如果 Agent 长时间思考不输出，需要发 Ping 包防止连接断开
    PING = "ping"
