from typing import Dict, Any, Optional
from .runnable import Runnable, WorkflowContext
from ..agent import Agent
from ..events import EventType
from ..tools.base import Tool

class AgentNode(Runnable[str, str]):
    """
    将 Agent 包装为工作流节点。
    输入：User Task String
    输出：Agent Final Response String
    """
    def __init__(self, agent: Agent):
        self.agent = agent

    async def invoke(self, input: str, context: WorkflowContext) -> str:
        session_id = context.session_id
        
        # 1. 触发 Agent
        # 这里我们使用之前封装的 convenience method `reply`
        # 如果需要更细粒度的控制，可以使用 process + subscribe
        
        final_response = []
        
        # 我们假设 DAG 节点是同步等待结果的 (await invoke)
        async for event in self.agent.reply(session_id, user_input=input):
            if event.type == EventType.TEXT:
                # 收集所有文本作为输出
                final_response.append(event.text)
            elif event.type == EventType.ERROR:
                raise RuntimeError(f"Agent failed in workflow: {event.message}")
            # 工具调用过程对 DAG 引擎是透明的，除非我们需要记录日志
        
        return "".join(final_response)



class ToolNode(Runnable[Dict[str, Any], Any]):
    """
    直接执行一个工具。
    输入：工具参数 Dict
    输出：工具执行结果
    """
    def __init__(self, tool: Tool):
        self.tool = tool

    async def invoke(self, input: Dict[str, Any], context: WorkflowContext) -> Any:
        # 这里处理同步/异步工具的兼容性
        import asyncio
        from ..utils.concurrency import run_blocking
        
        if asyncio.iscoroutinefunction(self.tool.run):
            result = await self.tool.run(**input)
        else:
            result = await run_blocking(self.tool.run, **input)
            
        # 返回结果的内容
        # 这里需要决定是返回 CallToolResult 对象还是仅返回文本
        # 为了 DAG 的灵活性，通常返回原始对象或 Text
        if result.is_error:
             raise RuntimeError(f"Tool execution failed: {result.content}")
        
        return result.content[0].text if result.content else ""