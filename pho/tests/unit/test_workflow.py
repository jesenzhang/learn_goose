"""
Unit tests for Workflow module.

Tests cover:
- Graph construction and validation
- Node and Edge operations
- WorkflowExecutor execution
- WorkflowScheduler execution
- ValueResolver
- Control signals
"""

import pytest
import asyncio
from typing import Dict, Any

from pho.workflow.graph import Graph, Node, Edge
from pho.workflow.executor import WorkflowExecutor
from pho.workflow.scheduler import WorkflowScheduler
from pho.workflow.context import WorkflowContext
from pho.workflow.resolver import ValueResolver
from pho.workflow.protocol import ControlSignal, NodeConfig, EdgeConfig, WorkflowDefinition
from pho.workflow.nodes import ComponentNode


# ========================================================================
# Test Components
# ========================================================================


class TestComponent(ComponentNode):
    """Simple test component that returns input."""

    config_model = None
    input_model = None
    output_model = None

    async def execute(self, inputs: Any, **kwargs) -> Any:
        return {"result": inputs.get("value", "default")}


class AddComponent(ComponentNode):
    """Component that adds two numbers."""

    config_model = None
    input_model = None
    output_model = None

    async def execute(self, inputs: Any, **kwargs) -> Any:
        a = inputs.get("a", 0)
        b = inputs.get("b", 0)
        return {"sum": a + b}


class MultiplierComponent(ComponentNode):
    """Component that multiplies input by 2."""

    config_model = None
    input_model = None
    output_model = None

    async def execute(self, inputs: Any, **kwargs) -> Any:
        value = inputs.get("value", 0)
        return {"result": value * 2}


class ConditionalComponent(ComponentNode):
    """Component that returns conditional routing."""

    config_model = None
    input_model = None
    output_model = None

    async def execute(self, inputs: Any, **kwargs) -> Any:
        condition = inputs.get("condition", True)
        return {
            "result": "processed",
            ControlSignal.ACTIVE_HANDLE: "true" if condition else "false"
        }


class BreakComponent(ComponentNode):
    """Component that sends BREAK signal."""

    config_model = None
    input_model = None
    output_model = None

    async def execute(self, inputs: Any, **kwargs) -> Any:
        return {
            ControlSignal.SIGNAL_KEY: ControlSignal.BREAK,
            "result": "breaking"
        }


# ========================================================================
# Graph Tests
# ========================================================================


class TestGraph:
    """Test Graph construction and operations."""

    def test_graph_creation(self):
        """Test creating an empty graph."""
        graph = Graph()
        assert graph.nodes == {}
        assert graph.edges == {}
        assert graph.entry_point is None

    def test_add_node(self):
        """Test adding a node to the graph."""
        graph = Graph()
        component = TestComponent()

        node = Node(
            id="test_node",
            component=component,
            config={"key": "value"},
            inputs={"input": "value"}
        )

        graph.add_node(node)

        assert "test_node" in graph.nodes
        assert graph.nodes["test_node"].component == component
        assert graph.nodes["test_node"].config == {"key": "value"}

    def test_add_node_from(self):
        """Test adding node using helper method."""
        graph = Graph()
        component = TestComponent()

        graph.add_node_from(
            node_id="test_node",
            component=component,
            config={"key": "value"},
            inputs={"input": "value"}
        )

        assert "test_node" in graph.nodes
        assert graph.nodes["test_node"].config == {"key": "value"}

    def test_add_edge(self):
        """Test adding an edge between nodes."""
        graph = Graph()
        comp1 = TestComponent()
        comp2 = TestComponent()

        graph.add_node_from("node1", comp1)
        graph.add_node_from("node2", comp2)

        graph.add_edge("node1", "node2")

        edges = graph.get_outgoing_edges("node1")
        assert len(edges) == 1
        assert edges[0].source == "node1"
        assert edges[0].target == "node2"

    def test_add_conditional_edge(self):
        """Test adding edge with source_handle."""
        graph = Graph()
        comp1 = ConditionalComponent()
        comp2 = TestComponent()
        comp3 = TestComponent()

        graph.add_node_from("node1", comp1)
        graph.add_node_from("node2", comp2)
        graph.add_node_from("node3", comp3)

        graph.add_edge("node1", "node2", source_handle="true")
        graph.add_edge("node1", "node3", source_handle="false")

        edges = graph.get_outgoing_edges("node1")
        assert len(edges) == 2
        assert edges[0].source_handle == "true"
        assert edges[1].source_handle == "false"

    def test_set_entry_point(self):
        """Test setting the entry point."""
        graph = Graph()
        component = TestComponent()

        graph.add_node_from("start", component)
        graph.set_entry_point("start")

        assert graph.entry_point == "start"

    def test_graph_validation(self):
        """Test graph validation."""
        graph = Graph()

        # No entry point should fail
        with pytest.raises(ValueError, match="entry point"):
            graph.validate()

        # Add entry point but dangling edge
        component = TestComponent()
        graph.add_node_from("start", component)
        graph.set_entry_point("start")

        # Add edge to non-existent node
        graph.edges["start"] = [Edge(source="start", target="missing")]

        with pytest.raises(ValueError, match="missing node"):
            graph.validate()


