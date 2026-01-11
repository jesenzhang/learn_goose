"""
Workflow Scheduler - Infrastructure management and orchestration.

This module provides the production-ready workflow scheduler with:
- Persistence and checkpointing
- Session management
- Service injection
- State recovery and resume

Architecture:
- WorkflowExecutor: Pure execution logic
- WorkflowScheduler: Infrastructure + orchestration
"""

import logging
import uuid
from typing import Any, Optional, Dict, List, TYPE_CHECKING

from .graph import Graph
from .context import WorkflowContext
from .executor import WorkflowExecutor
from .hook import WorkflowHook
from .checkpointer import WorkflowCheckpointer, WorkflowCheckpointEntity
from .repository import WorkflowRepository
from .protocol import ControlSignal

# Import runtime dependencies
try:
    from pho.globals import get_runtime
    HAS_RUNTIME = True
except ImportError:
    HAS_RUNTIME = False
    get_runtime = None

# Import events
try:
    from pho.events import SystemEvents
    HAS_EVENTS = True
except ImportError:
    HAS_EVENTS = False
    SystemEvents = None

# Type hint for ResourceManager
if TYPE_CHECKING:
    from pho.resources.manager import ResourceManager

logger = logging.getLogger("pho.workflow.scheduler")


class WorkflowScheduler:
    """
    [Infrastructure] Workflow scheduler with full persistence support.

    Responsibilities:
    1. Infrastructure preparation (validation, run_id generation)
    2. Context building with service injection
    3. State recovery and persistence
    4. Event streaming
    5. Checkpoint management

    Delegates execution logic to WorkflowExecutor.
    """

    def __init__(
        self,
        checkpointer: Optional[WorkflowCheckpointer] = None,
        hooks: Optional[List[WorkflowHook]] = None
    ):
        """
        Initialize scheduler.

        Args:
            checkpointer: Optional checkpointer for state persistence (None = no persistence)
            hooks: Optional workflow hooks for lifecycle events
        """
        # Only create default checkpointer if none was explicitly provided
        # and we want persistence. If checkpointer is explicitly None, don't create one.
        self._checkpointer = checkpointer
        self.hooks = hooks or []
        self._executor = WorkflowExecutor(hooks=hooks)

    async def run(
        self,
        graph: Graph,
        inputs: Any,
        run_id: Optional[str] = None,
        streamer: Optional[Any] = None,
        resume: bool = False,
        parent_ctx: Optional[WorkflowContext] = None,
        resource_manager: Optional['ResourceManager'] = None,
        target_node_id: Optional[str] = None
    ) -> Any:
        """
        Execute workflow with full infrastructure support.

        Args:
            graph: Workflow graph to execute
            inputs: Input data
            run_id: Optional run ID (auto-generated if not provided)
            streamer: Optional event streamer
            resume: Whether to resume from checkpoint
            parent_ctx: Optional parent context (for sub-workflows)
            resource_manager: Optional resource manager
            target_node_id: Optional node to stop at

        Returns:
            Final workflow output
        """
        # ==========================================
        # 1. Infrastructure Preparation
        # ==========================================

        # Validate graph
        if not graph.entry_point:
            raise ValueError("Graph must have an entry point")

        # Generate run_id if not provided
        if not run_id:
            run_id = uuid.uuid4().hex
            logger.info(f"Generated run_id: {run_id}")

        # Get runtime services
        runtime = get_runtime() if HAS_RUNTIME else None

        # Get or create streamer
        if streamer is None and runtime:
            streamer = runtime.streamer_factory.create(run_id)

        # Create resource manager if not provided
        if resource_manager is None:
            if runtime:
                resource_manager = runtime.create_resource_manager(user_id=None)
            else:
                logger.warning("No runtime available. Creating minimal resource manager.")
                resource_manager = None  # Would create minimal manager here

        # ==========================================
        # 2. Context Building
        # ==========================================

        # Normalize inputs to dict
        initial_vars = inputs if isinstance(inputs, dict) else {"input": inputs}

        # Create context
        context = WorkflowContext(
            session_id=run_id,
            parent_run_id=parent_ctx.run_id if parent_ctx else None,
            variables=initial_vars
        )

        # Inherit variables from parent
        if parent_ctx:
            context.variables.update(parent_ctx.variables)

        # Inject services
        context.set_services(
            resources=resource_manager,
            streamer=streamer,
            executor=self._executor
        )

        # ==========================================
        # 3. State Recovery
        # ==========================================

        resume_queue = None
        if resume and self._checkpointer:
            state = await self._checkpointer.load_checkpoint(run_id)
            if state and state.status not in ["completed", "failed", "cancelled"]:
                logger.info(f"Resuming run {run_id} from checkpoint")
                context.node_outputs = state.context_data or {}
                if state.execution_queue:
                    resume_queue = state.execution_queue
            else:
                logger.warning(f"Cannot resume run {run_id}. Restarting.")

        # ==========================================
        # 4. Execution
        # ==========================================

        try:
            result = await self._execute_with_checkpointing(
                graph=graph,
                inputs=inputs,
                context=context,
                streamer=streamer,
                start_node_id=None,
                resume_queue=resume_queue,
                target_node_id=target_node_id
            )

            # Save final state
            await self._save_state(run_id, [], context, "completed")

            return result

        except Exception as e:
            # Save failed state
            await self._save_state(run_id, [], context, "failed")
            raise

    async def _execute_with_checkpointing(
        self,
        graph: Graph,
        inputs: Any,
        context: WorkflowContext,
        streamer: Any,
        start_node_id: Optional[str],
        resume_queue: Optional[List[str]],
        target_node_id: Optional[str]
    ) -> Any:
        """
        Execute workflow with periodic checkpointing.

        This wraps the executor to add checkpoint support.
        """
        run_id = context.session_id
        queue = []
        final_output = None

        # Initialize queue
        if resume_queue:
            queue = list(resume_queue)  # Copy to avoid modifying
        else:
            entry_point = start_node_id or graph.entry_point
            queue = [entry_point] if entry_point else []

        # Trigger start hooks
        await self._trigger_hooks("on_workflow_start", run_id, inputs, context)
        if streamer and HAS_EVENTS:
            await streamer.emit(SystemEvents.WORKFLOW_STARTED, inputs)

        try:
            while queue:
                current_node_id = queue.pop(0)

                # Check for suspension
                if current_node_id == "__SUSPEND__":
                    logger.info(f"Workflow {run_id} suspended")
                    await self._save_state(run_id, queue, context, "suspended")
                    return None

                # Get and execute node
                node = graph.get_node(current_node_id)
                if not node:
                    logger.error(f"Node {current_node_id} not found")
                    continue

                # Prepare inputs
                # For entry_point, merge the external inputs with node's defined inputs
                # For other nodes, use node's defined inputs (which may contain references)
                if current_node_id == graph.entry_point:
                    # Merge: external inputs take precedence over node's default inputs
                    invocation_inputs = {**(node.inputs or {}), **(inputs if isinstance(inputs, dict) else {"input": inputs})}
                else:
                    invocation_inputs = node.inputs or {}

                # Prepare config
                invocation_config = node.config.copy()
                invocation_config["id"] = current_node_id

                # Trigger node start hook
                await self._trigger_hooks("on_node_start", run_id, node, invocation_inputs, context)
                if streamer and HAS_EVENTS:
                    await streamer.emit(
                        SystemEvents.NODE_STARTED,
                        {"node_type": node.component.__class__.__name__},
                        producer_id=current_node_id
                    )

                # Execute node
                try:
                    output = await node.component.invoke(
                        inputs=invocation_inputs,
                        config=invocation_config,
                        context=context
                    )
                except Exception as e:
                    logger.error(f"Node {current_node_id} execution failed: {e}", exc_info=True)
                    if streamer and HAS_EVENTS:
                        await streamer.emit(SystemEvents.NODE_ERROR, str(e), producer_id=current_node_id)
                    raise

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

                # Check for target node
                if target_node_id and current_node_id == target_node_id:
                    logger.info(f"Reached target node {target_node_id}. Stopping.")
                    await self._save_state(run_id, queue, context, "stopped")
                    await self._trigger_hooks("on_workflow_end", run_id, output, context)
                    if streamer and HAS_EVENTS:
                        await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, output)
                    return output

                # Add next nodes to queue (deduplicated)
                for nid in next_nodes:
                    if nid not in queue:
                        queue.append(nid)

                # Save checkpoint
                status = "running" if queue else "completed"
                await self._save_state(run_id, queue, context, status)

            # Workflow completed
            logger.info(f"Workflow {run_id} completed")
            await self._trigger_hooks("on_workflow_end", run_id, final_output, context)
            if streamer and HAS_EVENTS:
                await streamer.emit(SystemEvents.WORKFLOW_COMPLETED, final_output)

            return final_output

        except Exception as e:
            logger.error(f"Workflow {run_id} crashed: {e}")
            if streamer and HAS_EVENTS:
                await streamer.emit(SystemEvents.WORKFLOW_FAILED, str(e))
            await self._trigger_hooks("on_workflow_error", run_id, e, context)
            raise

    async def run_to_completion(
        self,
        graph: Graph,
        inputs: Dict[str, Any],
        parent_ctx: Optional[WorkflowContext] = None
    ) -> Dict[str, Any]:
        """
        Helper method to run sub-workflow to completion.

        Used by Loop and Batch components for nested execution.
        """
        return await self.run(
            graph=graph,
            inputs=inputs,
            parent_ctx=parent_ctx,
            resource_manager=parent_ctx.resources if parent_ctx else None
        )

    # ==========================================
    # Private Methods
    # ==========================================

    async def _trigger_hooks(self, method_name: str, *args, **kwargs):
        """Safely trigger all hooks."""
        for hook in self.hooks:
            try:
                func = getattr(hook, method_name, None)
                if func:
                    await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook error in {method_name}: {e}", exc_info=True)

    async def _save_state(
        self,
        run_id: str,
        queue: List[str],
        context: WorkflowContext,
        status: str
    ):
        """Save checkpoint state."""
        if self._checkpointer:
            state = WorkflowCheckpointEntity(
                run_id=run_id,
                execution_queue=queue,
                context_data=context.node_outputs,
                status=status
            )
            await self._checkpointer.save_checkpoint(state)

    def _calculate_next_nodes(
        self,
        graph: Graph,
        current_node_id: str,
        output: Any
    ) -> List[str]:
        """Calculate next nodes based on output."""
        outgoing = graph.get_outgoing_edges(current_node_id)
        next_nodes = []

        active_handle = None
        if isinstance(output, dict) and ControlSignal.ACTIVE_HANDLE in output:
            active_handle = output[ControlSignal.ACTIVE_HANDLE]

        for edge in outgoing:
            if active_handle:
                if edge.source_handle == active_handle:
                    next_nodes.append(edge.target)
            elif edge.source_handle is None:
                next_nodes.append(edge.target)

        return next_nodes


__all__ = ["WorkflowScheduler"]
