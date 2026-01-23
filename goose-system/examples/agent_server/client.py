"""
Example Agent Client

This example demonstrates how to interact with the Goose Agent API
using Python with requests library.

Features:
- API key authentication
- Session management
- Tool calling
- Recipe management

Usage:
    python client.py --server-url http://localhost:8080 --secret-key your-secret-key

Requirements:
    pip install requests
"""

import argparse
import json
import sys
from typing import Dict, Any, Optional
from pathlib import Path

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    print("requests not installed. Install with: pip install requests")


class GooseAgentClient:
    """Client for Goose Agent API"""
    
    def __init__(self, base_url: str, secret_key: str = ""):
        """
        Initialize client
        
        Args:
            base_url: Server base URL (e.g., http://localhost:8080)
            secret_key: API secret key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.secret_key = secret_key
        self.session = requests.Session() if REQUESTS_AVAILABLE else None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication"""
        headers = {
            "Content-Type": "application/json",
        }
        if self.secret_key:
            headers["X-Secret-Key"] = self.secret_key
        return headers
    
    def _request(self, method: str, path: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request"""
        if not REQUESTS_AVAILABLE or not self.session:
            raise RuntimeError("requests library not available")
        
        url = f"{self.base_url}{path}"
        response = self.session.request(
            method=method,
            url=url,
            headers=self._get_headers(),
            json=data,
            timeout=30,
        )
        
        if not response.ok:
            try:
                error = response.json()
            except:
                error = {"error": response.text}
            raise RuntimeError(f"API error: {error}")
        
        return response.json()
    
    def health_check(self) -> Dict[str, Any]:
        """Check server health"""
        return self._request("GET", "/health")
    
    def get_version(self) -> Dict[str, Any]:
        """Get server version"""
        return self._request("GET", "/version")
    
    def list_sessions(self) -> Dict[str, Any]:
        """List all sessions"""
        return self._request("GET", "/api/v1/sessions")
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Get session by ID"""
        return self._request("GET", f"/api/v1/sessions/{session_id}")
    
    def create_session(self, working_dir: str, name: str = None) -> Dict[str, Any]:
        """Create a new session"""
        data = {"working_dir": working_dir}
        if name:
            data["name"] = name
        return self._request("POST", "/api/v1/sessions", data)
    
    def delete_session(self, session_id: str) -> Dict[str, Any]:
        """Delete a session"""
        return self._request("DELETE", f"/api/v1/sessions/{session_id}")
    
    def start_agent(self, working_dir: str = None, recipe_id: str = None) -> Dict[str, Any]:
        """Start a new agent session"""
        data = {}
        if working_dir:
            data["working_dir"] = working_dir
        if recipe_id:
            data["recipe_id"] = recipe_id
        return self._request("POST", "/api/v1/agent/start", data)
    
    def call_tool(
        self,
        session_id: str,
        tool_name: str,
        arguments: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Call a tool on an agent session"""
        data = {
            "session_id": session_id,
            "name": tool_name,
            "arguments": arguments or {},
        }
        return self._request("POST", "/api/v1/agent/call_tool", data)
    
    def list_recipes(self) -> Dict[str, Any]:
        """List all recipes"""
        return self._request("GET", "/api/v1/recipes")
    
    def get_recipe(self, recipe_id: str) -> Dict[str, Any]:
        """Get recipe by ID"""
        return self._request("GET", f"/api/v1/recipes/{recipe_id}")
    
    def save_recipe(self, recipe: Dict[str, Any]) -> Dict[str, Any]:
        """Save a recipe"""
        return self._request("POST", "/api/v1/recipes", recipe)
    
    def get_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self._request("GET", "/api/v1/config")


async def demo(client: GooseAgentClient):
    """Run demo interactions"""
    print("\n" + "=" * 60)
    print("Goose Agent API Demo")
    print("=" * 60)
    
    print("\n1. Health Check")
    print("-" * 40)
    health = client.health_check()
    print(f"Status: {health.get('status')}")
    print(f"Timestamp: {health.get('timestamp')}")
    
    print("\n2. Server Version")
    print("-" * 40)
    version = client.get_version()
    print(f"Name: {version.get('name')}")
    print(f"Version: {version.get('version')}")
    
    print("\n3. List Sessions")
    print("-" * 40)
    sessions = client.list_sessions()
    print(f"Session count: {len(sessions.get('sessions', []))}")
    
    print("\n4. Create Session")
    print("-" * 40)
    new_session = client.create_session(
        working_dir=str(Path.cwd()),
        name="Demo Session"
    )
    session_id = new_session.get('session', {}).get('id')
    print(f"Session ID: {session_id}")
    
    print("\n5. Get Session Details")
    print("-" * 40)
    session = client.get_session(session_id)
    print(f"Name: {session.get('session', {}).get('name')}")
    print(f"Created: {session.get('session', {}).get('created_at')}")
    
    print("\n6. List Recipes")
    print("-" * 40)
    recipes = client.list_recipes()
    recipe_count = len(recipes.get('recipes', []))
    print(f"Recipe count: {recipe_count}")
    
    if recipe_count > 0:
        print("Available recipes:")
        for r in recipes.get('recipes', []):
            print(f"  - {r.get('id')}: {r.get('title')}")
    
    print("\n7. Start Agent")
    print("-" * 40)
    agent = client.start_agent(working_dir=str(Path.cwd()))
    agent_session_id = agent.get('session', {}).get('id')
    print(f"Agent session: {agent_session_id}")
    
    print("\n8. Call Tool (read_file)")
    print("-" * 40)
    tool_result = client.call_tool(
        session_id=agent_session_id,
        tool_name="read_file",
        arguments={"path": "README.md"}
    )
    print(f"Tool result: {json.dumps(tool_result, indent=2)[:200]}...")
    
    print("\n9. Delete Sessions")
    print("-" * 40)
    client.delete_session(session_id)
    print(f"Deleted session: {session_id}")
    
    if agent_session_id:
        client.delete_session(agent_session_id)
        print(f"Deleted agent session: {agent_session_id}")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Goose Agent API Client")
    parser.add_argument("--server-url", type=str, default="http://localhost:8080", help="Server URL")
    parser.add_argument("--secret-key", type=str, default="", help="API secret key")
    parser.add_argument("--demo", action="store_true", help="Run demo interactions")
    parser.add_argument("--health", action="store_true", help="Check health")
    parser.add_argument("--sessions", action="store_true", help="List sessions")
    parser.add_argument("--recipes", action="store_true", help="List recipes")
    parser.add_argument("--start-agent", action="store_true", help="Start agent")
    
    args = parser.parse_args()
    
    if not REQUESTS_AVAILABLE:
        print("Error: requests library not available")
        print("Install with: pip install requests")
        sys.exit(1)
    
    client = GooseAgentClient(args.server_url, args.secret_key)
    
    if args.health:
        print(json.dumps(client.health_check(), indent=2))
    
    elif args.sessions:
        print(json.dumps(client.list_sessions(), indent=2))
    
    elif args.recipes:
        print(json.dumps(client.list_recipes(), indent=2))
    
    elif args.start_agent:
        print(json.dumps(client.start_agent(working_dir=str(Path.cwd())), indent=2))
    
    elif args.demo:
        import asyncio
        asyncio.run(demo(client))
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
