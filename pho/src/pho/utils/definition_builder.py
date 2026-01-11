"""
Definition builder for Pho framework.

Builds ComponentDefinition from Pydantic models for workflow components.
"""

from typing import Type, List, Dict, Any, Optional
from pydantic import BaseModel

from pho.components.protocol import (
    ComponentDefinition,
    UIConfig,
    Port
)


class DefinitionBuilder:
    """
    [Builder] Responsible for building ComponentDefinition.

    Creates component definitions including:
    - JSON schemas for config, input, and output
    - UI configuration with ports
    - Port metadata extracted from Pydantic models
    """

    @staticmethod
    def build(
        # 1. Explicit UI information
        label: str,
        description: str = "",
        icon: str = "default",
        group: str = "default",
        author: str = "System",
        version: str = "1.0.0",

        # 2. Pydantic models
        config_model: Optional[Type[BaseModel]] = None,
        input_model: Optional[Type[BaseModel]] = None,
        output_model: Optional[Type[BaseModel]] = None
    ) -> ComponentDefinition:
        """
        Build a ComponentDefinition from Pydantic models.

        Args:
            label: Display label for the component
            description: Description of what the component does
            icon: Icon identifier for UI display
            group: Group/category for the component
            author: Author of the component
            version: Component version string
            config_model: Pydantic model for configuration
            input_model: Pydantic model for inputs
            output_model: Pydantic model for outputs

        Returns:
            ComponentDefinition with schemas and UI configuration
        """
        # Generate JSON schemas from Pydantic models
        config_schema = config_model.model_json_schema() if config_model else {}
        input_schema = input_model.model_json_schema() if input_model else {}
        output_schema = output_model.model_json_schema() if output_model else {}

        # Extract ports from models
        input_ports = DefinitionBuilder._extract_ports(input_model, input_schema) if input_model else []
        output_ports = DefinitionBuilder._extract_ports(output_model, output_schema) if output_model else []

        # Config ports are treated as input ports in the UI
        config_ports = DefinitionBuilder._extract_ports(config_model, config_schema) if config_model else []

        # Build UI Config
        ui_config = UIConfig(
            label=label,
            description=description,
            icon=icon,
            group=group,
            author=author,
            version=version,
            ports={
                "inputs": input_ports + config_ports,
                "outputs": output_ports
            }
        )

        return ComponentDefinition(
            config_schema=config_schema,
            input_schema=input_schema,
            output_schema=output_schema,
            ui=ui_config
        )

    @staticmethod
    def _extract_ports(model: Type[BaseModel], json_schema: Dict[str, Any]) -> List[Port]:
        """
        Extract port definitions from a Pydantic model.

        This method extracts metadata from Pydantic field definitions
        to create Port objects for the workflow editor UI.

        Args:
            model: The Pydantic BaseModel subclass
            json_schema: The JSON schema generated from the model

        Returns:
            List of Port objects with metadata from the model fields
        """
        ports = []

        # Get property definitions from generated JSON Schema
        # This captures Field(..., title="xxx") processing results
        properties = json_schema.get("properties", {})

        # Iterate through model field definitions
        for name, field in model.model_fields.items():
            # 1. Get schema information
            prop_info = properties.get(name, {})

            # 2. Extract UI metadata
            # Prefer Field(title="..."), fallback to field name
            title = prop_info.get("title", name)

            # Extract type description (for frontend connection color coding)
            # Simple handling: if $ref (reference object), mark as "object"
            if "$ref" in prop_info:
                type_str = "object"
            else:
                type_str = prop_info.get("type", "any")

            # 3. Extract custom UI Widget hints
            # Method A: Extract from json_schema_extra (recommended Pydantic V2 approach)
            # field.json_schema_extra can be dict or callable
            extra = field.json_schema_extra
            ui_widget = "default"
            if isinstance(extra, dict):
                ui_widget = extra.get("x-ui-widget", "default")

            # Method B: Compatibility with legacy syntax, look in generated schema properties
            # (if using Field(json_schema_extra={...}))
            if ui_widget == "default":
                ui_widget = prop_info.get("x-ui-widget", "default")

            # 4. Build port object
            ports.append(Port(
                name=name,
                title=title,
                type=type_str,
                # Pydantic V2 check for required: field.is_required()
                required=field.is_required(),
                description=prop_info.get("description", ""),
                ui_widget=ui_widget
            ))

        return ports


__all__ = ["DefinitionBuilder"]
