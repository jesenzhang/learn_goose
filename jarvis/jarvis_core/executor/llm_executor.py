"""
LLM Executor - Execute LLM-related effects.

Provides async LLM generation and streaming.
"""

import asyncio
import logging
from typing import List, Dict, Any, AsyncIterator, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM generation."""
    content: str
    tool_calls: List[Dict[str, Any]] = None
    usage: Dict[str, Any] = None
    finish_reason: Optional[str] = None


class LLMExecutor:
    """
    Abstract LLM executor.

    Implementations:
    - MockLLMExecutor (for testing)
    - OpenAIExecutor (for production)
    - LocalExecutor (for local models)
    """

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate a complete response.

        Args:
            messages: Chat messages in OpenAI format
            tools: Tool definitions in OpenAI format
            **kwargs: Additional parameters (temperature, max_tokens, etc.)

        Returns:
            LLMResponse with content, tool_calls, and usage info
        """
        raise NotImplementedError

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream response chunks.

        Args:
            messages: Chat messages in OpenAI format
            tools: Tool definitions in OpenAI format
            **kwargs: Additional parameters

        Yields:
            Chunks with "delta" or "tool_call" fields
        """
        raise NotImplementedError


class MockLLMExecutor(LLMExecutor):
    """Mock LLM executor for testing."""

    def __init__(
        self,
        response: str = "This is a mock response.",
        delay: float = 0.1,
    ):
        self._response = response
        self._delay = delay
        self._call_count = 0

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        self._call_count += 1
        logger.debug(f"Mock LLM generate call #{self._call_count}")

        await asyncio.sleep(self._delay)

        return LLMResponse(
            content=self._response,
            usage={"prompt_tokens": 10, "completion_tokens": len(self._response)},
        )

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        self._call_count += 1
        logger.debug(f"Mock LLM stream call #{self._call_count}")

        # Stream character by character
        for i, char in enumerate(self._response):
            if i > 0 and i % 5 == 0:
                await asyncio.sleep(self._delay / 10)
            yield {"delta": char}

        yield {"finish_reason": "stop"}


class OpenAIExecutor(LLMExecutor):
    """
    Real LLM executor using OpenAI API.

    Supports:
    - OpenAI API
    - Azure OpenAI
    - OpenAI-compatible APIs
    """

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._client = None

    async def _get_client(self):
        """Lazy initialization of OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                )
                logger.info(f"OpenAI client initialized for model: {self._model}")
            except ImportError:
                raise ImportError(
                    "OpenAI package not installed. "
                    "Install with: pip install openai"
                )

        return self._client

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> LLMResponse:
        client = await self._get_client()

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            **kwargs,
        }

        if tools:
            payload["tools"] = tools

        try:
            response = await client.chat.completions.create(**payload)
            choice = response.choices[0]
            message = choice.message

            content = message.content or ""

            tool_calls = []
            if message.tool_calls:
                for tc in message.tool_calls:
                    tool_calls.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    })

            return LLMResponse(
                content=content,
                tool_calls=tool_calls if tool_calls else None,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                finish_reason=choice.finish_reason,
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> AsyncIterator[Dict[str, Any]]:
        client = await self._get_client()

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            **kwargs,
        }

        if tools:
            payload["tools"] = tools

        try:
            stream = await client.chat.completions.create(**payload)

            async for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                # Stream text content
                if delta.content:
                    yield {"delta": delta.content}

                # Stream tool calls
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        yield {
                            "tool_call": {
                                "id": tc.id,
                                "name": tc.function.name if tc.function else None,
                                "arguments": tc.function.arguments if tc.function else None,
                            }
                        }

                # Finish reason
                if chunk.choices[0].finish_reason:
                    yield {"finish_reason": chunk.choices[0].finish_reason}

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise


def create_llm_executor(
    executor_type: str = "mock",
    **kwargs,
) -> LLMExecutor:
    """
    Factory function to create LLM executor.

    Args:
        executor_type: Type of executor ("mock" or "openai")
        **kwargs: Configuration for the executor

    Returns:
        LLMExecutor instance
    """
    if executor_type == "mock":
        return MockLLMExecutor(**kwargs)
    elif executor_type == "openai":
        return OpenAIExecutor(**kwargs)
    else:
        raise ValueError(f"Unknown executor type: {executor_type}")
