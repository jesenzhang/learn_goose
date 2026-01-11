"""
API workflow example - Fetch and process data from external API.
"""

from pho.workflow import Graph
from pho.components.buildins import (
    StartComponent,
    ApiClientComponent,
    TransformComponent,
    ValidateComponent,
    OutputComponent,
)


def create_api_workflow_example() -> Graph:
    """
    Create an API integration workflow.

    Flow: Start -> API Request -> Validate -> Transform -> Output

    Demonstrates:
    - External API calls
    - Response validation
    - Data transformation
    - Error handling
    """
    graph = Graph()

    # Start node
    graph.add_node_from(
        node_id="start",
        component=StartComponent(),
        config={
            "variables": [
                {"key": "user_id", "type_info": {"type": "integer"}}
            ]
        },
        inputs={},
        label="Start"
    )

    # API Client node
    graph.add_node_from(
        node_id="api_request",
        component=ApiClientComponent(),
        config={
            "base_url": "https://jsonplaceholder.typicode.com",
            "global_headers": {
                "Content-Type": "application/json"
            },
            "retry_config": {
                "max_retries": 3,
                "retry_delay": 1.0
            },
            "endpoints": """[
                {
                    "name": "get_user",
                    "path": "/users/{id}",
                    "method": "GET",
                    "timeout": 10
                }
            ]""",
            "endpoint_name": "get_user",
            "path_params": {"id": "{{user_id}}"},
            "use_async": True
        },
        inputs={},
        label="Fetch User Data"
    )

    # Validate node
    graph.add_node_from(
        node_id="validate",
        component=ValidateComponent(),
        config={
            "rules": [
                {
                    "field": "response.id",
                    "rule": "required"
                },
                {
                    "field": "response.name",
                    "rule": "required"
                }
            ],
            "strict_mode": False,
            "output_valid": True,
            "output_errors": True
        },
        inputs={},
        label="Validate Response"
    )

    # Transform node
    graph.add_node_from(
        node_id="transform",
        component=TransformComponent(),
        config={
            "mode": "mapping",
            "mapping": {
                "user_id": "{{response.id}}",
                "name": "{{response.name}}",
                "email": "{{response.email}}",
                "company": "{{response.company.name}}"
            }
        },
        inputs={},
        label="Extract Fields"
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
    graph.add_edge("start", "api_request")
    graph.add_edge("api_request", "validate")
    graph.add_edge("validate", "transform")
    graph.add_edge("transform", "output")

    # Set entry point
    graph.set_entry_point("start")

    return graph
