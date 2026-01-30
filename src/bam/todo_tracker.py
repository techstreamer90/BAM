"""
BAM Todo Tracker

Manages developer tasks, cleanup items, features, and project work.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict

from .common import Todo, TodoType, TodoPriority, TodoStatus


class TodoTracker:
    """Manages the todo lifecycle."""

    def __init__(self, todo_path: str = "todo.json"):
        self._todo_path = Path(todo_path)
        self.todos_data = self._load_todos()

    def _load_todos(self) -> dict:
        with open(self._todo_path, 'r') as f:
            return json.load(f)

    def _save_todos(self):
        with open(self._todo_path, 'w') as f:
            json.dump(self.todos_data, f, indent=2)

    def create_todo(self, todo: Todo) -> str:
        """Create a new todo item."""
        self.todos_data["lastTodoId"] += 1
        todo.id = f"todo-{self.todos_data['lastTodoId']:04d}"

        self.todos_data["todos"].append(asdict(todo))
        self._save_todos()

        return todo.id

    def get_todo(self, todo_id: str) -> Optional[dict]:
        """Get a todo by ID."""
        for todo in self.todos_data["todos"]:
            if todo["id"] == todo_id:
                return todo
        return None

    def update_todo(self, todo_id: str, updates: dict) -> bool:
        """Update a todo item."""
        for i, todo in enumerate(self.todos_data["todos"]):
            if todo["id"] == todo_id:
                for key, value in updates.items():
                    if key in todo:
                        todo[key] = value
                todo["updated_at"] = datetime.utcnow().isoformat()
                self.todos_data["todos"][i] = todo
                self._save_todos()
                return True
        return False

    def complete_todo(self, todo_id: str, resolution: Optional[str] = None) -> bool:
        """Mark a todo as completed."""
        updates = {
            "status": TodoStatus.COMPLETED.value,
            "completed_at": datetime.utcnow().isoformat()
        }
        if resolution:
            updates["description"] = resolution
        return self.update_todo(todo_id, updates)

    def get_open_todos(self) -> List[dict]:
        """Get all non-completed todos."""
        return [t for t in self.todos_data["todos"]
                if t["status"] in [TodoStatus.OPEN.value, TodoStatus.IN_PROGRESS.value]]

    def get_todos_by_type(self, todo_type: str) -> List[dict]:
        """Get todos filtered by type."""
        return [t for t in self.todos_data["todos"]
                if t["type"] == todo_type]

    def get_todos_by_priority(self, priority: str) -> List[dict]:
        """Get todos filtered by priority."""
        return [t for t in self.todos_data["todos"]
                if t["priority"] == priority]

    def get_statistics(self) -> dict:
        """Get todo statistics."""
        todos = self.todos_data["todos"]

        by_status = {}
        by_type = {}
        by_priority = {}

        for todo in todos:
            status = todo["status"]
            todo_type = todo["type"]
            priority = todo["priority"]

            by_status[status] = by_status.get(status, 0) + 1
            by_type[todo_type] = by_type.get(todo_type, 0) + 1
            by_priority[priority] = by_priority.get(priority, 0) + 1

        return {
            "total": len(todos),
            "byStatus": by_status,
            "byType": by_type,
            "byPriority": by_priority
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Todo Tracker")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create command
    create_parser = subparsers.add_parser("create", help="Create a todo")
    create_parser.add_argument("title", help="Todo title")
    create_parser.add_argument("--type", "-t", dest="todo_type",
                               choices=[t.value for t in TodoType],
                               default=TodoType.TASK.value, help="Todo type")
    create_parser.add_argument("--priority", "-p",
                               choices=[p.value for p in TodoPriority],
                               default=TodoPriority.MEDIUM.value, help="Priority level")
    create_parser.add_argument("--description", "-d", default="", help="Detailed description")
    create_parser.add_argument("--tags", nargs="+", default=[], help="Tags")
    create_parser.add_argument("--files", nargs="+", default=[], help="Related files")

    # List command
    list_parser = subparsers.add_parser("list", help="List todos")
    list_parser.add_argument("--status", "-s", help="Filter by status")
    list_parser.add_argument("--type", "-t", dest="todo_type", help="Filter by type")
    list_parser.add_argument("--priority", "-p", help="Filter by priority")
    list_parser.add_argument("--tag", help="Filter by tag")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show todo details")
    show_parser.add_argument("todo_id", help="Todo ID")

    # Update command
    update_parser = subparsers.add_parser("update", help="Update a todo")
    update_parser.add_argument("todo_id", help="Todo ID")
    update_parser.add_argument("--status", "-s",
                               choices=[s.value for s in TodoStatus],
                               help="New status")
    update_parser.add_argument("--priority", "-p",
                               choices=[p.value for p in TodoPriority],
                               help="New priority")
    update_parser.add_argument("--assign", help="Assign to someone")

    # Complete command
    complete_parser = subparsers.add_parser("complete", help="Mark todo as completed")
    complete_parser.add_argument("todo_id", help="Todo ID")
    complete_parser.add_argument("--resolution", "-r", help="Resolution note")

    # Stats command
    subparsers.add_parser("stats", help="Show todo statistics")

    args = parser.parse_args()

    tracker = TodoTracker()

    if args.command == "create":
        todo = Todo(
            title=args.title,
            type=args.todo_type,
            priority=args.priority,
            description=args.description,
            tags=args.tags,
            related_files=args.files
        )
        todo_id = tracker.create_todo(todo)
        print(f"Created: {todo_id} - {args.title}")

    elif args.command == "list":
        todos = tracker.todos_data["todos"]

        if args.status:
            todos = [t for t in todos if t["status"] == args.status]
        else:
            todos = [t for t in todos
                     if t["status"] in [TodoStatus.OPEN.value, TodoStatus.IN_PROGRESS.value]]

        if args.todo_type:
            todos = [t for t in todos if t["type"] == args.todo_type]
        if args.priority:
            todos = [t for t in todos if t["priority"] == args.priority]
        if args.tag:
            todos = [t for t in todos if args.tag in t.get("tags", [])]

        if todos:
            print(f"Found {len(todos)} todos:")
            for todo in todos:
                print(f"  [{todo['priority']}] {todo['id']}: {todo['title']}")
                print(f"           Type: {todo['type']}, Status: {todo['status']}")
        else:
            print("No todos found")

    elif args.command == "show":
        todo = tracker.get_todo(args.todo_id)
        if todo:
            print(f"Todo: {todo['id']}")
            print(f"  Title: {todo['title']}")
            print(f"  Type: {todo['type']}")
            print(f"  Priority: {todo['priority']}")
            print(f"  Status: {todo['status']}")
            if todo.get('description'):
                print(f"  Description: {todo['description']}")
            if todo.get('assigned_to'):
                print(f"  Assigned To: {todo['assigned_to']}")
            if todo.get('tags'):
                print(f"  Tags: {', '.join(todo['tags'])}")
            if todo.get('related_files'):
                print(f"  Related Files: {', '.join(todo['related_files'])}")
            print(f"  Created: {todo['created_at']}")
            print(f"  Updated: {todo['updated_at']}")
            if todo.get('completed_at'):
                print(f"  Completed: {todo['completed_at']}")
        else:
            print(f"Todo not found: {args.todo_id}")

    elif args.command == "update":
        updates = {}
        if args.status:
            updates["status"] = args.status
        if args.priority:
            updates["priority"] = args.priority
        if args.assign:
            updates["assigned_to"] = args.assign

        if updates:
            if tracker.update_todo(args.todo_id, updates):
                print(f"Updated: {args.todo_id}")
            else:
                print(f"Failed to update: {args.todo_id}")
        else:
            print("No updates specified")

    elif args.command == "complete":
        if tracker.complete_todo(args.todo_id, args.resolution):
            print(f"Completed: {args.todo_id}")
        else:
            print(f"Failed to complete: {args.todo_id}")

    elif args.command == "stats":
        stats = tracker.get_statistics()
        print("Todo Statistics:")
        print(f"  Total: {stats['total']}")
        print("  By Status:")
        for status, count in stats['byStatus'].items():
            print(f"    {status}: {count}")
        print("  By Type:")
        for todo_type, count in stats['byType'].items():
            print(f"    {todo_type}: {count}")
        print("  By Priority:")
        for priority, count in stats['byPriority'].items():
            print(f"    {priority}: {count}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
