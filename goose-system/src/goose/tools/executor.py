"""
Tool Executor

工具执行器。
"""

from typing import Dict, Any, Optional, Callable
from .base import Tool, ToolRequest, ToolResponse


class ToolExecutor:
    """工具执行器"""
    
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._default_handler: Optional[Callable] = None
    
    def register_handler(self, tool_name: str, handler: Callable) -> None:
        """注册工具处理器"""
        self._handlers[tool_name] = handler
    
    def unregister_handler(self, tool_name: str) -> bool:
        """注销工具处理器"""
        if tool_name in self._handlers:
            del self._handlers[tool_name]
            return True
        return False
    
    def set_default_handler(self, handler: Callable) -> None:
        """设置默认处理器"""
        self._default_handler = handler
    
    async def execute(self, tool: Tool, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工具
        
        Args:
            tool: 工具定义
            arguments: 参数
            
        Returns:
            执行结果
        """
        # 验证参数
        valid, error = tool.validate_arguments(arguments)
        if not valid:
            return {"error": error}
        
        # 查找处理器
        handler = self._handlers.get(tool.name)
        
        if handler is None and self._default_handler:
            handler = self._default_handler
        
        if handler is None:
            return {"error": f"No handler for tool: {tool.name}"}
        
        try:
            # 调用处理器
            if hasattr(handler, '__call__'):
                result = handler(**arguments)
                # 如果是协程，等待它
                import asyncio
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            else:
                return {"error": "Invalid handler"}
        except Exception as e:
            return {"error": str(e)}
    
    async def execute_request(self, request: ToolRequest) -> ToolResponse:
        """
        执行工具请求
        
        Args:
            request: 工具请求
            
        Returns:
            工具响应
        """
        result = await self.execute_by_name(request.name, request.arguments or {})
        
        if "error" in result:
            return ToolResponse.error_response(request.id, result["error"])
        else:
            return ToolResponse.success_response(request.id, result)
    
    async def execute_by_name(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        按名称执行工具
        
        Args:
            tool_name: 工具名称
            arguments: 参数
            
        Returns:
            执行结果
        """
        handler = self._handlers.get(tool_name)
        
        if handler is None and self._default_handler:
            handler = self._default_handler
        
        if handler is None:
            return {"error": f"No handler for tool: {tool_name}"}
        
        try:
            args = arguments or {}
            result = handler(**args)
            import asyncio
            if asyncio.iscoroutine(result):
                result = await result
            return result if isinstance(result, dict) else {"result": result}
        except Exception as e:
            return {"error": str(e)}


class SyncToolExecutor:
    """同步工具执行器（用于非 async 上下文）"""
    
    def __init__(self, executor: Optional[ToolExecutor] = None):
        self.executor = executor or ToolExecutor()
    
    def execute(self, tool: Tool, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """同步执行工具"""
        import asyncio
        
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.executor.execute(tool, arguments))
        finally:
            loop.close()
    
    def execute_request(self, request: ToolRequest) -> ToolResponse:
        """同步执行工具请求"""
        import asyncio
        
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.executor.execute_request(request))
        finally:
            loop.close()
