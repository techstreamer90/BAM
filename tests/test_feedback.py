"""
Tests for BAM Feedback System.

Tests feedback task creation, auto-processing rules, and listing/filtering.
"""

import json
import tempfile
import unittest
from pathlib import Path

from bam.project import init_project
from bam.orchestrator import Orchestrator


def _setup_project(tmp_dir: str, feedback_config: dict = None) -> str:
    """Create a minimal project and optionally patch feedback config."""
    init_project(tmp_dir, name="test-feedback-project")

    if feedback_config:
        project_path = Path(tmp_dir) / "project.json"
        with open(project_path, "r") as f:
            config = json.load(f)
        config["feedback"] = feedback_config
        with open(project_path, "w") as f:
            json.dump(config, f, indent=2)

    return tmp_dir


class TestCreateFeedbackTask(unittest.TestCase):
    """Tests for creating feedback tasks."""

    def test_create_feedback_task(self):
        """Creating a feedback task stores it correctly in tasks.json."""
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            orch = Orchestrator(tmp)

            task = orch.create_feedback_task(
                kind="correction",
                message="Node X has wrong label",
                author="alice",
                source_id="src-1",
                refs=["node-001", "edge-002"],
            )

            self.assertEqual(task["type"], "feedback")
            self.assertIn("task-feedback-", task["id"])
            self.assertEqual(task["sourceId"], "src-1")
            self.assertEqual(task["metadata"]["feedbackKind"], "correction")
            self.assertEqual(task["metadata"]["feedbackMessage"], "Node X has wrong label")
            self.assertEqual(task["metadata"]["feedbackAuthor"], "alice")
            self.assertEqual(task["metadata"]["feedbackRefs"], ["node-001", "edge-002"])

            # Verify persisted
            with open(Path(tmp) / "tasks.json") as f:
                data = json.load(f)
            stored = [t for t in data["tasks"] if t["id"] == task["id"]]
            self.assertEqual(len(stored), 1)
            self.assertEqual(stored[0]["type"], "feedback")


class TestFeedbackTaskNoPipelineStages(unittest.TestCase):
    """Feedback tasks should have no pipeline stages."""

    def test_feedback_task_no_pipeline_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            orch = Orchestrator(tmp)

            task = orch.create_feedback_task(
                kind="general",
                message="General observation",
                author="bob",
            )

            self.assertIsNone(task["pipelineType"])
            self.assertIsNone(task["stages"]["current"])
            self.assertEqual(task["stages"]["completed"], [])
            self.assertEqual(task["stages"]["remaining"], [])


class TestFeedbackReingestAutoProcess(unittest.TestCase):
    """Reingest feedback should auto-create an ingestion task when approved."""

    def test_feedback_reingest_auto_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp, feedback_config={
                "autoReingestSources": ["jama-requirements"],
                "autoApproveKinds": ["reingest"],
                "requireReviewKinds": ["correction", "gap", "general"],
            })
            orch = Orchestrator(tmp)

            task = orch.create_feedback_task(
                kind="reingest",
                message="New requirements added",
                author="tom",
                source_id="jama-requirements",
            )
            result = orch.process_feedback(task["id"])

            self.assertEqual(result["action"], "auto_ingestion")
            self.assertIn("task-ingestion-", result["childTaskId"])

            # Verify the child task exists
            child = orch.task_manager.get_task(result["childTaskId"])
            self.assertIsNotNone(child)
            self.assertEqual(child["type"], "ingestion")
            self.assertEqual(child["pipelineType"], "incremental")
            self.assertEqual(child["sourceId"], "jama-requirements")

            # Verify feedback task is completed
            updated = orch.task_manager.get_task(task["id"])
            self.assertEqual(updated["status"], "completed")
            self.assertEqual(updated["metadata"]["resolution"], "auto_ingestion")


class TestFeedbackCorrectionGoesToHumanQueue(unittest.TestCase):
    """Correction feedback should create an issue and land in human queue."""

    def test_feedback_correction_goes_to_human_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            orch = Orchestrator(tmp)

            task = orch.create_feedback_task(
                kind="correction",
                message="Requirement REQ-42 has wrong parent",
                author="jane",
                source_id="jama-specs",
            )
            result = orch.process_feedback(task["id"])

            self.assertEqual(result["action"], "queued_for_review")
            self.assertIn("issue-", result["issueId"])

            # Verify issue was created
            issue = orch.issue_tracker.get_issue(result["issueId"])
            self.assertIsNotNone(issue)
            self.assertIn("correction", issue["title"])
            self.assertEqual(issue["severity"], "info")

            # Verify human queue has an entry
            hq = orch.issue_tracker.get_human_queue()
            feedback_items = [i for i in hq if i["type"] == "feedback"]
            self.assertGreaterEqual(len(feedback_items), 1)

            # Verify feedback task is completed
            updated = orch.task_manager.get_task(task["id"])
            self.assertEqual(updated["status"], "completed")
            self.assertEqual(updated["metadata"]["resolution"], "queued_for_review")


class TestFeedbackListFilters(unittest.TestCase):
    """Listing feedback tasks supports filtering by kind and status."""

    def test_feedback_list_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            _setup_project(tmp)
            orch = Orchestrator(tmp)

            # Create several feedback tasks
            orch.create_feedback_task(kind="correction", message="Wrong label",
                                     author="a")
            orch.create_feedback_task(kind="gap", message="Missing node",
                                     author="b")
            orch.create_feedback_task(kind="correction", message="Bad edge",
                                     author="c")

            all_tasks = [t for t in orch.task_manager.tasks_data["tasks"]
                         if t["type"] == "feedback"]
            self.assertEqual(len(all_tasks), 3)

            # Filter by kind
            corrections = [t for t in all_tasks
                           if t["metadata"]["feedbackKind"] == "correction"]
            self.assertEqual(len(corrections), 2)

            gaps = [t for t in all_tasks
                    if t["metadata"]["feedbackKind"] == "gap"]
            self.assertEqual(len(gaps), 1)

            # Filter by status (all should be pending at this point)
            pending = [t for t in all_tasks if t["status"] == "pending"]
            self.assertEqual(len(pending), 3)

            # Process one and verify filter
            orch.process_feedback(all_tasks[0]["id"])
            # Re-read tasks after processing
            orch.task_manager.tasks_data = orch.task_manager._load_tasks()
            refreshed = [t for t in orch.task_manager.tasks_data["tasks"]
                         if t["type"] == "feedback"]
            completed = [t for t in refreshed if t["status"] == "completed"]
            self.assertEqual(len(completed), 1)


if __name__ == "__main__":
    unittest.main()
