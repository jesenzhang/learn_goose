"""V2 MicroAgent facade with clearer responsibility boundaries.

Behavior is delegated to the legacy runtime to keep outputs stable.
"""

from typing import Any, Dict, Optional

from .runtime import AgentRuntime


class MicroAgentV2:
    """V2 facade that preserves the legacy interface."""

    def __init__(self, config_path: str):
        self._runtime = AgentRuntime(config_path=config_path)

    # ---- Delegated public API ----
    def get_streamer(self, session_id: int, run_id: str):
        return self._runtime.get_streamer(session_id, run_id)

    def get_task_handle(self, session_id: int):
        return self._runtime.get_task_handle(session_id)

    async def run_task(
        self,
        state,
        run_id: str,
        input_data: Dict | str = None,
        resume: bool = False,
        approval_data: Dict = None,
        user_id: Optional[int] = None,
    ):
        return await self._runtime.run_task(
            state=state,
            run_id=run_id,
            input_data=input_data,
            resume=resume,
            approval_data=approval_data,
            user_id=user_id,
        )

    async def cancel_running_task(self, session_id: int) -> bool:
        return await self._runtime.cancel_running_task(session_id)

    async def cancel_task(self, session_id: int) -> bool:
        return await self._runtime.cancel_task(session_id)

    async def cleanup_session(self, session_id: int) -> int:
        return await self._runtime.cleanup_session(session_id)

    def shutdown(self):
        return self._runtime.shutdown()

    async def shutdown_async(self):
        return await self._runtime.shutdown_async()

    # ---- Pass-through for attributes used by routes ----
    @property
    def current_generation(self):
        return self._runtime.current_generation

    # ---- Fallback delegation for any other attributes ----
    def __getattr__(self, name: str) -> Any:
        return getattr(self._runtime, name)
