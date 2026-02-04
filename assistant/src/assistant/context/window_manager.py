from dataclasses import dataclass
from typing import Optional


@dataclass
class WindowState:
    compacted_until_message_id: Optional[str] = None


class WindowManager:
    def __init__(self, keep_recent_messages: int = 5):
        self.keep_recent_messages = max(1, int(keep_recent_messages))

    def prune_history(self, history, *, compacted_until_message_id: Optional[str]) -> list:
        if not history:
            return []
        if compacted_until_message_id:
            pruned = []
            keep = False
            for msg in history:
                if msg.get("id") == compacted_until_message_id:
                    keep = True
                if keep:
                    pruned.append(msg)
            if pruned:
                return pruned
        return history[-self.keep_recent_messages:]
