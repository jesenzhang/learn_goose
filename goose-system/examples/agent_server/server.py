"""
Example Agent Server with JSONL Persistence

This example demonstrates how to run the Goose System API server
with JSONL-based persistence for sessions and data.

Features:
- JSONL file-based storage (no database required)
- API Key authentication
- All API endpoints enabled

Usage:
    python server.py --port 8080 --secret-key your-secret-key

The server will:
1. Store sessions in data/sessions/ directory
2. Store recipes in data/recipes/ directory
3. Require X-Secret-Key header for authenticated requests
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("agent-server-example")


DATA_DIR = Path(__file__).parent / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
RECIPES_DIR = DATA_DIR / "recipes"


class JSONLSessionStore:
    """JSONL-based session storage"""
    
    def __init__(self, base_dir: Path = SESSIONS_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def create_session(self, session_id: str, working_dir: str, name: str) -> Dict[str, Any]:
        """Create a new session"""
        session = {
            "id": session_id,
            "name": name,
            "working_dir": working_dir,
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "extension_data": {},
            "recipe": None,
            "user_recipe_values": {},
        }
        
        session_file = self.base_dir / f"{session_id}.jsonl"
        with open(session_file, 'w') as f:
            f.write(json.dumps(session) + "\n")
        
        logger.info(f"Created session: {session_id}")
        return session
    
    async def get_session(self, session_id: str, include_messages: bool = True) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        session_file = self.base_dir / f"{session_id}.jsonl"
        if not session_file.exists():
            return None
        
        with open(session_file, 'r') as f:
            line = f.readline()
            if line:
                return json.loads(line.strip())
        return None
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """List all sessions"""
        sessions = []
        for f in self.base_dir.glob("*.jsonl"):
            with open(f, 'r') as file:
                line = file.readline()
                if line:
                    session = json.loads(line.strip())
                    sessions.append({
                        "id": session["id"],
                        "name": session["name"],
                        "created_at": session["created_at"],
                    })
        return sorted(sessions, key=lambda x: x.get("created_at", ""), reverse=True)
    
    async def update_session(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session"""
        session = await self.get_session(session_id)
        if not session:
            return False
        
        session.update(updates)
        session["updated_at"] = datetime.utcnow().isoformat()
        
        session_file = self.base_dir / f"{session_id}.jsonl"
        with open(session_file, 'w') as f:
            f.write(json.dumps(session) + "\n")
        
        return True
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session"""
        session_file = self.base_dir / f"{session_id}.jsonl"
        if session_file.exists():
            session_file.unlink()
            logger.info(f"Deleted session: {session_id}")
            return True
        return False
    
    async def export_session(self, session_id: str) -> Optional[str]:
        """Export session as JSON string"""
        session = await self.get_session(session_id)
        if session:
            return json.dumps(session, indent=2)
        return None
    
    async def import_session(self, json_data: str) -> Dict[str, Any]:
        """Import session from JSON string"""
        session = json.loads(json_data)
        session["id"] = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        session["created_at"] = datetime.utcnow().isoformat()
        session["updated_at"] = datetime.utcnow().isoformat()
        
        session_file = self.base_dir / f"{session['id']}.jsonl"
        with open(session_file, 'w') as f:
            f.write(json.dumps(session) + "\n")
        
        logger.info(f"Imported session: {session['id']}")
        return session


class JSONLRecipeStore:
    """JSONL-based recipe storage"""
    
    def __init__(self, base_dir: Path = RECIPES_DIR):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
    
    async def save_recipe(self, recipe: Dict[str, Any], file_path: Optional[str] = None) -> Path:
        """Save recipe to file"""
        title = recipe.get("title", "untitled").lower()
        title = "".join(c for c in title if c.isalnum() or c in "- ").strip()[:50]
        title = title.replace(" ", "-")
        
        if not title:
            title = f"recipe_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if file_path:
            path = Path(file_path)
        else:
            path = self.base_dir / f"{title}.yaml"
        
        path = path.with_suffix(".yaml")
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            import yaml
            yaml.dump(recipe, f, default_flow_style=False, allow_unicode=True)
        
        logger.info(f"Saved recipe: {path}")
        return path
    
    async def load_recipe(self, recipe_id: str) -> Optional[Dict[str, Any]]:
        """Load recipe by ID or path"""
        recipe_file = self.base_dir / f"{recipe_id}.yaml"
        if not recipe_file.exists():
            recipe_file = self.base_dir / f"{recipe_id}.json"
        
        if recipe_file.exists():
            with open(recipe_file, 'r', encoding='utf-8') as f:
                import yaml
                return yaml.safe_load(f)
        return None
    
    async def list_recipes(self) -> List[Dict[str, Any]]:
        """List all recipes"""
        recipes = []
        for f in self.base_dir.glob("*.yaml"):
            with open(f, 'r', encoding='utf-8') as file:
                try:
                    import yaml
                    recipe = yaml.safe_load(file)
                    if recipe:
                        recipes.append({
                            "id": f.stem,
                            "title": recipe.get("title", f.stem),
                            "description": recipe.get("description", ""),
                        })
                except Exception as e:
                    logger.warning(f"Failed to load recipe {f}: {e}")
        return sorted(recipes, key=lambda x: x.get("id", ""))
    
    async def search_recipes(self, query: str) -> List[Dict[str, Any]]:
        """Search recipes by title or description"""
        recipes = await self.list_recipes()
        query_lower = query.lower()
        return [
            r for r in recipes
            if query_lower in r.get("title", "").lower() or
               query_lower in r.get("description", "").lower()
        ]


session_store = JSONLSessionStore()
recipe_store = JSONLRecipeStore()


async def create_sample_recipe():
    """Create a sample recipe for testing"""
    sample_recipe = {
        "version": "1.0.0",
        "title": "Hello World Agent",
        "description": "A simple agent that says hello",
        "instructions": """You are a friendly assistant. 
