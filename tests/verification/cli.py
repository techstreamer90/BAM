"""
CLI interface for the verification testing system.

Usage:
    python -m tests.verification.cli run [--parallel] [--tags TAG1,TAG2]
    python -m tests.verification.cli list
    python -m tests.verification.cli stats
"""

import argparse
import sys
from pathlib import Path

from .models import VerificationStatus
from .questions import QuestionLoader
from .runner import VerificationRunner, print_progress, print_summary


def cmd_run(args):
    """Run verification tests."""
    tags = args.tags.split(",") if args.tags else None

    print("BAM Data Verification")
    print("=" * 60)

    # Initialize runner
    runner = VerificationRunner(
        parallel=args.parallel,
        max_workers=args.workers,
        progress_callback=print_progress if not args.quiet else None
    )

    # Load fixtures
    fixture_count = runner.load_fixtures(tags=tags)
    print(f"Loaded {fixture_count} fixture data points")

    # Load questions if requested
    if args.questions:
        loader = QuestionLoader()
        question_dps = loader.to_data_points(tags=tags)
        runner.add_data_points(question_dps)
        print(f"Loaded {len(question_dps)} questions")

    total = fixture_count + (len(question_dps) if args.questions else 0)
    if total == 0:
        print("No data points to verify. Check fixtures directory.")
        return 1

    print(f"\nRunning {total} verifications" + (" (parallel)" if args.parallel else "") + "...")
    print("-" * 60)

    # Run verifications
    summary = runner.run()

    # Print summary
    print_summary(summary)

    # Return exit code based on results
    return 0 if summary.all_passed else 1


def cmd_list(args):
    """List all available data points."""
    runner = VerificationRunner()
    fixture_count = runner.load_fixtures()

    print("Fixture Data Points:")
    print("-" * 40)
    for dp in runner._data_points:
        tags_str = f" [{', '.join(dp.tags)}]" if dp.tags else ""
        print(f"  {dp.id}: {dp.description}{tags_str}")

    print(f"\nTotal: {fixture_count} fixture data points")

    # Load questions
    loader = QuestionLoader()
    questions = loader.load_all()

    if questions:
        print("\nQuestion Database:")
        print("-" * 40)
        for q in questions:
            tags_str = f" [{', '.join(q.tags)}]" if q.tags else ""
            print(f"  {q.id} ({q.category}): {q.question}{tags_str}")
        print(f"\nTotal: {len(questions)} questions")


def cmd_stats(args):
    """Show current model statistics."""
    from .query_engine import VerificationQueryEngine

    print("Model Statistics")
    print("=" * 60)

    with VerificationQueryEngine() as engine:
        stats = engine.get_statistics()

        print(f"Version: {stats.get('version', 'unknown')}")
        print(f"Total Nodes: {stats.get('totalNodes', 0)}")
        print(f"Total Edges: {stats.get('totalEdges', 0)}")

        nodes_by_type = stats.get('nodesByType', {})
        if nodes_by_type:
            print("\nNodes by Type:")
            for node_type, count in sorted(nodes_by_type.items()):
                print(f"  {node_type}: {count}")

        edges_by_type = stats.get('edgesByType', {})
        if edges_by_type:
            print("\nEdges by Type:")
            for edge_type, count in sorted(edges_by_type.items()):
                print(f"  {edge_type}: {count}")


def cmd_verify_one(args):
    """Verify a single node by ID."""
    from .models import DataPoint, ExpectedValue, VerificationQuery, VerificationType
    from .query_engine import VerificationQueryEngine

    dp = DataPoint(
        id="cli-verify",
        type=VerificationType.NODE_EXISTS,
        description=f"Verify node {args.node_id}",
        query=VerificationQuery(node_id=args.node_id),
        expected=ExpectedValue(exists=True)
    )

    with VerificationQueryEngine() as engine:
        result = engine.verify(dp)
        print_progress(result)

        if result.status == VerificationStatus.PASS:
            # Print node details
            node = engine._gm.get_node(args.node_id)
            if node:
                print(f"\nNode Details:")
                print(f"  ID: {node.get('id')}")
                print(f"  Type: {node.get('type')}")
                print(f"  Label: {node.get('label')}")
                print(f"  Source: {node.get('source_id')}")
                props = node.get('properties', {})
                if props:
                    print(f"  Properties: {props}")

    return 0 if result.status == VerificationStatus.PASS else 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="BAM Data Verification Testing System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run verification tests")
    run_parser.add_argument(
        "--parallel", "-p",
        action="store_true",
        help="Run tests in parallel"
    )
    run_parser.add_argument(
        "--workers", "-w",
        type=int,
        default=4,
        help="Number of parallel workers (default: 4)"
    )
    run_parser.add_argument(
        "--tags", "-t",
        help="Comma-separated list of tags to filter by"
    )
    run_parser.add_argument(
        "--questions", "-q",
        action="store_true",
        help="Include Q&A database questions"
    )
    run_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress individual test output"
    )

    # List command
    subparsers.add_parser("list", help="List all data points and questions")

    # Stats command
    subparsers.add_parser("stats", help="Show model statistics")

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify a single node")
    verify_parser.add_argument("node_id", help="Node ID to verify")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "stats":
        return cmd_stats(args)
    elif args.command == "verify":
        return cmd_verify_one(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
