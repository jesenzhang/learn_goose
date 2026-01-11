"""
Pho Workflow Editor - A simple web-based workflow editor.

Built with Streamlit, this editor provides:
- Visual workflow builder (drag-and-drop interface)
- Component library sidebar
- Node configuration panel
- Workflow execution and monitoring
"""

import streamlit as st
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from pho.workflow import (
        Graph,
        WorkflowScheduler,
        WorkflowContext,
        WorkflowDefinition,
        NodeConfig,
        EdgeConfig,
        get_all_examples,
        get_example,
    )
    from pho.workflow.graph import Node, Edge
    from pho.components import component_registry
    from pho.components.buildins import (
        StartComponent,
        EndComponent,
        OutputComponent,
        CodeRunner,
        Lambda,
        LLMComponent,
        SelectorComponent,
        LoopComponent,
        BatchComponent,
        ApiClientComponent,
        TransformComponent,
        MergeComponent,
        SplitComponent,
        ValidateComponent,
        AssignComponent,
    )
    IMPORTS_AVAILABLE = True
except ImportError as e:
    IMPORTS_AVAILABLE = False
    st.error(f"Failed to import pho modules: {e}")
    st.info("Please ensure pho is installed: pip install -e pho/")


# ========================================================================
# Data Models
# ========================================================================


@dataclass
class ComponentDef:
    """Component definition for UI."""
    type: str
    label: str
    group: str
    description: str
    icon: str = "default"
    config_schema: Dict[str, Any] = None
    input_schema: Dict[str, Any] = None
    output_schema: Dict[str, Any] = None


@dataclass
class WorkflowNode:
    """Node in the workflow editor."""
    id: str
    type: str
    label: str
    x: int
    y: int
    inputs: Dict[str, Any] = None
    config: Dict[str, Any] = None


@dataclass
class WorkflowEdge:
    """Edge in the workflow editor."""
    id: str
    source: str
    target: str
    source_handle: Optional[str] = None


# ========================================================================
# Component Library
# ========================================================================


def get_component_library() -> List[ComponentDef]:
    """
    Get available components from the component registry.

    This dynamically loads components from component_registry,
    allowing new components to be automatically discovered.
    """
    if not IMPORTS_AVAILABLE:
        return []

    components = []

    # Get all registered components from the registry
    entries = component_registry.list_entries()

    for entry in entries:
        meta = entry.meta
        definition = meta.definition

        # Extract UI info from ComponentDefinition
        ui = definition.ui if definition else None

        if ui:
            components.append(ComponentDef(
                type=meta.type,
                label=ui.label,
                group=ui.group,
                description=ui.description,
                icon=ui.icon,
                config_schema=definition.config_schema,
                input_schema=definition.input_schema,
                output_schema=definition.output_schema,
            ))

    # If registry is empty (e.g., components not yet imported), fall back to hardcoded list
    if not components:
        components = _get_fallback_component_library()

    return components


def _get_fallback_component_library() -> List[ComponentDef]:
    """Fallback hardcoded component list."""
    return [
        # Basic components
        ComponentDef(
            type="start",
            label="Start",
            group="Basic",
            description="Entry point for the workflow"
        ),
        ComponentDef(
            type="end",
            label="End",
            group="Basic",
            description="Workflow endpoint"
        ),
        ComponentDef(
            type="output",
            label="Output",
            group="Basic",
            description="Output final result"
        ),
        # Code components
        ComponentDef(
            type="code",
            label="Code Runner",
            group="Code",
            description="Execute Python code"
        ),
        ComponentDef(
            type="lambda",
            label="Lambda",
            group="Code",
            description="Simple lambda function"
        ),
        # AI components
        ComponentDef(
            type="llm",
            label="LLM",
            group="AI",
            description="Large Language Model call"
        ),
        # Control components
        ComponentDef(
            type="selector",
            label="Selector",
            group="Control",
            description="Conditional branching"
        ),
        ComponentDef(
            type="loop",
            label="Loop",
            group="Control",
            description="Iterate over items"
        ),
        ComponentDef(
            type="batch",
            label="Batch",
            group="Control",
            description="Parallel batch processing"
        ),
        # API components
        ComponentDef(
            type="api",
            label="API Client",
            group="API",
            description="Configurable HTTP API client with retry support"
        ),
        # Logic components
        ComponentDef(
            type="transform",
            label="Transform",
            group="Logic",
            description="Transform and reshape data"
        ),
        ComponentDef(
            type="merge",
            label="Merge",
            group="Logic",
            description="Merge multiple inputs into one"
        ),
        ComponentDef(
            type="split",
            label="Split",
            group="Logic",
            description="Split data into multiple parts"
        ),
        ComponentDef(
            type="validate",
            label="Validate",
            group="Logic",
            description="Validate data against rules"
        ),
        ComponentDef(
            type="assign",
            label="Assign",
            group="Logic",
            description="Assign variables from inputs"
        ),
    ]


