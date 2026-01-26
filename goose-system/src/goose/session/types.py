"""
Session Types

Session data models matching goose-rs structure.
Reference: goose-rs/crates/goose/src/session/session_manager.rs.rs

Features:
- SessionType: User/Scheduled/SubAgent/Hidden/Terminal/Workflow session types
- Session: Core session data structure with full metadata
- ExtensionData: Extension state management
- TokenStats: Token usage tracking
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time
import logging

logger = logging.getLogger(__name__)


# --- Enums ---

class SessionType(str, Enum):
    """Session type matching Rust: pub enum SessionType"""
    USER = "user"
    SCHEDULED = "scheduled"
    SUB_AGENT = "sub_agent"
    HIDDEN = "hidden"
    TERMINAL = "terminal"
    WORKFLOW = "workflow"


# --- Data Models ---

@dataclass
class TokenStats:
    """Token usage statistics matching Rust: pub struct TokenStats"""
    total_tokens: Optional[int] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    accumulated_total_tokens: Optional[int] = None
    accumulated_input_tokens: Optional[int] = None
    accumulated_output_tokens: Optional[int] = None


@dataclass
class ExtensionData:
    """Extension data containing all extension states"""
    extension_states: Dict[str, Any] = field(default_factory=dict)

    def get_extension_state(self, extension_name: str, version: str) -> Optional[Any]:
        key = f"{extension_name}.{version}"
        return self.extension_states.get(key)

    def set_extension_state(self, extension_name: str, version: str, state: Any) -> None:
        key = f"{extension_name}.{version}"
        self.extension_states[key] = state

    @classmethod
    def new(cls) -> "ExtensionData":
        return cls()


@dataclass
class Session:
    """
    Session data matching Rust: pub struct Session

    Core fields:
    - id: Session identifier
    - working_dir: Working directory (sandbox root)
    - name: Session name set by user
    - user_set_name: Whether name was set by user
    - session_type: Type of session
    - created_at/updated_at: Timestamps
    - metadata: Generic metadata dictionary

    Extension data:
    - extension_data: Extension states

    Token tracking:
    - stats: TokenStats

    Context related:
    - schedule_id: Associated schedule ID
    - recipe_json: Associated recipe JSON
    - user_recipe_values: User-set recipe values

    Message tracking:
    - message_count: Number of messages

    Provider configuration:
    - provider_name: LLM provider name
    - current_model_config: Model configuration
    """
    id: str
    working_dir: str = field(default=".")
    name: str = field(default="")
    user_set_name: bool = field(default=False)
    session_type: SessionType = field(default=SessionType.USER)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    # 1. Generic metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # 2. Extension data
    extension_data: ExtensionData = field(default_factory=ExtensionData)

    # 3. Token statistics
    stats: TokenStats = field(default_factory=TokenStats)

    # 4. Context related
    schedule_id: Optional[str] = field(default=None)
    recipe_json: Optional[str] = field(default=None)
    user_recipe_values: Optional[Dict[str, str]] = field(default=None)

    # 5. Message tracking
    message_count: int = field(default=0)

    # 6. Provider configuration
    provider_name: Optional[str] = field(default=None)
    current_model_config: Optional[Dict[str, Any]] = field(default=None)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        # Handle ExtensionData from dict
        ext_data_dict = data.get("extension_data", {})
        if isinstance(ext_data_dict, dict):
            extension_data = ExtensionData(extension_states=ext_data_dict)
        else:
            extension_data = ExtensionData()

        # Handle TokenStats from dict
        stats_dict = data.get("stats", {})
        if isinstance(stats_dict, dict):
            token_stats = TokenStats(**stats_dict)
        else:
            token_stats = TokenStats()

        return cls(
            id=data.get("id", ""),
            working_dir=data.get("working_dir", "."),
            name=data.get("name", ""),
            user_set_name=data.get("user_set_name", False),
            session_type=SessionType(data.get("session_type", "user")),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            metadata=data.get("metadata", {}),
            extension_data=extension_data,
            stats=token_stats,
            schedule_id=data.get("schedule_id"),
            recipe_json=data.get("recipe_json"),
            user_recipe_values=data.get("user_recipeValues") or data.get("user_recipe_values"),
            message_count=data.get("message_count", 0),
            provider_name=data.get("provider_name"),
            current_model_config=data.get("model_config") or data.get("current_model_config"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "working_dir": self.working_dir,
            "name": self.name,
            "user_set_name": self.user_set_name,
            "session_type": self.session_type.value if isinstance(self.session_type, SessionType) else self.session_type,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "extension_data": self.extension_data.extension_states,
            "stats": {
                "total_tokens": self.stats.total_tokens,
                "input_tokens": self.stats.input_tokens,
                "output_tokens": self.stats.output_tokens,
                "accumulated_total_tokens": self.stats.accumulated_total_tokens,
                "accumulated_input_tokens": self.stats.accumulated_input_tokens,
                "accumulated_output_tokens": self.stats.accumulated_output_tokens,
            },
            "schedule_id": self.schedule_id,
            "recipe_json": self.recipe_json,
            "user_recipeValues": self.user_recipe_values,
            "message_count": self.message_count,
            "provider_name": self.provider_name,
            "model_config": self.current_model_config,
        }


# --- Exports ---

__all__ = [
    "SessionType",
    "TokenStats",
    "ExtensionData",
    "Session",
]
