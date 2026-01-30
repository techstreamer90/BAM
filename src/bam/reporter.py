"""
BAM Reporter

Generates reports for pipeline runs, model state, and issues.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .graph_manager import GraphManager
from .issue_tracker import IssueTracker


logger = logging.getLogger("bam.reporter")


class Reporter:
    """Generates various reports for BAM operations."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = Path(project_dir)
        self.runs_dir = self.project_dir / "runs"
        self.output_dir = self.project_dir / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_run_report(self, run_id: str) -> str:
        """Generate a comprehensive report for a pipeline run."""
        run_dir = self.runs_dir / run_id

        if not run_dir.exists():
            raise ValueError(f"Run not found: {run_id}")

        # Load manifest
        with open(run_dir / "manifest.json", 'r') as f:
            manifest = json.load(f)

        # Load stage results
        stages_dir = run_dir / "stages"
        stage_results = {}
        if stages_dir.exists():
            for stage_file in stages_dir.glob("*.json"):
                with open(stage_file, 'r') as f:
                    stage_data = json.load(f)
                    stage_results[stage_file.stem] = stage_data

        # Generate report
        report = self._format_run_report(manifest, stage_results)

        # Save report
        report_path = run_dir / "report.md"
        with open(report_path, 'w') as f:
            f.write(report)

        return report

    def _format_run_report(self, manifest: dict, stage_results: dict) -> str:
        """Format a run report as markdown."""
        lines = [
            f"# Pipeline Run Report",
            f"",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            f"",
            f"## Overview",
            f"",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Run ID | `{manifest['runId']}` |",
            f"| Task ID | `{manifest['taskId']}` |",
            f"| Pipeline | {manifest['pipelineType']} |",
            f"| Source | {manifest['sourceId']} |",
            f"| Started | {manifest['startedAt']} |",
            f"",
            f"## Stage Results",
            f""
        ]

        # Sort stages by order if possible
        for stage_id, result in sorted(stage_results.items()):
            status_emoji = "+" if result['status'] == 'completed' else "x"
            lines.append(f"### [{status_emoji}] {stage_id}")
            lines.append(f"")
            lines.append(f"- **Status:** {result['status']}")
            lines.append(f"- **Started:** {result['started_at']}")
            if result.get('completed_at'):
                lines.append(f"- **Completed:** {result['completed_at']}")

            if result.get('errors'):
                lines.append(f"")
                lines.append(f"**Errors:**")
                for error in result['errors']:
                    lines.append(f"- {error}")

            if result.get('warnings'):
                lines.append(f"")
                lines.append(f"**Warnings:**")
                for warning in result['warnings']:
                    lines.append(f"- {warning}")

            lines.append(f"")

        # Summary
        completed = sum(1 for r in stage_results.values() if r['status'] == 'completed')
        failed = sum(1 for r in stage_results.values() if r['status'] == 'failed')

        lines.extend([
            f"## Summary",
            f"",
            f"- **Stages Completed:** {completed}",
            f"- **Stages Failed:** {failed}",
            f"- **Total Stages:** {len(stage_results)}",
            f""
        ])

        return "\n".join(lines)

    def generate_model_report(self) -> str:
        """Generate a report on the current model state."""
        gm = GraphManager()
        stats = gm.get_statistics()
        snapshots = gm.list_snapshots()

        lines = [
            f"# BAM Model Report",
            f"",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            f"",
            f"## Statistics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Version | {stats['version']} |",
            f"| Total Nodes | {stats['totalNodes']} |",
            f"| Total Edges | {stats['totalEdges']} |",
            f""
        ]

        if stats['nodesByType']:
            lines.extend([
                f"### Nodes by Type",
                f"",
                f"| Type | Count |",
                f"|------|-------|"
            ])
            for node_type, count in sorted(stats['nodesByType'].items()):
                lines.append(f"| {node_type} | {count} |")
            lines.append(f"")

        if stats['edgesByType']:
            lines.extend([
                f"### Edges by Type",
                f"",
                f"| Type | Count |",
                f"|------|-------|"
            ])
            for edge_type, count in sorted(stats['edgesByType'].items()):
                lines.append(f"| {edge_type} | {count} |")
            lines.append(f"")

        if snapshots:
            lines.extend([
                f"## Snapshots",
                f"",
                f"| ID | Created | Nodes | Edges |",
                f"|----|---------|-------|-------|"
            ])
            for snap in snapshots[-5:]:  # Last 5
                lines.append(f"| {snap['id']} | {snap['createdAt'][:19]} | {snap['nodeCount']} | {snap['edgeCount']} |")
            lines.append(f"")

        report = "\n".join(lines)

        # Save report
        report_path = self.output_dir / f"model-report-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)

        return report

    def generate_issues_report(self) -> str:
        """Generate a report on current issues."""
        tracker = IssueTracker()
        stats = tracker.get_statistics()
        open_issues = tracker.get_open_issues()
        blocking = tracker.get_blocking_issues()
        queue = tracker.get_human_queue(status="pending")

        lines = [
            f"# BAM Issues Report",
            f"",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            f"",
            f"## Summary",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Issues | {stats['total']} |",
            f"| Open Issues | {len(open_issues)} |",
            f"| Blocking Issues | {len(blocking)} |",
            f"| Human Queue Pending | {stats['humanQueuePending']} |",
            f""
        ]

        if stats['bySeverity']:
            lines.extend([
                f"### By Severity",
                f""
            ])
            for sev in ['critical', 'error', 'warning', 'info']:
                count = stats['bySeverity'].get(sev, 0)
                if count > 0:
                    lines.append(f"- **{sev.upper()}:** {count}")
            lines.append(f"")

        if blocking:
            lines.extend([
                f"## Blocking Issues",
                f"",
                f"These issues must be resolved before pipeline can continue.",
                f""
            ])
            for issue in blocking:
                lines.extend([
                    f"### {issue['id']}: {issue['title']}",
                    f"",
                    f"- **Severity:** {issue['severity']}",
                    f"- **Type:** {issue['type']}",
                    f"- **Description:** {issue['description']}",
                ])
                if issue.get('suggestedActions'):
                    lines.append(f"- **Suggested Actions:**")
                    for action in issue['suggestedActions']:
                        lines.append(f"  - {action}")
                lines.append(f"")

        if queue:
            lines.extend([
                f"## Human Intervention Queue",
                f"",
                f"| Item | Issue | Severity | Status |",
                f"|------|-------|----------|--------|"
            ])
            for item in queue:
                lines.append(f"| {item['id']} | {item['issueId']} | {item['severity']} | {item['status']} |")
            lines.append(f"")

        report = "\n".join(lines)

        # Save report
        report_path = self.output_dir / f"issues-report-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)

        return report

    def generate_source_report(self, source_id: str) -> str:
        """Generate a report for a specific data source."""
        # Load source config
        sources_path = self.project_dir / "sources.json"
        with open(sources_path, 'r') as f:
            sources = json.load(f)

        source = sources.get("sources", {}).get(source_id)
        if not source:
            raise ValueError(f"Source not found: {source_id}")

        # Get related issues
        tracker = IssueTracker()
        issues = tracker.get_issues_for_source(source_id)

        # Get related nodes
        gm = GraphManager()
        nodes = gm.find_nodes(source_id=source_id)

        lines = [
            f"# Source Report: {source['name']}",
            f"",
            f"**Generated:** {datetime.utcnow().isoformat()}",
            f"",
            f"## Configuration",
            f"",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| ID | `{source['id']}` |",
            f"| Type | {source['type']} |",
            f"| Enabled | {source['enabled']} |",
            f"| Connection Type | {source['connection']['type']} |",
            f"",
            f"## Integration Status",
            f"",
            f"- **Nodes in Model:** {len(nodes)}",
            f"- **Open Issues:** {len([i for i in issues if i['status'] != 'resolved'])}",
            f""
        ]

        if nodes:
            # Group by type
            by_type = {}
            for node in nodes:
                node_type = node['type']
                by_type[node_type] = by_type.get(node_type, 0) + 1

            lines.extend([
                f"### Nodes by Type",
                f"",
                f"| Type | Count |",
                f"|------|-------|"
            ])
            for node_type, count in sorted(by_type.items()):
                lines.append(f"| {node_type} | {count} |")
            lines.append(f"")

        if issues:
            lines.extend([
                f"## Related Issues",
                f""
            ])
            for issue in issues[:10]:  # Limit to 10
                lines.append(f"- [{issue['severity']}] {issue['id']}: {issue['title']} ({issue['status']})")
            if len(issues) > 10:
                lines.append(f"- ... and {len(issues) - 10} more")
            lines.append(f"")

        report = "\n".join(lines)

        # Save report
        report_path = self.output_dir / f"source-{source_id}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.md"
        with open(report_path, 'w') as f:
            f.write(report)

        return report


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Reporter")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run report
    run_parser = subparsers.add_parser("run", help="Generate run report")
    run_parser.add_argument("run_id", help="Run ID")

    # Model report
    subparsers.add_parser("model", help="Generate model report")

    # Issues report
    subparsers.add_parser("issues", help="Generate issues report")

    # Source report
    source_parser = subparsers.add_parser("source", help="Generate source report")
    source_parser.add_argument("source_id", help="Source ID")

    args = parser.parse_args()

    reporter = Reporter()

    if args.command == "run":
        report = reporter.generate_run_report(args.run_id)
        print(report)

    elif args.command == "model":
        report = reporter.generate_model_report()
        print(report)

    elif args.command == "issues":
        report = reporter.generate_issues_report()
        print(report)

    elif args.command == "source":
        report = reporter.generate_source_report(args.source_id)
        print(report)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
