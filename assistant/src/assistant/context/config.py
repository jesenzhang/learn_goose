from dataclasses import dataclass
from typing import Optional


@dataclass
class ContextConfig:
    # Segmentation
    input_segment_max_tokens: Optional[int] = None
    input_overlap_ratio: float = 0.08
    reserved_tokens: int = 4000
    context_limit: Optional[int] = None
    threshold: float = 0.8
    auto_compact: bool = True
    max_messages_before_compact: int = 50
    keep_recent_messages: int = 5
    check_interval: int = 5

    # Requirement classifier
    requirement_classifier_enabled: bool = False
    requirement_classifier_threshold: float = 0.6
    requirement_classifier_max_segments: int = 8
    requirement_classifier_max_chars: int = 1200
    requirement_classifier_prompt: Optional[str] = None
    requirement_scan_front: int = 2
    requirement_scan_back: int = 2

    # Requirement extraction
    requirement_extraction_enabled: bool = False
    requirement_extraction_prompt: Optional[str] = None
    requirement_extraction_max_chars: int = 2000
    recall_summary_max_items: int = 3
    recall_summary_format: str = "- {session_id}: {count} matches (score={score:.2f})"

    # Recall / rewrite
    recall_max_msgs: int = 6
    recall_max_chars: int = 800
    query_rewrite_enabled: bool = False
    query_rewrite_max_msgs: int = 6
    query_rewrite_max_chars: int = 800
    query_rewrite_prompt: Optional[str] = None

    # Cache / metrics
    cache_enabled: bool = False
    cache_size: int = 128
    cache_ttl_seconds: int = 300
    metrics_enabled: bool = True
    summarize_max_concurrency: int = 4
    summarize_fuse_enabled: bool = True
    summarize_fuse_max_chars: int = 2000
    summarize_max_segments: int = 20
    summarize_fallback_strategy: str = "heuristic"
    summarize_fallback_max_chars: int = 2000
    summarize_fallback_max_segments: int = 12
    payload_history_keep: int = 1
