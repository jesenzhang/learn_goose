from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ContextBudget(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    context_limit: int
    reserved_tokens: int
    system_tokens: int = 0
    tools_tokens: int = 0
    history_tokens: int = 0
    input_tokens: int = 0

    @property
    def available_tokens(self) -> int:
        return max(
            0,
            self.context_limit
            - self.reserved_tokens
            - self.system_tokens
            - self.tools_tokens
            - self.history_tokens,
        )


class ContextAnalysis(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    original_tokens: int
    segment_tokens: List[int]
    segments: List[str]
    requirement_indices: List[int]
    requirement_text: str
    background_summary: Optional[str]
    extraction: Optional["RequirementExtraction"] = None


class RequirementExtraction(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    goal: str
    scope: str
    constraints: List[str]
    output_format: str
    uncertainties: List[str]
    need_clarification: bool
    questions: List[str]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RequirementExtraction":
        return cls(
            goal=data.get("goal", "") or "",
            scope=data.get("scope", "") or "",
            constraints=list(data.get("constraints") or []),
            output_format=data.get("output_format", "") or "",
            uncertainties=list(data.get("uncertainties") or []),
            need_clarification=bool(data.get("need_clarification", False)),
            questions=list(data.get("questions") or []),
        )


class RecallSummary(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    results: List[Any]
    summary_text: str


class RecallBundle(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    query: str
    rewritten_query: Optional[str]
    summary: RecallSummary


class TruncationResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    truncated: bool
    summary_text: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None


class ContextPayload(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    input_text: str
    compressed_context: Optional[str]
    recall_summary: Optional[str]
    recent_history: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ContextProcessResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    analysis: ContextAnalysis
    normalized_input: str
    requirement_text: str
    background_summary: Optional[str]
    extraction: Optional[RequirementExtraction]
    segments: List[str]
    requirement_segments: List[int]
    summary: Optional[str]
