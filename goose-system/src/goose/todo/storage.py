"""
Todo Storage

Persistence layer for Todo items.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from .models import TodoItem, TodoStatus, TodoPriority

logger = logging.getLogger("goose.todo.storage")


class TodoStorage:
    """
    Storage backend for Todo items.
    
    Supports both JSON file storage and SQLite storage.
    """
    
    def __init__(self, storage_path: str = "./data/todos.jsonl"):
        """Initialize todo storage."""
        self.storage_path = Path(storage_path)
        self._ensure_storage_dir()
    
    def _ensure_storage_dir(self) -> None:
        """Ensure storage directory exists."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_all(self) -> List[Dict[str, Any]]:
        """Load all todos from storage."""
        if not self.storage_path.exists():
            return []
        
        todos = []
        with open(self.storage_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        todos.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse todo: {e}")
        return todos
    
    def _save_all(self, todos: List[Dict[str, Any]]) -> None:
        """Save all todos to storage."""
        with open(self.storage_path, 'w', encoding='utf-8') as f:
            for todo in todos:
                f.write(json.dumps(todo, ensure_ascii=False) + '\n')
    
    def _deserialize_todo(self, data: Dict[str, Any]) -> TodoItem:
        """Deserialize a todo from dict."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = TodoStatus(data["status"])
        if "priority" in data and isinstance(data["priority"], str):
            data["priority"] = TodoPriority(data["priority"])
        if "created_at" in data and isinstance(data["created_at"], str):
            data["created_at"] = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data and isinstance(data["updated_at"], str):
            data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        if "completed_at" in data and data["completed_at"] and isinstance(data["completed_at"], str):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])
        if "due_date" in data and data["due_date"] and isinstance(data["due_date"], str):
            data["due_date"] = datetime.fromisoformat(data["due_date"])
        return TodoItem(**data)
    
    def _serialize_todo(self, todo: TodoItem) -> Dict[str, Any]:
        """Serialize a todo to dict."""
        data = todo.model_dump()
        data["status"] = todo.status.value
        data["priority"] = todo.priority.value
        data["created_at"] = todo.created_at.isoformat()
        data["updated_at"] = todo.updated_at.isoformat()
        if todo.completed_at:
            data["completed_at"] = todo.completed_at.isoformat()
        if todo.due_date:
            data["due_date"] = todo.due_date.isoformat()
        return data
    
    def get(self, todo_id: str) -> Optional[TodoItem]:
        """Get a todo by ID."""
        todos = self._load_all()
        for data in todos:
            if data.get("id") == todo_id:
                return self._deserialize_todo(data)
        return None
    
    def get_all(self) -> List[TodoItem]:
        """Get all todos."""
        return [self._deserialize_todo(data) for data in self._load_all()]
    
    def get_by_status(self, status: TodoStatus) -> List[TodoItem]:
        """Get todos by status."""
        todos = self._load_all()
        return [
            self._deserialize_todo(data) for data in todos
            if data.get("status") == status.value
        ]
    
    def get_by_session(self, session_id: str) -> List[TodoItem]:
        """Get todos by session ID."""
        todos = self._load_all()
        return [
            self._deserialize_todo(data) for data in todos
            if data.get("session_id") == session_id
        ]
    
    def create(self, todo: TodoItem) -> TodoItem:
        """Create a new todo."""
        todos = self._load_all()
        todos.append(self._serialize_todo(todo))
        self._save_all(todos)
        logger.info(f"Created todo: {todo.id}")
        return todo
    
    def update(self, todo_id: str, updates: Dict[str, Any]) -> Optional[TodoItem]:
        """Update a todo."""
        todos = self._load_all()
        for i, data in enumerate(todos):
            if data.get("id") == todo_id:
                todo = self._deserialize_todo(data)
                
                if "title" in updates:
                    todo.title = updates["title"]
                if "description" in updates:
                    todo.description = updates["description"]
                if "status" in updates:
                    todo.status = updates["status"]
                    if updates["status"] == TodoStatus.COMPLETED:
                        todo.completed_at = datetime.utcnow()
                if "priority" in updates:
                    todo.priority = updates["priority"]
                if "tags" in updates:
                    todo.tags = updates["tags"]
                if "due_date" in updates:
                    todo.due_date = updates["due_date"]
                if "metadata" in updates:
                    todo.metadata.update(updates["metadata"])
                
                todo.updated_at = datetime.utcnow()
                todos[i] = self._serialize_todo(todo)
                self._save_all(todos)
                logger.info(f"Updated todo: {todo_id}")
                return todo
        return None
    
    def delete(self, todo_id: str) -> bool:
        """Delete a todo."""
        todos = self._load_all()
        original_count = len(todos)
        todos = [data for data in todos if data.get("id") != todo_id]
        
        if len(todos) < original_count:
            self._save_all(todos)
            logger.info(f"Deleted todo: {todo_id}")
            return True
        return False
    
    def delete_by_session(self, session_id: str) -> int:
        """Delete all todos for a session."""
        todos = self._load_all()
        original_count = len(todos)
        todos = [data for data in todos if data.get("session_id") != session_id]
        
        deleted_count = original_count - len(todos)
        if deleted_count > 0:
            self._save_all(todos)
            logger.info(f"Deleted {deleted_count} todos for session: {session_id}")
        return deleted_count
    
    def clear_completed(self) -> int:
        """Clear all completed todos."""
        todos = self._load_all()
        original_count = len(todos)
        todos = [data for data in todos if data.get("status") != TodoStatus.COMPLETED.value]
        
        cleared_count = original_count - len(todos)
        if cleared_count > 0:
            self._save_all(todos)
            logger.info(f"Cleared {cleared_count} completed todos")
        return cleared_count
    
    def search(self, query: str) -> List[TodoItem]:
        """Search todos by title or description."""
        todos = self._load_all()
        query_lower = query.lower()
        return [
            self._deserialize_todo(data) for data in todos
            if query_lower in data.get("title", "").lower()
            or query_lower in data.get("description", "").lower()
            or any(query_lower in tag.lower() for tag in data.get("tags", []))
        ]
    
    def count(self) -> int:
        """Count total todos."""
        return len(self._load_all())


class InMemoryTodoStorage(TodoStorage):
    """
    In-memory todo storage for testing.
    """
    
    def __init__(self):
        """Initialize in-memory storage."""
        self._todos: List[Dict[str, Any]] = []
        super().__init__("/dev/null")
    
    def _load_all(self) -> List[Dict[str, Any]]:
        """Load all todos from memory."""
        return self._todos
    
    def _save_all(self, todos: List[Dict[str, Any]]) -> None:
        """Save all todos to memory."""
        self._todos = todos
