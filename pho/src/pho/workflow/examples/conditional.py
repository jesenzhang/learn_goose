"""
Conditional workflow example - Branching based on validation.
"""

from pho.workflow import Graph
from pho.components.buildins import (
    StartComponent,
    ValidateComponent,
    SelectorComponent,
    TransformComponent,
    OutputComponent,
)


def create_conditional_example() -> Graph:
    """
    Create a conditional workflow with branching.

    Flow: Start -> Validate -> Selector -> [Process/Reject] -> Output

    Demonstrates:
    - Data validation
    - Conditional routing
    - Multiple processing paths
    """
    graph = Graph()

    # Start node
    graph.add_node_from(
        node_id="start",
        component=StartComponent(),
        config={
            "variables": [
                {"key": "email", "type_info": {"type": "string"}},
                {"key": "age", "type_info": {"type": "integer"}}
            ]
        },
        inputs={},
        label="Start"
    )

    # Validate node
    graph.add_node_from(
        node_id="validate",
        component=ValidateComponent(),
        config={
            "rules": [
                {
                    "field": "email",
                    "rule": "regex",
                    "params": {"pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"}
                },
                {
                    "field": "age",
                    "rule": "range",
                    "params": {"min": 18, "max": 120}
                }
            ],
            "strict_mode": False,
            "output_valid": True,
            "output_errors": True
        },
        inputs={},
        label="Validate Input"
    )

    # Selector node - routes based on validation
    graph.add_node_from(
        node_id="selector",
        component=SelectorComponent(),
        config={
            "selector_key": "is_valid",
            "routes": {
                "True": "process",
                "False": "reject"
            }
        },
        inputs={},
        label="Route by Result"
    )

    # Process node (valid data)
    graph.add_node_from(
        node_id="process",
        component=TransformComponent(),
        config={
            "mode": "template",
            "template": "Valid user: {{email}}, Age: {{age}}"
        },
        inputs={},
        label="Process Valid"
    )

    # Reject node (invalid data)
    graph.add_node_from(
        node_id="reject",
        component=TransformComponent(),
        config={
            "mode": "template",
            "template": "Invalid input: {{errors}}"
        },
        inputs={},
        label="Handle Invalid"
    )

    # Output node
    graph.add_node_from(
        node_id="output",
        component=OutputComponent(),
        config={},
        inputs={},
        label="Output"
    )

    # Connect nodes
    graph.add_edge("start", "validate")
    graph.add_edge("validate", "selector")
    graph.add_edge("selector", "process", source_handle="True")
    graph.add_edge("selector", "reject", source_handle="False")
    graph.add_edge("process", "output")
    graph.add_edge("reject", "output")

    # Set entry point
    graph.set_entry_point("start")

    return graph
