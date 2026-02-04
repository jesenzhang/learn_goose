from typing import Any, Dict, List, Optional, Protocol, Sequence

from .models import ContextBudget, TruncationResult
from ..providers.types import Document


class TokenCounter(Protocol):
    def count_text_tokens(self, text: str) -> int:
        ...

    def estimate_context_usage(
        self,
        *,
        system_prompt: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        context_limit: int,
    ) -> Dict[str, Any]:
        ...


class LLMClient(Protocol):
    async def agenerate(self, *, messages: Sequence[Any], tools: Optional[List[Dict[str, Any]]]) -> Any:
        ...


class RecallProvider(Protocol):
    async def search_with_history(
        self,
        user_input: str,
        history: List[Dict[str, Any]],
        *,
        session_id: str,
        max_msgs: Optional[int] = None,
        max_chars: Optional[int] = None,
        llm: Any = None,
        session_memory: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        ...


class EmbeddingProvider(Protocol):
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    async def aembed_query(self, text: str) -> List[float]:
        ...


class RerankProvider(Protocol):
    async def arerank(self, query: str, documents: List[Document], top_k: int = 5) -> List[Document]:
        ...


class TruncationProvider(Protocol):
    def build_context_budget(self, system_prompt: str, tools: Optional[List[Dict[str, Any]]] = None) -> ContextBudget:
        ...

    async def check_and_apply_truncation(
        self,
        conversation: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[TruncationResult]:
        ...

    def enforce_budget_on_conversation(
        self,
        conversation: Any,
        *,
        system_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[TruncationResult]:
        ...


class SessionMemoryProvider(Protocol):
    async def load_session_memory(self, session_id: str | int) -> Optional[Dict[str, Any]]:
        ...

    async def save_session_memory(self, session_id: str | int, payload: Dict[str, Any]) -> None:
        ...
