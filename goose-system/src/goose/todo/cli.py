"""
Todo CLI Commands

Command-line interface for todo management.
"""

import sys
import json
from datetime import datetime
from typing import Optional, List

from .models import TodoStatus, TodoPriority, TodoCreate, TodoUpdate, TodoFilter
from .manager import TodoManager, TodoManagerFactory


def format_todo(todo, index: Optional[int] = None) -> str:
    """Format a todo for display."""
    status_icons = {
        TodoStatus.PENDING: "[ ]",
        TodoStatus.IN_PROGRESS: "[~]",
        TodoStatus.COMPLETED: "[X]",
        TodoStatus.CANCELLED: "[-]",
    }
    
    priority_marks = {
        TodoPriority.LOW: "L",
        TodoPriority.MEDIUM: "M",
        TodoPriority.HIGH: "H",
        TodoPriority.URGENT: "U",
    }
    
    status_icon = status_icons.get(todo.status, "[ ]")
    priority_mark = priority_marks.get(todo.priority, "")
    
    index_str = f"{index}. " if index is not None else ""
    due_str = f" (due: {todo.due_date.strftime('%Y-%m-%d')})" if todo.due_date else ""
    tags_str = f" #{', '.join(todo.tags)}" if todo.tags else ""
    
    return f"{index_str}{status_icon} {priority_mark} {todo.title}{due_str}{tags_str}"


