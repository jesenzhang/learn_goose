import threading
from typing import Optional, Any
from .manager import DatabaseManager
from skill_micro_agent.core.state import AgentState

# Global Singleton
_db_instance: Optional[DatabaseManager] = None
_db_lock = threading.Lock()

def get_db(db_path: str = "agent_ultra.db") -> DatabaseManager:
    """Get or create global database instance."""
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = DatabaseManager(db_path)
                _db_instance.initialize()
    return _db_instance

def db_ops(op: str, db_path: str = "agent_ultra.db", **kwargs) -> Any:
    """
    Legacy wrapper for backward compatibility.
    """
    db = get_db(db_path)
    
    # Session Ops
    if op == "save":
        return db.save_state(kwargs.get('state'))
    elif op == "load":
        res = db.load_state(kwargs.get('id'))
        return res if res else AgentState(session_id=kwargs.get('id'))
    elif op == "list_sessions":
        return db.list_sessions()
    elif op == "clear_history":
        return db.delete_session(kwargs.get('id'))
        
    # Memory Ops
    elif op == "get_memories":
        return db.get_memories(kwargs.get('uid'), limit=kwargs.get('limit', 100))
    elif op == "search_memories":
        return db.search_memories(kwargs.get('uid'), kwargs.get('query'), limit=kwargs.get('limit', 20))
    elif op == "add_memory":
        return db.add_memory(kwargs.get('uid'), kwargs.get('content'))
    elif op == "delete_memory":
        return db.delete_memory(kwargs.get('memory_id'))
        
    return None