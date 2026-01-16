"""
core/intent/defaults.py
System-level built-in intent definitions.
"""
from .models import IntentDefinition, SlotSchema

# 定义常量：自主执行意图
ADHOC_INTENT = IntentDefinition(
    name="adhoc_execution",
    description=(
        "Universal Fallback Intent. Use this when the user's request does NOT match any specific "
        "search/view intents defined above, OR as a subsequent step in a complex plan "
        "(e.g., 'search then [write essay]'). Handles writing, summarizing, reasoning, analysis, etc."
    ),
    slots=[
        SlotSchema(
            name="instruction",
            description="The specific instruction for the agent to execute based on context.",
            required=True,
            data_type=str
        ),
        SlotSchema(
            name="context_source",
            description="Source of information (default: conversation_history).",
            default="conversation_history",
            data_type=str
        )
    ]
)