# ========================================================================
# WorkflowExecutor Tests
# ========================================================================


class TestWorkflowExecutor:
    """Test WorkflowExecutor execution."""

    @pytest.mark.asyncio
    async def test_simple_execution(self):
        """Test executing a simple single-node workflow."""
        graph = Graph()
        component = TestComponent()
        graph.add_node_from("node1", component)
        graph.set_entry_point("node1")

        context = WorkflowContext(session_id="test_session")
        executor = WorkflowExecutor()

        result = await executor.run(
            graph=graph,
            inputs={"value": "test_input"},
            context=context
        )

        assert result["result"] == "test_input"

    @pytest.mark.asyncio
    async def test_linear_execution(self):
        """Test executing a linear chain of nodes."""
        graph = Graph()
        add_comp = AddComponent()
        mult_comp = MultiplierComponent()

        graph.add_node_from("add", add_comp, inputs={"a": 5, "b": 3})
        graph.add_node_from("multiply", mult_comp, inputs={"value": "{{ add.sum }}"})
        graph.set_entry_point("add")

        graph.add_edge("add", "multiply")

        context = WorkflowContext(session_id="test_session")
        executor = WorkflowExecutor()

        result = await executor.run(
            graph=graph,
            inputs={},
            context=context
        )

        # 5 + 3 = 8, 8 * 2 = 16
        assert result["result"] == 16

    @pytest.mark.asyncio
    async def test_conditional_routing(self):
        """Test conditional routing based on source_handle."""
        graph = Graph()
        cond_comp = ConditionalComponent()
        true_comp = TestComponent()
        false_comp = TestComponent()

        graph.add_node_from("cond", cond_comp, inputs={"condition": True})
        graph.add_node_from("true_node", true_comp)
        graph.add_node_from("false_node", false_comp)
        graph.set_entry_point("cond")

        graph.add_edge("cond", "true_node", source_handle="true")
        graph.add_edge("cond", "false_node", source_handle="false")

        context = WorkflowContext(session_id="test_session")
        executor = WorkflowExecutor()

        result = await executor.run(
            graph=graph,
            inputs={},
            context=context
        )

        # Should execute true_node
        assert "true_node" in context.node_outputs
        assert "false_node" not in context.node_outputs


# ========================================================================
# ValueResolver Tests
# ========================================================================


class TestValueResolver:
    """Test ValueResolver reference resolution."""

    def test_resolve_reference_in_dict(self):
        """Test resolving a reference in a dictionary."""
        context = WorkflowContext(session_id="test")
        context.set_node_output("node1", {"name": "test", "value": 42})

        mapping = {"result": "{{ node1.name }}"}
        result = ValueResolver.resolve(mapping, context)

        assert result["result"] == "test"

    def test_resolve_nested_reference(self):
        """Test resolving nested path reference."""
        context = WorkflowContext(session_id="test")
        context.set_node_output("node1", {
            "data": {"nested": {"value": "deep"}}
        })

        mapping = {"output": "{{ node1.data.nested.value }}"}
        result = ValueResolver.resolve(mapping, context)

        assert result["output"] == "deep"

    def test_resolve_dict(self):
        """Test resolving a dictionary with references."""
        context = WorkflowContext(session_id="test")
        context.set_node_output("node1", {"value": 42})
        context.set_node_output("node2", {"name": "test"})

        data = {
            "a": "{{ node1.value }}",
            "b": "{{ node2.name }}",
            "c": "static"
        }

        result = ValueResolver.resolve(data, context)

        assert result["a"] == 42
        assert result["b"] == "test"
        assert result["c"] == "static"

    def test_resolve_list(self):
        """Test resolving a list with references."""
        context = WorkflowContext(session_id="test")
        context.set_node_output("node1", {"value": 42})

        data = {"items": ["{{ node1.value }}", "static", "{{ node1.value }}"]}
        result = ValueResolver.resolve(data, context)

        assert result["items"] == [42, "static", 42]

    def test_resolve_with_overrides(self):
        """Test resolving with variable overrides."""
        context = WorkflowContext(session_id="test")

        mapping = {"item": "{{ item }}"}
        result = ValueResolver.resolve(mapping, context, overrides={"item": "overridden"})

        assert result["item"] == "overridden"


# ========================================================================
# WorkflowScheduler Tests
# ========================================================================


