"""
Todo Extension - Test Suite

Tests for the Todo Extension.
"""

import sys
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest
from goose.todo import (
    TodoItem,
    TodoCreate,
    TodoUpdate,
    TodoFilter,
    TodoStatus,
    TodoPriority,
    TodoListResponse,
    TodoStats,
    TodoManager,
    TodoManagerFactory,
    TodoStorage,
    InMemoryTodoStorage,
    create_todo_manager,
    get_default_todo_manager,
)


class TestTodoModels:
    """Tests for Todo models."""

    def test_todo_item_default_values(self):
        """Test default values for TodoItem."""
        todo = TodoItem(title="Test Todo")
        
        assert todo.title == "Test Todo"
        assert todo.description == ""
        assert todo.status == TodoStatus.PENDING
        assert todo.priority == TodoPriority.MEDIUM
        assert todo.tags == []
        assert todo.due_date is None
        assert todo.completed_at is None
        assert todo.metadata == {}
        assert todo.session_id is None
        assert todo.id is not None

    def test_todo_item_with_all_fields(self):
        """Test TodoItem with all fields."""
        due_date = datetime.utcnow() + timedelta(days=7)
        todo = TodoItem(
            title="Full Todo",
            description="Description",
            status=TodoStatus.IN_PROGRESS,
            priority=TodoPriority.HIGH,
            tags=["work", "urgent"],
            due_date=due_date,
            session_id="session-123",
            metadata={"project": "goose"},
        )
        
        assert todo.title == "Full Todo"
        assert todo.status == TodoStatus.IN_PROGRESS
        assert todo.priority == TodoPriority.HIGH
        assert len(todo.tags) == 2
        assert todo.due_date == due_date
        assert todo.session_id == "session-123"

    def test_todo_create(self):
        """Test TodoCreate model."""
        data = TodoCreate(
            title="New Todo",
            description="Test description",
            priority=TodoPriority.URGENT,
            tags=["important"],
        )
        
        assert data.title == "New Todo"
        assert data.description == "Test description"
        assert data.priority == TodoPriority.URGENT
        assert data.tags == ["important"]

    def test_todo_update(self):
        """Test TodoUpdate model."""
        update = TodoUpdate(
            title="Updated Title",
            status=TodoStatus.COMPLETED,
            priority=TodoPriority.LOW,
        )
        
        assert update.title == "Updated Title"
        assert update.status == TodoStatus.COMPLETED
        assert update.priority == TodoPriority.LOW
        assert update.description is None
        assert update.tags is None

    def test_todo_status_values(self):
        """Test TodoStatus enum values."""
        assert TodoStatus.PENDING.value == "pending"
        assert TodoStatus.IN_PROGRESS.value == "in_progress"
        assert TodoStatus.COMPLETED.value == "completed"
        assert TodoStatus.CANCELLED.value == "cancelled"

    def test_todo_priority_values(self):
        """Test TodoPriority enum values."""
        assert TodoPriority.LOW.value == "low"
        assert TodoPriority.MEDIUM.value == "medium"
        assert TodoPriority.HIGH.value == "high"
        assert TodoPriority.URGENT.value == "urgent"

    def test_todo_stats_from_todos(self):
        """Test TodoStats.from_todos method."""
        todos = [
            TodoItem(title="Pending 1", status=TodoStatus.PENDING),
            TodoItem(title="Pending 2", status=TodoStatus.PENDING),
            TodoItem(title="In Progress", status=TodoStatus.IN_PROGRESS),
            TodoItem(title="Completed", status=TodoStatus.COMPLETED),
            TodoItem(title="Cancelled", status=TodoStatus.CANCELLED),
        ]
        
        stats = TodoStats.from_todos(todos)
        
        assert stats.total == 5
        assert stats.pending == 2
        assert stats.in_progress == 1
        assert stats.completed == 1
        assert stats.cancelled == 1
        assert stats.completion_rate == 25.0  # 1/4 * 100 (excludes cancelled)

    def test_todo_stats_overdue(self):
        """Test TodoStats calculates overdue correctly."""
        now = datetime.utcnow()
        todos = [
            TodoItem(
                title="Overdue",
                status=TodoStatus.PENDING,
                due_date=now - timedelta(days=1),
            ),
            TodoItem(
                title="Not Overdue",
                status=TodoStatus.PENDING,
                due_date=now + timedelta(days=1),
            ),
            TodoItem(
                title="Completed Overdue",
                status=TodoStatus.COMPLETED,
                due_date=now - timedelta(days=1),
            ),
        ]
        
        stats = TodoStats.from_todos(todos)
        
        assert stats.overdue == 1  # Only the pending overdue one


