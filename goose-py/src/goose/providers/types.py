from typing import List, Optional, Any
from pydantic import BaseModel,Field

class RerankResult(BaseModel):
    index: int
    document: str
    score: float
    relevance_score: float # Alias for score

class RerankResponse(BaseModel):
    results: List[RerankResult]
    id: Optional[str] = None
    usage: Optional[Any] = None

class Document(BaseModel):
    id: str | None = Field(default=None, coerce_numbers_to_str=True)
    content: str = Field(..., description="The content of the document")
    metadata: dict = Field(default_factory=dict)