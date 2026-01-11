"""
LLM Chain workflow example - Chain multiple LLM calls for complex reasoning.
"""

from pho.workflow import Graph
from pho.components.buildins import (
    StartComponent,
    LLMComponent,
    TransformComponent,
    MergeComponent,
    OutputComponent,
)


def create_llm_chain_example() -> Graph:
    """
    Create an LLM chain workflow.

    Flow: Start -> LLM (Analyze) -> LLM (Summarize) -> Merge -> Output

    Demonstrates:
    - Chaining multiple LLM calls
    - Context passing between LLMs
    - Merging multiple outputs
    - Prompt engineering
    """
    graph = Graph()

    # Start node
    graph.add_node_from(
        node_id="start",
        component=StartComponent(),
        config={
            "variables": [
                {"key": "text", "type_info": {"type": "string"}}
            ]
        },
        inputs={},
        label="Start"
    )

    # First LLM - Analyze the text
    graph.add_node_from(
        node_id="analyze",
        component=LLMComponent(),
        config={
            "model": "gpt-4o-mini",
            "prompt": "Analyze the following text and identify the main topics, sentiment, and key points:\n\n{{text}}",
            "system_prompt": "You are a text analysis expert. Provide structured, concise analysis.",
            "max_tokens": 500,
            "temperature": 0.3
        },
        inputs={},
        label="LLM: Analyze"
    )

    # Second LLM - Summarize with context
    graph.add_node_from(
        node_id="summarize",
        component=LLMComponent(),
        config={
            "model": "gpt-4o-mini",
            "prompt": "Based on this analysis:\n\n{{analyze.output}}\n\nCreate a brief summary of the original text in 2-3 sentences.",
            "system_prompt": "You are a summary writer. Create clear, concise summaries.",
            "max_tokens": 200,
            "temperature": 0.5
        },
        inputs={},
        label="LLM: Summarize"
    )

    # Transform - Extract key insights
    graph.add_node_from(
        node_id="extract",
        component=TransformComponent(),
        config={
            "mode": "template",
            "template": "Analysis: {{analyze.output}}\n\nSummary: {{summarize.output}}"
        },
        inputs={},
        label="Combine Results"
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
    graph.add_edge("start", "analyze")
    graph.add_edge("analyze", "summarize")
    graph.add_edge("analyze", "extract")
    graph.add_edge("summarize", "extract")
    graph.add_edge("extract", "output")

    # Set entry point
    graph.set_entry_point("start")

    return graph