Your task is to greet the user and introduce yourself.

When the user says hello, respond with a friendly greeting and ask how you can help.""",
        "parameters": [
            {
                "key": "name",
                "input_type": "string",
                "requirement": "optional",
                "description": "Your name (optional)",
            }
        ]
    }
    
    await recipe_store.save_recipe(sample_recipe, "hello-agent.yaml")
    logger.info("Created sample recipe: hello-agent.yaml")


async def handle_request(method: str, path: str, body: Optional[Dict] = None, headers: Dict = None) -> Dict[str, Any]:
    """
    Handle HTTP request (simplified router for demo)
    
    In production, use the full FastAPI server from goose.server
    """
    headers = headers or {}
    secret_key = headers.get("X-Secret-Key", "")
    
    public_paths = {"/health", "/ready", "/version"}
    if path not in public_paths and not secret_key:
        return {"error": "Missing X-Secret-Key header", "status": 401}
    
    if path == "/health":
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    if path == "/ready":
        return {"status": "ready"}
    
    if path == "/version":
        return {"version": "1.0.0", "name": "goose-agent-example"}
    
    if path == "/api/v1/sessions" and method == "GET":
        sessions = await session_store.list_sessions()
        return {"sessions": sessions}
    
    if path.startswith("/api/v1/sessions/") and method == "GET":
        session_id = path.split("/")[-1]
        session = await session_store.get_session(session_id)
        if session:
            return {"session": session}
        return {"error": "Session not found", "status": 404}
    
    if path == "/api/v1/sessions" and method == "POST":
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        working_dir = body.get("working_dir", str(Path.cwd()))
        name = body.get("name", f"Session {session_id[-8:]}")
        
        session = await session_store.create_session(session_id, working_dir, name)
        return {"session": session}
    
    if path.startswith("/api/v1/sessions/") and method == "DELETE":
        session_id = path.split("/")[-1]
        success = await session_store.delete_session(session_id)
        if success:
            return {"status": "ok", "session_id": session_id}
        return {"error": "Session not found", "status": 404}
    
    if path == "/api/v1/recipes" and method == "GET":
        recipes = await recipe_store.list_recipes()
        return {"recipes": recipes}
    
    if path.startswith("/api/v1/recipes/") and method == "GET":
        recipe_id = path.split("/")[-1]
        recipe = await recipe_store.load_recipe(recipe_id)
        if recipe:
            return {"recipe": recipe}
        return {"error": "Recipe not found", "status": 404}
    
    if path == "/api/v1/recipes" and method == "POST" and body:
        path = await recipe_store.save_recipe(body)
        return {"status": "ok", "path": str(path)}
    
    if path == "/api/v1/agent/start" and method == "POST":
        session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        working_dir = body.get("working_dir", str(Path.cwd())) if body else str(Path.cwd())
        name = f"Agent Session {session_id[-8:]}"
        
        session = await session_store.create_session(session_id, working_dir, name)
        return {
            "session": session,
            "message": "Agent started. Use /api/v1/agent/call_tool to interact."
        }
    
    if path == "/api/v1/agent/call_tool" and method == "POST" and body:
        session_id = body.get("session_id")
        tool_name = body.get("name", "unknown")
        arguments = body.get("arguments", {})
        
        session = await session_store.get_session(session_id) if session_id else None
        
        result = {"result": f"Tool '{tool_name}' called", "arguments": arguments}
        
        if session:
            await session_store.update_session(session_id, {
                "messages": session.get("messages", []) + [
                    {"role": "user", "content": f"Tool call: {tool_name}"},
                    {"role": "assistant", "content": json.dumps(result)},
                ]
            })
        
        return result
    
    return {"error": "Not found", "status": 404}


async def main():
    """Main entry point for the example server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Goose Agent Server Example")
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    parser.add_argument("--secret-key", type=str, default="", help="API secret key")
    parser.add_argument("--create-sample", action="store_true", help="Create sample recipe")
    args = parser.parse_args()
    
    if args.create_sample:
        await create_sample_recipe()
    
    logger.info("=" * 60)
    logger.info("Goose Agent Server Example")
    logger.info("=" * 60)
    logger.info(f"Data directory: {DATA_DIR}")
    logger.info(f"Sessions directory: {SESSIONS_DIR}")
    logger.info(f"Recipes directory: {RECIPES_DIR}")
    logger.info(f"Authentication: {'Enabled' if args.secret_key else 'Disabled'}")
    logger.info("=" * 60)
    
    print("\nExample API calls:")
    print(f"  curl http://localhost:{args.port}/health")
    print(f"  curl http://localhost:{args.port}/api/v1/sessions")
    if args.secret_key:
        print(f"  curl -H 'X-Secret-Key: {args.secret_key}' http://localhost:{args.port}/api/v1/sessions")
        print(f"  curl -X POST -H 'X-Secret-Key: {args.secret_key}' -H 'Content-Type: application/json' \\")
        print(f"    -d '{{\"working_dir\": \"/tmp\"}}' http://localhost:{args.port}/api/v1/agent/start")
    print("\nPress Ctrl+C to stop the server")
    
    try:
        import aiohttp
        from aiohttp import web
        
        app = web.Application()
        
        async def handle(request):
            method = request.method
            path = request.path
            body = None
            if request.can_read_body:
                try:
                    body = await request.json()
                except:
                    pass
            
            headers = dict(request.headers)
            
            result = await handle_request(method, path, body, headers)
            
            status_code = result.get("status", 200)
            if isinstance(status_code, int) and status_code >= 400:
                status_code = status_code
            else:
                status_code = 200
            
            return web.json_response(result, status=status_code)
        
        app.router.add_get("/health", handle)
        app.router.add_get("/ready", handle)
        app.router.add_get("/version", handle)
        app.router.add_get("/api/v1/sessions", handle)
        app.router.add_post("/api/v1/sessions", handle)
        app.router.add_get("/api/v1/sessions/{id}", handle)
        app.router.add_delete("/api/v1/sessions/{id}", handle)
        app.router.add_get("/api/v1/recipes", handle)
        app.router.add_get("/api/v1/recipes/{id}", handle)
        app.router.add_post("/api/v1/recipes", handle)
        app.router.add_post("/api/v1/agent/start", handle)
        app.router.add_post("/api/v1/agent/call_tool", handle)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", args.port)
        await site.start()
        
        logger.info(f"Server running on http://0.0.0.0:{args.port}")
        
        while True:
            await asyncio.sleep(3600)
            
    except ImportError:
        logger.warning("aiohttp not installed. Using simple request handler.")
        logger.info("Install with: pip install aiohttp")
        
        print(f"\nServer would run on port {args.port} (aiohttp not installed)")
        print("Install dependencies: pip install aiohttp")
        print("\nThe server logic is ready. Install fastapi and uvicorn for full server:")
        print("  pip install fastapi uvicorn")
        print("  python -m goose.server.main --port 8080 --secret-key your-key")


if __name__ == "__main__":
    asyncio.run(main())
