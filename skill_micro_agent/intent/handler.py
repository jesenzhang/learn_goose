"""
Intent Handler System - Connect intents to executable behaviors.

This module provides:
- Intent handler registration
- Intent-based tool filtering
- Handler execution with context injection
"""

import asyncio
import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, TypeVar

from ..skills.context import ServiceContext

logger = logging.getLogger(__name__)

T = TypeVar('T')


class IntentHandler:
    """
    Wrapper for intent execution logic.

    Associates an intent name with:
    - Handler function (to execute when intent is triggered)
    - Allowed tools (to restrict LLM's tool access)
    - Pre/post processing hooks
    """

    def __init__(
        self,
        intent_name: str,
        handler: Callable,
        allowed_tools: Optional[List[str]] = None,
        description: str = ""
    ):
        self.intent_name = intent_name
        self.handler = handler
        self.allowed_tools = allowed_tools or []
        self.description = description or handler.__doc__ or f"Handler for {intent_name}"

    async def execute(self, slots: Dict[str, Any], context: ServiceContext) -> Any:
        """
        Execute the intent handler.

        Args:
            slots: Extracted slot values from intent recognition
            context: Service context

        Returns:
            Handler result
        """
        # Prepare arguments
        sig = inspect.signature(self.handler)
        valid_params = {
            name: param for name, param in sig.parameters.items()
            if param.kind in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY)
        }

        # Merge slots with context
        kwargs = {}
        for param_name, param in valid_params.items():
            if param_name == 'ctx' or param.annotation == ServiceContext:
                kwargs[param_name] = context
            elif param_name in slots:
                kwargs[param_name] = slots[param_name]
            elif param.default != inspect.Parameter.empty:
                kwargs[param_name] = param.default

        # Execute handler
        if inspect.iscoroutinefunction(self.handler):
            return await self.handler(**kwargs)
        else:
            # Run sync handlers in thread pool
            return await asyncio.to_thread(self.handler, **kwargs)

    def get_allowed_tools(self) -> List[str]:
        """Get list of tools this intent can use."""
        return self.allowed_tools.copy()


class IntentRouter:
    """
    Routes recognized intents to their handlers.

    Usage:
        router = IntentRouter()

        @router.register("recommend_exhibits", allowed_tools=["search", "get_details"])
        async def handle_recommend(keywords: str, count: int, ctx: ServiceContext):
            assets = await ctx.ai_services.search(keywords)
            return format_results(assets[:count])

        # Execute
        result = await router.execute("recommend_exhibits", {"keywords": "古代", "count": 5}, context)
    """

    def __init__(self):
        self._handlers: Dict[str, IntentHandler] = {}

    def register(
        self,
        intent_name: str,
        allowed_tools: Optional[List[str]] = None,
        description: str = ""
    ) -> Callable:
        """
        Decorator to register an intent handler.

        Args:
            intent_name: Name of the intent this handles
            allowed_tools: Tools this intent is allowed to use
            description: Handler description

        Returns:
            Decorator function
        """
        def decorator(func: Callable) -> Callable:
            handler = IntentHandler(
                intent_name=intent_name,
                handler=func,
                allowed_tools=allowed_tools,
                description=description
            )
            self._handlers[intent_name] = handler
            logger.info(f"Registered handler for intent: {intent_name}")
            return func

        return decorator

    def register_handler(self, handler: IntentHandler) -> None:
        """Register a pre-configured IntentHandler."""
        self._handlers[handler.intent_name] = handler
        logger.info(f"Registered handler for intent: {handler.intent_name}")

    def get_handler(self, intent_name: str) -> Optional[IntentHandler]:
        """Get handler by intent name."""
        return self._handlers.get(intent_name)

    def get_allowed_tools(self, intent_name: str) -> List[str]:
        """
        Get allowed tools for an intent.

        Returns empty list if intent not registered (no restriction).
        """
        handler = self.get_handler(intent_name)
        if handler:
            return handler.get_allowed_tools()
        return []

    async def execute(
        self,
        intent_name: str,
        slots: Dict[str, Any],
        context: ServiceContext
    ) -> Any:
        """
        Execute handler for the given intent.

        Args:
            intent_name: Intent to execute
            slots: Extracted slot values
            context: Service context

        Returns:
            Handler result

        Raises:
            ValueError: If intent not registered
        """
        handler = self.get_handler(intent_name)
        if not handler:
            raise ValueError(f"No handler registered for intent: {intent_name}")

        return await handler.execute(slots, context)

    def has_handler(self, intent_name: str) -> bool:
        """Check if intent has a registered handler."""
        return intent_name in self._handlers

    def list_intents(self) -> List[str]:
        """Get list of all registered intent names."""
        return list(self._handlers.keys())


def create_handler_from_config(
    intent_name: str,
    intent_config: Dict[str, Any],
    handler_func: Callable
) -> IntentHandler:
    """
    Create an IntentHandler from configuration.

    Args:
        intent_name: Intent identifier
        intent_config: Intent configuration from YAML
        handler_func: Handler function

    Returns:
        Configured IntentHandler
    """
    return IntentHandler(
        intent_name=intent_name,
        handler=handler_func,
        allowed_tools=intent_config.get("allowed_tools", []),
        description=intent_config.get("description", "")
    )