def format_todo_detail(todo) -> str:
    """Format a todo with full details."""
    status_icons = {
        TodoStatus.PENDING: "Pending",
        TodoStatus.IN_PROGRESS: "In Progress",
        TodoStatus.COMPLETED: "Completed",
        TodoStatus.CANCELLED: "Cancelled",
    }
    
    lines = [
        f"ID: {todo.id}",
        f"Title: {todo.title}",
        f"Description: {todo.description or '(none)'}",
        f"Status: {status_icons.get(todo.status, 'Unknown')}",
        f"Priority: {todo.priority.value.capitalize()}",
        f"Tags: {', '.join(todo.tags) if todo.tags else '(none)'}",
        f"Created: {todo.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Updated: {todo.updated_at.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    
    if todo.due_date:
        lines.append(f"Due: {todo.due_date.strftime('%Y-%m-%d %H:%M:%S')}")
    if todo.completed_at:
        lines.append(f"Completed: {todo.completed_at.strftime('%Y-%m-%d %H:%M:%S')}")
    if todo.session_id:
        lines.append(f"Session: {todo.session_id}")
    
    return "\n".join(lines)


def cmd_add(args) -> int:
    """Add a new todo."""
    manager = TodoManagerFactory.get_default()
    
    priority = TodoPriority(args.priority) if args.priority else TodoPriority.MEDIUM
    tags = args.tags.split(",") if args.tags else []
    due_date = None
    if args.due:
        try:
            due_date = datetime.strptime(args.due, "%Y-%m-%d")
        except ValueError:
            print(f"Error: Invalid due date format. Use YYYY-MM-DD")
            return 1
    
    todo_data = TodoCreate(
        title=args.title,
        description=args.description or "",
        priority=priority,
        tags=tags,
        due_date=due_date,
        session_id=args.session,
    )
    
    todo = manager.create_todo(todo_data)
    print(f"Created todo: {todo.id}")
    print(format_todo(todo))
    return 0


def cmd_list(args) -> int:
    """List todos."""
    manager = TodoManagerFactory.get_default()
    
    status = None
    if args.status:
        try:
            status = TodoStatus(args.status)
        except ValueError:
            print(f"Error: Invalid status '{args.status}'. Valid values: pending, in_progress, completed, cancelled")
            return 1
    
    priority = None
    if args.priority:
        try:
            priority = TodoPriority(args.priority)
        except ValueError:
            print(f"Error: Invalid priority '{args.priority}'. Valid values: low, medium, high, urgent")
            return 1
    
    response = manager.list_todos(
        status=status,
        priority=priority,
        tags=args.tags.split(",") if args.tags else None,
        session_id=args.session,
    )
    
    print(f"\nTotal: {response.total} | Pending: {response.pending} | In Progress: {response.in_progress} | Completed: {response.completed} | Cancelled: {response.cancelled}\n")
    
    if not response.todos:
        print("No todos found.")
        return 0
    
    for i, todo in enumerate(response.todos):
        print(format_todo(todo, i + 1))
    
    return 0


def cmd_show(args) -> int:
    """Show todo details."""
    manager = TodoManagerFactory.get_default()
    
    todo = manager.get_todo(args.id)
    if not todo:
        print(f"Error: Todo not found: {args.id}")
        return 1
    
    print(format_todo_detail(todo))
    return 0


def cmd_update(args) -> int:
    """Update a todo."""
    manager = TodoManagerFactory.get_default()
    
    updates = {}
    if args.title is not None:
        updates["title"] = args.title
    if args.description is not None:
        updates["description"] = args.description
    if args.status is not None:
        try:
            updates["status"] = TodoStatus(args.status)
        except ValueError:
            print(f"Error: Invalid status '{args.status}'")
            return 1
    if args.priority is not None:
        try:
            updates["priority"] = TodoPriority(args.priority)
        except ValueError:
            print(f"Error: Invalid priority '{args.priority}'")
            return 1
    if args.tags is not None:
        updates["tags"] = args.tags.split(",")
    
    if not updates:
        print("Error: No updates specified")
        return 1
    
    todo = manager.update_todo(args.id, TodoUpdate(**updates))
    if not todo:
        print(f"Error: Todo not found: {args.id}")
        return 1
    
    print("Updated todo:")
    print(format_todo_detail(todo))
    return 0


def cmd_delete(args) -> int:
    """Delete a todo."""
    manager = TodoManagerFactory.get_default()
    
    if manager.delete_todo(args.id):
        print(f"Deleted todo: {args.id}")
        return 0
    else:
        print(f"Error: Todo not found: {args.id}")
        return 1


def cmd_start(args) -> int:
    """Start a todo."""
    manager = TodoManagerFactory.get_default()
    
    todo = manager.start_todo(args.id)
    if not todo:
        print(f"Error: Todo not found: {args.id}")
        return 1
    
    print("Started todo:")
    print(format_todo(todo))
    return 0


def cmd_complete(args) -> int:
    """Complete a todo."""
    manager = TodoManagerFactory.get_default()
    
    todo = manager.complete_todo(args.id)
    if not todo:
        print(f"Error: Todo not found: {args.id}")
        return 1
    
    print("Completed todo:")
    print(format_todo(todo))
    return 0


def cmd_cancel(args) -> int:
    """Cancel a todo."""
    manager = TodoManagerFactory.get_default()
    
    todo = manager.cancel_todo(args.id)
    if not todo:
        print(f"Error: Todo not found: {args.id}")
        return 1
    
    print("Cancelled todo:")
    print(format_todo(todo))
    return 0


def cmd_stats(args) -> int:
    """Show todo statistics."""
    manager = TodoManagerFactory.get_default()
    
    stats = manager.get_stats()
    
    print("\nTodo Statistics")
    print("=" * 40)
    print(f"Total:      {stats.total}")
    print(f"Pending:    {stats.pending}")
    print(f"In Progress: {stats.in_progress}")
    print(f"Completed:  {stats.completed}")
    print(f"Cancelled:  {stats.cancelled}")
    print(f"Overdue:    {stats.overdue}")
    print(f"\nCompletion Rate: {stats.completion_rate}%")
    return 0


def cmd_search(args) -> int:
    """Search todos."""
    manager = TodoManagerFactory.get_default()
    
    todos = manager.search_todos(args.query)
    
    if not todos:
        print(f"No todos found matching '{args.query}'")
        return 0
    
    print(f"Found {len(todos)} todos matching '{args.query}':\n")
    for i, todo in enumerate(todos):
        print(format_todo(todo, i + 1))
    
    return 0


def cmd_overdue(args) -> int:
    """Show overdue todos."""
    manager = TodoManagerFactory.get_default()
    
    todos = manager.get_overdue()
    
    if not todos:
        print("No overdue todos.")
        return 0
    
    print(f"Overdue todos ({len(todos)}):\n")
    for i, todo in enumerate(todos):
        print(format_todo(todo, i + 1))
    
    return 0


def cmd_upcoming(args) -> int:
    """Show upcoming todos."""
    manager = TodoManagerFactory.get_default()
    
    days = args.days or 7
    todos = manager.get_upcoming(days)
    
    if not todos:
        print(f"No upcoming todos in the next {days} days.")
        return 0
    
    print(f"Upcoming todos ({len(todos)}) in next {days} days:\n")
    for i, todo in enumerate(todos):
        print(format_todo(todo, i + 1))
    
    return 0


def cmd_clear_completed(args) -> int:
    """Clear completed todos."""
    manager = TodoManagerFactory.get_default()
    
    count = manager.clear_completed()
    print(f"Cleared {count} completed todos.")
    return 0


def cmd_tags(args) -> int:
    """List all tags."""
    manager = TodoManagerFactory.get_default()
    
    tags = manager.get_all_tags()
    
    if not tags:
        print("No tags found.")
        return 0
    
    print(f"All tags ({len(tags)}):")
    for tag in tags:
        count = len(manager.get_todos_with_tag(tag))
        print(f"  #{tag} ({count})")
    
    return 0


def cmd_export(args) -> int:
    """Export todos to JSON."""
    manager = TodoManagerFactory.get_default()
    
    todos = manager.get_all_todos()
    data = [todo.model_dump() for todo in todos]
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"Exported {len(todos)} todos to {args.output}")
    return 0


