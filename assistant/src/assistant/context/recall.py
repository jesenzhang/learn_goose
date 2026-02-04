from typing import Any, Dict, List, Optional

from .config import ContextConfig
from .interfaces import RecallProvider, RerankProvider
from ..providers.types import Document


class ContextRecall:
    def __init__(
        self,
        config: ContextConfig,
        *,
        recall_provider: Optional[RecallProvider] = None,
        rerank_provider: Optional[RerankProvider] = None,
    ) -> None:
        self.config = config
        self.recall_provider = recall_provider
        self.rerank_provider = rerank_provider

    async def recall(
        self,
        *,
        user_input: str,
        history: List[Dict[str, Any]],
        session_id: str,
        llm: Any = None,
        session_memory: Optional[Dict[str, Any]] = None,
    ) -> List[Any]:
        if not self.recall_provider:
            return []
        results = await self.recall_provider.search_with_history(
            user_input,
            history,
            session_id=session_id,
            max_msgs=self.config.recall_max_msgs,
            max_chars=self.config.recall_max_chars,
            llm=llm,
            session_memory=session_memory,
        )
        if not results or not self.rerank_provider:
            return results
        try:
            docs_map: List[Document] = []
            for idx, item in enumerate(results):
                docs_map.append(
                    Document(
                        page_content=self._format_result(item),
                        metadata={"_original_index": idx},
                    )
                )
            ranked_docs = await self.rerank_provider.arerank(user_input, docs_map, top_k=len(docs_map))
            ranked = []
            for doc in ranked_docs:
                idx = doc.metadata.get("_original_index") if doc.metadata else None
                if idx is None or idx < 0 or idx >= len(results):
                    continue
                ranked.append(results[idx])
            return ranked or results
        except Exception:
            return results
        return results

    @staticmethod
    def _format_result(item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("summary") or item.get("text") or item)
        return str(getattr(item, "summary", "") or getattr(item, "text", "") or item)
