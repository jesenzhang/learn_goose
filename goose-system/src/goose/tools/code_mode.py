"""
Code Mode Executor

Code Mode 支持批量工具调用和本地结果处理。
参考 goose-rs 的 Code Mode 设计。

与 Traditional Mode 的区别:
- Traditional: 顺序调用，每次结果发送给 LLM
- Code Mode: 批量调用，中间结果本地处理
"""

import re
import asyncio
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field

from .base import Tool, ToolRequest
from .executor import ToolExecutor
from .inspection import InspectionManager, PermissionStore, PermissionLevel


@dataclass
class CodeExecutionResult:
    """代码执行结果"""
    success: bool
    output: str = ""
    error: Optional[str] = None
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    execution_time_ms: float = 0.0


@dataclass
class DiscoveredTool:
    """发现的可执行工具"""
    name: str
    description: str
    parameters: Dict[str, Any]
    executor: Optional[Callable] = None


class CodeModeExecutor:
    """
    Code Mode 执行器
    
    特点:
    - 批量工具调用
    - 中间结果本地处理
    - 支持工具发现
    - 适合复杂工作流
    """
    
    def __init__(
        self,
        tool_executor: ToolExecutor,
        inspection_manager: Optional[InspectionManager] = None,
        permission_store: Optional[PermissionStore] = None
    ):
        """
        初始化 Code Mode 执行器
        
        Args:
            tool_executor: 工具执行器
            inspection_manager: 检查器管理器
            permission_store: 权限存储
        """
        self._executor = tool_executor
        self._inspection_manager = inspection_manager
        self._permission_store = permission_store
        self._discovered_tools: Dict[str, DiscoveredTool] = {}
        self._execution_history: List[Dict[str, Any]] = []
    
    @property
    def discovered_tools(self) -> Dict[str, DiscoveredTool]:
        """获取已发现的工具"""
        return self._discovered_tools.copy()
    
    @property
    def execution_history(self) -> List[Dict[str, Any]]:
        """获取执行历史"""
        return self._execution_history.copy()
    
    def discover_tools_from_code(self, code: str) -> List[DiscoveredTool]:
        """
        从代码中发现需要使用的工具
        
        Args:
            code: 要执行的代码
            
        Returns:
            发现的可执行工具列表
        """
        discovered = []
        
        for tool_name, handler in self._executor._handlers.items():
            if self._can_use_tool(tool_name):
                if self._tool_mentioned_in_code(tool_name, code):
                    tool = DiscoveredTool(
                        name=tool_name,
                        description=f"Tool: {tool_name}",
                        parameters={},
                        executor=handler
                    )
                    discovered.append(tool)
                    self._discovered_tools[tool_name] = tool
        
        return discovered
    
    def _tool_mentioned_in_code(self, tool_name: str, code: str) -> bool:
        """检查工具是否在代码中被提及"""
        patterns = [
            rf'\b{re.escape(tool_name)}\b',
            rf'["\']?\s*{re.escape(tool_name)}\s*["\']?',
        ]
        
        for pattern in patterns:
            if re.search(pattern, code, re.IGNORECASE):
                return True
        
        return False
    
    def _can_use_tool(self, tool_name: str) -> bool:
        """检查是否可以使用工具"""
        if not self._permission_store:
            return True
        
        level = self._permission_store.get_permission(tool_name)
        return level != PermissionLevel.NEVER_ALLOW
    
    async def execute_code(
        self,
        code: str,
        context: Optional[Dict[str, Any]] = None
    ) -> CodeExecutionResult:
        """
        执行代码
        
        Args:
            code: 要执行的代码（描述要做什么）
            context: 可选的上下文信息
            
        Returns:
            执行结果
        """
        import time
        start_time = time.time()
        
        results = []
        output_parts = []
        error = None
        
        try:
            discovered = self.discover_tools_from_code(code)
            
            if not discovered:
                output_parts.append("No tools found in code that can be executed.")
            else:
                for tool in discovered:
                    tool_result = await self._execute_tool_with_check(
                        tool.name,
                        {}
                    )
                    
                    results.append({
                        "tool": tool.name,
                        "result": tool_result
                    })
                    
                    if "error" in tool_result:
                        error = tool_result.get("error")
                        output_parts.append(f"[{tool.name}] Error: {error}")
                    else:
                        content = tool_result.get("content", str(tool_result))
                        output_parts.append(f"[{tool.name}] {content}")
                
                self._execution_history.extend(results)
        
        except Exception as e:
            error = str(e)
            output_parts.append(f"Execution error: {error}")
        
        execution_time_ms = (time.time() - start_time) * 1000
        
        return CodeExecutionResult(
            success=error is None,
            output="\n".join(output_parts),
            error=error,
            tool_results=results,
            execution_time_ms=execution_time_ms
        )
    
    async def execute_batch(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        批量执行工具调用
        
        Args:
            tool_calls: 工具调用列表 [{"name": "...", "arguments": {...}}]
            
        Returns:
            执行结果列表
        """
        results = []
        
        for call in tool_calls:
            name = call.get("name")
            arguments = call.get("arguments", {})
            
            if not name:
                results.append({"error": "Missing tool name"})
                continue
            
            if not self._can_use_tool(name):
                results.append({
                    "error": f"Tool '{name}' is not allowed",
                    "tool": name
                })
                continue
            
            result = await self._execute_tool_with_check(name, arguments)
            results.append({
                "tool": name,
                "result": result
            })
        
        self._execution_history.extend(results)
        return results
    
    async def execute_with_dependencies(
        self,
        code: str,
        dependencies: List[Dict[str, Any]] = None
    ) -> CodeExecutionResult:
        """
        执行带依赖的代码
        
        Args:
            code: 要执行的代码
            dependencies: 依赖的先决工具调用结果
            
        Returns:
            执行结果
        """
        if dependencies:
            context_str = "\n".join([
                f"Previous result {i+1}: {d}"
                for i, d in enumerate(dependencies)
            ])
            code = f"# Previous results:\n{context_str}\n\n# Current task:\n{code}"
        
        return await self.execute_code(code)
    
    async def _execute_tool_with_check(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具（带检查）"""
        if self._inspection_manager:
            request = ToolRequest(name=tool_name, arguments=arguments)
            inspection_results = await self._inspection_manager.inspect(
                request, []
            )
            
            for result in inspection_results:
                if result.action.value == "deny":
                    return {"error": f"Tool denied: {result.message}"}
                elif result.action.value == "require_approval":
                    return {"error": f"Tool requires approval: {result.message}"}
        
        return await self._executor.execute_by_name(tool_name, arguments)
    
    def clear_discovered_tools(self) -> None:
        """清除已发现的工具"""
        self._discovered_tools.clear()
    
    def clear_history(self) -> None:
        """清除执行历史"""
        self._execution_history.clear()
    
    def get_tool_summary(self) -> str:
        """获取工具摘要"""
        lines = [
            "Available Tools:",
            f"  Total discovered: {len(self._discovered_tools)}",
            "",
            "Tool List:"
        ]
        
        for name, tool in sorted(self._discovered_tools.items()):
            lines.append(f"  - {name}")
        
        lines.extend([
            "",
            f"Execution History: {len(self._execution_history)} calls"
        ])
        
        return "\n".join(lines)


class CodeModeAgent:
    """
    Code Mode Agent
    
    结合 LLM 和 Code Mode 执行器的代理。
    适合复杂的多步骤工作流。
    """
    
    def __init__(
        self,
        llm_provider: Any,
        code_mode_executor: CodeModeExecutor,
        system_prompt: str = ""
    ):
        """
        初始化 Code Mode Agent
        
        Args:
            llm_provider: LLM 提供者
            code_mode_executor: Code Mode 执行器
            system_prompt: 系统提示
        """
        self._llm = llm_provider
        self._executor = code_mode_executor
        self._system_prompt = system_prompt
    
    async def run(self, user_message: str) -> CodeExecutionResult:
        """
        运行 Agent
        
        Args:
            user_message: 用户消息
            
        Returns:
            执行结果
        """
        prompt = self._build_prompt(user_message)
        
        response = await self._llm.generate(prompt)
        
        return await self._executor.execute_code(response)
    
    def _build_prompt(self, user_message: str) -> str:
        """构建提示"""
        tools_summary = self._executor.get_tool_summary()
        
        return f"""{self._system_prompt}

User: {user_message}

Available Tools Summary:
{tools_summary}

Please describe what tools to use and how to chain them.
Write code that will be executed to accomplish the task.
"""