class TestWorkflowScheduler:
    """Test WorkflowScheduler with persistence."""

    @pytest.mark.asyncio
    async def test_scheduler_execution(self):
        """Test basic scheduler execution without persistence."""
        graph = Graph()
        comp = TestComponent()
        graph.add_node_from("node1", comp)
        graph.set_entry_point("node1")

        # Create scheduler without checkpointer (in-memory)
        scheduler = WorkflowScheduler(checkpointer=None)

        result = await scheduler.run(
            graph=graph,
            inputs={"value": "test_input"}
        )

        assert result["result"] == "test_input"

    @pytest.mark.asyncio
    async def test_scheduler_with_multiple_nodes(self):
        """Test scheduler with multiple nodes."""
        graph = Graph()
        add_comp = AddComponent()
        mult_comp = MultiplierComponent()

        graph.add_node_from("add", add_comp, inputs={"a": 10, "b": 5})
        graph.add_node_from("multiply", mult_comp, inputs={"value": "{{ add.sum }}"})
        graph.set_entry_point("add")

        graph.add_edge("add", "multiply")

        scheduler = WorkflowScheduler(checkpointer=None)

        result = await scheduler.run(
            graph=graph,
            inputs={}
        )

        # 10 + 5 = 15, 15 * 2 = 30
        assert result["result"] == 30


# ========================================================================
# ControlSignal Tests
# ========================================================================


class TestControlSignals:
    """Test control signal handling."""

    @pytest.mark.asyncio
    async def test_break_signal(self):
        """Test BREAK signal stops execution."""
        graph = Graph()
        break_comp = BreakComponent()
        after_comp = TestComponent()

        graph.add_node_from("break", break_comp)
        graph.add_node_from("after", after_comp)
        graph.set_entry_point("break")

        graph.add_edge("break", "after")

        context = WorkflowContext(session_id="test")
        executor = WorkflowExecutor()

        result = await executor.run(
            graph=graph,
            inputs={},
            context=context
        )

        # Break component should execute
        assert result["result"] == "breaking"

        # After component should NOT execute
        assert "after" not in context.node_outputs


# ========================================================================
# WorkflowDefinition Tests
# ========================================================================


class TestWorkflowDefinition:
    """Test workflow definition protocol models."""

    def test_node_config(self):
        """Test NodeConfig model."""
        config = NodeConfig(
            id="test_node",
            type="test",
            title="Test Node",
            inputs={"key": "value"},
            config={"setting": "value"}
        )

        assert config.id == "test_node"
        assert config.type == "test"
        assert config.inputs == {"key": "value"}

    def test_edge_config(self):
        """Test EdgeConfig model."""
        edge = EdgeConfig(
            id="edge1",
            source="node1",
            target="node2",
            source_handle="true"
        )

        assert edge.source == "node1"
        assert edge.target == "node2"
        assert edge.source_handle == "true"

    def test_workflow_definition(self):
        """Test WorkflowDefinition model."""
        definition = WorkflowDefinition(
            id="workflow1",
            name="Test Workflow",
            nodes=[
                NodeConfig(id="n1", type="start"),
                NodeConfig(id="n2", type="end")
            ],
            edges=[
                EdgeConfig(id="e1", source="n1", target="n2")
            ]
        )

        assert definition.id == "workflow1"
        assert len(definition.nodes) == 2
        assert len(definition.edges) == 1


# ========================================================================
# Integration Tests
# ========================================================================


class TestWorkflowIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_complex_workflow(self):
        """Test a more complex workflow with multiple paths."""
        graph = Graph()

        # Create components
        cond_comp = ConditionalComponent()
        add1_comp = AddComponent()
        add2_comp = AddComponent()
        mult_comp = MultiplierComponent()
        output_comp = TestComponent()

        # Add nodes
        graph.add_node_from("condition", cond_comp, inputs={"condition": True})
        graph.add_node_from("add1", add1_comp, inputs={"a": 10, "b": 5})
        graph.add_node_from("add2", add2_comp, inputs={"a": 20, "b": 30})
        graph.add_node_from("multiply", mult_comp, inputs={"value": "{{ add1.sum }}"})
        graph.add_node_from("output", output_comp, inputs={"value": "{{ multiply.result }}"})

        graph.set_entry_point("condition")

        # Add edges (conditional routing)
        graph.add_edge("condition", "add1", source_handle="true")
        graph.add_edge("condition", "add2", source_handle="false")
        graph.add_edge("add1", "multiply")
        graph.add_edge("multiply", "output")

        context = WorkflowContext(session_id="test_complex")
        executor = WorkflowExecutor()

        result = await executor.run(
            graph=graph,
            inputs={},
            context=context
        )

        # Condition is True, so add1 executes
        assert "add1" in context.node_outputs
        assert "add2" not in context.node_outputs

        # add1: 10 + 5 = 15, multiply: 15 * 2 = 30
        assert context.node_outputs["add1"]["sum"] == 15
        assert result["result"] == 30
