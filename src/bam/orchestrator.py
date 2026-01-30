"""
BAM Ingestion Orchestrator

Main pipeline orchestrator for BAM data ingestion.
Manages task execution, stage sequencing, and error handling.

All project data lives outside BAM. Every class requires project_dir.
Tool-level resources (pipelines, prompts) remain in the BAM tool directory.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import asdict
import uuid

from .common import (
    Issue, IssueSeverity, IssueStatus, IssueType, TaskStatus, StageResult,
    FeedbackKind, PipelinePauseException, setup_logging
)
from .issue_tracker import IssueTracker
from .stage_runner import StageRunner, StageContext
from ._paths import PIPELINES_DIR, PROMPTS_DIR

logger = logging.getLogger("bam.orchestrator")


def load_pipeline(pipeline_type: str) -> dict:
    """Load a pipeline definition by type (from tool directory)."""
    pipeline_path = PIPELINES_DIR / f"{pipeline_type}.json"
    with open(pipeline_path, 'r') as f:
        return json.load(f)


class ConfigManager:
    """Manages orchestrator configuration."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        with open(self.project_dir / "project.json", 'r') as f:
            return json.load(f)

    def get(self, *keys, default=None) -> Any:
        value = self.config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value


class TaskManager:
    """Manages the task queue."""

    def __init__(self, project_dir: str):
        self._tasks_path = Path(project_dir) / "tasks.json"
        self.tasks_data = self._load_tasks()

    def _load_tasks(self) -> dict:
        with open(self._tasks_path, 'r') as f:
            return json.load(f)

    def _save_tasks(self):
        with open(self._tasks_path, 'w') as f:
            json.dump(self.tasks_data, f, indent=2)

    def create_task(self, task_type: str, pipeline_type: Optional[str], source_id: str,
                    metadata: dict = None) -> dict:
        """Create a new task.

        Args:
            task_type: Task type (e.g. "ingestion", "feedback").
            pipeline_type: Pipeline to load stages from, or None for
                non-pipeline tasks (e.g. feedback).
            source_id: Related source ID (may be empty for feedback).
            metadata: Arbitrary task metadata.
        """
        self.tasks_data["lastTaskId"] += 1
        task_id = f"task-{task_type}-{self.tasks_data['lastTaskId']:03d}"

        if pipeline_type is not None:
            # Load pipeline to get stages
            pipeline = load_pipeline(pipeline_type)
            stages = [s["id"] for s in pipeline["stages"]]
        else:
            stages = []

        task = {
            "id": task_id,
            "type": task_type,
            "pipelineType": pipeline_type,
            "sourceId": source_id,
            "status": TaskStatus.PENDING.value,
            "createdAt": datetime.utcnow().isoformat(),
            "stages": {
                "current": None,
                "completed": [],
                "remaining": stages
            },
            "stageResults": {},
            "metadata": metadata or {}
        }

        self.tasks_data["tasks"].append(task)
        self._save_tasks()
        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        for task in self.tasks_data["tasks"]:
            if task["id"] == task_id:
                return task
        return None

    def get_pending_tasks(self) -> list:
        return [t for t in self.tasks_data["tasks"]
                if t["status"] == TaskStatus.PENDING.value]

    def update_task(self, task_id: str, updates: dict):
        for i, task in enumerate(self.tasks_data["tasks"]):
            if task["id"] == task_id:
                self.tasks_data["tasks"][i].update(updates)
                self._save_tasks()
                return

    def advance_stage(self, task_id: str, stage_result: StageResult):
        """Mark current stage complete and advance to next."""
        task = self.get_task(task_id)
        if not task:
            return

        current = task["stages"]["current"]
        if current:
            task["stages"]["completed"].append(current)
            task["stageResults"][current] = asdict(stage_result)

        if task["stages"]["remaining"]:
            task["stages"]["current"] = task["stages"]["remaining"].pop(0)
        else:
            task["stages"]["current"] = None
            task["status"] = TaskStatus.COMPLETED.value

        self._save_tasks()