def cmd_import(args) -> int:
    """Import todos from JSON."""
    manager = TodoManagerFactory.get_default()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    count = 0
    for item in data:
        todo = manager.create_todo(TodoCreate(**item))
        count += 1
    
    print(f"Imported {count} todos from {args.input}")
    return 0


def create_parser():
    """Create argument parser."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Todo Manager")
    parser.add_argument("--storage", "-s", help="Storage path")
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    add_parser = subparsers.add_parser("add", help="Add a new todo")
    add_parser.add_argument("title", help="Todo title")
    add_parser.add_argument("--description", "-d", help="Todo description")
    add_parser.add_argument("--priority", "-p", choices=["low", "medium", "high", "urgent"], help="Priority")
    add_parser.add_argument("--tags", "-t", help="Tags (comma-separated)")
    add_parser.add_argument("--due", help="Due date (YYYY-MM-DD)")
    add_parser.add_argument("--session", help="Session ID")
    
    list_parser = subparsers.add_parser("list", help="List todos")
    list_parser.add_argument("--status", choices=["pending", "in_progress", "completed", "cancelled"], help="Filter by status")
    list_parser.add_argument("--priority", choices=["low", "medium", "high", "urgent"], help="Filter by priority")
    list_parser.add_argument("--tags", "-t", help="Filter by tags (comma-separated)")
    list_parser.add_argument("--session", help="Filter by session ID")
    
    show_parser = subparsers.add_parser("show", help="Show todo details")
    show_parser.add_argument("id", help="Todo ID")
    
    update_parser = subparsers.add_parser("update", help="Update a todo")
    update_parser.add_argument("id", help="Todo ID")
    update_parser.add_argument("--title", help="New title")
    update_parser.add_argument("--description", "-d", help="New description")
    update_parser.add_argument("--status", choices=["pending", "in_progress", "completed", "cancelled"], help="New status")
    update_parser.add_argument("--priority", "-p", choices=["low", "medium", "high", "urgent"], help="New priority")
    update_parser.add_argument("--tags", "-t", help="New tags (comma-separated)")
    
    delete_parser = subparsers.add_parser("delete", help="Delete a todo")
    delete_parser.add_argument("id", help="Todo ID")
    
    subparsers.add_parser("start", help="Start a todo").add_argument("id", help="Todo ID")
    
    complete_parser = subparsers.add_parser("complete", help="Complete a todo")
    complete_parser.add_argument("id", help="Todo ID")
    
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a todo")
    cancel_parser.add_argument("id", help="Todo ID")
    
    subparsers.add_parser("stats", help="Show statistics")
    
    search_parser = subparsers.add_parser("search", help="Search todos")
    search_parser.add_argument("query", help="Search query")
    
    subparsers.add_parser("overdue", help="Show overdue todos")
    
    upcoming_parser = subparsers.add_parser("upcoming", help="Show upcoming todos")
    upcoming_parser.add_argument("--days", type=int, default=7, help="Number of days (default: 7)")
    
    subparsers.add_parser("clear-completed", help="Clear completed todos")
    
    subparsers.add_parser("tags", help="List all tags")
    
    export_parser = subparsers.add_parser("export", help="Export todos to JSON")
    export_parser.add_argument("output", help="Output file path")
    
    import_parser = subparsers.add_parser("import", help="Import todos from JSON")
    import_parser.add_argument("input", help="Input file path")
    
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)
    
    if args.command is None:
        parser.print_help()
        return 1
    
    storage_path = getattr(args, "storage", None)
    TodoManagerFactory.get_default(storage_path)
    
    command_map = {
        "add": cmd_add,
        "list": cmd_list,
        "show": cmd_show,
        "update": cmd_update,
        "delete": cmd_delete,
        "start": cmd_start,
        "complete": cmd_complete,
        "cancel": cmd_cancel,
        "stats": cmd_stats,
        "search": cmd_search,
        "overdue": cmd_overdue,
        "upcoming": cmd_upcoming,
        "clear-completed": cmd_clear_completed,
        "tags": cmd_tags,
        "export": cmd_export,
        "import": cmd_import,
    }
    
    cmd_func = command_map.get(args.command)
    if cmd_func:
        return cmd_func(args)
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
