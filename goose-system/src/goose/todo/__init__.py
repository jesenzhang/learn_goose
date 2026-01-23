"""
Todo Extension

Task management extension for Goose-System.

Features:
- Create, update, delete, and list todos
- Status tracking (pending, in_progress, completed, cancelled)
- Priority levels (low, medium, high, urgent)
- Tags and categories
- Due dates
- Session-based todo management
- Search and filtering
- Statistics
"""

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
from .manager import TodoManager, TodoManagerFactory
from .cli import main as run_cli

__version__ = "0.1.0"

__all__ = [
    "TodoItem",
    "TodoCreate",
    "TodoUpdate",
    "TodoFilter",
    "TodoStatus",
    "TodoPriority",
    "TodoListResponse",
    "TodoStats",
    "TodoStorage",
    "InMemoryTodoStorage",
    "TodoManager",
    "TodoManagerFactory",
    "run_cli",
]


def create_todo_manager(storage_path: str = "./data/todos.jsonl") -> TodoManager:
    """
    Create a new todo manager.
    
    Args:
        storage_path: Path to storage file
        
    Returns:
        TodoManager instance
    """
    return TodoManager(storage_path)


def get_default_todo_manager() -> TodoManager:
    """Get or create the default todo manager."""
    return TodoManagerFactory.get_default()
