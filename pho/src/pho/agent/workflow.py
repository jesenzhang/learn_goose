"""
WorkflowAgent - DAG workflow orchestration engine.

This agent implements workflow-based execution using the DAG engine:
- Execute workflows with component-based nodes
- Support for conditional branching
- Sub-workflow execution
- State management and persistence
"""

import logging
from typing import Optional, Dict, Any, List, AsyncIterator

from .core import (
    AgentEngine,
    AgentResponse,
    AgentStatus,
    AgentEvent,
    AgentEventType,
    Context,
    ExecutionMode,
    AgentStyle,
    AgentConfig,
)
from pho.conversation import Message, Conversation
from pho.providers import BaseLLM

logger = logging.getLogger(__name__)


class WorkflowAgentEngine(AgentEngine):
    """
    Workflow-based agent engine implementation.

    Uses DAG (Directed Acyclic Graph) execution:
    - Nodes: Components that process data
    - Edges: Connections between components
    - Conditions: Branching logic
    - Subgraphs: Nested workflows

    The agent can:
    1. Execute workflows by ID (stored in workflow registry)
    2. Create ad-hoc workflows from natural language
    3. Fall back to LLM for non-workflow queries
    """

    def __init__(
        self,
        llm: BaseLLM,
        config: Optional[AgentConfig] = None,
        tools: Optional[Dict[str, Any]] = None,
    ):
        self.llm = llm
        self.config = config or AgentConfig()
        self.tools = tools or {}

        # Workflow registry (lazy import to avoid circular dependencies)
        self._workflow_registry = None
        self._scheduler = None

    def get_mode(self) -> ExecutionMode:
        return ExecutionMode.WORKFLOW

    def get_style(self) -> AgentStyle:
        return AgentStyle.ORCHESTRATED

    async def execute(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Execute workflow-based agent.

        Args:
            input: User input or workflow command
            context: Execution context

        Returns:
            AgentResponse with results
        """
        # Check if input is a workflow invocation
        if input.strip().startswith("workflow:"):
            return await self._execute_workflow_command(input, context)

        # Check if we should create a workflow from natural language
        if self._should_create_workflow(input):
            return await self._create_and_execute_workflow(input, context)

        # Otherwise, use LLM directly
        return await self._execute_with_llm(input, context)

    async def execute_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream execution with real-time updates"""
        # Emit start event
        yield AgentResponse(
            text="",
            status=AgentStatus.THINKING,
            events=[AgentEvent(type=AgentEventType.START, data={"input": input})]
        )

        # Check if input is a workflow invocation
        if input.strip().startswith("workflow:"):
            async for response in self._execute_workflow_command_stream(input, context):
                yield response
        elif self._should_create_workflow(input):
            async for response in self._create_and_execute_workflow_stream(input, context):
                yield response
        else:
            async for response in self._execute_with_llm_stream(input, context):
                yield response

    # ========================================================================
    # Workflow Execution Methods
    # ========================================================================

    async def _execute_workflow_command(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Execute workflow by command.

        Command format: workflow:workflow_id?param1=value1&param2=value2

        Example:
            workflow:data_pipeline?source=api&format=json
        """
        # Parse command
        parts = input[len("workflow:"):].strip().split("?")
        workflow_id = parts[0]

        # Parse parameters
        params = {}
        if len(parts) > 1:
            for param in parts[1].split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    params[key] = value

        # Get scheduler
        scheduler = self._get_scheduler()

        # Try to get workflow from registry
        graph = self._get_workflow_from_registry(workflow_id)
        if graph is None:
            return AgentResponse(
                text=f"Workflow '{workflow_id}' not found. Available workflows: {self._list_available_workflows()}",
                status=AgentStatus.COMPLETED,
            )

        try:
            # Execute workflow
            result = await scheduler.run(
                graph=graph,
                inputs=params or {"input": input},
                run_id=context.session_id,
            )

            return AgentResponse(
                text=self._format_workflow_result(result),
                status=AgentStatus.COMPLETED,
            )
        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            return AgentResponse(
                text=f"Workflow execution failed: {str(e)}",
                status=AgentStatus.ERROR,
            )

    async def _execute_workflow_command_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream workflow execution"""
        parts = input[len("workflow:"):].strip().split("?")
        workflow_id = parts[0]

        yield AgentResponse(
            text=f"Executing workflow: {workflow_id}\n",
            status=AgentStatus.STREAMING,
        )

        # Get and execute workflow
        scheduler = self._get_scheduler()
        graph = self._get_workflow_from_registry(workflow_id)

        if graph is None:
            yield AgentResponse(
                text=f"\nWorkflow '{workflow_id}' not found.",
                status=AgentStatus.COMPLETED,
            )
            return

        try:
            # For now, execute synchronously
            # In future, we can hook into the streamer for real-time updates
            result = await scheduler.run(
                graph=graph,
                inputs={},
                run_id=context.session_id,
            )

            yield AgentResponse(
                text=f"\n{self._format_workflow_result(result)}",
                status=AgentStatus.COMPLETED,
            )
        except Exception as e:
            yield AgentResponse(
                text=f"\nWorkflow execution failed: {str(e)}",
                status=AgentStatus.ERROR,
            )

    async def _create_and_execute_workflow(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """
        Create an ad-hoc workflow from natural language and execute it.

        This uses the LLM to understand the task and create a simple workflow.
        """
        # For now, fall back to LLM
        # In future, we can use LLM to generate workflow definitions
        return await self._execute_with_llm(input, context)

    async def _create_and_execute_workflow_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream ad-hoc workflow creation and execution"""
        async for response in self._execute_with_llm_stream(input, context):
            yield response

    # ========================================================================
    # LLM Fallback Methods
    # ========================================================================

    async def _execute_with_llm(
        self,
        input: str,
        context: Context
    ) -> AgentResponse:
        """Use LLM to handle the request"""
        conversation = self.create_conversation(input, context)

        response_msg, _ = await self.call_llm(
            conversation.agent_visible_messages()
        )

        return AgentResponse(
            text=response_msg.text or "",
            status=AgentStatus.COMPLETED,
        )

    async def _execute_with_llm_stream(
        self,
        input: str,
        context: Context
    ) -> AsyncIterator[AgentResponse]:
        """Stream LLM response"""
        conversation = self.create_conversation(input, context)

        async for msg, _ in self.call_llm_stream(
            conversation.agent_visible_messages()
        ):
            if msg and msg.content:
                for item in msg.content:
                    if hasattr(item, 'text'):
                        yield AgentResponse(
                            text=item.text,
                            status=AgentStatus.STREAMING,
                        )

        yield AgentResponse(
            text="",
            status=AgentStatus.COMPLETED,
        )

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _should_create_workflow(self, input: str) -> bool:
        """
        Determine if input should trigger workflow creation.

        For now, always return False.
        In future, we can use heuristics or LLM to decide.
        """
        return False

    def _get_scheduler(self):
        """Get or create workflow scheduler"""
        if self._scheduler is None:
            from pho.workflow import WorkflowScheduler
            self._scheduler = WorkflowScheduler()
        return self._scheduler

    def _get_workflow_from_registry(self, workflow_id: str):
        """
        Get workflow graph from registry.

        For now, return None (no registry implemented).
        In future, this will query the workflow registry/database.
        """
        # TODO: Implement workflow registry lookup
        # from pho.workflow import WorkflowRepository
        # repo = WorkflowRepository()
        # return repo.get_workflow(workflow_id)
        return None

    def _list_available_workflows(self) -> List[str]:
        """List available workflow IDs"""
        # TODO: Implement workflow listing
        return ["No workflows registered"]

    def _format_workflow_result(self, result: Any) -> str:
        """Format workflow result for display"""
        if isinstance(result, dict):
            return "\n".join(f"{k}: {v}" for k, v in result.items())
        return str(result)

    def create_conversation(self, input: str, context: Context) -> Conversation:
        """Create initial conversation from input."""
        conversation = Conversation()

        if self.config and hasattr(self.config, 'system_prompt') and self.config.system_prompt:
            conversation.push(Message.system(self.config.system_prompt))

        conversation.push(Message.user(input))
        return conversation

    async def call_llm(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> tuple[Message, Optional[Any]]:
        """Call the LLM with messages."""
        try:
            msg, usage = await self.llm.agenerate(messages, tools=tools)
            return msg, usage
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def call_llm_stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None
    ) -> AsyncIterator[tuple[Message, Optional[Any]]]:
        """Call the LLM with streaming."""
        try:
            async for msg, usage in self.llm.astream(messages, tools=tools):
                yield msg, usage
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            raise


__all__ = ["WorkflowAgentEngine"]
