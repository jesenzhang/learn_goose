"""
WebSearch tool for searching the web via MCP.

This tool provides web search:
- MCP-based search via https://mcp.exa.ai
- SSE (Server-Sent Events) streaming
- 25-second timeout
- Search types: auto, fast, deep
"""

import asyncio
import json
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


API_CONFIG = {
    "BASE_URL": "https://mcp.exa.ai",
    "ENDPOINTS": {
        "SEARCH": "/mcp",
    },
    "DEFAULT_NUM_RESULTS": 8,
}


class WebSearchParams(ToolInputSchema):
    """Parameters for the WebSearch tool."""

    query: str = Field(..., description="Websearch query")
    numResults: Optional[int] = Field(
        8,
        description="Number of search results to return (default: 8)",
    )
    livecrawl: Optional[Literal["fallback", "preferred"]] = Field(
        "fallback",
        description=(
            "Live crawl mode - 'fallback': use live crawling as backup if cached content "
            "unavailable, 'preferred': prioritize live crawling (default: 'fallback')"
        ),
    )
    type: Optional[Literal["auto", "fast", "deep"]] = Field(
        "auto",
        description=(
            "Search type - 'auto': balanced search (default), "
            "'fast': quick results, 'deep': comprehensive search"
        ),
    )
    contextMaxCharacters: Optional[int] = Field(
        None,
        description="Maximum characters for context string optimized for LLMs (default: 10000)",
    )


class WebSearchTool(BaseTool):
    """
    Web search via MCP (https://mcp.exa.ai).

    Features:
    - MCP-based search
    - Server-Sent Events (SSE) streaming
    - 25-second timeout
    - Search types: auto, fast, deep
    - Live crawl options: fallback, preferred

    Usage:
    - query (required): Search query
    - numResults (optional): Number of results (default 8)
    - livecrawl (optional): Live crawl mode (default fallback)
    - type (optional): Search type (default auto)
    - contextMaxCharacters (optional): Max context chars (default 10000)
    """

    name = "websearch"
    description = (
        "Web search via MCP (https://mcp.exa.ai). "
        "Supports Server-Sent Events (SSE) streaming. "
        "Search types: auto (balanced), fast (quick), deep (comprehensive). "
        "Live crawl options: fallback (use as backup), preferred (prioritize)."
    )
    input_schema = WebSearchParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._timeout = self.config.get("timeout", 25)
        self._api_key = self.config.get("api_key")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the web search.

        Args:
            params: Dictionary containing 'query', optional 'numResults', 'livecrawl',
                     'type', and 'contextMaxCharacters'.

        Returns:
            ToolResult with search results.

        Raises:
            ToolError: If search fails or times out.
        """
        query = params["query"]
        num_results = params.get("numResults", API_CONFIG["DEFAULT_NUM_RESULTS"])
        livecrawl = params.get("livecrawl", "fallback")
        search_type = params.get("type", "auto")
        context_max_chars = params.get("contextMaxCharacters")

        # Prepare search request
        search_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "web_search_exa",
                "arguments": {
                    "query": query,
                    "type": search_type,
                    "numResults": num_results,
                    "livecrawl": livecrawl,
                },
            },
        }

        # Add optional parameters
        if context_max_chars is not None:
            search_request["params"]["arguments"]["contextMaxCharacters"] = context_max_chars

        # Execute search with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_search(search_request),
                timeout=self._timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise ToolError("Search request timed out")
        except Exception as e:
            raise ToolError(f"Web search failed: {e}")

    async def _execute_search(self, search_request: Dict[str, Any]) -> ToolResult:
        """
        Execute the search request and parse SSE response.

        Args:
            search_request: Search request dictionary.

        Returns:
            ToolResult with search results.
        """
        import aiohttp

        url = API_CONFIG["BASE_URL"] + API_CONFIG["ENDPOINTS"]["SEARCH"]

        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }

        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    json=search_request,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ToolError(f"Search error ({response.status}): {error_text}")

                    # Parse SSE response
                    response_text = await response.text()

                    for line in response_text.split("\n"):
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if (
                                    data.get("result")
                                    and data["result"].get("content")
                                    and len(data["result"]["content"]) > 0
                                ):
                                    return ToolResult(
                                        content=data["result"]["content"][0]["text"],
                                        metadata={},
                                    )
                            except json.JSONDecodeError:
                                continue

                    return ToolResult(
                        content="No search results found. Please try a different query.",
                        metadata={},
                    )

            except aiohttp.ClientError as e:
                raise ToolError(f"Network error: {e}")

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "query": {
                "type": "string",
                "description": "Websearch query",
            },
            "numResults": {
                "type": "integer",
                "description": "Number of search results to return (default: 8)",
                "default": 8,
            },
            "livecrawl": {
                "type": "string",
                "enum": ["fallback", "preferred"],
                "description": (
                    "Live crawl mode - 'fallback': use live crawling as backup, "
                    "'preferred': prioritize live crawling"
                ),
                "default": "fallback",
            },
            "type": {
                "type": "string",
                "enum": ["auto", "fast", "deep"],
                "description": (
                    "Search type - 'auto': balanced search, "
                    "'fast': quick results, 'deep': comprehensive search"
                ),
                "default": "auto",
            },
            "contextMaxCharacters": {
                "type": "integer",
                "description": (
                    "Maximum characters for context string optimized for LLMs"
                ),
                "default": 10000,
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