# ========================================================================
# Session State Management
# ========================================================================


def init_session_state():
    """Initialize session state for the workflow editor."""
    if "workflow_nodes" not in st.session_state:
        st.session_state.workflow_nodes = []
    if "workflow_edges" not in st.session_state:
        st.session_state.workflow_edges = []
    if "selected_node" not in st.session_state:
        st.session_state.selected_node = None
    if "workflow_name" not in st.session_state:
        st.session_state.workflow_name = "Untitled Workflow"
    if "node_counter" not in st.session_state:
        st.session_state.node_counter = 0
    if "execution_result" not in st.session_state:
        st.session_state.execution_result = None


# ========================================================================
# UI Components
# ========================================================================


def render_component_library():
    """Render the component library sidebar."""
    st.sidebar.title("Component Library")

    components = get_component_library()
    groups = {}

    # Group components
    for comp in components:
        if comp.group not in groups:
            groups[comp.group] = []
        groups[comp.group].append(comp)

    # Render groups
    for group_name, group_components in groups.items():
        with st.sidebar.expander(group_name):
            for comp in group_components:
                if st.button(
                    f"{comp.icon} {comp.label}",
                    key=f"add_{comp.type}",
                    help=comp.description,
                    use_container_width=True
                ):
                    add_node(comp.type, comp.label)


def add_node(node_type: str, label: str):
    """Add a new node to the workflow."""
    st.session_state.node_counter += 1
    node_id = f"{node_type}_{st.session_state.node_counter}"

    new_node = WorkflowNode(
        id=node_id,
        type=node_type,
        label=label,
        x=100 + len(st.session_state.workflow_nodes) * 50,
        y=100 + len(st.session_state.workflow_nodes) * 50,
        inputs={},
        config={}
    )

    st.session_state.workflow_nodes.append(new_node)
    st.session_state.selected_node = node_id


def render_workflow_canvas():
    """Render the workflow canvas."""
    col1, col2 = st.columns([3, 1])

    with col1:
        st.subheader("Workflow Canvas")

        if not st.session_state.workflow_nodes:
            st.info("Drag components from the library to start building your workflow.")
        else:
            # Display nodes
            for node in st.session_state.workflow_nodes:
                with st.container():
                    col_a, col_b, col_c = st.columns([1, 3, 1])

                    with col_a:
                        if st.button("x", key=f"del_{node.id}", help="Delete node"):
                            delete_node(node.id)

                    with col_b:
                        is_selected = st.session_state.selected_node == node.id
                        if st.button(
                            f"**{node.label}** ({node.id})",
                            key=f"sel_{node.id}",
                            use_container_width=True,
                            type="primary" if is_selected else "secondary"
                        ):
                            st.session_state.selected_node = node.id

                    with col_c:
                        st.caption(node.type)

                    # Show inputs/edges
                    incoming_edges = [e for e in st.session_state.workflow_edges if e.target == node.id]
                    if incoming_edges:
                        st.caption(f"In: {', '.join(e.source for e in incoming_edges)}")

                    st.divider()

    with col2:
        st.subheader("Connections")

        if len(st.session_state.workflow_nodes) >= 2:
            # Add edge form
            source_options = [n.id for n in st.session_state.workflow_nodes]
            target_options = [n.id for n in st.session_state.workflow_nodes]

            source = st.selectbox("From", source_options, key="edge_source")
            target = st.selectbox("To", target_options, key="edge_target")

            if st.button("Add Connection"):
                add_edge(source, target)

        # Display existing edges
        st.write("**Existing Connections:**")
        for edge in st.session_state.workflow_edges:
            with st.container():
                cols = st.columns([3, 1])
                with cols[0]:
                    st.text(f"{edge.source} -> {edge.target}")
                with cols[1]:
                    if st.button("x", key=f"del_edge_{edge.id}"):
                        delete_edge(edge.id)


def add_edge(source: str, target: str):
    """Add a new edge to the workflow."""
    if source == target:
        st.warning("Cannot connect node to itself.")
        return

    # Check if edge already exists
    for edge in st.session_state.workflow_edges:
        if edge.source == source and edge.target == target:
            st.warning("Connection already exists.")
            return

    edge_id = f"edge_{source}_{target}"
    new_edge = WorkflowEdge(id=edge_id, source=source, target=target)
    st.session_state.workflow_edges.append(new_edge)


