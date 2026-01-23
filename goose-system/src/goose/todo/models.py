"""
Todo Models

Data models for the Todo Extension.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
import uuid


class TodoStatus(str, Enum):
    """Todo status enumeration."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    """Todo priority enumeration."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TodoItem(BaseModel):
    """
    Todo item model.
    
    Attributes:
        id: Unique todo identifier
        title: Todo title
        description: Todo description
        status: Current status
        priority: Priority level
        tags: Tags for categorization
        due_date: Due date (optional)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        completed_at: Completion timestamp (optional)
        metadata: Additional metadata
        session_id: Associated session ID
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    tags: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    
    def model_dump(self, *args, **kwargs) -> Dict[str, Any]:
        """Custom dump to handle datetime serialization."""
        data = super().model_dump(*args, **kwargs)
        data["status"] = self.status.value if hasattr(self.status, "value") else self.status
        data["priority"] = self.priority.value if hasattr(self.priority, "value") else self.priority
        return data


class TodoCreate(BaseModel):
    """Model for creating a new todo."""
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    tags: List[str] = Field(default_factory=list)
    due_date: Optional[datetime] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TodoUpdate(BaseModel):
    """Model for updating a todo."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TodoStatus] = None
    priority: Optional[TodoPriority] = None
    tags: Optional[List[str]] = None
    due_date: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class TodoFilter(BaseModel):
    """Model for filtering todos."""
    status: Optional[TodoStatus] = None
    priority: Optional[TodoPriority] = None
    tags: Optional[List[str]] = None
    session_id: Optional[str] = None
    due_before: Optional[datetime] = None
    due_after: Optional[datetime] = None
    search: Optional[str] = None


class TodoListResponse(BaseModel):
    """Response model for todo list."""
    todos: List[TodoItem]
    total: int
    pending: int
    in_progress: int
    completed: int
    cancelled: int


class TodoStats(BaseModel):
    """Todo statistics."""
    total: int = 0
    pending: int = 0
    in_progress: int = 0
    completed: int = 0
    cancelled: int = 0
    overdue: int = 0
    completion_rate: float = 0.0
    
    @classmethod
    def from_todos(cls, todos: List[TodoItem]) -> "TodoStats":
        """Calculate stats from todo list."""
        now = datetime.utcnow()
        stats = cls()
        stats.total = len(todos)
        
        for todo in todos:
            status = todo.status.value if hasattr(todo.status, "value") else todo.status
            if status == TodoStatus.PENDING:
                stats.pending += 1
            elif status == TodoStatus.IN_PROGRESS:
                stats.in_progress += 1
            elif status == TodoStatus.COMPLETED:
                stats.completed += 1
            elif status == TodoStatus.CANCELLED:
                stats.cancelled += 1
            
            if todo.due_date and todo.due_date < now and status not in [TodoStatus.COMPLETED, TodoStatus.CANCELLED]:
                stats.overdue += 1
        
        total_active = stats.pending + stats.in_progress + stats.completed
        if total_active > 0:
            stats.completion_rate = round(stats.completed / total_active * 100, 2)
        
        return stats
