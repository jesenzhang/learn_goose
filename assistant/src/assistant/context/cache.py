import time
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    def __init__(self, max_size: int = 128, ttl_seconds: int = 300) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()
