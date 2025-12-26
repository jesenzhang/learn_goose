import logging
from typing import List, Tuple, Optional
from .conversation import Message, Conversation, MessageContent, MessageMetadata, Role,ToolResponse,TextContent,ToolRequest
from .providers.base import Provider, ProviderUsage
from .utils.token_counter import create_token_counter
from .prompts import get_prompt_manager
# from .config import Config # 假设你有配置模块

logger = logging.getLogger(__name__)

DEFAULT_COMPACTION_THRESHOLD = 0.8

CONVERSATION_CONTINUATION_TEXT = """The previous message contains a summary that was prepared because a context limit was reached.
Do not mention that you read a summary or that conversation summarization occurred.
Just continue the conversation naturally based on the summarized context"""

TOOL_LOOP_CONTINUATION_TEXT = """The previous message contains a summary that was prepared because a context limit was reached.
Do not mention that you read a summary or that conversation summarization occurred.
Continue calling tools as necessary to complete the task."""

MANUAL_COMPACT_CONTINUATION_TEXT = """The previous message contains a summary that was prepared at the user's request.
Do not mention that you read a summary or that conversation summarization occurred.
Just continue the conversation naturally based on the summarized context"""

async def check_if_compaction_needed(
    provider: Provider,
    conversation: Conversation,
    session_total_tokens: Optional[int], # 从 Session 对象传入
    threshold_override: Optional[float] = None
) -> bool:
    """
    检查是否需要进行消息压缩
    Rust: pub async fn check_if_compaction_needed(...)
    """
    messages = conversation.messages
    threshold = threshold_override or DEFAULT_COMPACTION_THRESHOLD
    
    context_limit = provider.get_model_config().context_limit or 128_000 # 默认值防止 None

    # Determine current tokens
    if session_total_tokens:
        current_tokens = session_total_tokens
        source = "session metadata"
    else:
        token_counter = create_token_counter()
        # Filter agent visible messages
        visible_msgs = [m for m in messages if m.metadata.agent_visible]
        current_tokens = token_counter.count_chat_tokens("", visible_msgs, [])
        source = "estimated"

    usage_ratio = current_tokens / float(context_limit)
    needs_compaction = False if (threshold <= 0.0 or threshold >= 1.0) else (usage_ratio > threshold)

    logger.debug(
        f"Compaction check: {current_tokens} / {context_limit} tokens ({usage_ratio:.1%}), "
        f"threshold: {threshold:.1%}, needs: {needs_compaction}, source: {source}"
    )

    return needs_compaction

def filter_tool_responses(messages: List[Message], remove_percent: int) -> List[Message]:
    """
    渐进式移除 Tool Response 消息 (Middle-out 策略)
    Rust: fn filter_tool_responses(...)
    """
    if remove_percent == 0:
        return list(messages)

    # 找到所有 ToolResponse 的索引
    tool_indices = [
        i for i, m in enumerate(messages) 
        if any(isinstance(c, ToolResponse) for c in m.content)
    ]

    if not tool_indices:
        return list(messages)

    num_to_remove = max(1, int((len(tool_indices) * remove_percent) / 100))
    middle = len(tool_indices) // 2
    indices_to_remove = set()

    # 从中间向两边移除 (Middle out)
    for i in range(num_to_remove):
        if i % 2 == 0:
            offset = i // 2
            if middle > offset:
                indices_to_remove.add(tool_indices[middle - offset - 1])
        else:
            offset = i // 2
            if middle + offset < len(tool_indices):
                indices_to_remove.add(tool_indices[middle + offset])

    return [m for i, m in enumerate(messages) if i not in indices_to_remove]