class TestTodoStorage:
    """Tests for TodoStorage."""

    def test_in_memory_storage_basic_operations(self):
        """Test basic CRUD operations with in-memory storage."""
        storage = InMemoryTodoStorage()
        
        todo = TodoItem(title="Test Todo")
        
        created = storage.create(todo)
        assert created.id == todo.id
        
        retrieved = storage.get(todo.id)
        assert retrieved is not None
        assert retrieved.title == "Test Todo"
        
        all_todos = storage.get_all()
        assert len(all_todos) == 1
        
        updated = storage.update(todo.id, {"title": "Updated Title"})
        assert updated is not None
        assert updated.title == "Updated Title"
        
        deleted = storage.delete(todo.id)
        assert deleted is True
        
        retrieved = storage.get(todo.id)
        assert retrieved is None

    def test_in_memory_storage_get_by_status(self):
        """Test filtering by status."""
        storage = InMemoryTodoStorage()
        
        pending = TodoItem(title="Pending", status=TodoStatus.PENDING)
        in_progress = TodoItem(title="In Progress", status=TodoStatus.IN_PROGRESS)
        completed = TodoItem(title="Completed", status=TodoStatus.COMPLETED)
        
        storage.create(pending)
        storage.create(in_progress)
        storage.create(completed)
        
        pending_todos = storage.get_by_status(TodoStatus.PENDING)
        assert len(pending_todos) == 1
        assert pending_todos[0].title == "Pending"

    def test_in_memory_storage_get_by_session(self):
        """Test filtering by session."""
        storage = InMemoryTodoStorage()
        
        todo1 = TodoItem(title="Session 1", session_id="session-1")
        todo2 = TodoItem(title="Session 1 - 2", session_id="session-1")
        todo3 = TodoItem(title="Session 2", session_id="session-2")
        
        storage.create(todo1)
        storage.create(todo2)
        storage.create(todo3)
        
        session1_todos = storage.get_by_session("session-1")
        assert len(session1_todos) == 2
        
        session2_todos = storage.get_by_session("session-2")
        assert len(session2_todos) == 1

    def test_in_memory_storage_search(self):
        """Test search functionality."""
        storage = InMemoryTodoStorage()
        
        storage.create(TodoItem(title="Python task", description="Write code"))
        storage.create(TodoItem(title="JavaScript task", description="Frontend"))
        storage.create(TodoItem(title="Another Python task"))
        
        results = storage.search("Python")
        assert len(results) == 2
        
        results = storage.search("Write code")
        assert len(results) == 1

    def test_in_memory_storage_clear_completed(self):
        """Test clearing completed todos."""
        storage = InMemoryTodoStorage()
        
        storage.create(TodoItem(title="Keep 1", status=TodoStatus.PENDING))
        storage.create(TodoItem(title="Keep 2", status=TodoStatus.IN_PROGRESS))
        storage.create(TodoItem(title="Remove", status=TodoStatus.COMPLETED))
        
        count = storage.clear_completed()
        assert count == 1
        
        all_todos = storage.get_all()
        assert len(all_todos) == 2

    def test_file_storage_basic_operations(self):
        """Test file-based storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage_path = os.path.join(tmpdir, "todos.jsonl")
            storage = TodoStorage(storage_path)
            
            todo = TodoItem(title="File Storage Test")
            created = storage.create(todo)
            
            assert storage.get(created.id) is not None
            assert storage.count() == 1


class TestTodoManager:
    """Tests for TodoManager."""

    def test_create_todo(self):
        """Test creating a todo."""
        manager = TodoManager(use_in_memory=True)
        
        todo_data = TodoCreate(
            title="New Todo",
            description="Test description",
            priority=TodoPriority.HIGH,
        )
        
        todo = manager.create_todo(todo_data)
        
        assert todo is not None
        assert todo.title == "New Todo"
        assert todo.description == "Test description"
        assert todo.priority == TodoPriority.HIGH
        assert todo.status == TodoStatus.PENDING

    def test_get_todo(self):
        """Test getting a todo by ID."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Test Todo"))
        retrieved = manager.get_todo(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_todo_not_found(self):
        """Test getting a non-existent todo."""
        manager = TodoManager(use_in_memory=True)
        
        todo = manager.get_todo("non-existent-id")
        
        assert todo is None

    def test_get_all_todos(self):
        """Test getting all todos."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Todo 1"))
        manager.create_todo(TodoCreate(title="Todo 2"))
        manager.create_todo(TodoCreate(title="Todo 3"))
        
        todos = manager.get_all_todos()
        
        assert len(todos) == 3

    def test_update_todo(self):
        """Test updating a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Original"))
        updated = manager.update_todo(
            created.id,
            TodoUpdate(title="Updated", status=TodoStatus.COMPLETED)
        )
        
        assert updated is not None
        assert updated.title == "Updated"
        assert updated.status == TodoStatus.COMPLETED
        assert updated.completed_at is not None

    def test_delete_todo(self):
        """Test deleting a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="To Delete"))
        
        deleted = manager.delete_todo(created.id)
        assert deleted is True
        
        todo = manager.get_todo(created.id)
        assert todo is None

    def test_start_todo(self):
        """Test starting a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Start Me"))
        started = manager.start_todo(created.id)
        
        assert started is not None
        assert started.status == TodoStatus.IN_PROGRESS

    def test_complete_todo(self):
        """Test completing a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Complete Me"))
        completed = manager.complete_todo(created.id)
        
        assert completed is not None
        assert completed.status == TodoStatus.COMPLETED
        assert completed.completed_at is not None

    def test_cancel_todo(self):
        """Test cancelling a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Cancel Me"))
        cancelled = manager.cancel_todo(created.id)
        
        assert cancelled is not None
        assert cancelled.status == TodoStatus.CANCELLED

    def test_add_tag(self):
        """Test adding a tag to a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Tag Me"))
        tagged = manager.add_tag(created.id, "important")
        
        assert tagged is not None
        assert "important" in tagged.tags

    def test_remove_tag(self):
        """Test removing a tag from a todo."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(
            TodoCreate(title="Tag Me", tags=["old", "new"])
        )
        untagged = manager.remove_tag(created.id, "old")
        
        assert untagged is not None
        assert "old" not in untagged.tags
        assert "new" in untagged.tags

    def test_set_priority(self):
        """Test setting todo priority."""
        manager = TodoManager(use_in_memory=True)
        
        created = manager.create_todo(TodoCreate(title="Priority Me"))
        prioritized = manager.set_priority(created.id, TodoPriority.URGENT)
        
        assert prioritized is not None
        assert prioritized.priority == TodoPriority.URGENT

    def test_set_due_date(self):
        """Test setting todo due date."""
        manager = TodoManager(use_in_memory=True)
        
        due_date = datetime.utcnow() + timedelta(days=3)
        created = manager.create_todo(TodoCreate(title="Due Me"))
        dated = manager.set_due_date(created.id, due_date)
        
        assert dated is not None
        assert dated.due_date == due_date

    def test_get_overdue(self):
        """Test getting overdue todos."""
        manager = TodoManager(use_in_memory=True)
        
        now = datetime.utcnow()
        manager.create_todo(TodoCreate(
            title="Overdue",
            status=TodoStatus.PENDING,
            due_date=now - timedelta(days=1),
        ))
        manager.create_todo(TodoCreate(
            title="Not Overdue",
            status=TodoStatus.PENDING,
            due_date=now + timedelta(days=1),
        ))
        manager.create_todo(TodoCreate(
            title="Completed",
            status=TodoStatus.COMPLETED,
            due_date=now - timedelta(days=1),
        ))
        
        overdue = manager.get_overdue()
        
        assert len(overdue) == 1
        assert overdue[0].title == "Overdue"

    def test_get_upcoming(self):
        """Test getting upcoming todos."""
        manager = TodoManager(use_in_memory=True)
        
        now = datetime.utcnow()
        manager.create_todo(TodoCreate(
            title="Upcoming",
            status=TodoStatus.PENDING,
            due_date=now + timedelta(days=2),
        ))
        manager.create_todo(TodoCreate(
            title="Far Future",
            status=TodoStatus.PENDING,
            due_date=now + timedelta(days=10),
        ))
        
        upcoming = manager.get_upcoming(days=7)
        
        assert len(upcoming) == 1
        assert upcoming[0].title == "Upcoming"

    def test_get_todos_with_tag(self):
        """Test getting todos with a specific tag."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Has Tag", tags=["work"]))
        manager.create_todo(TodoCreate(title="No Tag"))
        manager.create_todo(TodoCreate(title="Has Tag Too", tags=["work", "personal"]))
        
        tagged = manager.get_todos_with_tag("work")
        
        assert len(tagged) == 2

    def test_get_all_tags(self):
        """Test getting all unique tags."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="T1", tags=["work", "urgent"]))
        manager.create_todo(TodoCreate(title="T2", tags=["work"]))
        manager.create_todo(TodoCreate(title="T3", tags=["personal"]))
        
        tags = manager.get_all_tags()
        
        assert len(tags) == 3
        assert "work" in tags
        assert "urgent" in tags
        assert "personal" in tags

    def test_get_stats(self):
        """Test getting todo statistics."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Pending", status=TodoStatus.PENDING))
        manager.create_todo(TodoCreate(title="In Progress", status=TodoStatus.IN_PROGRESS))
        manager.create_todo(TodoCreate(title="Completed", status=TodoStatus.COMPLETED))
        
        stats = manager.get_stats()
        
        assert stats.total == 3
        assert stats.pending == 1
        assert stats.in_progress == 1
        assert stats.completed == 1

    def test_list_todos(self):
        """Test listing todos with filters."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(
            title="High Priority",
            status=TodoStatus.PENDING,
            priority=TodoPriority.HIGH,
        ))
        manager.create_todo(TodoCreate(
            title="Low Priority",
            status=TodoStatus.PENDING,
            priority=TodoPriority.LOW,
        ))
        
        response = manager.list_todos(priority=TodoPriority.HIGH)
        
        assert response.total == 1
        assert response.todos[0].title == "High Priority"

    def test_search_todos(self):
        """Test searching todos."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Python task"))
        manager.create_todo(TodoCreate(title="JavaScript task"))
        manager.create_todo(TodoCreate(title="Python web app"))
        
        results = manager.search_todos("Python")
        
        assert len(results) == 2

    def test_filter_todos(self):
        """Test filtering todos with multiple criteria."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(
            title="Filterable",
            status=TodoStatus.PENDING,
            priority=TodoPriority.HIGH,
            tags=["work"],
        ))
        manager.create_todo(TodoCreate(
            title="Not Filterable",
            status=TodoStatus.COMPLETED,
            priority=TodoPriority.HIGH,
            tags=["work"],
        ))
        
        filter_data = TodoFilter(
            status=TodoStatus.PENDING,
            priority=TodoPriority.HIGH,
            tags=["work"],
        )
        
        todos = manager.filter_todos(filter_data)
        
        assert len(todos) == 1
        assert todos[0].title == "Filterable"

    def test_delete_todos_by_session(self):
        """Test deleting todos by session."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Session 1", session_id="s1"))
        manager.create_todo(TodoCreate(title="Session 1 - 2", session_id="s1"))
        manager.create_todo(TodoCreate(title="Session 2", session_id="s2"))
        
        count = manager.delete_todos_by_session("s1")
        
        assert count == 2
        assert manager.count() == 1

    def test_clear_completed(self):
        """Test clearing completed todos."""
        manager = TodoManager(use_in_memory=True)
        
        manager.create_todo(TodoCreate(title="Keep", status=TodoStatus.PENDING))
        manager.create_todo(TodoCreate(title="Remove", status=TodoStatus.COMPLETED))
        
        count = manager.clear_completed()
        
        assert count == 1
        assert manager.count() == 1


class TestTodoManagerFactory:
    """Tests for TodoManagerFactory."""

    def test_get_default_manager(self):
        """Test getting default manager."""
        TodoManagerFactory.reset_default()
        
        manager1 = TodoManagerFactory.get_default()
        manager2 = TodoManagerFactory.get_default()
        
        assert manager1 is manager2

    def test_reset_default(self):
        """Test resetting default manager."""
        manager1 = TodoManagerFactory.get_default()
        TodoManagerFactory.reset_default()
        manager2 = TodoManagerFactory.get_default()
        
        assert manager1 is not manager2

    def test_get_named_manager(self):
        """Test getting named managers."""
        TodoManagerFactory.reset_all()
        
        manager1 = TodoManagerFactory.get_manager("work")
        manager2 = TodoManagerFactory.get_manager("personal")
        manager3 = TodoManagerFactory.get_manager("work")
        
        assert manager1 is manager3
        assert manager1 is not manager2


class TestTodoIntegration:
    """Integration tests for Todo Extension."""

    def test_full_todo_workflow(self):
        """Test a complete todo workflow."""
        manager = TodoManager(use_in_memory=True)
        
        todo = manager.create_todo(TodoCreate(
            title="Learn Goose-System",
            description="Study the codebase and write tests",
            priority=TodoPriority.HIGH,
            tags=["learning", "goose"],
        ))
        
        assert todo.id is not None
        
        todo = manager.start_todo(todo.id)
        assert todo.status == TodoStatus.IN_PROGRESS
        
        todo = manager.add_tag(todo.id, "python")
        assert "python" in todo.tags
        
        todo = manager.set_due_date(todo.id, datetime.utcnow() + timedelta(days=7))
        assert todo.due_date is not None
        
        todo = manager.complete_todo(todo.id)
        assert todo.status == TodoStatus.COMPLETED
        assert todo.completed_at is not None
        
        stats = manager.get_stats()
        assert stats.completed == 1
        assert stats.completion_rate == 100.0


def run_all_tests():
    """Run all tests."""
    pytest.main([__file__, "-v"])


if __name__ == "__main__":
    run_all_tests()
