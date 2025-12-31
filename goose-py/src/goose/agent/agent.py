import logging
import asyncio
from typing import Optional, List,AsyncGenerator
from enum import Enum

from goose.session import SessionManager
from goose.conversation import Message, Role, TextContent, ToolRequest, ToolResponse, CallToolResult, Conversation
from goose.providers.base import Provider
from goose.toolkit import ToolRegistry
from .events import (
    EventBus, EventType, StreamerEvent, 
    TextEvent, ToolCallEvent, ToolResultEvent, StateEvent, ErrorEvent
)
from goose.events import MemoryEventBus
from goose.utils.concurrency import run_blocking
from goose.truncation.truncator import ContextTruncator


logger = logging.getLogger("goose.agent")

class AgentStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOLING = "tooling" # Executing tools
    SUSPENDED = "suspended" # Waiting for user confirmation/input

class Agent:
    def __init__(
        self, 
        name: str, 
        provider: Provider, 
        tools: Optional[ToolRegistry] = None,
        system_prompt: str = "You are a helpful AI assistant."
    ):
        self.name = name
        self.provider = provider
        self.tools = tools or ToolRegistry()
        self.system_prompt = system_prompt
        self.max_turns = 10
        
        # [新增] 事件总线
        self.events = MemoryEventBus()
        
        # [新增] 内部状态控制
        self._status = AgentStatus.IDLE
        self._running_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        
        self.truncator = ContextTruncator(max_tokens=16000, keep_last_messages=10)

    # --- 公共 API ---
    async def reply(
        self, 
        session_id: str, 
        user_input: Optional[str] = None
    ) -> AsyncGenerator[StreamerEvent, None]:
        """
        [便利方法] 包装了 process + subscribe 的逻辑。
        像以前一样使用 async for event in agent.reply(...)。
        """
        # 1. 启动后台任务
        await self.process(session_id, user_input)

        # 2. 订阅事件流
        # 注意：要在 process 之后尽快订阅，或者 EventBus 应该有极其短暂的 buffer (asyncio.Queue 自带缓冲)
        subscriber = self.events.subscribe()

        try:
            async for event in subscriber:
                yield event
                
                # 3. 自动退出条件
                # 当 Agent 变回 IDLE 或 SUSPENDED (等待用户输入) 时，停止 yield
                if event.type == EventType.STATE:
                    if event.status == AgentStatus.IDLE:
                        break
                    if event.status == AgentStatus.SUSPENDED:
                        # 可以在这里 yield 一个特殊的 "InputRequired" 事件，或者直接 break
                        break
        finally:
            # Generator 退出时会自动清理 subscriber (在 events.py 的 finally 块中处理)
            pass

    async def process(self, session_id: str, user_input: Optional[str] = None):
        """
        触发 Agent 处理流程（非阻塞，立即返回）。
        客户端应该 subscribe() 来获取结果。
        """
        if self._status != AgentStatus.IDLE and self._status != AgentStatus.SUSPENDED:
            logger.warning(f"Agent is busy ({self._status}), ignoring request.")
            return

        # 如果之前在运行，先确保它结束
        if self._running_task and not self._running_task.done():
            self._running_task.cancel()

        # 启动后台任务 (Actor Pattern)
        self._running_task = asyncio.create_task(
            self._main_loop(session_id, user_input)
        )

    async def stop(self):
        """强制停止"""
        if self._running_task:
            self._running_task.cancel()
            try:
                await self._running_task
            except asyncio.CancelledError:
                pass
        await self._set_state(AgentStatus.IDLE)

    # --- 核心循环 (The Actor Loop) ---

    async def _set_state(self, status: AgentStatus):
        self._status = status
        await self.events.publish(StateEvent(status=status.value))
        logger.info(f"State changed to: {status}")

    async def _main_loop(self, session_id: str, user_input: Optional[str]):
        try:
            # 1. 预处理输入
            if user_input:
                await SessionManager.add_message(session_id, Message.user(user_input))

            # 加载历史
            full_history = await SessionManager.get_messages(session_id)
            conversation_view = Conversation(messages=full_history).agent_visible_messages()

            # [Resume Check] 检查是否是从中断恢复
            pending_tools = self._check_resume_state(full_history)
            
            current_turn = 0
            while current_turn < self.max_turns:
                current_turn += 1
                
                # === Phase 1: Thinking (LLM) ===
                if not pending_tools:
                    await self._set_state(AgentStatus.THINKING)
                    
                    # [关键修改]
                    # 1. 构建视图 (Agent 可见的消息)
                    visible_msgs = Conversation(messages=full_history).agent_visible_messages()
                    
                    # 2. 应用截断
                    truncated_msgs = self.truncator.truncate(visible_msgs, self.system_prompt)
                    
                    tool_defs = self.tools.list_definitions()
                    ai_message = Message.assistant()
                    
                    try:
                        async for partial, _ in self.provider.stream(
                            self.system_prompt, truncated_msgs, tool_defs
                        ):
                            # 流式合并 & 分发
                            if partial:
                                self._merge_partial_message(ai_message, partial)
                                for c in partial.content:
                                    if isinstance(c, TextContent):
                                        await self.events.publish(TextEvent(text=c.text))
                    except Exception as e:
                        await self.events.publish(ErrorEvent(message=str(e)))
                        break

                    # 保存 AI 消息
                    await SessionManager.add_message(session_id, ai_message)
                    conversation_view.append(ai_message)
                    
                    # 检查是否有工具调用
                    pending_tools = [c for c in ai_message.content if isinstance(c, ToolRequest)]
                
                # === Phase 2: Tooling (Execution) ===
                if not pending_tools:
                    # 任务结束
                    break

                await self._set_state(AgentStatus.TOOLING)
                
                # 分发调用事件
                for req in pending_tools:
                    if req.tool_call.value:
                        await self.events.publish(ToolCallEvent(
                            tool_name=req.tool_call.value.name,
                            tool_args=req.tool_call.value.arguments,
                            tool_call_id=req.id
                        ))

                # [Concurrency Optimization] 并发执行工具
                # 这里我们使用 asyncio.gather 并发运行所有工具
                # 并且在 _execute_single_tool 内部使用 run_blocking 释放主线程
                tool_results_msg = await self._execute_tools_concurrently(pending_tools)

                # 保存结果
                await SessionManager.add_message(session_id, tool_results_msg)
                conversation_view.append(tool_results_msg)
                
                # 清空 pending，准备下一轮思考
                pending_tools = []

        except asyncio.CancelledError:
            logger.info("Agent execution cancelled")
        except Exception as e:
            logger.error(f"Agent loop error: {e}", exc_info=True)
            await self.events.publish(ErrorEvent(message=f"System Error: {e}"))
        finally:
            await self._set_state(AgentStatus.IDLE)

    # --- 辅助方法 ---

    def _check_resume_state(self, history: List[Message]) -> List[ToolRequest]:
        if not history: return []
        last = history[-1]
        if last.role == Role.ASSISTANT:
            return [c for c in last.content if isinstance(c, ToolRequest)]
        return []

    async def _execute_tools_concurrently(self, requests: List[ToolRequest]) -> Message:
        """
        并发执行工具，这是性能优化的关键点。
        """
        tasks = []
        for req in requests:
            tasks.append(self._execute_single_tool(req))
        
        # 等待所有工具完成
        results = await asyncio.gather(*tasks)
        
        result_msg = Message(role=Role.USER)
        for res in results:
            result_msg.content.append(res)
        return result_msg

    async def _execute_single_tool(self, req: ToolRequest) -> ToolResponse:
        call_id = req.id
        if req.tool_call.status == "error":
            # 构造失败的 CallToolResult
            error_result = CallToolResult.failure(req.tool_call.error)
            return ToolResponse(id=call_id, toolResult=error_result)

        tool_name = req.tool_call.value.name
        args = req.tool_call.value.arguments or {}
        
        tool = self.tools.get(tool_name)
        if not tool:
            error_result = CallToolResult.failure(f"Tool not found: {tool_name}")
            return ToolResponse(id=call_id, toolResult=error_result)

        try:
            if asyncio.iscoroutinefunction(tool.run):
                # tool.run 必须返回 CallToolResult
                result = await tool.run(**args)
            else:
                from ..utils.concurrency import run_blocking
                result = await run_blocking(tool.run, **args)
                
        except Exception as e:
            result = CallToolResult.failure(f"Execution Error: {e}")

        # 发布事件 (略) ...

        # [修复] 直接使用 result (CallToolResult)，不要再包装
        return ToolResponse(id=call_id, toolResult=result)

    def _merge_partial_message(self, target, partial):
        # (同之前的合并逻辑)
        for content in partial.content:
            if isinstance(content, TextContent):
                if target.content and isinstance(target.content[-1], TextContent):
                    target.content[-1].text += content.text
                else:
                    target.content.append(content)
            elif isinstance(content, ToolRequest):
                target.content.append(content)