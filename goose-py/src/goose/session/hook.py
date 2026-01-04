import logging
import json
from typing import Any, Dict
from goose.workflow.hooks import WorkflowHook
from goose.workflow.context import WorkflowContext
from goose.workflow.graph import Node
from goose.session.repository import SessionRepository
from goose.conversation import Message, Role
from goose.resources.types import ResourceKind
from goose.session import SessionManager, SessionType

logger = logging.getLogger("goose.session.hook")

class SessionPersistenceHook(WorkflowHook):
    """
    负责将工作流执行映射到会话记录 (Session/Messages)
    """
    def __init__(self):
        self.repo = SessionRepository()

    async def on_workflow_start(self, run_id: str, inputs: Any, context: WorkflowContext):
        """
        1. 保存用户输入 (User Message)
        2. [读取] 加载历史记录并注入 Context
        """
        # --- A. 确保 Session 存在 (初始化逻辑迁移至此) ---
        # 注意：这里我们假设 run_id 已经被 Scheduler 生成好了
        try:
            session = await SessionManager.get_session(run_id)
            if not session:
                # Session 不存在，延迟创建 (Lazy Creation)
                # 这完全符合逻辑：只有当工作流真的跑起来了，我们才需要这个 Session
                logger.info(f"🆕 [Hook] Registering new session for run: {run_id}")
                await SessionManager.create_session(
                    session_id=run_id, 
                    name=f"Run {run_id[:8]}",
                    session_type=SessionType.WORKFLOW
                )
        except Exception as e:
            logger.error(f"Failed to ensure session: {e}")
            # 根据策略，这里可以选择抛出异常阻断流程，或者降级运行

        # --- A. 写入用户消息 ---
        # 提取用户输入文本
        content = ""
        if isinstance(inputs, dict):
            content = json.dumps(inputs, ensure_ascii=False)
        else:
            content = str(inputs)
        
        if content:
            await self.repo.add_message(
                session_id=run_id,
                message=Message(role=Role.USER, content=content)
            )
            logger.info(f"📝 [Hook] User message saved for {run_id}")

        # --- B. [读取] 历史注入 (Context Injection) ---
        # 自动查库，将历史记录放入变量，这样 LLM 节点直接用 {{ chat_history }} 就能拿到
        history = await self.repo.get_messages(session_id=run_id)
        
        # 将 Message 对象列表转为 LLM 友好的字典格式
        # 排除掉刚刚插入的那条(避免重复)，或者由 LLM 组件自己处理
        # 这里简单全量注入
        history_dicts = [
            {"role": msg.role.value, "content": msg.content} 
            for msg in history
        ]
        
        # 注入到上下文变量池中
        context.variables["chat_history"] = history_dicts
        logger.info(f"📚 [Hook] Injected {len(history)} history messages into context")

    async def on_node_end(self, run_id: str, node: Node, output: Any, context: WorkflowContext):
        """
        保存 AI 回复 (Assistant Message)
        """
        # 1. 判断是否是 LLM 节点 (保持原逻辑)
        is_llm = False
        # 增加对 type 字符串的判断，更加鲁棒
        if hasattr(node, 'type') and (node.type == 'model.llm' or 'llm' in str(node.type).lower()):
            is_llm = True
        elif hasattr(node.component, 'kind') and str(node.component.kind) == 'llm':
            is_llm = True
        elif "LLM" in node.component.__class__.__name__:
            is_llm = True
            
        if is_llm and output:
            # 2. 智能提取文本内容
            text_content = ""
            
            if isinstance(output, str):
                text_content = output
            elif isinstance(output, dict):
                # 优先找 'result', 'text', 'answer', 'content' 这些常见字段
                for key in ["result", "text", "content", "answer"]:
                    if key in output and output[key]:
                        val = output[key]
                        text_content = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
                        break
                # 如果没找到常见字段，为了不丢数据，转存整个 JSON
                if not text_content:
                    text_content = json.dumps(output, ensure_ascii=False)
            elif hasattr(output, "content"): 
                text_content = str(output.content)
            else:
                text_content = str(output)

            # 3. [关键修复] 构造符合 Pydantic 定义的 Message
            # 既然报错说要 List，我们就把字符串包在列表里
            # 假设 Message 定义是 content: List[str] 或 List[ContentItem]
            # 如果是 List[str]:
            final_content = [text_content]
            
            # 如果是 List[ContentItem]，你需要根据你的 domain 定义来构造，例如:
            # final_content = [ContentItem(type="text", text=text_content)]
            
            # 这里按最常见的 List[str] 或兼容格式处理：
            try:
                await self.repo.add_message(
                    session_id=run_id,
                    message=Message(role=Role.ASSISTANT, content=final_content)
                )
                logger.info(f"🤖 [Hook] Assistant message saved from node {node.id}")
            except Exception as e:
                # 兜底日志，防止 hook 炸掉整个流程
                logger.error(f"Failed to save assistant message: {e}")
            
    async def on_workflow_end(self, run_id: str, outputs: Any, context: WorkflowContext):
        """
        保存工作流输出 (Workflow Output)
        """
        logger.info(f"📝 [Hook] Workflow outputs saved for {run_id}")

    async def on_workflow_error(self, run_id: str, error: Any, context: WorkflowContext):
        """
        保存工作流错误 (Workflow Error)
        """
        logger.info(f"💥 [Hook] Workflow error saved for {run_id}")
