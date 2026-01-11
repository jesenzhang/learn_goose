"""
Linear workflow example - Simple start-to-finish processing.
"""

from pho.workflow import Graph
from pho.components.buildins import (
    StartComponent,
    TransformComponent,
    OutputComponent,
)


def create_linear_example() -> Graph:
    """
    Create a simple linear workflow.

    Flow: Start -> Transform -> Output

    Demonstrates:
    - Basic component connection
    - Data transformation
    - Output generation
    """
    graph = Graph()

    # Start node - receives initial input
    graph.add_node_from(
        node_id="start",
        component=StartComponent(),
        config={
            "variables": [
                {"key": "name", "type_info": {"type": "string"}},
                {"key": "value", "type_info": {"type": "integer"}}
            ]
        },
        inputs={},
        label="Start"
    )

    # Transform node - processes the data
    graph.add_node_from(
        node_id="transform",
        component=TransformComponent(),
        config={
            "mode": "mapping",
            "mapping": {
                "greeting": "Hello, {{name}}!",
                "doubled_value": "{{value}} * 2"
            }
        },
        inputs={},
        label="Transform Data"
    )

    # Output node - returns final result
    graph.add_node_from(
        node_id="output",
        component=OutputComponent(),
        config={},
        inputs={},
        label="Output"
    )

    # Connect nodes
    graph.add_edge("start", "transform")
    graph.add_edge("transform", "output")

    # Set entry point
    graph.set_entry_point("start")

    return graph