def delete_node(node_id: str):
    """Delete a node and its connected edges."""
    st.session_state.workflow_nodes = [
        n for n in st.session_state.workflow_nodes if n.id != node_id
    ]
    st.session_state.workflow_edges = [
        e for e in st.session_state.workflow_edges
        if e.source != node_id and e.target != node_id
    ]

    if st.session_state.selected_node == node_id:
        st.session_state.selected_node = None


def delete_edge(edge_id: str):
    """Delete an edge."""
    st.session_state.workflow_edges = [
        e for e in st.session_state.workflow_edges if e.id != edge_id
    ]


def render_node_config():
    """Render the node configuration panel."""
    if st.session_state.selected_node is None:
        st.info("Select a node to configure it.")
        return

    node = next(
        (n for n in st.session_state.workflow_nodes if n.id == st.session_state.selected_node),
        None
    )

    if node is None:
        st.warning("Selected node not found.")
        return

    st.subheader(f"Configure: {node.label}")

    # Basic config
    node.label = st.text_input("Label", value=node.label)

    # Node-specific config based on type
    if node.type == "llm":
        st.write("**LLM Configuration**")
        if node.config is None:
            node.config = {}
        node.config["model"] = st.text_input("Model", value=node.config.get("model", "gpt-4o-mini"))
        node.config["prompt"] = st.text_area("System Prompt", value=node.config.get("prompt", ""))
        node.config["max_tokens"] = st.number_input("Max Tokens", value=node.config.get("max_tokens", 1000))

    elif node.type == "code":
        st.write("**Code Configuration**")
        if node.config is None:
            node.config = {}
        node.config["code"] = st.text_area("Python Code", value=node.config.get("code", ""), height=200)

    elif node.type == "loop":
        st.write("**Loop Configuration**")
        if node.config is None:
            node.config = {}
        node.config["count"] = st.number_input("Iterations", value=node.config.get("count", 3))

    # Input mapping
    st.write("**Input Mapping**")
    if node.inputs is None:
        node.inputs = {}

    input_key = st.text_input("Input Key")
    input_value = st.text_input("Input Value (use {{ node_id.field }} for references)")

    if st.button("Add Input Mapping") and input_key and input_value:
        node.inputs[input_key] = input_value


def render_workflow_actions():
    """Render workflow action buttons."""
    st.subheader("Actions")

    # Example workflows section
    if IMPORTS_AVAILABLE:
        st.write("**Example Workflows**")
        examples = get_all_examples()
        example_options = ["-- Select Example --"] + list(examples.keys())
        example_labels = ["-- Select Example --"] + [examples[k]["name"] for k in examples.keys()]

        selected_example = st.selectbox(
            "Load an example workflow to get started",
            options=range(len(example_options)),
            format_func=lambda i: f"{example_labels[i]} - {examples[list(examples.keys())[i-1]]['description']}" if i > 0 else example_options[i]
        )

        if selected_example > 0 and st.button("Load Example", key="load_example"):
            example_id = list(examples.keys())[selected_example - 1]
            load_example_workflow(example_id)

        st.divider()

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("Save Workflow", type="primary"):
            save_workflow()

    with col2:
        if st.button("Load Workflow"):
            load_workflow()

    with col3:
        if st.button("Clear Workflow"):
            st.session_state.workflow_nodes = []
            st.session_state.workflow_edges = []
            st.session_state.selected_node = None
            st.rerun()

    st.divider()

    # Execute workflow
    if st.button("Execute Workflow", type="primary", use_container_width=True):
        execute_workflow()


def save_workflow():
    """Save workflow to session state."""
    workflow_def = {
        "name": st.session_state.workflow_name,
        "nodes": [asdict(n) for n in st.session_state.workflow_nodes],
        "edges": [asdict(e) for e in st.session_state.workflow_edges]
    }

    st.session_state["saved_workflow"] = workflow_def
    st.success("Workflow saved!")


def load_workflow():
    """Load workflow from session state."""
    if "saved_workflow" not in st.session_state:
        st.warning("No saved workflow found.")
        return

    workflow_def = st.session_state["saved_workflow"]

    st.session_state.workflow_name = workflow_def.get("name", "Untitled Workflow")
    st.session_state.workflow_nodes = [
        WorkflowNode(**n) for n in workflow_def.get("nodes", [])
    ]
    st.session_state.workflow_edges = [
        WorkflowEdge(**e) for e in workflow_def.get("edges", [])
    ]

    st.success("Workflow loaded!")
    st.rerun()


