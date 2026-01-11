"""
Workflow Execution Engine - Core execution logic without infrastructure.

This module provides the pure execution engine for workflow graphs:
- Graph traversal and node execution
- Control signal handling
- Routing logic
- Hook triggering

Separation of concerns:
- WorkflowScheduler: Infrastructure setup (persistence, session management)
- WorkflowExecutor: Pure execution logic
"""

import logging
import asyncio
from typing import Any, Optional, List, Dict

from .graph import Graph
from .context import WorkflowContext
from .protocol import ControlSignal
from .hook import WorkflowHook

# Import events when available
try:
    from pho.events import SystemEvents
    HAS_EVENTS = True
except ImportError:
    HAS_EVENTS = False
    SystemEvents = None

logger = logging.getLogger("pho.workflow.executor")


class WorkflowExecutor:
    """
    [Core] Pure workflow execution engine.

    Responsibilities:
    1. Graph traversal and node execution
    2. Control signal handling
    3. Routing logic (source_handle based)
    4. Hook triggering

    NOT responsible for:
    - Database operations
    - HTTP streaming
    - User authentication
    - Session management

    This design allows the executor to be used in different contexts:
    - With WorkflowScheduler (full persistence)
    - In tests (in-memory)
    - In sub-workflows (nested execution)
    """

    def __init__(self, hooks: Optional[List[WorkflowHook]] = None):
        """
        Initialize executor.

        Args:
            hooks: Optional list of workflow hooks for lifecycle events
        """
        self.hooks = hooks or []

    async def _trigger_hooks(self, method_name: str, *args, **kwargs):
        """Safely execute all hooks with the given method name."""
        for hook in self.hooks:
            try:
                func = getattr(hook, method_name, None)
                if func:
                    await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook error in {method_name}: {e}", exc_info=True)

    async def run(
        self,
        graph: Graph,
        inputs: Any,
        context: WorkflowContext,
        start_node_id: Optional[str] = None,
        resume_queue: Optional[List[str]] = None,
        streamer: Optional[Any] = None,
    ) -> Any:
        """
        Execute the workflow graph.

        Args:
            graph: The workflow graph to execute
            inputs: Initial input data
            context: Workflow execution context
            start_node_id: Optional node to start from (for resume)
            resume_queue: Optional queue to resume from
            streamer: Optional event streamer

        Returns:
            Final output from the workflow
        """
        run_id = context.session_id

        # 1. Initialize queue
        queue = resume_queue or []
        if not queue:
            entry_point = start_node_id or graph.entry_point
            if not entry_point:
                raise ValueError("Graph has no entry point")
            queue.append(entry_point)

        # 2. Trigger start hooks
        await self._trigger_hooks("on_workflow_start", run_id, inputs, context)
        if streamer and HAS_EVENTS:
            await streamer.emit(SystemEvents.WORKFLOW_STARTED, inputs)

        final_output = None

        try:
            while queue:
                # Check for suspension signal
                if context.is_suspended:
                    logger.info(f"Workflow {run_id} suspended by signal.")
                    return {"status": "suspended", "queue": queue}

                current_node_id = queue.pop(0)

                # Get node
                node = graph.get_node(current_node_id)
                if not node:
                    logger.error(f"Node {current_node_id} not found.")
                    continue

                # Prepare inputs
                # For entry_point, merge the external inputs with node's defined inputs
                # For other nodes, use node's defined inputs (which may contain references)
                if current_node_id == graph.entry_point:
                    # Merge: external inputs take precedence over node's default inputs
                    node_inputs = {**(node.inputs or {}), **(inputs if isinstance(inputs, dict) else {"input": inputs})}
                else:
                    node_inputs = node.inputs or {}

                node_config = node.config.copy()
                node_config["id"] = current_node_id

                # Trigger node start hook
                await self._trigger_hooks("on_node_start", run_id, node, node_inputs, context)
                if streamer and HAS_EVENTS:
                    await streamer.emit(
                        SystemEvents.NODE_STARTED,
                        {"node_type": node.component.__class__.__name__},
                        producer_id=current_node_id
                    )

                # Execute node
                try:
                    output = await node.component.invoke(
                        inputs=node_inputs,
                        config=node_config,
                        context=context
                    )
                except asyncio.CancelledError:
                    raise  # Propagate cancellation
                except Exception as e:
                    if streamer and HAS_EVENTS:
                        await streamer.emit(SystemEvents.NODE_ERROR, str(e), producer_id=current_node_id)
                    raise e

                # Update context
                if output is not None:
                    context.set_node_output(current_node_id, output)
                    final_output = output

                # Trigger node end hook
                await self._trigger_hooks("on_node_end", run_id, node, output, context)
                if streamer and HAS_EVENTS:
                    await streamer.emit(
                        SystemEvents.NODE_FINISHED,
                        output,
                        producer_id=current_node_id
                    )

                # Check for control signals
                if isinstance(output, dict) and ControlSignal.SIGNAL_KEY in output:
                    signal = output[ControlSignal.SIGNAL_KEY]
                    logger.debug(f"Control signal: {signal}")
                    continue

                # Calculate next nodes
                next_nodes = self._calculate_next_nodes(graph, current_node_id, output)
                for nid in next_nodes:
                    if nid not in queue:
                        queue.append(nid)

            # Workflow completed
            logger.info(f"Workflow {run_id} completed.")
            await self._trigger_hooks("on_workflow_end", run_id, final_output, context)
            if streamer and HAS_EVENTS:
                await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, final_output)

            return final_output

        except asyncio.CancelledError:
            logger.info(f"Workflow {run_id} terminated by cancellation.")
            raise
        except Exception as e:
            logger.error(f"Workflow {run_id} crashed: {e}")
            if streamer and HAS_EVENTS:
                await streamer.emit(SystemEvents.WORKFLOW_FAILED, str(e))
            await self._trigger_hooks("on_workflow_error", run_id, e, context)
            raise

    def _calculate_next_nodes(
        self,
        graph: Graph,
        current_node_id: str,
        output: Any
    ) -> List[str]:
        """
        Calculate next nodes based on output and edges.

        Args:
            graph: The workflow graph
            current_node_id: Current node ID
            output: Output from current node

        Returns:
            List of next node IDs to execute
        """
        outgoing = graph.get_outgoing_edges(current_node_id)
        next_nodes = []

        # Get active handle from output (for conditional routing)
        active_handle = None
        if isinstance(output, dict) and ControlSignal.ACTIVE_HANDLE in output:
            active_handle = output[ControlSignal.ACTIVE_HANDLE]

        for edge in outgoing:
            # Conditional routing based on source_handle
            if active_handle:
                if edge.source_handle == active_handle:
                    next_nodes.append(edge.target)
            elif edge.source_handle is None:
                # No handle means always execute this edge
                next_nodes.append(edge.target)

        return next_nodes


__all__ = ["WorkflowExecutor"]
