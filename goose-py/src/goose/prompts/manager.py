import platform
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

from ..conversation import Message, Role, ToolResponse, ToolRequest
from .base import PromptEngine
from ..utils.token_counter import TokenCounter


class PromptManager:
    def __init__(self, template_dir: Optional[Path] = None):
        self.engine = PromptEngine(template_dir) if template_dir else PromptEngine()
        # [新增] 全局上下文缓存 (例如 OS 信息不需要每次都获取)
        self._global_context = {
            "os_name": platform.system(),
            "os_version": platform.release(),
        }
        self.token_counter:TokenCounter = TokenCounter()

    def _get_context(self, overrides: Dict[str, Any] = {}) -> Dict[str, Any]:
        """合并：全局上下文 + 动态上下文 (时间/CWD) + 用户参数"""
        ctx = self._global_context.copy()
        ctx.update({
            "current_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "working_dir": os.getcwd(),
        })
        ctx.update(overrides)
        return ctx

    def render(self, template_name: str, **kwargs) -> str:
        """通用渲染入口"""
        context = self._get_context(kwargs)
        return self.engine.render(template_name, context)

    # --- 高级功能：消息构建器 (Chat Builder) ---

    def build_system_message(self, tools: List[Dict] = [], template: str = "system.md") -> Message:
        """构建 System Message 对象"""
        content = self.render(template, tools=tools)
        return Message(role=Role.SYSTEM, content=[{"type": "text", "text": content}])

    def build_user_message(self, template_name: str, **kwargs) -> Message:
        """
        根据模板构建 User Message
        例如：render('task.md', task="Fix bugs") -> Message.user(...)
        """
        content = self.render(template_name, **kwargs)
        return Message.user(content)

    def _is_tool_request(self, msg: Message) -> bool:
        """Helper: 判断消息是否包含工具请求"""
        return any(isinstance(c, ToolRequest) for c in msg.content)

    def _is_tool_response(self, msg: Message) -> bool:
        """Helper: 判断消息是否包含工具结果"""
        return any(isinstance(c, ToolResponse) for c in msg.content)

    def format_history(
        self, 
        history: List[Message], 
        max_tokens: int = 4000
    ) -> List[Message]:
        """
        [核心升级] 智能截断历史记录 (Fail-safe Pruner)
        
        策略：
        1. 计算总 Token。
        2. 如果超限，从头部开始删除。
        3. 保护机制：如果遇到 ToolRequest，尝试连同其后的 ToolResponse 一起删除 (Atomic Removal)，
           防止破坏工具调用的上下文完整性。
        """
        if not history:
            return []

        # 1. 计算当前总 Token
        current_tokens = self.token_counter.count_messages(history)
        
        # 如果未超限，直接返回
        if current_tokens <= max_tokens:
            return history

        # 复制列表以进行操作
        pruned_history = history.copy()
        
        # print(f"✂️ [Pruner] Start pruning: {current_tokens} > {max_tokens} tokens")

        while current_tokens > max_tokens and pruned_history:
            # 准备移除的消息列表 (本轮循环要删除的消息)
            msgs_to_remove = []
            
            first_msg = pruned_history[0]
            
            # --- 智能成对删除逻辑 ---
            
            if self._is_tool_response(first_msg):
                # 情况 A: 头部是工具结果 (ToolResponse)
                # 这通常是"孤儿"消息 (其对应的 Request 已经被删了)，直接删除
                msgs_to_remove.append(first_msg)
            
            elif self._is_tool_request(first_msg):
                # 情况 B: 头部是工具请求 (ToolRequest)
                # 必须向后看，尝试找到对应的 Result 一起删除
                msgs_to_remove.append(first_msg)
                
                # 检查下一条是否是结果
                if len(pruned_history) > 1:
                    next_msg = pruned_history[1]
                    if self._is_tool_response(next_msg):
                        # 找到了成对的 Result，加入删除列表
                        msgs_to_remove.append(next_msg)
                    # 注意：如果下一条不是 Result (比如连续 Call 或者用户打断)，
                    # 我们就只删这个 Request，这也是安全的。
            
            else:
                # 情况 C: 普通文本消息 (User/Assistant Text)
                # 直接删除
                msgs_to_remove.append(first_msg)

            # --- 执行删除并更新 Token ---
            
            for msg in msgs_to_remove:
                # 扣减 Token
                msg_tokens = self.token_counter.count_message(msg)
                current_tokens -= msg_tokens
                
                # 从列表中移除 (始终移除 index 0，因为我们是顺序处理的)
                if pruned_history:
                    pruned_history.pop(0)

            # print(f"   - Removed batch of {len(msgs_to_remove)} msgs. Remaining tokens: {current_tokens}")

        # 最后的一道防线：如果因为某种边界情况删空了或者还不够 (极少发生)
        # 这里不需要额外操作，while 循环条件保证了退出时要么空了，要么满足 token 限制

        return pruned_history

    def create_chat_completion_payload(
        self,
        system_template: str,
        user_template: str,
        history: List[Message],
        variables: Dict[str, Any],
        max_tokens: int = 4000 # [新增] Token 限制参数
    ) -> List[Message]:
        """
        构建完整的消息载荷 (含截断逻辑)
        """
        # 1. 构建 System Message (这是必须保留的)
        tools = variables.get("tools", [])
        system_msg = self.build_system_message(tools, system_template)
        
        # 2. 构建 User Message (这是必须保留的)
        user_vars = {k: v for k, v in variables.items() if k != "tools"}
        user_msg = self.build_user_message(user_template, **user_vars)

        # 3. 计算预留空间
        # 我们需要保留空间给 System Prompt, User Query 和 模型回复
        # 假设 system + user_msg 占用了 X token，剩下的空间 (max_tokens - X) 给历史记录
        reserved_tokens = self.token_counter.count_messages([system_msg, user_msg])
        available_for_history = max_tokens - reserved_tokens

        # 如果连 System + User 都放不下，那说明 max_tokens 设置太小了，或者 Prompt 太长
        if available_for_history < 0:
            print("⚠️ Warning: System prompt + User input exceeds token limit!")
            available_for_history = 0 

        # 4. 截断历史记录
        pruned_history = self.format_history(history, max_tokens=available_for_history)

        # 5. 组装最终列表
        messages = [system_msg] + pruned_history + [user_msg]
        
        total_final = self.token_counter.count_messages(messages)
        # print(f"📊 Final Payload: {len(messages)} msgs, ~{total_final} tokens")
        
        return messages

_global_manager = None

def get_prompt_manager() -> PromptManager:
    global _global_manager
    if _global_manager is None:
        _global_manager = PromptManager()
    return _global_manager