"""
Logic Components - Basic data manipulation components.

Provides:
- TransformComponent: Transform data using mappings or templates
- MergeComponent: Merge multiple inputs into one output
- SplitComponent: Split data into multiple outputs
- ValidateComponent: Validate data against rules
- AssignComponent: Assign variables from inputs
"""

import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from pho.components.base import Component
from pho.components.registry import register_component
from pho.utils.template import TemplateRenderer
from pho.utils.type_converter import DataValidator
from pho.types import DataType, TypeInfo, NodeTypes


# ================== Transform Component ==================

class TransformConfig(BaseModel):
    # Transform mode
    mode: str = Field(
        "mapping",
        description="Transform mode: mapping, template, or regex"
    )

    # For mapping mode
    mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Field mapping: {'new_key': 'old_key'} or {'new_key': '{{template}}'}"
    )

    # For template mode
    template: Optional[str] = Field(None, description="Output template string")

    # For regex mode
    regex_pattern: Optional[str] = Field(None, description="Regex pattern to match")
    regex_replace: Optional[str] = Field(None, description="Replacement string")
    regex_flags: int = Field(0, description="Regex flags (0=none, 2=IGNORECASE)")

    # Options
    remove_empty: bool = Field(False, description="Remove empty/null values")
    flatten: bool = Field(False, description="Flatten nested structures")


@register_component(
    name="transform",
    group="Logic",
    label="Transform",
    description="Transform and reshape data",
    icon="transform",
    author="System",
    version="1.0.0",
    config_model=TransformConfig,
)
class TransformComponent(Component):
    """Transform data using various methods"""

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: TransformConfig
    ) -> Dict[str, Any]:
        result = {}

        if config.mode == "mapping":
            for new_key, old_key_or_template in config.mapping.items():
                # Check if it's a template or a simple key reference
                if '{{' in old_key_or_template and '}}' in old_key_or_template:
                    result[new_key] = TemplateRenderer.render(old_key_or_template, inputs)
                else:
                    result[new_key] = inputs.get(old_key_or_template)

        elif config.mode == "template":
            if config.template:
                result["output"] = TemplateRenderer.render(config.template, inputs)
            else:
                result = inputs.copy()

        elif config.mode == "regex":
            flags = config.regex_flags
            text = inputs.get("text", "")
            if config.regex_pattern:
                result["output"] = re.sub(
                    config.regex_pattern,
                    config.regex_replace or "",
                    text,
                    flags=flags
                )
            else:
                result["output"] = text

        else:
            result = inputs.copy()

        # Apply options
        if config.remove_empty:
            result = {k: v for k, v in result.items() if v is not None and v != ""}

        return result


# ================== Merge Component ==================

class MergeConfig(BaseModel):
    merge_strategy: str = Field(
        "deep",
        description="Merge strategy: flat, deep, or concat"
    )
    separator: str = Field(
        ", ",
        description="Separator for concat mode"
    )
    prefix: Optional[str] = Field(None, description="Prefix for merged keys")
    output_key: str = Field("merged", description="Output key name")


@register_component(
    name="merge",
    group="Logic",
    label="Merge",
    description="Merge multiple inputs into one",
    icon="merge",
    author="System",
    version="1.0.0",
    config_model=MergeConfig,
)
class MergeComponent(Component):
    """Merge multiple input sources"""

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: MergeConfig
    ) -> Dict[str, Any]:
        if config.merge_strategy == "flat":
            # Simple flat merge (later values override earlier)
            result = {}
            for key, value in inputs.items():
                if isinstance(value, dict):
                    result.update(value)
                else:
                    result[key] = value

        elif config.merge_strategy == "deep":
            # Deep merge
            result = {}
            for key, value in inputs.items():
                if isinstance(value, dict):
                    for k, v in value.items():
                        if k in result and isinstance(result[k], dict):
                            result[k].update(v)
                        else:
                            result[k] = v
                else:
                    result[key] = value

        elif config.merge_strategy == "concat":
            # Concatenate all values as strings
            result = {
                config.output_key: config.separator.join(
                    str(v) for v in inputs.values() if v is not None
                )
            }

        else:
            result = inputs.copy()

        # Apply prefix if specified
        if config.prefix and config.merge_strategy != "concat":
            result = {
                f"{config.prefix}{k}": v
                for k, v in result.items()
            }

        return {config.output_key: result}


# ================== Split Component ==================

class SplitConfig(BaseModel):
    split_by: str = Field(
        "key",
        description="Split method: key, value, or custom"
    )
    split_key: Optional[str] = Field(None, description="Key to split on")
    delimiter: Optional[str] = Field(None, description="Delimiter for string splitting")
    max_splits: int = Field(-1, description="Maximum number of splits (-1 = unlimited)")
    output_prefix: str = Field("part", description="Prefix for output parts")


