import json
from typing import Any, Dict, Optional

from ...context.interfaces import SessionMemoryProvider
from ..manager import MemoryManager


class MemorySessionMemoryProvider(SessionMemoryProvider):
    def __init__(self, manager: MemoryManager) -> None:
        self.manager = manager

    async def load_session_memory(self, session_id: str | int) -> Optional[Dict[str, Any]]:
        data = await self.manager.load(
            session_id=session_id,
            item_id=f"session_memory:{session_id}",
        )
        if isinstance(data, str):
            try:
                return json.loads(data)
            except Exception:
                return None
        if isinstance(data, dict):
            return data
        return None

    async def save_session_memory(self, session_id: str | int, payload: Dict[str, Any]) -> None:
        await self.manager.store(
            session_id=session_id,
            item_id=f"session_memory:{session_id}",
            item_type="session_memory",
            data=payload,
            text=json.dumps(payload, ensure_ascii=False),
        )


__all__ = ["MemorySessionMemoryProvider"]
