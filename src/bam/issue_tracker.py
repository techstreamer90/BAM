"""
BAM Issue Tracker

Manages issues, human intervention queue, and issue resolution workflow.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from .common import Issue, IssueType, IssueSeverity, IssueStatus, to_camel_dict


class IssueTracker:
    """Manages the issue lifecycle."""

    def __init__(self, project_dir: str):
        pdir = Path(project_dir)
        self._issues_path = pdir / "issues.json"
        self._human_queue_path = pdir / "human-queue.json"
        self.issues_data = self._load_issues()
        self.human_queue = self._load_human_queue()

    def _load_issues(self) -> dict:
        with open(self._issues_path, 'r') as f:
            return json.load(f)

    def _load_human_queue(self) -> dict:
        with open(self._human_queue_path, 'r') as f:
            return json.load(f)

    def _save_issues(self):
        with open(self._issues_path, 'w') as f:
            json.dump(self.issues_data, f, indent=2)

    def _save_human_queue(self):
        with open(self._human_queue_path, 'w') as f:
            json.dump(self.human_queue, f, indent=2)

    def create_issue(self, issue: Issue) -> str:
        """Create a new issue."""
        self.issues_data["lastIssueId"] += 1
        issue.id = f"issue-{self.issues_data['lastIssueId']:04d}"

        # Auto-set to blocking if critical/error
        if issue.severity in [IssueSeverity.CRITICAL.value, IssueSeverity.ERROR.value]:
            issue.status = IssueStatus.BLOCKING.value

        self.issues_data["issues"].append(to_camel_dict(issue))
        self._save_issues()

        # Add to human queue if blocking
        if issue.status == IssueStatus.BLOCKING.value:
            self._add_to_human_queue(issue)

        return issue.id

    def _add_to_human_queue(self, issue: Issue):
        """Add issue to human intervention queue."""
        item = {
            "id": f"hq-{len(self.human_queue['items']) + 1:04d}",
            "issueId": issue.id,
            "type": issue.type,
            "severity": issue.severity,
            "title": issue.title,
            "sourceId": issue.source_id,
            "runId": issue.run_id,
            "addedAt": datetime.utcnow().isoformat(),
            "status": "pending",
            "assignedTo": None,
            "notes": []
        }
        self.human_queue["items"].append(item)
        self._save_human_queue()

    def get_issue(self, issue_id: str) -> Optional[dict]:
        """Get an issue by ID."""
        for issue in self.issues_data["issues"]:
            if issue["id"] == issue_id:
                return issue
        return None

    def update_issue(self, issue_id: str, updates: dict) -> bool:
        """Update an issue."""
        for i, issue in enumerate(self.issues_data["issues"]):
            if issue["id"] == issue_id:
                for key, value in updates.items():
                    if key in issue:
                        issue[key] = value
                issue["updatedAt"] = datetime.utcnow().isoformat()
                self.issues_data["issues"][i] = issue
                self._save_issues()
                return True
        return False

    def add_comment(self, issue_id: str, author: str, text: str) -> bool:
        """Add a comment to an issue."""
        issue = self.get_issue(issue_id)
        if not issue:
            return False

        comment = {
            "author": author,
            "text": text,
            "timestamp": datetime.utcnow().isoformat()
        }

        for i, iss in enumerate(self.issues_data["issues"]):
            if iss["id"] == issue_id:
                self.issues_data["issues"][i]["comments"].append(comment)
                self.issues_data["issues"][i]["updatedAt"] = datetime.utcnow().isoformat()
                self._save_issues()
                return True
        return False

    def resolve_issue(self, issue_id: str, resolution: str) -> bool:
        """Resolve an issue."""
        return self.update_issue(issue_id, {
            "status": IssueStatus.RESOLVED.value,
            "resolution": resolution,
            "resolvedAt": datetime.utcnow().isoformat()
        })

    def get_blocking_issues(self) -> List[dict]:
        """Get all blocking issues."""
        return [i for i in self.issues_data["issues"]
                if i["status"] == IssueStatus.BLOCKING.value]

    def get_issues_for_source(self, source_id: str) -> List[dict]:
        """Get all issues for a source."""
        return [i for i in self.issues_data["issues"]
                if i.get("sourceId") == source_id]

    def get_issues_for_run(self, run_id: str) -> List[dict]:
        """Get all issues for a run."""
        return [i for i in self.issues_data["issues"]
                if i.get("runId") == run_id]

    def get_open_issues(self) -> List[dict]:
        """Get all open issues."""
        return [i for i in self.issues_data["issues"]
                if i["status"] in [IssueStatus.OPEN.value, IssueStatus.BLOCKING.value,
                                   IssueStatus.IN_PROGRESS.value]]

    def get_human_queue(self, status: str = None) -> List[dict]:
        """Get items in human intervention queue."""
        items = self.human_queue["items"]
        if status:
            items = [i for i in items if i["status"] == status]
        return items

    def claim_human_queue_item(self, item_id: str, assignee: str) -> bool:
        """Claim an item from the human queue."""
        for i, item in enumerate(self.human_queue["items"]):
            if item["id"] == item_id:
                self.human_queue["items"][i]["status"] = "in-progress"
                self.human_queue["items"][i]["assignedTo"] = assignee
                self.human_queue["items"][i]["claimedAt"] = datetime.utcnow().isoformat()
                self._save_human_queue()
                return True
        return False

    def complete_human_queue_item(self, item_id: str, notes: str = None) -> bool:
        """Complete a human queue item."""
        for i, item in enumerate(self.human_queue["items"]):
            if item["id"] == item_id:
                self.human_queue["items"][i]["status"] = "completed"
                self.human_queue["items"][i]["completedAt"] = datetime.utcnow().isoformat()
                if notes:
                    self.human_queue["items"][i]["notes"].append({
                        "text": notes,
                        "timestamp": datetime.utcnow().isoformat()
                    })
                self._save_human_queue()
                return True
        return False

    def get_statistics(self) -> dict:
        """Get issue statistics."""
        issues = self.issues_data["issues"]

        by_status = {}
        by_severity = {}
        by_type = {}

        for issue in issues:
            status = issue["status"]
            severity = issue["severity"]
            issue_type = issue["type"]

            by_status[status] = by_status.get(status, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            by_type[issue_type] = by_type.get(issue_type, 0) + 1

        return {
            "total": len(issues),
            "byStatus": by_status,
            "bySeverity": by_severity,
            "byType": by_type,
            "humanQueuePending": len([i for i in self.human_queue["items"]
                                      if i["status"] == "pending"])
        }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Issue Tracker")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # List command
    list_parser = subparsers.add_parser("list", help="List issues")
    list_parser.add_argument("--status", "-s", help="Filter by status")
    list_parser.add_argument("--blocking", "-b", action="store_true",
                             help="Show only blocking issues")

    # Show command
    show_parser = subparsers.add_parser("show", help="Show issue details")
    show_parser.add_argument("issue_id", help="Issue ID")

    # Resolve command
    resolve_parser = subparsers.add_parser("resolve", help="Resolve an issue")
    resolve_parser.add_argument("issue_id", help="Issue ID")
    resolve_parser.add_argument("resolution", help="Resolution description")

    # Stats command
    subparsers.add_parser("stats", help="Show issue statistics")

    # Human queue commands
    subparsers.add_parser("queue", help="Show human intervention queue")

    claim_parser = subparsers.add_parser("claim", help="Claim queue item")
    claim_parser.add_argument("item_id", help="Queue item ID")
    claim_parser.add_argument("assignee", help="Assignee name")

    args = parser.parse_args()

    tracker = IssueTracker()

    if args.command == "list":
        if args.blocking:
            issues = tracker.get_blocking_issues()
        else:
            issues = tracker.get_open_issues()

        if issues:
            print(f"Found {len(issues)} issues:")
            for issue in issues:
                print(f"  [{issue['severity']}] {issue['id']}: {issue['title']}")
                print(f"           Status: {issue['status']}")
        else:
            print("No issues found")

    elif args.command == "show":
        issue = tracker.get_issue(args.issue_id)
        if issue:
            print(f"Issue: {issue['id']}")
            print(f"  Title: {issue['title']}")
            print(f"  Type: {issue['type']}")
            print(f"  Severity: {issue['severity']}")
            print(f"  Status: {issue['status']}")
            print(f"  Description: {issue['description']}")
            if issue.get('sourceId'):
                print(f"  Source: {issue['sourceId']}")
            if issue.get('runId'):
                print(f"  Run: {issue['runId']}")
            if issue.get('suggestedActions'):
                print(f"  Suggested Actions:")
                for action in issue['suggestedActions']:
                    print(f"    - {action}")
        else:
            print(f"Issue not found: {args.issue_id}")

    elif args.command == "resolve":
        if tracker.resolve_issue(args.issue_id, args.resolution):
            print(f"Resolved: {args.issue_id}")
        else:
            print(f"Failed to resolve: {args.issue_id}")

    elif args.command == "stats":
        stats = tracker.get_statistics()
        print("Issue Statistics:")
        print(f"  Total: {stats['total']}")
        print(f"  Human Queue Pending: {stats['humanQueuePending']}")
        print("  By Status:")
        for status, count in stats['byStatus'].items():
            print(f"    {status}: {count}")
        print("  By Severity:")
        for sev, count in stats['bySeverity'].items():
            print(f"    {sev}: {count}")

    elif args.command == "queue":
        items = tracker.get_human_queue()
        if items:
            print("Human Intervention Queue:")
            for item in items:
                print(f"  {item['id']}: {item['title']}")
                print(f"    Severity: {item['severity']}, Status: {item['status']}")
                if item.get('assignedTo'):
                    print(f"    Assigned to: {item['assignedTo']}")
        else:
            print("Human queue is empty")

    elif args.command == "claim":
        if tracker.claim_human_queue_item(args.item_id, args.assignee):
            print(f"Claimed {args.item_id} for {args.assignee}")
        else:
            print(f"Failed to claim: {args.item_id}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
