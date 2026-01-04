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
        if isinstance(inputs, str):
            content = inputs
        elif isinstance(inputs, dict):
            # 尝试寻找常见的输入字段
            content = inputs.get("query") or inputs.get("input") or json.dumps(inputs)
        
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
        仅针对 LLM 类型的节点
        """
        # 1. 判断是否是 LLM 节点
        # 假设 Component 有 kind 属性，或者根据类名判断
        is_llm = False
        if hasattr(node.component, 'kind') and node.component.kind == ResourceKind.LLM:
            is_llm = True
        elif "LLM" in node.component.__class__.__name__:
            is_llm = True
            
        if is_llm and output:
            # 2. 提取内容
            content = output
            if isinstance(output, dict):
                content = output.get("content") or output.get("text") or json.dumps(output)
            elif hasattr(output, "content"): # Message object
                content = output.content
                
            # 3. 写入数据库
            await self.repo.add_message(
                session_id=run_id,
                message=Message(role=Role.ASSISTANT, content=str(content))
            )
            logger.info(f"🤖 [Hook] Assistant message saved from node {node.id}")
            
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
