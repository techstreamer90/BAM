"""
BAM CLI - Multi-project Digital Twin Tool

Entry point for all BAM operations. Every command operates on a specific
project directory via --project.

Usage:
    python -m bam seed show-playbook 0            # start here — agent reads playbook
    python -m bam --project ./my-project stats
    python -m bam --project ./my-project plan show
    python -m bam list-projects C:/BAM_projects
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .project import load_project_config, list_projects
from .ingestion_plan import IngestionPlanManager
from .seed_runner import SeedRunner
from ._paths import SEED_DIR


def cmd_ingest(args):
    """Run ingestion via orchestrator pipeline.

    Requires ``--pipeline`` and ``--source-id`` to select the pipeline
    type and data source.
    """
    if not args.pipeline or not args.source_id:
        print("Error: --pipeline and --source-id are required.")
        print("  Example: python -m bam --project ./p ingest --pipeline standard --source-id my-source")
        sys.exit(1)

    from .orchestrator import Orchestrator

    orch = Orchestrator(args.project)
    task = orch.create_ingestion_task(
        source_id=args.source_id,
        pipeline_type=args.pipeline,
    )
    print(f"Created task: {task['id']}")

    run_id = orch.run_task(task["id"])
    if run_id:
        task = orch.task_manager.get_task(task["id"])
        status = task["status"] if task else "unknown"
        if status == "paused":
            print(f"Pipeline paused (run {run_id}) — sketch review required.")
            print(f"  bam --project {args.project} review show")
            print(f"  bam --project {args.project} review approve")
            print(f"  bam --project {args.project} resume {task['id']}")
        else:
            print(f"Run completed: {run_id} (status: {status})")


def cmd_stats(args):
    """Show project model statistics."""
    from .graph_manager import GraphManager

    gm = GraphManager(project_dir=args.project)
    stats = gm.get_statistics()

    print(f"Model Statistics for: {args.project}")
    print(f"  Nodes: {stats['totalNodes']}")
    print(f"  Edges: {stats['totalEdges']}")

    if stats.get('nodesByType'):
        print(f"\n  Nodes by type:")
        for ntype, count in sorted(stats['nodesByType'].items()):
            print(f"    {ntype}: {count}")

    if stats.get('edgesByType'):
        print(f"\n  Edges by type:")
        for etype, count in sorted(stats['edgesByType'].items()):
            print(f"    {etype}: {count}")

    gm.close()


def cmd_plan(args):
    """Handle plan subcommands."""
    mgr = IngestionPlanManager(args.project)

    if args.plan_command == "create":
        plan = mgr.create()
        print(f"Created ingestion plan at {mgr.plan_path}")
        print(f"Status: {plan['status']}")
        print(f"Phases: {len(plan['phases'])}")
        print("\nNext: add steps with 'plan add-step'")

    elif args.plan_command == "show":
        print(mgr.show())

    elif args.plan_command == "next":
        result = mgr.next_step()
        if result is None:
            print("All steps are completed (or no steps defined).")
        else:
            step = result["step"]
            print(f"Next step — Phase: {result['phaseName']}")
            print(f"  ID: {step['id']}")
            print(f"  Name: {step['name']}")
            print(f"  Description: {step.get('description', '-')}")
            print(f"  Source: {step.get('source', '-')}")
            print(f"  Agent Tier: {step.get('agentTier', '-')}")
            chunk = step.get("chunkStrategy", {})
            if chunk.get("maxBatchSize"):
                print(f"  Max Batch Size: {chunk['maxBatchSize']}")
            if chunk.get("groupBy"):
                print(f"  Group By: {chunk['groupBy']}")
            if step.get("processHints"):
                print("  Hints:")
                for h in step["processHints"]:
                    print(f"    - {h}")
            if step.get("preChecks"):
                print("  Pre-checks:")
                for c in step["preChecks"]:
                    print(f"    - {c}")

    elif args.plan_command == "validate":
        report = mgr.validate()
        status = "VALID" if report["valid"] else "INVALID"
        print(f"Plan Validation: {status}")
        print(f"Total steps: {report['totalSteps']}")
        if report["errors"]:
            print("\nErrors:")
            for e in report["errors"]:
                print(f"  [ERROR] {e}")
        if report["warnings"]:
            print("\nWarnings:")
            for w in report["warnings"]:
                print(f"  [WARN] {w}")
        if report["valid"] and not report["warnings"]:
            print("No issues found.")

    elif args.plan_command == "add-step":
        hints = [h.strip() for h in args.hints.split(";")] if args.hints else []
        pre = [c.strip() for c in args.pre_checks.split(";")] if args.pre_checks else []
        post = [c.strip() for c in args.post_checks.split(";")] if args.post_checks else []
        step = mgr.add_step(
            phase_id=args.phase,
            name=args.name,
            description=args.description or "",
            source=args.source or "",
            agent_tier=args.agent_tier or "standard",
            max_batch_size=args.max_batch_size or 100,
            group_by=args.group_by or "",
            process_hints=hints,
            pre_checks=pre,
            post_checks=post,
        )
        print(f"Added step '{step['name']}' (id={step['id']}) to phase '{args.phase}'")

    elif args.plan_command == "complete-step":
        step = mgr.complete_step(args.step, result=args.result)
        print(f"Completed step '{step['id']}': {step['name']}")

    else:
        print("Unknown plan command. Use: create, show, next, validate, add-step, complete-step")


def cmd_seed(args):
    """Handle seed subcommands."""
    if args.seed_command == "check-prereqs":
        # Use a minimal profile just for prerequisite checks
        dummy_profile = {"projectName": "", "projectDir": ".", "domain": "other",
                         "sourceRoot": "", "dataSources": [],
                         "complexity": {"sourceTypeCount": 0, "estimatedNodeCount": 0}}
        runner = SeedRunner(dummy_profile)
        result = runner.check_prerequisites(backend=args.backend or "json")
        status = "PASSED" if result["passed"] else "FAILED"
        print(f"Prerequisite Checks: {status}")
        for r in result["results"]:
            icon = "[OK]" if r["status"] == "pass" else "[!!]" if r["status"] == "fail" else "[--]"
            print(f"  {icon} {r['name']}: {r['message']}")
        if not result["passed"]:
            sys.exit(1)

    elif args.seed_command == "recommend":
        if not args.profile:
            print("Error: --profile is required for 'seed recommend'")
            sys.exit(1)
        with open(args.profile, "r") as f:
            profile = json.load(f)
        runner = SeedRunner(profile)
        rec = runner.generate_recommendations()
        print("Recommendations:")
        print(f"  Template: {rec['template']}")
        print(f"  Backend:  {rec['backend']}")
        print(f"  Pipeline: {rec['pipeline']}")
        print(f"  Parsers:  {', '.join(rec['parsers']) if rec['parsers'] else '(none)'}")
        print("\nRationale:")
        for key, val in rec["rationale"].items():
            print(f"  {key}: {val}")

    elif args.seed_command == "execute":
        if not args.profile:
            print("Error: --profile is required for 'seed execute'")
            sys.exit(1)
        with open(args.profile, "r") as f:
            profile = json.load(f)
        runner = SeedRunner(profile)
        report = runner.execute_setup(dry_run=args.dry_run)
        mode = "DRY RUN" if args.dry_run else "EXECUTION"
        print(f"Seed {mode} Report")
        print(f"  Seed version: {report['seedVersion']}")
        print(f"  Executed at:  {report['executedAt']}")
        print(f"\nSteps:")
        for step in report["steps"]:
            icon = "[OK]" if step["status"] == "done" else "[~~]" if step["status"] == "dry_run" else "[!!]"
            print(f"  {icon} {step['name']}: {step['detail']}")
        has_errors = any(s["status"] == "error" for s in report["steps"])
        if has_errors:
            print("\nSetup completed with errors. Check details above.")
            sys.exit(1)
        else:
            print(f"\nNext actions:")
            for action in report.get("nextActions", []):
                print(f"  - {action}")

    elif args.seed_command == "show-playbook":
        playbook_dir = SEED_DIR / "playbooks"
        if args.step_number is not None:
            pattern = f"{args.step_number:02d}_*.md"
            matches = list(playbook_dir.glob(pattern))
            if not matches:
                print(f"No playbook found for step {args.step_number}")
                sys.exit(1)
            with open(matches[0], "r") as f:
                print(f.read())
        else:
            print("Available playbooks:")
            for pb in sorted(playbook_dir.glob("*.md")):
                print(f"  {pb.stem}")

    else:
        print("Unknown seed command. Use: check-prereqs, recommend, execute, show-playbook")


def cmd_test(args):
    """Handle test subcommands."""
    from .test_chain import TestChainManager

    chain = TestChainManager(args.project)

    if args.test_command == "run":
        summary = chain.run_all(project_dir=args.project)
        print(chain.format_summary(summary))
        if not summary.all_passed:
            sys.exit(1)

    elif args.test_command == "show":
        print(chain.format_chain_overview())

    elif args.test_command == "add-check":
        query = {}
        expected = {}

        vtype = args.type or "node_exists"

        if args.node_id:
            query["node_id"] = args.node_id
        if args.node_type:
            query["node_type"] = args.node_type
        if args.source_id:
            query["source_id"] = args.source_id

        if vtype == "node_exists":
            expected["exists"] = True
        if args.expected_count is not None:
            expected["count"] = args.expected_count
        if args.min_count is not None:
            expected["min_count"] = args.min_count

        chain.add_manual_check(
            description=args.description,
            verification_type=vtype,
            query=query,
            expected=expected,
            gate=args.gate or "blocking",
        )
        print(f"Added manual check: {args.description}")

    else:
        print("Unknown test command. Use: run, show, add-check")


def cmd_review(args):
    """Handle review subcommands."""
    from .sketch_review import SketchReviewManager

    mgr = SketchReviewManager(args.project)

    if args.review_command == "show":
        print(mgr.show())

    elif args.review_command == "approve":
        review = mgr.approve()
        print(f"Sketch review approved.")
        print(f"  Task: {review['taskId']}")
        print(f"  Decided at: {review['decidedAt']}")
        print(f"\nResume the pipeline with: bam --project {args.project} resume {review['taskId']}")

    elif args.review_command == "reject":
        feedback = args.feedback or ""
        review = mgr.reject(feedback=feedback)
        print(f"Sketch review rejected.")
        if feedback:
            print(f"  Feedback: {feedback}")
        print(f"\nResume (re-runs agent review): bam --project {args.project} resume {review['taskId']}")

    else:
        print("Unknown review command. Use: show, approve, reject")


def cmd_feedback(args):
    """Handle feedback subcommands."""
    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(args.project)

    if args.feedback_command == "submit":
        task = orchestrator.create_feedback_task(
            kind=args.kind,
            message=args.message,
            author=args.author,
            source_id=args.source or "",
            refs=args.refs or [],
        )
        result = orchestrator.process_feedback(task["id"])
        print(f"Feedback submitted: {task['id']}")
        if result["action"] == "auto_ingestion":
            print(f"  Auto-processed: created ingestion task {result['childTaskId']}")
        else:
            print(f"  Queued for review: issue {result['issueId']}")

    elif args.feedback_command == "list":
        tasks = [
            t for t in orchestrator.task_manager.tasks_data["tasks"]
            if t["type"] == "feedback"
        ]
        if args.status:
            tasks = [t for t in tasks if t["status"] == args.status]
        if args.kind:
            tasks = [t for t in tasks
                     if t.get("metadata", {}).get("feedbackKind") == args.kind]

        if tasks:
            print(f"Feedback tasks ({len(tasks)}):")
            for t in tasks:
                meta = t.get("metadata", {})
                print(f"  {t['id']} [{meta.get('feedbackKind', '?')}] "
                      f"status={t['status']}  by {meta.get('feedbackAuthor', '?')}")
                print(f"    {meta.get('feedbackMessage', '')[:60]}")
        else:
            print("No feedback tasks found.")

    elif args.feedback_command == "show":
        task = orchestrator.task_manager.get_task(args.task_id)
        if not task or task["type"] != "feedback":
            print(f"Feedback task not found: {args.task_id}")
            sys.exit(1)
        meta = task.get("metadata", {})
        print(f"Feedback Task: {task['id']}")
        print(f"  Kind: {meta.get('feedbackKind', '?')}")
        print(f"  Author: {meta.get('feedbackAuthor', '?')}")
        print(f"  Status: {task['status']}")
        print(f"  Source: {task.get('sourceId') or '(none)'}")
        print(f"  Message: {meta.get('feedbackMessage', '')}")
        if meta.get("feedbackRefs"):
            print(f"  Refs: {', '.join(meta['feedbackRefs'])}")
        if meta.get("resolution"):
            print(f"  Resolution: {meta['resolution']}")
        if meta.get("childTaskId"):
            print(f"  Child task: {meta['childTaskId']}")
        if meta.get("issueId"):
            print(f"  Issue: {meta['issueId']}")

    else:
        print("Unknown feedback command. Use: submit, list, show")


def cmd_resume(args):
    """Resume a paused pipeline."""
    from .orchestrator import Orchestrator

    orchestrator = Orchestrator(args.project)
    run_id = orchestrator.resume_task(args.task_id)
    if run_id:
        print(f"Pipeline resumed. Run: {run_id}")
    else:
        print("Resume failed.")


def cmd_control(args):
    """Handle control subcommands."""
    from .control import ControlManager, create_env_example

    mgr = ControlManager(args.project)

    if args.control_command == "show":
        print(mgr.show())

    elif args.control_command == "init":
        if mgr.exists() and not args.force:
            print(f"control.json already exists at {mgr.control_path}")
            print("Use --force to overwrite")
            sys.exit(1)

        mgr.save()  # Creates default
        print(f"Created {mgr.control_path}")

        env_path = create_env_example(args.project)
        print(f"Created {env_path}")

    elif args.control_command == "validate":
        result = mgr.validate()
        if result["valid"]:
            print("Configuration is valid")
        else:
            print("Configuration has errors:")
            for err in result["errors"]:
                print(f"  [!] {err}")
        if result["warnings"]:
            print("Warnings:")
            for warn in result["warnings"]:
                print(f"  [?] {warn}")
        if not result["valid"]:
            sys.exit(1)

    elif args.control_command == "set-model":
        if not args.task:
            print("Error: --task is required")
            sys.exit(1)
        if not args.model:
            print("Error: --model is required")
            sys.exit(1)

        mgr.set_model_for_task(
            task_type=args.task,
            model=args.model,
            source_type=args.source if hasattr(args, 'source') else None,
        )
        print(f"Set model for task '{args.task}': {args.model}")
        if hasattr(args, 'source') and args.source:
            print(f"  (source-specific: {args.source})")

    else:
        print("Unknown control command. Use: show, init, validate, set-model")


def cmd_setup(args):
    """Handle setup subcommands."""
    if args.setup_command == "wizard":
        from .setup_wizard import run_wizard
        project_dir = getattr(args, 'project', None)
        run_wizard(project_dir=project_dir, force=True)

    elif args.setup_command == "llm":
        from .llm.factory import load_global_config, save_global_config

        config = load_global_config()

        provider = args.provider or "claude"
        api_key = args.api_key or ""

        llm_config = config.get("llm", {})
        llm_config["provider"] = provider
        if api_key:
            llm_config["api_key"] = api_key
        if args.model:
            llm_config["model"] = args.model
        config["llm"] = llm_config

        save_global_config(config)
        print(f"LLM provider configured: {provider}")

        # Test availability
        try:
            from .llm.factory import get_llm_provider
            p = get_llm_provider(provider)
            if p.is_available():
                print("  Status: available (credentials configured)")

                # If --test flag, make a real API call
                if args.test:
                    print("  Testing connection...")
                    result = p.test_connection()
                    if result.success:
                        print(f"  Test: PASSED - {result.message}")
                        if result.usage:
                            print(f"  Tokens used: {result.usage}")
                    else:
                        print(f"  Test: FAILED - {result.message}")
                        sys.exit(1)
            else:
                print("  Status: not available (API key not set)")
                if provider == "claude":
                    print("  Set ANTHROPIC_API_KEY environment variable or use --api-key")
                elif provider == "copilot":
                    print("  Ensure GitHub Copilot CLI is installed and you're authenticated")
                    print("  Install: pip install github-copilot-sdk")
                else:
                    print("  Configure the provider credentials")

                if args.test:
                    print("  Test: SKIPPED (provider not available)")
                    sys.exit(1)
        except Exception as e:
            print(f"  Status: error ({e})")
            if args.test:
                sys.exit(1)

    elif args.setup_command == "show":
        from .llm.factory import load_global_config, GLOBAL_CONFIG_PATH
        config = load_global_config()
        llm_config = config.get("llm", {})

        print(f"Global config: {GLOBAL_CONFIG_PATH}")
        print(f"  Provider: {llm_config.get('provider', '(not set)')}")
        print(f"  Model: {llm_config.get('model', '(default)')}")
        print(f"  API key: {'****' + llm_config.get('api_key', '')[-4:] if llm_config.get('api_key') else '(from env)'}")

    else:
        print("Unknown setup command. Use: wizard, llm, show")


def cmd_list_projects(args):
    """List all projects in a directory."""
    projects = list_projects(args.projects_dir)
    if not projects:
        print(f"No projects found in {args.projects_dir}")
        return

    print(f"Projects in {args.projects_dir}:")
    for p in projects:
        print(f"  {p['name']}")
        print(f"    Path: {p['path']}")
        print(f"    Source: {p['source_root']}")
        print(f"    Created: {p['created_at']}")


def cmd_info(args):
    """Show project info."""
    config = load_project_config(args.project)
    print(f"Project: {config.get('name', '(unnamed)')}")
    print(f"  Directory: {args.project}")
    print(f"  Source root: {config.get('source_root', '(not set)')}")
    print(f"  Created: {config.get('created_at', '(unknown)')}")

    storage = config.get("storage", {})
    colors = storage.get("colors", {})
    backends = storage.get("color_backends", {})
    print(f"  Colors: {', '.join(colors.keys())}")
    print(f"  Backends: {', '.join(backends.keys())}")


def main():
    parser = argparse.ArgumentParser(
        description="BAM - Build Accurate Models (Digital Twin Tool)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start a new project (agent-guided)
  python -m bam seed show-playbook 0

  # Check model stats
  python -m bam --project ./my-project stats

  # View ingestion plan
  python -m bam --project ./my-project plan show

  # List all projects
  python -m bam list-projects C:/models
"""
    )

    parser.add_argument(
        "--project", "-p",
        help="Path to the BAM project model directory"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ingest
    ingest_p = subparsers.add_parser("ingest", help="Run ingestion pipeline")
    ingest_p.add_argument("--pipeline",
                          choices=["standard", "incremental", "agent-driven"],
                          help="Pipeline type (uses orchestrator)")
    ingest_p.add_argument("--source-id", help="Source ID to ingest")

    # stats
    subparsers.add_parser("stats", help="Show model statistics")

    # info
    subparsers.add_parser("info", help="Show project info")

    # plan
    plan_p = subparsers.add_parser("plan", help="Manage ingestion plan")
    plan_sub = plan_p.add_subparsers(dest="plan_command", help="Plan commands")

    plan_sub.add_parser("create", help="Create a new ingestion plan from template")
    plan_sub.add_parser("show", help="Show the current ingestion plan")
    plan_sub.add_parser("next", help="Show the next pending step")
    plan_sub.add_parser("validate", help="Validate the ingestion plan")

    add_step_p = plan_sub.add_parser("add-step", help="Add a step to a phase")
    add_step_p.add_argument("--phase", required=True,
                            help="Phase ID (backbone, enrichment, cross-references, validation)")
    add_step_p.add_argument("--name", required=True, help="Step name")
    add_step_p.add_argument("--description", help="Step description")
    add_step_p.add_argument("--source", help="Source identifier")
    add_step_p.add_argument("--agent-tier", default="standard",
                            choices=["low", "standard", "high"],
                            help="Recommended agent tier (default: standard)")
    add_step_p.add_argument("--max-batch-size", type=int, default=100,
                            help="Max items per batch (default: 100)")
    add_step_p.add_argument("--group-by", help="How to group items in batches")
    add_step_p.add_argument("--hints", help="Process hints (semicolon-separated)")
    add_step_p.add_argument("--pre-checks", help="Pre-checks (semicolon-separated)")
    add_step_p.add_argument("--post-checks", help="Post-checks (semicolon-separated)")

    complete_p = plan_sub.add_parser("complete-step", help="Mark a step as completed")
    complete_p.add_argument("--step", required=True, help="Step ID to complete")
    complete_p.add_argument("--result", help="Optional result summary")

    # seed
    seed_p = subparsers.add_parser("seed", help="Interactive project bootstrapping")
    seed_sub = seed_p.add_subparsers(dest="seed_command", help="Seed commands")

    seed_prereq = seed_sub.add_parser("check-prereqs", help="Check system prerequisites")
    seed_prereq.add_argument("--backend", choices=["json", "sqlite", "neo4j", "arango"],
                             help="Backend to check prerequisites for (default: json)")

    seed_rec = seed_sub.add_parser("recommend", help="Generate setup recommendations from profile")
    seed_rec.add_argument("--profile", required=True, help="Path to project profile JSON")

    seed_exec = seed_sub.add_parser("execute", help="Execute project setup from profile")
    seed_exec.add_argument("--profile", required=True, help="Path to project profile JSON")
    seed_exec.add_argument("--dry-run", action="store_true",
                           help="Show what would be done without doing it")

    seed_show = seed_sub.add_parser("show-playbook", help="Show a seed playbook")
    seed_show.add_argument("step_number", nargs="?", type=int,
                           help="Playbook step number (0-6), omit to list all")

    # test
    test_p = subparsers.add_parser("test", help="Manage test chain")
    test_sub = test_p.add_subparsers(dest="test_command", help="Test commands")

    test_sub.add_parser("run", help="Run full test chain")
    test_sub.add_parser("show", help="Show test chain overview")

    add_check_p = test_sub.add_parser("add-check", help="Add a manual check")
    add_check_p.add_argument("--description", required=True, help="Check description")
    add_check_p.add_argument("--type", choices=[
        "node_exists", "node_count", "edge_exists", "node_properties",
        "node_content", "relationship_count"
    ], default="node_exists", help="Verification type (default: node_exists)")
    add_check_p.add_argument("--node-id", help="Node ID to check")
    add_check_p.add_argument("--node-type", help="Node type filter")
    add_check_p.add_argument("--source-id", help="Source ID filter")
    add_check_p.add_argument("--expected-count", type=int, help="Expected exact count")
    add_check_p.add_argument("--min-count", type=int, help="Expected minimum count")
    add_check_p.add_argument("--gate", choices=["blocking", "warning"],
                             default="blocking", help="Gate level (default: blocking)")

    # feedback
    feedback_p = subparsers.add_parser("feedback", help="Submit and manage model feedback")
    feedback_sub = feedback_p.add_subparsers(dest="feedback_command", help="Feedback commands")

    fb_submit = feedback_sub.add_parser("submit", help="Submit feedback")
    fb_submit.add_argument("--kind", required=True,
                           choices=["reingest", "correction", "gap", "general"],
                           help="Feedback kind")
    fb_submit.add_argument("--source", help="Source ID (required for reingest)")
    fb_submit.add_argument("--message", required=True, help="Feedback message")
    fb_submit.add_argument("--author", required=True, help="Author name")
    fb_submit.add_argument("--refs", nargs="*", help="Referenced node/edge IDs")

    fb_list = feedback_sub.add_parser("list", help="List feedback tasks")
    fb_list.add_argument("--status", help="Filter by status (pending/completed)")
    fb_list.add_argument("--kind", help="Filter by feedback kind")

    fb_show = feedback_sub.add_parser("show", help="Show feedback task details")
    fb_show.add_argument("task_id", help="Feedback task ID")

    # review
    review_p = subparsers.add_parser("review", help="Manage sketch change reviews")
    review_sub = review_p.add_subparsers(dest="review_command", help="Review commands")

    review_sub.add_parser("show", help="Show pending sketch review")
    review_sub.add_parser("approve", help="Approve pending sketch changes")

    review_reject = review_sub.add_parser("reject", help="Reject pending sketch changes")
    review_reject.add_argument("--feedback", help="Feedback for the rejection")

    # resume
    resume_p = subparsers.add_parser("resume", help="Resume a paused pipeline")
    resume_p.add_argument("task_id", help="Task ID to resume")

    # control
    control_p = subparsers.add_parser("control", help="Manage project control configuration")
    control_sub = control_p.add_subparsers(dest="control_command", help="Control commands")

    control_sub.add_parser("show", help="Show control configuration")

    control_init = control_sub.add_parser("init", help="Initialize control.json")
    control_init.add_argument("--force", action="store_true",
                              help="Overwrite existing control.json")

    control_sub.add_parser("validate", help="Validate control configuration")

    control_set = control_sub.add_parser("set-model", help="Set model for a task")
    control_set.add_argument("--task", required=True,
                             choices=["agent-review", "transform-fallback", "verification"],
                             help="Task type")
    control_set.add_argument("--model", required=True, help="Model name")
    control_set.add_argument("--source", help="Source type (for source-specific override)")

    # setup
    setup_p = subparsers.add_parser("setup", help="Configure BAM settings")
    setup_sub = setup_p.add_subparsers(dest="setup_command", help="Setup commands")

    setup_sub.add_parser("wizard", help="Interactive setup wizard for first-time users")
    setup_sub.add_parser("show", help="Show current configuration")

    setup_llm = setup_sub.add_parser("llm", help="Configure LLM provider")
    setup_llm.add_argument("--provider", default="claude",
                           choices=["claude", "copilot", "mock"],
                           help="LLM provider: claude (Anthropic), copilot (GitHub), mock (testing)")
    setup_llm.add_argument("--api-key", help="API key for the provider")
    setup_llm.add_argument("--model", help="Model name override")
    setup_llm.add_argument("--test", action="store_true",
                           help="Test connection with a real API call")

    # list-projects
    list_p = subparsers.add_parser("list-projects", help="List projects in a directory")
    list_p.add_argument("projects_dir", help="Directory containing project folders")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # First-time user detection (only for commands that need LLM)
    # This check is intentionally narrow - only triggers for agent-driven pipeline
    if args.command == "ingest":
        pipeline = getattr(args, 'pipeline', None)
        if pipeline == "agent-driven":
            from .setup_wizard import is_first_time_user, check_first_time_and_prompt
            if is_first_time_user():
                check_first_time_and_prompt()

    # Validate --project for commands that need it
    needs_project = {"ingest", "stats", "info", "plan", "test", "review", "resume", "feedback", "control"}
    if args.command in needs_project and not args.project:
        # Also accept --project on init
        parser.error(f"--project is required for '{args.command}'")

    if args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "info":
        cmd_info(args)
    elif args.command == "plan":
        if not args.plan_command:
            plan_p.print_help()
        else:
            cmd_plan(args)
    elif args.command == "test":
        if not args.test_command:
            test_p.print_help()
        else:
            cmd_test(args)
    elif args.command == "seed":
        if not args.seed_command:
            seed_p.print_help()
        else:
            cmd_seed(args)
    elif args.command == "feedback":
        if not args.feedback_command:
            feedback_p.print_help()
        else:
            cmd_feedback(args)
    elif args.command == "review":
        if not args.review_command:
            review_p.print_help()
        else:
            cmd_review(args)
    elif args.command == "resume":
        cmd_resume(args)
    elif args.command == "control":
        if not args.control_command:
            control_p.print_help()
        else:
            cmd_control(args)
    elif args.command == "setup":
        if not args.setup_command:
            setup_p.print_help()
        else:
            cmd_setup(args)
    elif args.command == "list-projects":
        cmd_list_projects(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