class HistoryManager:
    """Manages pipeline run history."""

    def __init__(self, project_dir: str):
        self._project_dir = Path(project_dir)
        self._history_path = self._project_dir / "history.json"
        self._runs_dir = self._project_dir / "runs"
        self.history_data = self._load_history()

    def _load_history(self) -> dict:
        with open(self._history_path, 'r') as f:
            return json.load(f)

    def _save_history(self):
        with open(self._history_path, 'w') as f:
            json.dump(self.history_data, f, indent=2)

    def start_run(self, task_id: str, pipeline_type: str, source_id: str) -> str:
        """Record the start of a pipeline run."""
        run_id = f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"

        run = {
            "id": run_id,
            "taskId": task_id,
            "pipelineType": pipeline_type,
            "sourceId": source_id,
            "status": "running",
            "startedAt": datetime.utcnow().isoformat(),
            "completedAt": None,
            "stagesCompleted": 0,
            "stagesTotal": 0
        }

        self.history_data["runs"].append(run)
        self._save_history()

        # Create run directory
        run_dir = self._runs_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "stages").mkdir(exist_ok=True)

        # Write manifest
        manifest = {
            "runId": run_id,
            "taskId": task_id,
            "pipelineType": pipeline_type,
            "sourceId": source_id,
            "startedAt": run["startedAt"]
        }
        with open(run_dir / "manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)

        return run_id

    def complete_run(self, run_id: str, status: str, report: str = None):
        """Record the completion of a pipeline run."""
        for i, run in enumerate(self.history_data["runs"]):
            if run["id"] == run_id:
                self.history_data["runs"][i]["status"] = status
                self.history_data["runs"][i]["completedAt"] = datetime.utcnow().isoformat()
                self._save_history()

                if report:
                    run_dir = self._runs_dir / run_id
                    with open(run_dir / "report.md", 'w') as f:
                        f.write(report)
                return


class Orchestrator:
    """Main pipeline orchestrator."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.config = ConfigManager(project_dir)
        self.task_manager = TaskManager(project_dir)
        self.issue_tracker = IssueTracker(project_dir)
        self.history_manager = HistoryManager(project_dir)
        self.stage_runner = StageRunner(project_dir)

    def create_ingestion_task(self, source_id: str, pipeline_type: str = "standard",
                              metadata: dict = None) -> dict:
        """Create a new ingestion task."""
        return self.task_manager.create_task(
            task_type="ingestion",
            pipeline_type=pipeline_type,
            source_id=source_id,
            metadata=metadata
        )

    def create_feedback_task(self, kind: str, message: str, author: str,
                             source_id: str = "", refs: list = None) -> dict:
        """Create a feedback task.

        Args:
            kind: One of FeedbackKind values.
            message: Free-text feedback description.
            author: Who submitted the feedback.
            source_id: Optional source ID (required for reingest).
            refs: Optional list of node/edge IDs.

        Returns:
            The created task dict.
        """
        metadata = {
            "feedbackKind": kind,
            "feedbackMessage": message,
            "feedbackAuthor": author,
            "feedbackRefs": refs or [],
        }
        task = self.task_manager.create_task(
            task_type="feedback",
            pipeline_type=None,
            source_id=source_id,
            metadata=metadata,
        )
        return task

    def process_feedback(self, task_id: str) -> dict:
        """Process a feedback task according to provider rules.

        If the feedback kind is auto-approved (e.g. reingest), creates a child
        ingestion task. Otherwise creates an issue and adds to the human queue.

        Returns:
            A dict with "action" key ("auto_ingestion" or "queued_for_review")
            and related details.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        kind = task["metadata"].get("feedbackKind", "")
        source_id = task.get("sourceId", "")

        # Load feedback rules from project config
        feedback_config = self.config.get("feedback") or {}
        auto_approve_kinds = feedback_config.get("autoApproveKinds", [])
        auto_reingest_sources = feedback_config.get("autoReingestSources", [])

        # Check if this feedback should be auto-processed
        auto_process = False
        if kind in auto_approve_kinds:
            auto_process = True
        if kind == FeedbackKind.REINGEST.value and source_id in auto_reingest_sources:
            auto_process = True

        if auto_process and kind == FeedbackKind.REINGEST.value and source_id:
            # Create child ingestion task
            child_task = self.task_manager.create_task(
                task_type="ingestion",
                pipeline_type="incremental",
                source_id=source_id,
                metadata={"parentFeedbackTaskId": task_id},
            )
            # Mark feedback task completed
            self.task_manager.update_task(task_id, {
                "status": TaskStatus.COMPLETED.value,
                "metadata": {
                    **task["metadata"],
                    "resolution": "auto_ingestion",
                    "childTaskId": child_task["id"],
                },
            })
            return {
                "action": "auto_ingestion",
                "childTaskId": child_task["id"],
            }

        # Otherwise queue for human review
        issue = Issue(
            type=IssueType.DATA_INCONSISTENCY.value,
            severity=IssueSeverity.INFO.value,
            status=IssueStatus.OPEN.value,
            title=f"Feedback ({kind}): {task['metadata'].get('feedbackMessage', '')[:80]}",
            description=task["metadata"].get("feedbackMessage", ""),
            source_id=source_id or None,
        )
        issue_id = self.issue_tracker.create_issue(issue)

        # Add to human queue
        hq_item = {
            "id": f"hq-{len(self.issue_tracker.human_queue['items']) + 1:04d}",
            "issueId": issue_id,
            "type": "feedback",
            "severity": IssueSeverity.INFO.value,
            "title": issue.title,
            "sourceId": source_id or None,
            "runId": None,
            "addedAt": datetime.utcnow().isoformat(),
            "status": "pending",
            "assignedTo": None,
            "notes": [],
        }
        self.issue_tracker.human_queue["items"].append(hq_item)
        self.issue_tracker._save_human_queue()

        # Mark feedback task completed
        self.task_manager.update_task(task_id, {
            "status": TaskStatus.COMPLETED.value,
            "metadata": {
                **task["metadata"],
                "resolution": "queued_for_review",
                "issueId": issue_id,
            },
        })

        return {
            "action": "queued_for_review",
            "issueId": issue_id,
        }

    def run_task(self, task_id: str, _initial_stage_outputs: dict = None) -> str:
        """Execute a task through its pipeline.

        Args:
            task_id: Task to execute.
            _initial_stage_outputs: Pre-loaded stage outputs from a paused run.
                Used by resume_task to carry forward outputs across the pause.
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        # Check for blocking issues
        blocking = self.issue_tracker.get_blocking_issues()
        if blocking:
            logger.warning("Cannot start task - %d blocking issues exist", len(blocking))
            return None

        # Update task status
        self.task_manager.update_task(task_id, {"status": TaskStatus.RUNNING.value})

        # Load pipeline definition
        pipeline = load_pipeline(task["pipelineType"])

        # Start run
        run_id = self.history_manager.start_run(
            task_id, task["pipelineType"], task["sourceId"]
        )

        # Initialize stage tracking
        if not task["stages"]["current"] and task["stages"]["remaining"]:
            task["stages"]["current"] = task["stages"]["remaining"].pop(0)
            self.task_manager._save_tasks()

        # Execute stages — seed from prior run outputs if resuming
        stage_outputs = dict(_initial_stage_outputs) if _initial_stage_outputs else {}
        final_status = "completed"

        while task["stages"]["current"]:
            stage_id = task["stages"]["current"]
            stage_def = self._get_stage_def(pipeline, stage_id)

            if not stage_def:
                logger.error("Stage definition not found: %s", stage_id)
                break

            logger.info("Running stage: %s", stage_def['name'])

            # Gather inputs from previous stage outputs
            inputs = self._gather_inputs(stage_def, stage_outputs)

            # Build context for the stage runner
            context = StageContext(
                run_id=run_id,
                task_id=task_id,
                stage_id=stage_id,
                source_id=task["sourceId"],
                pipeline_type=task["pipelineType"],
                inputs=inputs,
                config=self.config.config,
                project_dir=self.project_dir,
            )

            try:
                # Run stage
                result = self.stage_runner.run(stage_def, context)
            except PipelinePauseException as e:
                logger.info("Pipeline paused at stage '%s': %s", stage_id, e)
                self.task_manager.update_task(task_id, {
                    "status": TaskStatus.PAUSED.value,
                    "pausedAt": datetime.utcnow().isoformat(),
                    "pausedStage": stage_id,
                    "pauseRunId": run_id,
                })
                # Save stage outputs so far for resume
                self._save_stage_outputs(run_id, stage_outputs)
                self.history_manager.complete_run(run_id, "paused")
                return run_id

            if result.status == "failed":
                self._handle_stage_error(stage_def, task, run_id, result.errors)
                if stage_def.get("onError") == "halt":
                    logger.error("Stage failed with halt policy - stopping pipeline")
                    final_status = "failed"
                    self.task_manager.update_task(task_id, {"status": TaskStatus.FAILED.value})
                    break

            # Store outputs for next stage
            stage_outputs[stage_id] = result.outputs

            # Advance to next stage
            self.task_manager.advance_stage(task_id, result)
            task = self.task_manager.get_task(task_id)

        # Generate report
        report = self._generate_report(task, run_id, stage_outputs)

        # Complete run
        self.history_manager.complete_run(run_id, final_status, report)

        logger.info("Pipeline %s: %s", final_status, run_id)
        return run_id

    def resume_task(self, task_id: str) -> str:
        """Resume a paused task after sketch review."""
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")
        if task["status"] != TaskStatus.PAUSED.value:
            raise ValueError(f"Task is not paused (status: {task['status']})")

        from .sketch_review import SketchReviewManager
        review_mgr = SketchReviewManager(self.project_dir)
        review = review_mgr.get_review()

        if not review:
            raise ValueError("No sketch review found")

        if review["status"] == "pending":
            raise ValueError(
                "Sketch review is still pending. "
                "Use 'bam review approve' or 'bam review reject' first."
            )

        paused_run_id = task.get("pauseRunId", "")

        if review["status"] == "rejected":
            # Re-run agent-review with feedback
            logger.info("Review rejected — re-running agent-review with feedback")

            # Load prior stage outputs so download data is preserved
            prior_outputs = self._load_stage_outputs(paused_run_id)

            # Prefer the stable raw data copy in the run directory
            paused_run_dir = Path(self.project_dir) / "runs" / paused_run_id
            stable_raw = paused_run_dir / "raw_data.json"
            if stable_raw.exists():
                prior_outputs.setdefault("download", {})
                prior_outputs["download"]["rawData"] = str(stable_raw)

            # Inject rejection feedback into context for the re-run
            feedback = review.get("feedback", "")
            if feedback:
                prior_outputs.setdefault("_review_feedback", feedback)

            # Reset task to re-run from agent-review stage
            task["stages"]["current"] = "agent-review"
            self.task_manager.update_task(task_id, {
                "status": TaskStatus.RUNNING.value,
                "stages": task["stages"],
            })
            return self.run_task(task_id, _initial_stage_outputs=prior_outputs)

        # Approved: continue from the stage after the paused stage
        logger.info("Review approved — resuming from transform stage")

        # Load saved stage outputs
        stage_outputs = self._load_stage_outputs(paused_run_id)

        # Load the transform plan from disk
        run_dir = Path(self.project_dir) / "runs" / paused_run_id
        plan_path = run_dir / "transform_plan.json"
        if plan_path.exists():
            with open(plan_path, "r") as f:
                transform_plan = json.load(f)
            # Inject the plan into stage outputs so transform can find it
            stage_outputs.setdefault("agent-review", {})
            stage_outputs["agent-review"]["transformPlan"] = transform_plan

        # Ensure rawData is available for transform, preferring the stable
        # copy that the agent-review handler placed in the run directory
        # (the original temp path may have been cleaned up during the pause).
        stage_outputs.setdefault("agent-review", {})
        stable_raw = run_dir / "raw_data.json"
        if stable_raw.exists():
            stage_outputs["agent-review"]["rawData"] = str(stable_raw)
        else:
            download_outputs = stage_outputs.get("download", {})
            if download_outputs.get("rawData"):
                stage_outputs["agent-review"]["rawData"] = download_outputs["rawData"]

        # Mark the agent-review stage as completed and advance
        from .common import StageResult as _SR
        agent_result = _SR(
            stage_id="agent-review",
            status="completed",
            outputs=stage_outputs.get("agent-review", {}),
        )
        self.task_manager.advance_stage(task_id, agent_result)

        # Update task status and continue with preserved outputs
        self.task_manager.update_task(task_id, {
            "status": TaskStatus.RUNNING.value,
        })

        return self.run_task(task_id, _initial_stage_outputs=stage_outputs)

    def _save_stage_outputs(self, run_id: str, stage_outputs: dict):
        """Save accumulated stage outputs for resume after pause."""
        run_dir = Path(self.project_dir) / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        outputs_path = run_dir / "stage_outputs.json"
        with open(outputs_path, "w") as f:
            json.dump(stage_outputs, f, indent=2, default=str)

    def _load_stage_outputs(self, run_id: str) -> dict:
        """Load saved stage outputs from a paused run."""
        outputs_path = Path(self.project_dir) / "runs" / run_id / "stage_outputs.json"
        if outputs_path.exists():
            with open(outputs_path, "r") as f:
                return json.load(f)
        return {}

    def _get_stage_def(self, pipeline: dict, stage_id: str) -> Optional[dict]:
        for stage in pipeline["stages"]:
            if stage["id"] == stage_id:
                return stage
        return None

    def _handle_stage_error(self, stage_def: dict, task: dict, run_id: str, errors: list):
        """Record a stage failure as an issue."""
        on_error = stage_def.get("onError", "halt")
        severity = IssueSeverity.ERROR if on_error == "halt" else IssueSeverity.WARNING

        issue = Issue(
            type="stage-failure",
            severity=severity.value,
            status=IssueStatus.BLOCKING.value if on_error == "halt" else IssueStatus.OPEN.value,
            title=f"Stage '{stage_def['name']}' failed",
            description="; ".join(errors) if errors else "Unknown error",
            source_id=task["sourceId"],
            run_id=run_id,
            stage_id=stage_def["id"]
        )

        self.issue_tracker.create_issue(issue)

    def _gather_inputs(self, stage_def: dict, stage_outputs: dict) -> dict:
        """Gather inputs for a stage from previous outputs."""
        inputs = {}
        for input_name in stage_def.get("inputs", []):
            # Look through previous stage outputs.  Later stages take
            # precedence (e.g. agent-review's stable rawData path
            # overrides download's temporary path).
            for stage_id, outputs in stage_outputs.items():
                if isinstance(outputs, dict) and input_name in outputs:
                    inputs[input_name] = outputs[input_name]

        # Forward internal keys (e.g. _review_feedback) from top-level
        # stage_outputs so the stage handler can access them.
        for key, value in stage_outputs.items():
            if key.startswith("_"):
                inputs[key] = value

        return inputs

    def _generate_report(self, task: dict, run_id: str, stage_outputs: dict) -> str:
        """Generate a markdown report for the pipeline run."""
        lines = [
            f"# Pipeline Run Report",
            f"",
            f"**Run ID:** {run_id}",
            f"**Task:** {task['id']}",
            f"**Pipeline:** {task['pipelineType']}",
            f"**Source:** {task['sourceId']}",
            f"**Status:** {task['status']}",
            f"",
            f"## Stages",
            f""
        ]

        for stage_id, result in task.get("stageResults", {}).items():
            lines.append(f"### {stage_id}")
            lines.append(f"- Status: {result['status']}")
            lines.append(f"- Started: {result['started_at']}")
            lines.append(f"- Completed: {result.get('completed_at', 'N/A')}")
            if result.get("errors"):
                lines.append(f"- Errors: {result['errors']}")
            lines.append("")

        return "\n".join(lines)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Ingestion Orchestrator")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Create task command
    create_parser = subparsers.add_parser("create", help="Create a new task")
    create_parser.add_argument("source_id", help="Source ID to ingest from")
    create_parser.add_argument("--pipeline", "-p", default="standard",
                               choices=["standard", "incremental", "agent-driven"],
                               help="Pipeline type")

    # Run task command
    run_parser = subparsers.add_parser("run", help="Run a task")
    run_parser.add_argument("task_id", help="Task ID to run")

    # List tasks command
    subparsers.add_parser("list", help="List pending tasks")

    # Status command
    status_parser = subparsers.add_parser("status", help="Get task status")
    status_parser.add_argument("task_id", help="Task ID")

    parser.add_argument("--project", "-P", required=True,
                        help="Path to the BAM project directory")

    args = parser.parse_args()

    orchestrator = Orchestrator(args.project)

    if args.command == "create":
        task = orchestrator.create_ingestion_task(args.source_id, args.pipeline)
        print(f"Created task: {task['id']}")

    elif args.command == "run":
        run_id = orchestrator.run_task(args.task_id)
        if run_id:
            print(f"Run completed: {run_id}")

    elif args.command == "list":
        tasks = orchestrator.task_manager.get_pending_tasks()
        if tasks:
            print("Pending tasks:")
            for t in tasks:
                print(f"  {t['id']} - {t['sourceId']} ({t['pipelineType']})")
        else:
            print("No pending tasks")

    elif args.command == "status":
        task = orchestrator.task_manager.get_task(args.task_id)
        if task:
            print(f"Task: {task['id']}")
            print(f"  Status: {task['status']}")
            print(f"  Pipeline: {task['pipelineType']}")
            print(f"  Source: {task['sourceId']}")
            print(f"  Current stage: {task['stages']['current']}")
            print(f"  Completed: {task['stages']['completed']}")
            print(f"  Remaining: {task['stages']['remaining']}")
        else:
            print(f"Task not found: {args.task_id}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
