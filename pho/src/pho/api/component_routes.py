"""
Component API routes - Provides component metadata for frontend.

This module exposes component definitions as JSON API endpoints,
enabling frontend to dynamically discover and render components.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

from pho.components import component_registry
from pho.components.protocol import ComponentDefinition


router = APIRouter(prefix="/components", tags=["components"])


class ComponentListItem(BaseModel):
    """Component list item for frontend."""
    type: str
    label: str
    group: str
    description: str
    icon: str


class ComponentDetail(ComponentListItem):
    """Detailed component definition with schemas."""
    config_schema: Dict[str, Any] = {}
    input_schema: Dict[str, Any] = {}
    output_schema: Dict[str, Any] = {}
    ports: Dict[str, List[Dict[str, Any]]] = {}


@router.get("/", response_model=List[ComponentListItem])
async def list_components() -> List[ComponentListItem]:
    """
    Get all registered components.

    Returns a list of components for the component library sidebar.
    """
    components = []

    for entry in component_registry.list_entries():
        meta = entry.meta
        definition = meta.definition
        ui = definition.ui if definition else None

        if ui:
            components.append(ComponentListItem(
                type=meta.type,
                label=ui.label,
                group=ui.group,
                description=ui.description,
                icon=ui.icon
            ))

    return components


@router.get("/{component_type}", response_model=ComponentDetail)
async def get_component_detail(component_type: str) -> ComponentDetail:
    """
    Get detailed component definition.

    Returns complete schema information for a specific component,
    including config_schema, input_schema, output_schema, and ports.
    """
    entry = component_registry.get_entry(component_type)

    if not entry:
        raise HTTPException(status_code=404, detail=f"Component '{component_type}' not found")

    meta = entry.meta
    definition = meta.definition
    ui = definition.ui if definition else None

    if not ui:
        raise HTTPException(status_code=404, detail=f"Component '{component_type}' has no UI definition")

    # Extract ports from UI config - convert Port objects to dicts
    if ui.ports:
        # Port objects need to be individually serialized to dicts
        ports = {
            "inputs": [port.model_dump() for port in ui.ports.get("inputs", [])],
            "outputs": [port.model_dump() for port in ui.ports.get("outputs", [])]
        }
    else:
        ports = {"inputs": [], "outputs": []}

    return ComponentDetail(
        type=meta.type,
        label=ui.label,
        group=ui.group,
        description=ui.description,
        icon=ui.icon,
        config_schema=definition.config_schema,
        input_schema=definition.input_schema,
        output_schema=definition.output_schema,
        ports=ports
    )


@router.get("/groups")
async def list_component_groups() -> Dict[str, List[Dict[str, Any]]]:
    """
    Get components grouped by category.

    Returns components organized by group for easier navigation.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for entry in component_registry.list_entries():
        meta = entry.meta
        definition = meta.definition
        ui = definition.ui if definition else None

        if ui:
            group = ui.group
            if group not in groups:
                groups[group] = []

            groups[group].append({
                "type": meta.type,
                "label": ui.label,
                "description": ui.description,
                "icon": ui.icon
            })

    return groups
