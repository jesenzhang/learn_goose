"""
WebFetch tool for fetching web content.

This tool provides web content fetching:
- HTTP/HTTPS support
- Multiple output formats: text, markdown, html
- Timeout support (max 120 seconds)
- Content size limit (5MB)
- User-Agent header
"""

import asyncio
import re
from html.parser import HTMLParser
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

from ..tool import BaseTool, ToolError, ToolInfo, ToolInputSchema, ToolResult


MAX_RESPONSE_SIZE = 5 * 1024 * 1024  # 5MB
DEFAULT_TIMEOUT = 30  # seconds
MAX_TIMEOUT = 120  # 2 minutes


class TextExtractor(HTMLParser):
    """HTML text extractor that skips scripts and styles."""

    def __init__(self):
        super().__init__()
        self.text = []
        self.skip_content = False
        self.skip_tags = {"script", "style", "noscript", "iframe", "object", "embed"}

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_content = True

    def handle_endtag(self, tag):
        if tag in self.skip_tags:
            self.skip_content = False

    def handle_data(self, data):
        if not self.skip_content:
            self.text.append(data)

    def get_text(self) -> str:
        """Get the extracted text."""
        return "".join(self.text).strip()


def html_to_markdown(html: str) -> str:
    """
    Convert HTML to markdown (simplified).

    Args:
        html: HTML string.

    Returns:
        Markdown string.
    """
    # Simple HTML to markdown conversion
    # This is a basic implementation; for production use a library like markdownify or html2text

    # Remove script and style tags
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<meta[^>]*>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<link[^>]*/>', '', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert headings
    html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1\n\n', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1\n\n', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1\n\n', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1\n\n', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert bold
    html = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert italic
    html = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert code blocks
    html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<pre[^>]*>(.*?)</pre>', r'```\n\1\n```', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert links
    html = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert paragraphs
    html = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', html, flags=re.DOTALL | re.IGNORECASE)

    # Convert line breaks
    html = re.sub(r'<br[^>]*/>', r'\n', html, flags=re.DOTALL | re.IGNORECASE)

    # Remove remaining tags
    html = re.sub(r'<[^>]+>', '', html, flags=re.DOTALL)

    # Clean up whitespace
    html = re.sub(r'\n\s*\n\s*\n+', '\n\n', html)
    html = re.sub(r'[ \t]+', ' ', html)

    return html.strip()


class WebFetchParams(ToolInputSchema):
    """Parameters for the WebFetch tool."""

    url: str = Field(..., description="The URL to fetch content from")
    format: Literal["text", "markdown", "html"] = Field(
        "markdown",
        description="The format to return content in (text, markdown, or html). Defaults to markdown.",
    )
    timeout: Optional[int] = Field(
        None,
        description="Optional timeout in seconds (max 120)",
    )


class WebFetchTool(BaseTool):
    """
    Fetch web content with format conversion.

    Features:
    - HTTP/HTTPS support
    - Multiple output formats: text, markdown, html
    - Timeout support (max 120 seconds)
    - Content size limit (5MB)
    - HTML to markdown/text conversion

    Usage:
    - url (required): URL to fetch
    - format (optional): Output format - text, markdown, or html (default markdown)
    - timeout (optional): Timeout in seconds (max 120, default 30)
    """

    name = "webfetch"
    description = (
        "Fetch web content from a URL. Supports HTTP/HTTPS. "
        "Can return content as text, markdown, or html. "
        "HTML responses are automatically converted to markdown or text when requested. "
        "Has a 5MB content size limit and configurable timeout (max 120s)."
    )
    input_schema = WebFetchParams

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._default_timeout = self.config.get("default_timeout", DEFAULT_TIMEOUT)
        self._max_timeout = self.config.get("max_timeout", MAX_TIMEOUT)

    async def execute(self, params: Dict[str, Any]) -> ToolResult:
        """
        Fetch web content.

        Args:
            params: Dictionary containing 'url', optional 'format', and 'timeout'.

        Returns:
            ToolResult with fetched content.

        Raises:
            ToolError: If URL is invalid, request fails, or response is too large.
        """
        url = params["url"]
        output_format = params.get("format", "markdown")
        timeout = params.get("timeout", self._default_timeout)

        # Validate URL
        if not url.startswith(("http://", "https://")):
            raise ToolError("URL must start with http:// or https://")

        # Cap timeout
        timeout = min(timeout, self._max_timeout)

        try:
            result = await asyncio.wait_for(
                self._fetch_content(url, output_format, timeout),
                timeout=timeout,
            )
            return result
        except asyncio.TimeoutError:
            raise ToolError(f"Request timed out after {timeout} seconds")
        except Exception as e:
            raise ToolError(f"Failed to fetch URL: {e}")

    async def _fetch_content(
        self,
        url: str,
        output_format: str,
        timeout: int,
    ) -> ToolResult:
        """
        Fetch and process web content.

        Args:
            url: URL to fetch.
            output_format: Desired output format.
            timeout: Request timeout.

        Returns:
            ToolResult with processed content.
        """
        import aiohttp

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        # Set Accept header based on format
        if output_format == "markdown":
            headers["Accept"] = (
                "text/markdown;q=1.0, text/x-markdown;q=0.9, "
                "text/plain;q=0.8, text/html;q=0.7, */*;q=0.1"
            )
        elif output_format == "text":
            headers["Accept"] = (
                "text/plain;q=1.0, text/markdown;q=0.9, "
                "text/html;q=0.8, */*;q=0.1"
            )
        elif output_format == "html":
            headers["Accept"] = (
                "text/html;q=1.0, application/xhtml+xml;q=0.9, "
                "text/plain;q=0.8, text/markdown;q=0.7, */*;q=0.1"
            )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        raise ToolError(f"Request failed with status code: {response.status}")

                    # Check content length
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_RESPONSE_SIZE:
                        raise ToolError(f"Response too large (exceeds {MAX_RESPONSE_SIZE // (1024*1024)}MB limit)")

                    # Read content
                    content = await response.text()

                    # Check actual size
                    if len(content.encode("utf-8")) > MAX_RESPONSE_SIZE:
                        raise ToolError(f"Response too large (exceeds {MAX_RESPONSE_SIZE // (1024*1024)}MB limit)")

                    content_type = response.headers.get("Content-Type", "")

                    # Process content based on format and content type
                    if output_format == "markdown":
                        if "text/html" in content_type:
                            processed = html_to_markdown(content)
                        else:
                            processed = content
                    elif output_format == "text":
                        if "text/html" in content_type:
                            extractor = TextExtractor()
                            extractor.feed(content)
                            processed = extractor.get_text()
                        else:
                            processed = content
                    else:  # html
                        processed = content

                    return ToolResult(
                        content=processed,
                        metadata={"content_type": content_type},
                    )

            except aiohttp.ClientError as e:
                raise ToolError(f"Network error: {e}")

    @property
    def info(self) -> ToolInfo:
        """Return tool metadata."""
        parameters = {
            "url": {
                "type": "string",
                "description": "The URL to fetch content from",
            },
            "format": {
                "type": "string",
                "enum": ["text", "markdown", "html"],
                "description": "The format to return content in (text, markdown, or html)",
                "default": "markdown",
            },
            "timeout": {
                "type": "integer",
                "description": "Optional timeout in seconds (max 120)",
            },
        }

        return ToolInfo(
            name=self.name,
            description=self.description,
            parameters=parameters,
        )
