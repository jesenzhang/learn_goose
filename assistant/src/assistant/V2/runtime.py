"""Runtime wrapper for V2 MicroAgent core."""

from .agent_core import MicroAgentV2Core
from .task_runner import TaskRunner


class AgentRuntime:
    """Delegates to the legacy MicroAgent implementation."""

    def __init__(self, config_path: str):
        self._legacy = MicroAgentV2Core(config_path=config_path)
        self._task_runner = TaskRunner(self._legacy)

    def __getattr__(self, name):
        return getattr(self._legacy, name)

    # --- Task scheduling (V2) ---
    def get_task_handle(self, session_id: int):
        return self._task_runner.get_task_handle(session_id)

    async def run_task(self, *args, **kwargs):
        return await self._task_runner.run_task(*args, **kwargs)

    async def cancel_running_task(self, session_id: int) -> bool:
        return await self._task_runner.cancel_running_task(session_id)
