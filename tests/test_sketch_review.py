"""Tests for the sketch_review module."""

import json
import os
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

from bam.agent_review import SketchChangeProposal
from bam.sketch_review import SketchReviewManager


class TestSketchReviewManager(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.mgr = SketchReviewManager(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_no_review_initially(self):
        self.assertFalse(self.mgr.has_pending_review())
        self.assertIsNone(self.mgr.get_review())

    def test_create_review(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "NewType", "description": "A new node type"}],
            new_edges=[],
            type_changes=[],
            rationale="Needed for new data source",
        )

        review = self.mgr.create_review(proposal, run_id="run-001", task_id="task-001")

        self.assertEqual(review["status"], "pending")
        self.assertEqual(review["taskId"], "task-001")
        self.assertEqual(review["runId"], "run-001")
        self.assertTrue(self.mgr.has_pending_review())

    def test_show(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "NewType", "description": "A new type"}],
            new_edges=[{"type": "NEW_EDGE", "description": "A new edge"}],
            type_changes=[],
            rationale="Test rationale",
        )
        self.mgr.create_review(proposal, run_id="run-001", task_id="task-001")

        output = self.mgr.show()
        self.assertIn("pending", output)
        self.assertIn("NewType", output)
        self.assertIn("NEW_EDGE", output)
        self.assertIn("Test rationale", output)

    def test_show_no_review(self):
        output = self.mgr.show()
        self.assertIn("No sketch review found", output)

    def test_approve(self):
        # Create a project.json so _register_types can update it
        config = {
            "name": "test-project",
            "storage": {
                "colors": {
                    "conceptual": {
                        "description": "Conceptual artifacts",
                        "node_types": ["Requirement"],
                    }
                }
            },
        }
        with open(os.path.join(self.tmpdir, "project.json"), "w") as f:
            json.dump(config, f)

        proposal = SketchChangeProposal(
            new_nodes=[{"type": "TestNode", "description": "Test"}],
            new_edges=[{"type": "TEST_EDGE", "description": "Test edge"}],
            type_changes=[],
            rationale="Test",
        )
        self.mgr.create_review(proposal, run_id="run-001", task_id="task-001")

        review = self.mgr.approve()

        self.assertEqual(review["status"], "approved")
        self.assertEqual(review["decision"], "approved")
        self.assertIsNotNone(review["decidedAt"])
        self.assertFalse(self.mgr.has_pending_review())

        # Verify types were registered in project.json config
        with open(os.path.join(self.tmpdir, "project.json")) as f:
            updated_config = json.load(f)

        # New node type should be in the "default" color
        default_types = updated_config["storage"]["colors"]["default"]["node_types"]
        self.assertIn("TestNode", default_types)

        # New edge type should be registered
        edge_types = updated_config["storage"]["registered_edge_types"]
        self.assertIn("TEST_EDGE", edge_types)

        # Existing config should be preserved
        self.assertIn("Requirement",
                       updated_config["storage"]["colors"]["conceptual"]["node_types"])

    def test_reject(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "TestNode"}],
            new_edges=[],
            type_changes=[],
            rationale="Test",
        )
        self.mgr.create_review(proposal, run_id="run-001", task_id="task-001")

        review = self.mgr.reject(feedback="Not needed")

        self.assertEqual(review["status"], "rejected")
        self.assertEqual(review["decision"], "rejected")
        self.assertEqual(review["feedback"], "Not needed")
        self.assertFalse(self.mgr.has_pending_review())

    def test_approve_without_pending_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.approve()

    def test_reject_without_pending_raises(self):
        with self.assertRaises(ValueError):
            self.mgr.reject()

    def test_approve_already_decided_raises(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "TestNode"}],
            new_edges=[],
            type_changes=[],
        )
        self.mgr.create_review(proposal, run_id="run-001", task_id="task-001")
        self.mgr.reject()

        with self.assertRaises(ValueError):
            self.mgr.approve()


if __name__ == "__main__":
    unittest.main()