@register_component(
    name="split",
    group="Logic",
    label="Split",
    description="Split data into multiple parts",
    icon="split",
    author="System",
    version="1.0.0",
    config_model=SplitConfig,
)
class SplitComponent(Component):
    """Split data into multiple outputs"""

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: SplitConfig
    ) -> Dict[str, Any]:
        result = {}

        if config.split_by == "key":
            if config.split_key and config.split_key in inputs:
                value = inputs[config.split_key]
                if isinstance(value, (list, tuple)):
                    for i, item in enumerate(value):
                        result[f"{config.output_prefix}_{i}"] = item
                elif config.delimiter and isinstance(value, str):
                    parts = value.split(config.delimiter, config.max_splits)
                    for i, part in enumerate(parts):
                        result[f"{config.output_prefix}_{i}"] = part
                else:
                    result[f"{config.output_prefix}_0"] = value
            else:
                result = inputs

        elif config.split_by == "value":
            for key, value in inputs.items():
                if isinstance(value, str) and config.delimiter:
                    parts = value.split(config.delimiter, config.max_splits)
                    for i, part in enumerate(parts):
                        result[f"{key}_{config.output_prefix}_{i}"] = part
                else:
                    result[key] = value

        else:
            result = inputs

        return result


# ================== Validate Component ==================

class ValidationRule(BaseModel):
    field: str
    rule: str  # required, type, range, regex, custom
    params: Dict[str, Any] = Field(default_factory=dict)


class ValidateConfig(BaseModel):
    rules: List[ValidationRule] = Field(
        default_factory=list,
        description="Validation rules to apply"
    )
    strict_mode: bool = Field(
        False,
        description="If True, raise error on validation failure"
    )
    output_valid: bool = Field(True, description="Include valid data in output")
    output_errors: bool = Field(True, description="Include validation errors in output")


@register_component(
    name="validate",
    group="Logic",
    label="Validate",
    description="Validate data against rules",
    icon="validate",
    author="System",
    version="1.0.0",
    config_model=ValidateConfig,
)
class ValidateComponent(Component):
    """Validate data against rules"""

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: ValidateConfig
    ) -> Dict[str, Any]:
        errors = []
        is_valid = True

        for rule in config.rules:
            field = rule.field
            value = inputs.get(field)

            if rule.rule == "required":
                if value is None or value == "":
                    errors.append(f"Field '{field}' is required")
                    is_valid = False

            elif rule.rule == "type":
                expected_type = rule.params.get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be a string")
                    is_valid = False
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    errors.append(f"Field '{field}' must be a number")
                    is_valid = False
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be a boolean")
                    is_valid = False

            elif rule.rule == "range":
                min_val = rule.params.get("min")
                max_val = rule.params.get("max")
                if isinstance(value, (int, float)):
                    if min_val is not None and value < min_val:
                        errors.append(f"Field '{field}' must be >= {min_val}")
                        is_valid = False
                    if max_val is not None and value > max_val:
                        errors.append(f"Field '{field}' must be <= {max_val}")
                        is_valid = False

            elif rule.rule == "regex":
                pattern = rule.params.get("pattern")
                if pattern and isinstance(value, str):
                    if not re.match(pattern, value):
                        errors.append(f"Field '{field}' does not match pattern")
                        is_valid = False

        result = {
            "is_valid": is_valid,
        }

        if config.output_valid:
            result["data"] = inputs

        if config.output_errors and errors:
            result["errors"] = errors

        if config.strict_mode and not is_valid:
            raise ValueError(f"Validation failed: {errors}")

        return result


# ================== Assign Component ==================

class AssignConfig(BaseModel):
    assignments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of assignments: {'key': 'name', 'value': '{{expr}}', 'default': None}"
    )
    overwrite: bool = Field(
        True,
        description="Overwrite existing values"
    )
    output_all: bool = Field(
        True,
        description="Include all original inputs in output"
    )


@register_component(
    name="assign",
    group="Logic",
    label="Assign",
    description="Assign variables from inputs or expressions",
    icon="assign",
    author="System",
    version="1.0.0",
    config_model=AssignConfig,
)
class AssignComponent(Component):
    """Assign variables based on inputs and expressions"""

    async def execute(
        self,
        inputs: Dict[str, Any],
        config: AssignConfig
    ) -> Dict[str, Any]:
        if config.output_all:
            result = inputs.copy()
        else:
            result = {}

        for assign in config.assignments:
            key = assign.get("key")
            value_expr = assign.get("value")
            default = assign.get("default")

            if not key:
                continue

            # Evaluate value expression
            if value_expr:
                if isinstance(value_expr, str) and '{{' in value_expr:
                    value = TemplateRenderer.render(value_expr, inputs)
                else:
                    value = value_expr
            else:
                value = inputs.get(key, default)

            # Check if we should overwrite
            if value is not None and (config.overwrite or key not in result):
                result[key] = value

        return result


# Export all components
__all__ = [
    "TransformComponent",
    "TransformConfig",
    "MergeComponent",
    "MergeConfig",
    "SplitComponent",
    "SplitConfig",
    "ValidateComponent",
    "ValidateConfig",
    "AssignComponent",
    "AssignConfig",
]