def load_example_workflow(example_id: str):
    """Load an example workflow by ID."""
    if not IMPORTS_AVAILABLE:
        st.error("Cannot load example: imports not available.")
        return

    example = get_example(example_id)
    if not example:
        st.warning(f"Example '{example_id}' not found.")
        return

    graph = example["graph"]

    # Convert Graph to workflow editor format
    st.session_state.workflow_name = example["name"]
    st.session_state.workflow_nodes = []
    st.session_state.workflow_edges = []

    # Get node and edge data from graph
    for node_id, node_data in graph._nodes.items():
        st.session_state.workflow_nodes.append(
            WorkflowNode(
                id=node_id,
                type=node_data.component.type if hasattr(node_data.component, 'type') else "unknown",
                label=node_data.label or node_id,
                x=100,
                y=100,
                inputs=node_data.inputs or {},
                config=node_data.config or {}
            )
        )

    for edge_id, edge_data in graph._edges.items():
        for target in edge_data:
            st.session_state.workflow_edges.append(
                WorkflowEdge(
                    id=f"{edge_id}_{target}",
                    source=edge_id,
                    target=target,
                    source_handle=target if edge_data[target] else None
                )
            )

    st.success(f"Loaded example: {example['name']}")
    st.rerun()


def execute_workflow():
    """Execute the current workflow."""
    import asyncio

    if not IMPORTS_AVAILABLE:
        st.error("Cannot execute workflow: imports not available.")
        return

    if not st.session_state.workflow_nodes:
        st.warning("Cannot execute empty workflow.")
        return

    async def _execute():
        """Internal async function to run the workflow."""
        # Build Graph from nodes and edges
        graph = build_graph_from_workflow()

        # Execute
        scheduler = WorkflowScheduler(checkpointer=None)
        result = await scheduler.run(
            graph=graph,
            inputs={},
            run_id=None
        )
        return result

    try:
        with st.spinner("Executing workflow..."):
            result = asyncio.run(_execute())
            st.session_state.execution_result = result
            st.success("Workflow executed successfully!")

    except Exception as e:
        st.error(f"Workflow execution failed: {str(e)}")


def build_graph_from_workflow() -> "Graph":
    """Build a Graph from workflow nodes and edges."""
    from pho.components.buildins import (
        StartComponent,
        EndComponent,
        OutputComponent,
        CodeRunner,
        Lambda,
        LLMComponent,
        SelectorComponent,
        LoopComponent,
        BatchComponent,
        ApiClientComponent,
        TransformComponent,
        MergeComponent,
        SplitComponent,
        ValidateComponent,
        AssignComponent,
    )

    # Component mapping
    component_map = {
        "start": StartComponent(),
        "end": EndComponent(),
        "output": OutputComponent(),
        "code": CodeRunner(),
        "lambda": Lambda(),
        "llm": LLMComponent(),
        "selector": SelectorComponent(),
        "loop": LoopComponent(),
        "batch": BatchComponent(),
        "api": ApiClientComponent(),
        "transform": TransformComponent(),
        "merge": MergeComponent(),
        "split": SplitComponent(),
        "validate": ValidateComponent(),
        "assign": AssignComponent(),
    }

    graph = Graph()

    # Add nodes
    for node in st.session_state.workflow_nodes:
        component = component_map.get(node.type)
        if component is None:
            st.warning(f"Unknown component type: {node.type}")
            continue

        graph.add_node_from(
            node_id=node.id,
            component=component,
            config=node.config or {},
            inputs=node.inputs or {},
            label=node.label
        )

    # Add edges
    for edge in st.session_state.workflow_edges:
        graph.add_edge(
            source=edge.source,
            target=edge.target,
            source_handle=edge.source_handle
        )

    # Set entry point (first node or a node with type "start")
    if st.session_state.workflow_nodes:
        entry = st.session_state.workflow_nodes[0].id
        graph.set_entry_point(entry)

    return graph


# ========================================================================
# Main App
# ========================================================================


def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="Pho Workflow Editor",
        page_icon="🔄",
        layout="wide"
    )

    st.title("Pho Workflow Editor")
    st.markdown("Build and execute workflows visually.")

    # Initialize session state
    init_session_state()

    # Layout
    render_component_library()

    tab1, tab2, tab3 = st.tabs(["Builder", "Configuration", "Execute"])

    with tab1:
        render_workflow_canvas()

    with tab2:
        render_node_config()

    with tab3:
        render_workflow_actions()

        # Display execution result
        if st.session_state.execution_result is not None:
            st.subheader("Execution Result")
            st.json(st.session_state.execution_result)


if __name__ == "__main__":
    main()
