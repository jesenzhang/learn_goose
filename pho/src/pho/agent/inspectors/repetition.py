"""
RepetitionInspector - Detect and prevent repetitive tool calls.

This inspector tracks tool call history and detects:
- Exact duplicate calls
- Similar calls with minor variations
- Excessive calls to the same tool
- Potential infinite loops
"""

import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from collections import deque, defaultdict
from datetime import datetime, timedelta
from .base import ToolInspector, InspectorResult, InspectorAction

logger = logging.getLogger(__name__)


class CallSignature:
    """Signature of a tool call for comparison"""

    def __init__(
        self,
        tool_name: str,
        args: Dict[str, Any],
        ignore_keys: Optional[List[str]] = None
    ):
        self.tool_name = tool_name
        self.ignore_keys = set(ignore_keys or [])

        # Create normalized signature
        self.signature = self._create_signature(args)

    def _create_signature(self, args: Dict[str, Any]) -> str:
        """Create a normalized signature from arguments"""
        # Filter out ignored keys
        filtered_args = {
            k: v for k, v in args.items()
            if k not in self.ignore_keys
        }

        # Sort keys for consistent hashing
        sorted_items = sorted(filtered_args.items())

        # Convert to string and hash
        args_str = str(sorted_items)
        return hashlib.md5(args_str.encode()).hexdigest()

    def __eq__(self, other) -> bool:
        return self.signature == other.signature

    def __hash__(self) -> int:
        return hash(self.signature)

    def __repr__(self) -> str:
        return f"CallSignature({self.tool_name}, {self.signature[:8]}...)"


class CallRecord:
    """Record of a tool call"""

    def __init__(
        self,
        signature: CallSignature,
        timestamp: datetime,
        result: Optional[Any] = None
    ):
        self.signature = signature
        self.timestamp = timestamp
        self.result = result
        self.count = 1

    def increment(self) -> None:
        """Increment call count"""
        self.count += 1

    def is_recent(self, seconds: int = 60) -> bool:
        """Check if call was recent"""
        delta = datetime.now() - self.timestamp
        return delta.total_seconds() <= seconds


class RepetitionInspector(ToolInspector):
    """
    Inspector that detects and prevents repetitive tool calls.

    Tracks:
    - Exact duplicates (same tool, same args)
    - Tool frequency (calls per time window)
    - Call patterns that suggest loops
    """

    def __init__(
        self,
        priority: int = 30,
        enabled: bool = True,
        max_duplicates: int = 3,
        max_calls_per_minute: int = 10,
        max_calls_per_tool: int = 50,
        history_window: int = 300,
        ignore_keys: Optional[List[str]] = None,
        cache_results: bool = True
    ):
        """
        Initialize RepetitionInspector.

        Args:
            priority: Inspector priority (default 30)
            enabled: Whether inspector is enabled
            max_duplicates: Max identical calls before blocking
            max_calls_per_minute: Max calls to same tool per minute
            max_calls_per_tool: Max total calls to same tool
            history_window: Time window to track history (seconds)
            ignore_keys: Argument keys to ignore when comparing
            cache_results: Whether to cache and return previous results
        """
        super().__init__(priority=priority)
        if not enabled:
            self.disable()

        self.max_duplicates = max_duplicates
        self.max_calls_per_minute = max_calls_per_minute
        self.max_calls_per_tool = max_calls_per_tool
        self.history_window = history_window
        self.ignore_keys = ignore_keys or ["timestamp", "request_id"]
        self.cache_results = cache_results

        # Call history: signature -> CallRecord
        self.call_history: Dict[CallSignature, CallRecord] = {}

        # Per-tool call tracking: tool_name -> deque of timestamps
        self.tool_calls: defaultdict[str, deque] = defaultdict(deque)

        # Result cache: signature -> result
        self.result_cache: Dict[CallSignature, Any] = {}

    async def inspect(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> InspectorResult:
        """Inspect tool call for repetition patterns"""

        # Clean old history
        self._clean_old_history()

        # Create call signature
        signature = CallSignature(tool_name, tool_args, self.ignore_keys)

        # Check for exact duplicates
        if signature in self.call_history:
            record = self.call_history[signature]

            # Check if we've exceeded max duplicates
            if record.count >= self.max_duplicates:
                logger.warning(
                    f"Duplicate call detected: {tool_name} "
                    f"(called {record.count} times)"
                )

                # Return cached result if available
                if self.cache_results and signature in self.result_cache:
                    return InspectorResult.replace(
                        result=self.result_cache[signature],
                        reason=f"Duplicate call blocked (already called {record.count} times)"
                    )

                return InspectorResult.deny(
                    reason=f"Too many duplicate calls (max: {self.max_duplicates})",
                    error_message=f"This tool has already been called {record.count} times"
                )

            # Check if previous call was recent
            if record.is_recent(seconds=30):
                # If caching is enabled, return cached result
                if self.cache_results and signature in self.result_cache:
                    logger.debug(f"Returning cached result for {tool_name}")
                    return InspectorResult.replace(
                        result=self.result_cache[signature],
                        reason=f"Using cached result from recent call"
                    )

        # Check tool call frequency
        now = datetime.now()
        tool_timestamps = self.tool_calls[tool_name]

        # Count calls in last minute
        recent_calls = [
            ts for ts in tool_timestamps
            if (now - ts).total_seconds() <= 60
        ]

        if len(recent_calls) >= self.max_calls_per_minute:
            return InspectorResult.deny(
                reason=f"Tool '{tool_name}' called too frequently "
                       f"({len(recent_calls)} calls in last minute)",
                error_message=f"Rate limit exceeded for this tool"
            )

        # Check total calls to this tool
        if len(tool_timestamps) >= self.max_calls_per_tool:
            return InspectorResult.deny(
                reason=f"Tool '{tool_name}' exceeded max calls "
                       f"({len(tool_timestamps)} total calls)",
                error_message=f"This tool has been used too many times"
            )

        return InspectorResult.allow(reason="No repetition issues")

    async def after_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: Any,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """Track call after execution"""
        signature = CallSignature(tool_name, tool_args, self.ignore_keys)
        now = datetime.now()

        # Update call record
        if signature in self.call_history:
            self.call_history[signature].increment()
            self.call_history[signature].timestamp = now
        else:
            self.call_history[signature] = CallRecord(signature, now)

        # Track tool calls
        self.tool_calls[tool_name].append(now)

        # Cache result if enabled
        if self.cache_results:
            self.result_cache[signature] = result

    def _clean_old_history(self) -> None:
        """Remove old call records outside the history window"""
        cutoff = datetime.now() - timedelta(seconds=self.history_window)

        # Clean call history
        to_remove = [
            sig for sig, record in self.call_history.items()
            if record.timestamp < cutoff
        ]
        for sig in to_remove:
            del self.call_history[sig]
            self.result_cache.pop(sig, None)

        # Clean tool timestamps
        for tool_name in self.tool_calls:
            while self.tool_calls[tool_name] and self.tool_calls[tool_name][0] < cutoff:
                self.tool_calls[tool_name].popleft()

    def reset(self) -> None:
        """Clear all history"""
        self.call_history.clear()
        self.tool_calls.clear()
        self.result_cache.clear()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about tool calls"""
        return {
            "total_unique_calls": len(self.call_history),
            "cached_results": len(self.result_cache),
            "calls_by_tool": {
                tool: len(ts)
                for tool, ts in self.tool_calls.items()
            }
        }


__all__ = ["RepetitionInspector", "CallSignature", "CallRecord"]
