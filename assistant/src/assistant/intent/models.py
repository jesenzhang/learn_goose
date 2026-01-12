"""
Intent Recognition Models - Source of Truth for Intent Definitions.
"""

from typing import Any, Dict, List, Optional, Type
from pydantic import BaseModel, Field, field_serializer, model_validator

class SlotSchema(BaseModel):
    """
    Definition of a single slot (parameter) in an intent.
    """
    name: str = Field(..., description="Slot name")
    description: str = Field(default="", description="Human-readable description")
    required: bool = Field(default=False, description="Whether this slot is required")
    # data_type expects a Python Type object (e.g., str, int), not a string
    data_type: Any = Field(default=str, description="Expected data type class")
    default: Optional[Any] = Field(default=None, description="Default value if not extracted")
    options: Optional[List[str]] = Field(default=None, description="Enum options")

    @field_serializer('data_type')
    def serialize_type(self, v: Any, _info) -> str:
        """Serialize type to string for LLM prompts."""
        if isinstance(v, type):
            return v.__name__
        return str(v)

class IntentDefinition(BaseModel):
    """
    Definition of an intent with its slots.
    """
    name: str = Field(..., description="Unique intent identifier")
    description: str = Field(..., description="Intent description for LLM")
    slots: List[SlotSchema] = Field(default_factory=list, description="Parameters")

    def get_required_slots(self) -> List[SlotSchema]:
        return [s for s in self.slots if s.required]

class IntentResult(BaseModel):
    """Recognition result for a single intent."""
    intent: str
    confidence: float = 0.8
    status: str = "ready" # ready, incomplete
    entities: Dict[str, Any] = {}
    missing_slots: List[str] = []
    reply_to_user: Optional[str] = None
    thought: str = ""

    @property
    def is_ready(self) -> bool: return self.status == "ready"
    @property
    def is_incomplete(self) -> bool: return self.status == "incomplete"

class MultiIntentResult(BaseModel):
    """Result containing multiple recognized intents."""
    intents: List[IntentResult] = []
    primary_intent: Optional[str] = None

    @property
    def has_ready_intents(self) -> bool:
        return any(i.is_ready for i in self.intents)
    
    @property
    def ready_intents(self) -> List[IntentResult]:
        return [i for i in self.intents if i.is_ready]

    @property
    def incomplete_intents(self) -> List[IntentResult]:
        return [i for i in self.intents if i.is_incomplete]

    def get_intent(self, name: str) -> Optional[IntentResult]:
        for i in self.intents:
            if i.intent == name: return i
        return None

class IntentSession(BaseModel):
    """Session state for multi-turn intent conversations."""
    session_id: str
    current_intent: Optional[str] = None
    collected_slots: Dict[str, Any] = {}
    last_updated: float = 0.0

    def clear_intent(self):
        self.current_intent = None
        self.collected_slots = {}

class IntentRecognitionConfig(BaseModel):
    """Configuration for intent recognition engine."""
    confidence_threshold: float = 0.6