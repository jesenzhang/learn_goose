"""
Todo Manager

Main service for managing todo items.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from pathlib import Path

from .models import (
    TodoItem,
    TodoCreate,
    TodoUpdate,
    TodoFilter,
    TodoStatus,
    TodoPriority,
    TodoListResponse,
    TodoStats,
)
from .storage import TodoStorage, InMemoryTodoStorage

logger = logging.getLogger("goose.todo.manager")


class TodoManager:
    """
    Todo Manager service.
    
    Provides CRUD operations and advanced todo management features.
    """
    
    def __init__(
        self,
        storage_path: Optional[str] = None,
        use_in_memory: bool = False,
    ):
        """
        Initialize todo manager.
        
        Args:
            storage_path: Path to storage file (default: ./data/todos.jsonl)
            use_in_memory: Use in-memory storage for testing
        """
        if use_in_memory:
            self._storage = InMemoryTodoStorage()
            logger.info("TodoManager initialized with in-memory storage")
        else:
            path = storage_path or str(Path("./data/todos.jsonl").absolute())
            self._storage = TodoStorage(path)
            logger.info(f"TodoManager initialized with storage: {path}")
    
    @property
    def storage(self) -> TodoStorage:
        """Get storage backend."""
        return self._storage
    
    def create_todo(self, todo_data: TodoCreate) -> TodoItem:
        """
        Create a new todo.
        
        Args:
            todo_data: Todo creation data
            
        Returns:
            Created todo item
        """
        todo = TodoItem(
            title=todo_data.title,
            description=todo_data.description,
            status=todo_data.status,
            priority=todo_data.priority,
            tags=todo_data.tags,
            due_date=todo_data.due_date,
            session_id=todo_data.session_id,
            metadata=todo_data.metadata,
        )
        return self._storage.create(todo)
    
    def get_todo(self, todo_id: str) -> Optional[TodoItem]:
        """
        Get a todo by ID.
        
        Args:
            todo_id: Todo ID
            
        Returns:
            Todo item or None
        """
        return self._storage.get(todo_id)
    
    def get_all_todos(self) -> List[TodoItem]:
        """
        Get all todos.
        
        Returns:
            List of all todos
        """
        return self._storage.get_all()
    
    def get_todos_by_status(self, status: TodoStatus) -> List[TodoItem]:
        """
        Get todos by status.
        
        Args:
            status: Todo status
            
        Returns:
            List of todos with the specified status
        """
        return self._storage.get_by_status(status)
    
    def get_todos_by_session(self, session_id: str) -> List[TodoItem]:
        """
        Get todos by session ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            List of todos for the session
        """
        return self._storage.get_by_session(session_id)
    
    def update_todo(self, todo_id: str, updates: TodoUpdate) -> Optional[TodoItem]:
        """
        Update a todo.
        
        Args:
            todo_id: Todo ID
            updates: Update data
            
        Returns:
            Updated todo or None
        """
        updates_dict = {}
        if updates.title is not None:
            updates_dict["title"] = updates.title
        if updates.description is not None:
            updates_dict["description"] = updates.description
        if updates.status is not None:
            updates_dict["status"] = updates.status
        if updates.priority is not None:
            updates_dict["priority"] = updates.priority
        if updates.tags is not None:
            updates_dict["tags"] = updates.tags
        if updates.due_date is not None:
            updates_dict["due_date"] = updates.due_date
        if updates.metadata is not None:
            updates_dict["metadata"] = updates.metadata
        
        return self._storage.update(todo_id, updates_dict)
    
    def delete_todo(self, todo_id: str) -> bool:
        """
        Delete a todo.
        
        Args:
            todo_id: Todo ID
            
        Returns:
            True if deleted, False if not found
        """
        return self._storage.delete(todo_id)
    
    def delete_todos_by_session(self, session_id: str) -> int:
        """
        Delete all todos for a session.
        
        Args:
            session_id: Session ID
            
        Returns:
            Number of deleted todos
        """
        return self._storage.delete_by_session(session_id)
    
    def clear_completed(self) -> int:
        """
        Clear all completed todos.
        
        Returns:
            Number of cleared todos
        """
        return self._storage.clear_completed()
    
    def search_todos(self, query: str) -> List[TodoItem]:
        """
        Search todos.
        
        Args:
            query: Search query
            
        Returns:
            List of matching todos
        """
        return self._storage.search(query)
    
    def filter_todos(self, filter_data: TodoFilter) -> List[TodoItem]:
        """
        Filter todos with multiple criteria.
        
        Args:
            filter_data: Filter criteria
            
        Returns:
            List of matching todos
        """
        todos = self._storage.get_all()
        
        if filter_data.status:
            todos = [t for t in todos if t.status == filter_data.status]
        
        if filter_data.priority:
            todos = [t for t in todos if t.priority == filter_data.priority]
        
        if filter_data.tags:
            todos = [t for t in todos if any(tag in t.tags for tag in filter_data.tags)]
        
        if filter_data.session_id:
            todos = [t for t in todos if t.session_id == filter_data.session_id]
        
        if filter_data.due_before:
            todos = [t for t in todos if t.due_date and t.due_date <= filter_data.due_before]
        
        if filter_data.due_after:
            todos = [t for t in todos if t.due_date and t.due_date >= filter_data.due_after]
        
        if filter_data.search:
            query = filter_data.search.lower()
            todos = [
                t for t in todos
                if query in t.title.lower() or query in t.description.lower()
            ]
        
        return todos
    
    def list_todos(
        self,
        status: Optional[TodoStatus] = None,
        priority: Optional[TodoPriority] = None,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None,
    ) -> TodoListResponse:
        """
        List todos with optional filters.
        
        Args:
            status: Filter by status
            priority: Filter by priority
            tags: Filter by tags
            session_id: Filter by session
            
        Returns:
            Todo list response with stats
        """
        todos = self._storage.get_all()
        
        if status:
            todos = [t for t in todos if t.status == status]
        if priority:
            todos = [t for t in todos if t.priority == priority]
        if tags:
            todos = [t for t in todos if any(tag in t.tags for tag in tags)]
        if session_id:
            todos = [t for t in todos if t.session_id == session_id]
        
        stats = TodoStats.from_todos(todos)
        
        return TodoListResponse(
            todos=todos,
            total=stats.total,
            pending=stats.pending,
            in_progress=stats.in_progress,
            completed=stats.completed,
            cancelled=stats.cancelled,
        )
    
    def get_stats(self) -> TodoStats:
        """
        Get todo statistics.
        
        Returns:
            Todo statistics
        """
        todos = self._storage.get_all()
        return TodoStats.from_todos(todos)
    
    def start_todo(self, todo_id: str) -> Optional[TodoItem]:
        """
        Start a todo (set status to in_progress).
        
        Args:
            todo_id: Todo ID
            
        Returns:
            Updated todo or None
        """
        return self._storage.update(todo_id, {"status": TodoStatus.IN_PROGRESS})
    
    def complete_todo(self, todo_id: str) -> Optional[TodoItem]:
        """
        Complete a todo.
        
        Args:
            todo_id: Todo ID
            
        Returns:
            Updated todo or None
        """
        now = datetime.utcnow()
        return self._storage.update(todo_id, {
            "status": TodoStatus.COMPLETED,
            "completed_at": now,
        })
    
    def cancel_todo(self, todo_id: str) -> Optional[TodoItem]:
        """
        Cancel a todo.
        
        Args:
            todo_id: Todo ID
            
        Returns:
            Updated todo or None
        """
        return self._storage.update(todo_id, {"status": TodoStatus.CANCELLED})
    
    def add_tag(self, todo_id: str, tag: str) -> Optional[TodoItem]:
        """
        Add a tag to a todo.
        
        Args:
            todo_id: Todo ID
            tag: Tag to add
            
        Returns:
            Updated todo or None
        """
        todo = self._storage.get(todo_id)
        if todo and tag not in todo.tags:
            todo.tags.append(tag)
            return self._storage.update(todo_id, {"tags": todo.tags})
        return todo
    
    def remove_tag(self, todo_id: str, tag: str) -> Optional[TodoItem]:
        """
        Remove a tag from a todo.
        
        Args:
            todo_id: Todo ID
            tag: Tag to remove
            
        Returns:
            Updated todo or None
        """
        todo = self._storage.get(todo_id)
        if todo and tag in todo.tags:
            todo.tags.remove(tag)
            return self._storage.update(todo_id, {"tags": todo.tags})
        return todo
    
    def set_priority(self, todo_id: str, priority: TodoPriority) -> Optional[TodoItem]:
        """
        Set todo priority.
        
        Args:
            todo_id: Todo ID
            priority: New priority
            
        Returns:
            Updated todo or None
        """
        return self._storage.update(todo_id, {"priority": priority})
    
    def set_due_date(self, todo_id: str, due_date: Optional[datetime]) -> Optional[TodoItem]:
        """
        Set todo due date.
        
        Args:
            todo_id: Todo ID
            due_date: Due date or None
            
        Returns:
            Updated todo or None
        """
        return self._storage.update(todo_id, {"due_date": due_date})
    
    def get_overdue(self) -> List[TodoItem]:
        """
        Get overdue todos.
        
        Returns:
            List of overdue todos
        """
        now = datetime.utcnow()
        todos = self._storage.get_all()
        return [
            t for t in todos
            if t.due_date and t.due_date < now
            and t.status not in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]
        ]
    
    def get_upcoming(self, days: int = 7) -> List[TodoItem]:
        """
        Get upcoming todos within specified days.
        
        Args:
            days: Number of days to look ahead
            
        Returns:
            List of upcoming todos
        """
        from datetime import timedelta
        
        now = datetime.utcnow()
        end = now + timedelta(days=days)
        
        todos = self._storage.get_all()
        return [
            t for t in todos
            if t.due_date and now <= t.due_date <= end
            and t.status not in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]
        ]
    
    def get_todos_with_tag(self, tag: str) -> List[TodoItem]:
        """
        Get todos with a specific tag.
        
        Args:
            tag: Tag to filter by
            
        Returns:
            List of todos with the tag
        """
        todos = self._storage.get_all()
        return [t for t in todos if tag in t.tags]
    
    def get_all_tags(self) -> List[str]:
        """
        Get all unique tags.
        
        Returns:
            List of unique tags
        """
        todos = self._storage.get_all()
        tags = set()
        for todo in todos:
            tags.update(todo.tags)
        return sorted(list(tags))
    
    def count(self) -> int:
        """Count total todos."""
        return self._storage.count()


class TodoManagerFactory:
    """Factory for creating TodoManager instances."""
    
    _default_manager: Optional[TodoManager] = None
    _managers: Dict[str, TodoManager] = {}
    
    @classmethod
    def get_default(cls, storage_path: Optional[str] = None) -> TodoManager:
        """Get or create default todo manager."""
        if cls._default_manager is None:
            cls._default_manager = TodoManager(storage_path)
        return cls._default_manager
    
    @classmethod
    def get_manager(cls, name: str, storage_path: Optional[str] = None) -> TodoManager:
        """Get or create named todo manager."""
        if name not in cls._managers:
            cls._managers[name] = TodoManager(storage_path)
        return cls._managers[name]
    
    @classmethod
    def reset_default(cls) -> None:
        """Reset default manager."""
        cls._default_manager = None
    
    @classmethod
    def reset_all(cls) -> None:
        """Reset all managers."""
        cls._default_manager = None
        cls._managers.clear()