async def do_compact(
    provider: Provider,
    messages: List[Message]
) -> Tuple[Message, ProviderUsage]:
    """
    执行实际的压缩逻辑：尝试移除工具结果 -> 生成总结
    Rust: async fn do_compact(...)
    """
    agent_visible_messages = [m for m in messages if m.metadata.agent_visible]
    
    # 渐进式移除策略：0% -> 10% -> ... -> 100%
    removal_percentages = [0, 10, 20, 50, 100]
    
    pm = get_prompt_manager() # 获取 PromptManager
    
    for attempt, remove_percent in enumerate(removal_percentages):
        # 1. 过滤消息
        filtered_msgs = filter_tool_responses(agent_visible_messages, remove_percent)
        
        # 2. 格式化为文本 (用于生成 Summary)
        # 这里为了简化，直接用 as_concat_text，实际 Rust 中有专门的 format_message_for_compacting
        messages_text = "\n".join([f"[{m.role.value}]: {m.as_concat_text()}" for m in filtered_msgs])
        
        # 3. 渲染 Prompt
        system_prompt = pm.render("summarize_oneshot.md", messages=messages_text)
        
        user_msg = Message.user("Please summarize the conversation history provided in the system prompt.")
        
        try:
            # 4. 调用 LLM 生成总结
            # 注意：这里需要 Provider 支持 complete_fast 或者 standard complete
            response, usage = await provider.complete(system_prompt, [user_msg])
            
            # 修正 Role 为 User (因为这个总结将作为下一段对话的"背景信息")
            # Rust 代码中把 Role 改为了 User，虽然它是由 Assistant 生成的
            response.role = Role.USER 
            
            return response, usage
            
        except Exception as e:
            # 如果即使移除了部分工具结果还是超长，继续尝试更高的移除比例
            if "ContextLengthExceeded" in str(e): 
                if attempt < len(removal_percentages) - 1:
                    continue
                else:
                    raise RuntimeError("Failed to compact: context limit exceeded even after removing all tool responses")
            raise e

    raise RuntimeError("Unexpected: exhausted all attempts")

async def compact_messages(
    provider: Provider,
    conversation: Conversation,
    manual_compact: bool = False
) -> Tuple[Conversation, ProviderUsage]:
    """
    压缩入口函数
    Rust: pub async fn compact_messages(...)
    """
    messages = conversation.messages
    
    # 辅助函数: 检查是否只有文本 (Rust logic)
    def has_text_only(msg: Message):
        # 简化版实现
        has_text = any(isinstance(c, TextContent) for c in msg.content)
        has_tool = any(isinstance(c, (ToolRequest, ToolResponse)) for c in msg.content)
        return has_text and not has_tool

    # 1. Find preserved user message
    preserved_msg = None
    is_most_recent = False
    
    if not manual_compact:
        # 从后往前找最近一条 Agent 可见的纯文本用户消息
        for idx in range(len(messages) - 1, -1, -1):
            msg = messages[idx]
            if msg.metadata.agent_visible and msg.role == Role.USER and has_text_only(msg):
                preserved_msg = msg
                is_most_recent = (idx == len(messages) - 1)
                break

    # 2. 执行压缩 (生成总结)
    summary_msg, usage = await do_compact(provider, messages)

    # 3. 构建新的消息列表
    final_messages = []
    
    # A. 标记旧消息为不可见
    for idx, msg in enumerate(messages):
        # 特殊处理：如果是我们要保留的那条最新用户消息，我们先隐藏它，后面会追加一条新的
        updated_meta = MessageMetadata(agent_visible=False, user_visible=True)
        if is_most_recent and preserved_msg and msg.id == preserved_msg.id:
             updated_meta = MessageMetadata.invisible() # 完全隐藏旧的
        
        # 创建副本并更新元数据
        new_msg = msg.model_copy(update={"metadata": updated_meta})
        final_messages.append(new_msg)

    # B. 添加 Summary (Agent Only)
    summary_msg.metadata = MessageMetadata.agent_only()
    final_messages.append(summary_msg)

    # C. 添加 Continuation Text (告诉模型发生了什么)
    cont_text = MANUAL_COMPACT_CONTINUATION_TEXT if manual_compact else \
                CONVERSATION_CONTINUATION_TEXT if is_most_recent else \
                TOOL_LOOP_CONTINUATION_TEXT
    
    cont_msg = Message.assistant(cont_text)
    cont_msg.metadata = MessageMetadata.agent_only()
    final_messages.append(cont_msg)

    # D. 追加被保留的用户消息 (如果存在)
    if preserved_msg:
        # 提取文本并重新创建消息
        text = preserved_msg.as_concat_text()
        restored_msg = Message.user(text)
        final_messages.append(restored_msg)

    return Conversation(final_messages), usage