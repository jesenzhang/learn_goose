"""
Intent Execution Strategy - Configurable intent behavior for MicroAgent.

This module defines how intents should be executed within the MicroAgent pipeline.
Supports multiple execution modes that leverage MicroAgent's unique features.

Execution Modes:
1. llm: Default - LLM uses available tools to accomplish the intent
2. direct: Skip LLM, call handler function directly
3. skill: Activate a skill and let LLM work within that context
4. chain: Execute a predefined sequence of tool calls
5. hybrid: Combine LLM with direct function calls
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
from pydantic import BaseModel, Field

from ..skills.context import ServiceContext

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Intent execution modes."""
    LLM = "llm"           # Default: LLM decides which tools to use
    DIRECT = "direct"     # Skip LLM, call handler directly
    SKILL = "skill"       # Activate a skill, then LLM executes
    CHAIN = "chain"       # Execute predefined tool chain
    HYBRID = "hybrid"     # Combine LLM with function calls


class TerminationAction(str, Enum):
    """What to do after intent execution."""
    CONTINUE = "continue"     # Continue LLM loop (default)
    STOP = "stop"           # Stop and return result
    AWAIT_USER = "await_user" # Wait for user input
    SWITCH_SKILL = "switch_skill"  # Switch to different skill


@dataclass
class ToolCall:
    """Single tool call in a chain."""
    tool: str                          # Tool name
    arguments: Dict[str, Any]          # Static arguments
    from_slot: Optional[str] = None    # If set, use slot value
    output_to: Optional[str] = None    # Store result in shared_memory


@dataclass
class ExecutionConfig:
    """
    Defines how an intent should be executed.

    This config bridges intent recognition with MicroAgent's execution pipeline.
    """
    mode: ExecutionMode = ExecutionMode.LLM

    # Mode-specific settings
    handler: Optional[Callable] = None              # For DIRECT mode
    skill_name: Optional[str] = None                 # For SKILL mode
    tool_chain: List[ToolCall] = field(default_factory=list)  # For CHAIN mode

    # Tool filtering (for LLM mode)
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)

    # Pipeline hooks
    pre_hook: Optional[Callable] = None              # Before LLM
    post_hook: Optional[Callable] = None             # After LLM

    # Termination control
    on_complete: TerminationAction = TerminationAction.CONTINUE
    response_template: Optional[str] = None          # For formatting direct results

    # Skill-specific settings
    skill_params: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> bool:
        """Validate execution config."""
        if self.mode == ExecutionMode.DIRECT and not self.handler:
            logger.error("DIRECT mode requires handler")
            return False
        if self.mode == ExecutionMode.SKILL and not self.skill_name:
            logger.error("SKILL mode requires skill_name")
            return False
        if self.mode == ExecutionMode.CHAIN and not self.tool_chain:
            logger.error("CHAIN mode requires tool_chain")
            return False
        return True


