"""
Server State Management

AppState holds shared state for the FastAPI application:
- AgentManager for agent lifecycle management
- SessionManager for session storage
- Recipe file hash map for caching

Reference: goose-rs/crates/goose-server/src/state.rs
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from ..execution import AgentManager, SessionExecutionMode
from ..session import SessionManager

logger = logging.getLogger("goose.server.state")


@dataclass
class ServerConfig:
    """Server configuration"""
    host: str = "127.0.0.1"
    port: int = 8080
    debug: bool = False
    secret_key: str = ""
    workers: int = 1


@dataclass
class AppState:
    """
    Application state shared across all routes
    
    Attributes:
        agent_manager: Agent lifecycle manager
        session_manager: Session storage manager
        server_config: Server configuration
        recipe_file_hash_map: Cache of recipe file paths by hash
        extension_loading_tasks: Track background extension loading tasks
    """
    agent_manager: AgentManager
    session_manager: SessionManager
    server_config: ServerConfig = field(default_factory=ServerConfig)
    recipe_file_hash_map: Dict[str, Path] = field(default_factory=dict)
    extension_loading_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    _executor: ThreadPoolExecutor = field(default_factory=ThreadPoolExecutor)
    
    @classmethod
    async def create(
        cls,
        server_config: Optional[ServerConfig] = None
    ) -> "AppState":
        """
        Create a new AppState instance
        
        Args:
            server_config: Optional server configuration
            
        Returns:
            Initialized AppState
        """
        config = server_config or ServerConfig()
        
        agent_manager = AgentManager.get_instance()
        
        session_manager = SessionManager.get_instance()
        
        return cls(
            agent_manager=agent_manager,
            session_manager=session_manager,
            server_config=config,
        )
    
    async def get_agent(self, session_id: str) -> Any:
        """Get or create an agent for the given session"""
        return await self.agent_manager.get_or_create_agent(
            session_id=session_id,
            execution_mode=SessionExecutionMode.INTERACTIVE,
        )
    
    async def get_agent_for_route(self, session_id: str) -> Any:
        """
        Get agent for route, returning HTTP status on failure
        
        Args:
            session_id: Session ID
            
        Returns:
            Agent instance
            
        Raises:
            HTTPException: If agent cannot be retrieved
        """
        try:
            return await self.get_agent(session_id)
        except Exception as e:
            logger.error(f"Failed to get agent for session {session_id}: {e}")
            raise
    
    async def set_extension_loading_task(self, session_id: str, task: asyncio.Task) -> None:
        """Set a background extension loading task for a session"""
        self.extension_loading_tasks[session_id] = task
    
    async def take_extension_loading_task(self, session_id: str) -> Optional[Any]:
        """Get and remove a background extension loading task result"""
        task = self.extension_loading_tasks.pop(session_id, None)
        if task:
            return await task
        return None
    
    async def remove_extension_loading_task(self, session_id: str) -> None:
        """Remove a background extension loading task"""
        self.extension_loading_tasks.pop(session_id, None)
    
    def get_session_counter(self) -> int:
        """Get a new session counter value"""
        import time
        return int(time.time() * 1000) % 1000000
    
    async def close(self) -> None:
        """Clean up resources"""
        logger.info("Shutting down AppState...")
        
        for task in self.extension_loading_tasks.values():
            task.cancel()
        
        if self._executor:
            self._executor.shutdown(wait=False)
        
        logger.info("AppState shutdown complete")


def create_app_state(
    host: str = "127.0.0.1",
    port: int = 8080,
    debug: bool = False,
    secret_key: str = "",
) -> AppState:
    """
    Create and configure AppState
    
    Args:
        host: Server host
        port: Server port
        debug: Debug mode
        secret_key: API secret key
        
    Returns:
        Configured AppState
    """
    config = ServerConfig(
        host=host,
        port=port,
        debug=debug,
        secret_key=secret_key,
    )
    return AppState(
        agent_manager=AgentManager.get_instance(),
        session_manager=SessionManager.get_instance(),
        server_config=config,
    )
