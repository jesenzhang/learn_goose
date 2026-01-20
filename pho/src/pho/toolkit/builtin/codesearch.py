"""
CodeSearch tool for semantic code search.

This tool provides:
- Semantic code search via embeddings
- Similarity-based matching
- Configurable token limits
- Search for APIs, libraries, and SDKs
"""

import asyncio
import json
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


API_CONFIG = {
    "BASE_URL": "https://mcp.exa.ai",
    "ENDPOINTS": {
        "CONTEXT": "/mcp",
    },
}


class CodeSearchParams(ToolInputSchema):
    """Parameters for the CodeSearch tool."""

    query: str = Field(
        ...,
        description=(
            "Search query to find relevant context for APIs, Libraries, and SDKs. "
            "For example, 'React useState hook examples', 'Python pandas dataframe filtering', "
            "'Express.js middleware', 'Next.js partial prerendering configuration'"
        ),
    )
    tokensNum: Optional[int] = Field(
        5000,
        ge=1000,
        le=50000,
        description=(
            "Number of tokens to return (1000-50000). Default is 5000 tokens. "
            "Adjust this value based on how much context you need - "
            "use lower values for focused queries and higher values for comprehensive documentation."
        ),
    )


class CodeSearchTool(BaseTool):
    """
    Semantic code search via embeddings.

    Features:
    - Semantic code search via embeddings
    - Similarity-based matching for code snippets
    - Configurable token limits
    - Search for APIs, libraries, and SDKs

    Usage:
    - query (required): Search query for code/API/library context
    - tokensNum (optional): Number of tokens to return (1000-50000, default 5000)
    """

    name = "codesearch"
    description = (
        "Semantic code search for finding relevant code snippets, API documentation, "
        "library examples, and SDK usage patterns. Uses embedding-based similarity matching. "
        "Adjust token count based on context needed - lower for focused queries, "
        "higher for comprehensive documentation."
    )
    input_schema = CodeSearchParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._timeout = self.config.get("timeout", 30)
        self._api_key = self.config.get("api_key")

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Execute the code search.

        Args:
            params: Dictionary containing 'query' and optional 'tokensNum'.

        Returns:
            ToolResult with search results.

        Raises:
            ToolError: If search fails or times out.
        """
        query = params["query"]
        tokens_num = params.get("tokensNum", 5000)

        # Prepare search request
        search_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "get_code_context_exa",
                "arguments": {
                    "query": query,
                    "tokensNum": tokens_num,
                },
            },
        }

        # Execute search with timeout
        try:
            result = await asyncio.wait_for(
                self._execute_search(search_request),
                timeout=self._timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise ToolError("Code search request timed out")
        except Exception as e:
            raise ToolError(f"Code search failed: {e}")

    async def _execute_search(self, search_request: Dict[str, Any]) -> ToolResult:
        """
        Execute the code search request and parse SSE response.

        Args:
            search_request: Search request dictionary.

        Returns:
            ToolResult with search results.
        """
        import aiohttp

        url = API_CONFIG["BASE_URL"] + API_CONFIG["ENDPOINTS"]["CONTEXT"]

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
                        raise ToolError(f"Code search error ({response.status}): {error_text}")

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
                        content=(
                            "No code snippets or documentation found. "
                            "Please try a different query, be more specific about "
                            "the library or programming concept, or check spelling of framework names."
                        ),
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
                "description": (
                    "Search query to find relevant context for APIs, "
                    "Libraries, and SDKs"
                ),
            },
            "tokensNum": {
                "type": "integer",
                "description": (
                    "Number of tokens to return (1000-50000). "
                    "Adjust based on context needed"
                ),
                "default": 5000,
                "minimum": 1000,
                "maximum": 50000,
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