class IntentExecutor:
    """
    Executes intents according to their ExecutionConfig.

    Integrates with MicroAgent's pipeline:
    - Can intercept before LLM (pre-hook)
    - Can modify LLM's available tools
    - Can execute instead of LLM (direct/hybrid)
    - Can intercept after LLM (post-hook)
    - Can control loop termination
    """

    def __init__(self, skill_loader=None, ai_services=None):
        self.skill_loader = skill_loader
        self.ai_services = ai_services
        self._configs: Dict[str, ExecutionConfig] = {}

    def register(self, intent_name: str, config: ExecutionConfig) -> None:
        """Register execution config for an intent."""
        if not config.validate():
            raise ValueError(f"Invalid config for intent: {intent_name}")
        self._configs[intent_name] = config
        logger.info(f"Registered execution config for {intent_name}: mode={config.mode}")

    def get_config(self, intent_name: str) -> Optional[ExecutionConfig]:
        """Get execution config for an intent."""
        return self._configs.get(intent_name)

    def get_allowed_tools(self, intent_name: str, default_tools: List[str]) -> List[str]:
        """
        Get allowed tools for an intent (for LLM mode).

        Applies intent-specific filtering to the default tool list.
        """
        config = self.get_config(intent_name)
        if not config or config.mode != ExecutionMode.LLM:
            return default_tools

        # Start with intent's allowed tools
        if config.allowed_tools:
            tools = [t for t in default_tools if t in config.allowed_tools]
        else:
            tools = default_tools.copy()

        # Remove denied tools
        if config.denied_tools:
            tools = [t for t in tools if t not in config.denied_tools]

        return tools

    async def execute_pre_hook(
        self,
        intent_name: str,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> Optional[str]:
        """
        Execute pre-hook before LLM.

        Returns:
            Response if hook handled the intent (skip LLM), None otherwise
        """
        config = self.get_config(intent_name)
        if not config or not config.pre_hook:
            return None

        try:
            result = await self._run_hook(config.pre_hook, slots, context)
            # If pre_hook returns a value and mode is DIRECT, skip LLM
            if result is not None and config.mode == ExecutionMode.DIRECT:
                return self._format_result(result, config)
            return None
        except Exception as e:
            logger.error(f"Pre-hook error for {intent_name}: {e}")
            return None

    async def execute_direct(
        self,
        intent_name: str,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> str:
        """
        Execute intent directly (no LLM).

        Used for DIRECT mode or when pre-hook handles the intent.
        """
        config = self.get_config(intent_name)
        if not config or not config.handler:
            raise ValueError(f"No handler for intent: {intent_name}")

        result = await self._run_handler(config.handler, slots, context)
        return self._format_result(result, config)

    async def execute_chain(
        self,
        intent_name: str,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> str:
        """
        Execute predefined tool chain.

        Each tool's output can be fed into the next tool.
        """
        config = self.get_config(intent_name)
        if not config or config.mode != ExecutionMode.CHAIN:
            raise ValueError(f"Invalid mode for chain execution: {intent_name}")

        results = []
        memory = {}

        for call in config.tool_chain:
            # Prepare arguments
            args = call.arguments.copy()

            # Substitute slot values
            if call.from_slot and call.from_slot in slots:
                args.update(slots[call.from_slot])

            # Substitute previous results
            for key, value in args.items():
                if isinstance(value, str) and value.startswith("$") and value[1:] in memory:
                    args[key] = memory[value[1:]]

            # Execute tool
            tool_result = await self._execute_tool(call.tool, args, context)
            results.append(tool_result)

            # Store for next tool
            if call.output_to:
                memory[call.output_to] = tool_result

        return "\n".join(str(r) for r in results)

    def should_activate_skill(
        self,
        intent_name: str
    ) -> Optional[tuple[str, Dict[str, Any]]]:
        """
        Check if intent requires skill activation.

        Returns:
            (skill_name, params) or None
        """
        config = self.get_config(intent_name)
        if config and config.mode == ExecutionMode.SKILL:
            return (config.skill_name, config.skill_params)
        return None

    def get_termination_action(
        self,
        intent_name: str
    ) -> TerminationAction:
        """Get what to do after intent execution."""
        config = self.get_config(intent_name)
        if config:
            return config.on_complete
        return TerminationAction.CONTINUE

    async def execute_post_hook(
        self,
        intent_name: str,
        llm_result: str,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> Optional[str]:
        """Execute post-hook after LLM."""
        config = self.get_config(intent_name)
        if not config or not config.post_hook:
            return None

        try:
            return await self._run_hook(
                config.post_hook,
                {**slots, "llm_result": llm_result},
                context
            )
        except Exception as e:
            logger.error(f"Post-hook error for {intent_name}: {e}")
            return None

    # ========================================================================
    # Internal helpers
    # ========================================================================

    async def _run_hook(
        self,
        hook: Callable,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> Any:
        """Run a hook function."""
        import inspect
        sig = inspect.signature(hook)

        kwargs = {}
        for param_name, param in sig.parameters.items():
            if param_name == 'ctx' or param.annotation == ServiceContext:
                kwargs[param_name] = context
            elif param_name in slots:
                kwargs[param_name] = slots[param_name]

        if inspect.iscoroutinefunction(hook):
            return await hook(**kwargs)
        else:
            return await asyncio.to_thread(hook, **kwargs)

    async def _run_handler(
        self,
        handler: Callable,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> Any:
        """Run a direct handler function."""
        return await self._run_hook(handler, slots, context)

    async def _execute_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        context: ServiceContext
    ) -> Any:
        """Execute a single tool."""
        # Find tool from skill loader or core tools
        func = None
        if self.skill_loader:
            func = self.skill_loader.get_tool_func(tool_name)

        if not func:
            raise ValueError(f"Tool not found: {tool_name}")

        # Inject context if needed
        import inspect
        sig = inspect.signature(func)
        if 'ctx' in sig.parameters or any(
            p.annotation == ServiceContext for p in sig.parameters.values()
        ):
            args['ctx'] = context

        if inspect.iscoroutinefunction(func):
            return await func(**args)
        else:
            return await asyncio.to_thread(func, **args)

    def _format_result(self, result: Any, config: ExecutionConfig) -> str:
        """Format handler result using template."""
        result_str = str(result)

        if config.response_template:
            try:
                return config.response_template.format(result=result_str)
            except KeyError as e:
                logger.warning(f"Template error: {e}")

        return result_str


def create_execution_config(
    mode: Union[str, ExecutionMode] = ExecutionMode.LLM,
    **kwargs
) -> ExecutionConfig:
    """
    Helper to create ExecutionConfig.

    Args:
        mode: Execution mode
        **kwargs: Mode-specific parameters

    Returns:
        Configured ExecutionConfig
    """
    if isinstance(mode, str):
        mode = ExecutionMode(mode.lower())

    return ExecutionConfig(mode=mode, **kwargs)


# Convenience creators
def llm_mode(
    allowed_tools: Optional[List[str]] = None,
    denied_tools: Optional[List[str]] = None,
    pre_hook: Optional[Callable] = None,
    post_hook: Optional[Callable] = None,
    on_complete: TerminationAction = TerminationAction.CONTINUE
) -> ExecutionConfig:
    """Create LLM mode config."""
    return ExecutionConfig(
        mode=ExecutionMode.LLM,
        allowed_tools=allowed_tools or [],
        denied_tools=denied_tools or [],
        pre_hook=pre_hook,
        post_hook=post_hook,
        on_complete=on_complete
    )


def direct_mode(
    handler: Callable,
    response_template: Optional[str] = None,
    on_complete: TerminationAction = TerminationAction.STOP
) -> ExecutionConfig:
    """Create DIRECT mode config."""
    return ExecutionConfig(
        mode=ExecutionMode.DIRECT,
        handler=handler,
        response_template=response_template,
        on_complete=on_complete
    )


def skill_mode(
    skill_name: str,
    skill_params: Optional[Dict[str, Any]] = None,
    on_complete: TerminationAction = TerminationAction.CONTINUE
) -> ExecutionConfig:
    """Create SKILL mode config."""
    return ExecutionConfig(
        mode=ExecutionMode.SKILL,
        skill_name=skill_name,
        skill_params=skill_params or {},
        on_complete=on_complete
    )


def chain_mode(
    tool_chain: List[ToolCall],
    on_complete: TerminationAction = TerminationAction.STOP
) -> ExecutionConfig:
    """Create CHAIN mode config."""
    return ExecutionConfig(
        mode=ExecutionMode.CHAIN,
        tool_chain=tool_chain,
        on_complete=on_complete
    )
