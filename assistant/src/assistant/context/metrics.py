from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ContextMetrics:
    original_tokens: int = 0
    segment_count: int = 0
    truncated: bool = False
    dropped_messages: int = 0
    summary_tokens: int = 0
    recall_count: int = 0
    cache_hit: Optional[bool] = None
    rewrite_used: Optional[bool] = None
    summary_fallback_used: bool = False
    context_limit: int = 0
    reserved_tokens: int = 0
    available_tokens: int = 0
    total_tokens: int = 0
    timings_ms: Dict[str, int] = field(default_factory=dict)


class ContextTracer:
    def __init__(self) -> None:
        self.metrics = ContextMetrics()

    def mark(self, key: str, duration_ms: int) -> None:
        self.metrics.timings_ms[key] = int(duration_ms)

    def set_tokens(self, *, original: int, summary: int = 0) -> None:
        self.metrics.original_tokens = int(original)
        self.metrics.summary_tokens = int(summary)

    def set_summary_tokens(self, summary_tokens: int) -> None:
        self.metrics.summary_tokens = int(summary_tokens)

    def set_segments(self, count: int) -> None:
        self.metrics.segment_count = int(count)

    def set_recall_count(self, count: int) -> None:
        self.metrics.recall_count = int(count)

    def set_truncation(self, truncated: bool, dropped_messages: int = 0) -> None:
        self.metrics.truncated = bool(truncated)
        self.metrics.dropped_messages = int(dropped_messages)

    def set_cache_hit(self, hit: bool) -> None:
        self.metrics.cache_hit = bool(hit)

    def set_rewrite_used(self, used: bool) -> None:
        self.metrics.rewrite_used = bool(used)

    def set_summary_fallback(self, used: bool) -> None:
        self.metrics.summary_fallback_used = bool(used)

    def set_budget(
        self,
        *,
        context_limit: int,
        reserved_tokens: int,
        available_tokens: int,
        total_tokens: int,
    ) -> None:
        self.metrics.context_limit = int(context_limit)
        self.metrics.reserved_tokens = int(reserved_tokens)
        self.metrics.available_tokens = int(available_tokens)
        self.metrics.total_tokens = int(total_tokens)
