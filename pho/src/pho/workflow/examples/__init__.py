"""
Built-in example workflows for Pho framework.

Provides ready-to-use workflows demonstrating common patterns:
- Linear workflow
- Conditional branching
- Loop processing
- API integration
- LLM chaining
"""

from .linear import create_linear_example
from .conditional import create_conditional_example
from .api_workflow import create_api_workflow_example
from .llm_chain import create_llm_chain_example


def get_all_examples() -> dict:
    """Get all built-in example workflows."""
    return {
        "linear": {
            "name": "Linear Processing",
            "description": "Simple linear workflow: Start -> Transform -> Output",
            "graph": create_linear_example(),
        },
        "conditional": {
            "name": "Conditional Branching",
            "description": "Workflow with conditional logic based on data validation",
            "graph": create_conditional_example(),
        },
        "api_workflow": {
            "name": "API Integration",
            "description": "Fetch data from API, process it, and return result",
            "graph": create_api_workflow_example(),
        },
        "llm_chain": {
            "name": "LLM Chain",
            "description": "Chain multiple LLM calls for complex reasoning",
            "graph": create_llm_chain_example(),
        },
    }


def get_example(example_id: str):
    """Get a specific example workflow by ID."""
    examples = get_all_examples()
    return examples.get(example_id)


__all__ = [
    "get_all_examples",
    "get_example",
    "create_linear_example",
    "create_conditional_example",
    "create_api_workflow_example",
    "create_llm_chain_example",
]
