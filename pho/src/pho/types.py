"""
Type definitions for Pho framework.

Contains DataType enum and TypeInfo model for type conversion.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class NodeTypes:
    """Node type constants for workflow components."""
    # --- Basic ---
    UNDEFINED = "Undefined"
    ENTRY = "Entry"
    EXIT = "Exit"
    OUTPUT_EMITTER = "OutputEmitter"

    # --- AI & Code ---
    LLM = "LLM"
    CODE_RUNNER = "CodeRunner"
    LAMBDA = "Lambda"
    TEXT_PROCESSOR = "TextProcessor"
    INTENT_DETECTOR = "IntentDetector"
    QUESTION_ANSWER = "QuestionAnswer"

    # --- Control Flow ---
    LOOP = "Loop"
    BATCH = "Batch"
    BREAK = "Break"
    CONTINUE = "Continue"
    SELECTOR = "Selector"
    SUB_WORKFLOW = "SubWorkflow"

    # --- Variables & Data ---
    VARIABLE_ASSIGNER = "VariableAssigner"
    VARIABLE_AGGREGATOR = "VariableAggregator"
    VARIABLE_ASSIGNER_WITHIN_LOOP = "VariableAssignerWithinLoop"
    JSON_SERIALIZATION = "JsonSerialization"
    JSON_DESERIALIZATION = "JsonDeserialization"

    # --- Tools & Connections ---
    TOOL = "Tool"
    PLUGIN = "Plugin"
    HTTP_REQUESTER = "HTTPRequester"


class DataType(str, Enum):
    """Basic data types for type system."""
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "list"
    TIME = "time"
    FILE = "file"


class TypeInfo(BaseModel):
    """Type information for schema generation and validation."""

    # Core type definition
    type: DataType

    # Recursive definition for object properties
    properties: Optional[Dict[str, "TypeInfo"]] = None

    # Array element type
    elem_type_info: Optional["TypeInfo"] = Field(default=None, alias="elem_type")

    # UI/business metadata
    title: Optional[str] = None
    description: Optional[str] = None
    required: bool = False
    default: Any = None

    # Domain extensions
    file_type: Optional[str] = None
    time_format: Optional[str] = None

    # Debug info
    original_source: Optional[str] = Field(None, description="e.g. node_id.output_key")

    model_config = ConfigDict(
        populate_by_name=True,
        use_enum_values=True
    )


# Fix Pydantic recursive model reference
TypeInfo.model_rebuild()


class InputMapping(BaseModel):
    """Input mapping for workflow nodes."""
    name: str
    value: Any = None  # Supports {{ var }} references


class ParameterDefinition(BaseModel):
    """
    [Optimized] Variable definition.

    Separates 'Key' (variable name) from 'Value Schema' (TypeInfo),
    enabling definition of complex nested objects or array structures.
    """
    key: str = Field(..., description="Variable name/field name")

    # Reuse TypeInfo to describe value structure (supports recursive properties and elem_type)
    type_info: TypeInfo = Field(..., description="Value type description")

    # Business attributes
    label: Optional[str] = None  # Friendly display name for UI
    description: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


__all__ = [
    "NodeTypes",
    "DataType",
    "TypeInfo",
    "InputMapping",
    "ParameterDefinition",
]
