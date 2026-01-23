"""
Auto Visualiser Platform Extension

Provides visualization capabilities for data and code.

Reference: goose-rs/crates/goose-mcp/src/autovisualiser/mod.rs
"""

import json
from typing import Any, Dict, List, Optional

from ...session import SessionManager


class AutoVisualiserPlatformExtension:
    """Auto Visualiser Platform Extension"""

    EXTENSION_NAME = "auto_visualiser"

    def __init__(self, session_manager: Optional[SessionManager] = None):
        self.session_manager = session_manager
        self._initialized = False

    async def initialize(self) -> Dict[str, Any]:
        """Initialize the extension"""
        self._initialized = True

        return {
            "name": self.EXTENSION_NAME,
            "version": "1.0.0",
            "description": "Automatic visualization of data and code structures",
            "instructions": """This extension provides tools for automatic visualization.
Use it when you need to create visual representations of data or code structures.
Available tools help generate charts, diagrams, and other visualizations.""",
        }

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List available tools"""
        if not self._initialized:
            await self.initialize()

        return [
            {
                "name": "visualize_data",
                "description": "Create a visualization from data (JSON, CSV, or structured data)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "object", "description": "Data to visualize"},
                        "type": {"type": "string", "enum": ["bar", "line", "pie", "scatter", "table"], "description": "Chart type"},
                        "title": {"type": "string", "description": "Chart title"},
                    },
                    "required": ["data", "type"],
                }
            },
            {
                "name": "visualize_graph",
                "description": "Create a graph visualization from nodes and edges",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "nodes": {"type": "array", "description": "List of nodes"},
                        "edges": {"type": "array", "description": "List of edges (source, target)"},
                        "direction": {"type": "string", "enum": ["horizontal", "vertical", "radial"], "default": "horizontal"},
                    },
                    "required": ["nodes", "edges"],
                }
            },
        ]

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        if not self._initialized:
            await self.initialize()

        if name == "visualize_data":
            return self._visualize_data(arguments)
        elif name == "visualize_graph":
            return self._visualize_graph(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    def _visualize_data(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create data visualization"""
        data = args.get("data", {})
        viz_type = args.get("type", "table")
        title = args.get("title", "Data Visualization")

        if not data:
            return {"error": "Missing 'data' parameter"}

        if viz_type == "table":
            return {"content": [{"type": "text", "text": "## {title}\n\n```json\n{json_data}\n```".format(title=title, json_data=json.dumps(data, indent=2))}]}
        else:
            return {
                "content": [
                    {"type": "text", "text": "## {title}\n\nVisualization type: {viz_type}".format(title=title, viz_type=viz_type)},
                    {"type": "text", "text": "Data: {json_data}".format(json_data=json.dumps(data, indent=2))}
                ]
            }

    def _visualize_graph(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create graph visualization"""
        nodes = args.get("nodes", [])
        edges = args.get("edges", [])
        direction = args.get("direction", "horizontal")

        if not nodes or not edges:
            return {"error": "Missing 'nodes' or 'edges' parameter"}

        edge_strs = []
        for e in edges:
            edge_strs.append("{from_q}->{to_q}".format(from_q=e.get("from", "?"), to_q=e.get("to", "?")))

        return {
            "content": [
                {"type": "text", "text": "## Graph Visualization\n\nDirection: {direction}".format(direction=direction)},
                {"type": "text", "text": "Nodes ({count}): {nodes}".format(count=len(nodes), nodes=", ".join(str(n) for n in nodes))},
                {"type": "text", "text": "Edges ({count}): {edges}".format(count=len(edges), edges=", ".join(edge_strs))}
            ]
        }

    async def close(self) -> None:
        """Close extension"""
        self._initialized = False


def create_auto_visualiser_extension() -> AutoVisualiserPlatformExtension:
    """Create Auto Visualiser Platform Extension"""
    return AutoVisualiserPlatformExtension()
