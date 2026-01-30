"""Tool execution wrapper for V2."""

from typing import List, Any, Optional

from ...conversation import ToolRequest


class ToolExecutor:
    """Delegates tool execution to legacy agent methods."""

    def __init__(self, agent):
        self._agent = agent

    async def execute_concurrent(
        self,
        tool_requests: List[ToolRequest],
        state,
        gen,
        req_ctx,
        *,
        run_id: str,
        user_id: Optional[int],
    ) -> List[Any]:
        return await self._agent._execute_tools_concurrent(
            tool_requests,
            state,
            gen,
            req_ctx,
            run_id=run_id,
            user_id=user_id,
        )

    async def exec_tool_func(self, name, args, state, gen, req_ctx, *, run_id: str, user_id: Optional[int]):
        return await self._agent._exec_tool_func(
            name,
            args,
            state,
            gen,
            req_ctx,
            run_id=run_id,
            user_id=user_id,
        )
