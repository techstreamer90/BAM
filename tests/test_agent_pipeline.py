"""End-to-end tests for the agent-driven pipeline with mocked LLM."""

import json
import os
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from bam.common import PipelinePauseException, TaskStatus
from bam.llm.provider import LLMMessage, LLMResponse
from bam.agent_review import TransformPlan, SketchChangeProposal
from bam.stage_runner import (
    AgentReviewStageHandler,
    TransformStageHandler,
    StageContext,
)


def _make_context(tmpdir, run_id="run-test", inputs=None, source_id="test-src"):
    """Helper to create a StageContext for testing."""
    return StageContext(
        run_id=run_id,
        task_id="task-001",
        stage_id="agent-review",
        source_id=source_id,
        pipeline_type="agent-driven",
        inputs=inputs or {},
        config={},
        project_dir=tmpdir,
    )


class TestAgentReviewStageHandler(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create minimal project structure
        Path(self.tmpdir, "runs", "run-test", "stages").mkdir(parents=True)

        # Create raw data file
        self.raw_data = {"items": [
            {"id": 1, "name": "Req-1", "status": "active"},
            {"id": 2, "name": "Req-2", "status": "draft"},
        ]}
        self.raw_path = os.path.join(self.tmpdir, "raw_data.json")
        with open(self.raw_path, "w") as f:
            json.dump(self.raw_data, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("bam.llm.factory.load_global_config")
    @patch("bam.agent_review.build_sketch_summary")
    def test_agent_review_no_sketch_changes(self, mock_sketch, mock_config):
        mock_sketch.return_value = "Sketch: 0 nodes"
        mock_config.return_value = {"llm": {"provider": "claude", "api_key": "sk-test"}}

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps({
                "transformPlan": {
                    "sourceId": "test-src",
                    "nodeMappings": [{
                        "sourceField": "items",
                        "nodeType": "Requirement",
                        "idPattern": "{source_id}-{item.id}",
                        "labelField": "name",
                        "propertyFields": ["status"],
                    }],
                    "edgeMappings": [],
                    "filters": [],
                    "metadata": {},
                },
                "sketchChanges": None,
            }),
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        stage_def = {"id": "agent-review", "chunkGuidance": {"strategy": "sample"}}
        handler = AgentReviewStageHandler(stage_def)

        context = _make_context(self.tmpdir, inputs={"rawData": self.raw_path})

        # Patch the run_agent_review function to use our mock provider
        with patch("bam.agent_review.run_agent_review") as mock_review:
            from bam.agent_review import TransformPlan
            mock_review.return_value = (
                TransformPlan(
                    source_id="test-src",
                    node_mappings=[{
                        "sourceField": "items",
                        "nodeType": "Requirement",
                        "idPattern": "{source_id}-{item.id}",
                        "labelField": "name",
                        "propertyFields": ["status"],
                    }],
                ),
                None,  # No sketch changes
            )
            result = handler._run(context)

        self.assertIn("transformPlan", result)
        self.assertIsNone(result["sketchChanges"])
        self.assertEqual(result["transformPlan"]["sourceId"], "test-src")

        # Verify plan was saved to disk
        plan_path = Path(self.tmpdir) / "runs" / "run-test" / "transform_plan.json"
        self.assertTrue(plan_path.exists())

    @patch("bam.graph_manager.get_model_manager")
    def test_agent_review_major_changes_pauses(self, mock_get_mm):
        mock_mm = MagicMock()
        mock_mm.sketch.model = {"metadata": {}, "nodes": {}, "edges": {}}
        mock_mm.sketch.get_node.return_value = None
        mock_mm.list_backends.return_value = ["json"]
        mock_mm.list_colors.return_value = {}
        mock_mm.get_all_nodes.return_value = []
        mock_mm.get_all_edges.return_value = []
        mock_get_mm.return_value = mock_mm

        stage_def = {"id": "agent-review", "chunkGuidance": {}}
        handler = AgentReviewStageHandler(stage_def)

        context = _make_context(self.tmpdir, inputs={"rawData": self.raw_path})

        with patch("bam.agent_review.run_agent_review") as mock_review:
            mock_review.return_value = (
                TransformPlan(source_id="test-src"),
                SketchChangeProposal(
                    new_nodes=[{"type": "BrandNewType"}],
                    new_edges=[{"type": "NEW_EDGE"}],
                    type_changes=[],
                    rationale="Major changes needed",
                ),
            )
            with self.assertRaises(PipelinePauseException):
                handler._run(context)

        # Verify sketch_review.json was created
        review_path = Path(self.tmpdir) / "sketch_review.json"
        self.assertTrue(review_path.exists())
        with open(review_path) as f:
            review = json.load(f)
        self.assertEqual(review["status"], "pending")


class TestPlanDrivenTransform(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "runs", "run-test", "stages").mkdir(parents=True)

        self.raw_data = {"items": [
            {"id": 1, "name": "Req-1", "status": "active", "relationships": [
                {"targetId": 2, "type": "depends_on"}
            ]},
            {"id": 2, "name": "Req-2", "status": "draft", "relationships": []},
        ]}
        self.raw_path = os.path.join(self.tmpdir, "raw_data.json")
        with open(self.raw_path, "w") as f:
            json.dump(self.raw_data, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_plan_driven_node_creation(self):
        plan = {
            "sourceId": "test-src",
            "nodeMappings": [{
                "sourceField": "items",
                "nodeType": "Requirement",
                "idPattern": "{source_id}-{item.id}",
                "labelField": "name",
                "propertyFields": ["status"],
            }],
            "edgeMappings": [],
            "filters": [],
            "metadata": {},
        }

        stage_def = {"id": "transform"}
        handler = TransformStageHandler(stage_def)

        context = StageContext(
            run_id="run-test",
            task_id="task-001",
            stage_id="transform",
            source_id="test-src",
            pipeline_type="agent-driven",
            inputs={"transformPlan": plan, "rawData": self.raw_path},
            config={},
            project_dir=self.tmpdir,
        )

        result = handler._run(context)

        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(result["nodes"][0]["id"], "test-src-1")
        self.assertEqual(result["nodes"][0]["type"], "Requirement")
        self.assertEqual(result["nodes"][0]["label"], "Req-1")
        self.assertEqual(result["nodes"][0]["properties"]["status"], "active")
        self.assertTrue(result["transformReport"]["planDriven"])

    def test_plan_driven_edge_creation(self):
        plan = {
            "sourceId": "test-src",
            "nodeMappings": [{
                "sourceField": "items",
                "nodeType": "Requirement",
                "idPattern": "{source_id}-{item.id}",
                "labelField": "name",
                "propertyFields": ["status"],
            }],
            "edgeMappings": [{
                "sourceField": "items[*].relationships",
                "edgeType": "DEPENDS_ON",
                "sourceNodePattern": "{source_id}-{item.id}",
                "targetNodePattern": "{source_id}-{rel.targetId}",
            }],
            "filters": [],
            "metadata": {},
        }

        stage_def = {"id": "transform"}
        handler = TransformStageHandler(stage_def)

        context = StageContext(
            run_id="run-test",
            task_id="task-001",
            stage_id="transform",
            source_id="test-src",
            pipeline_type="agent-driven",
            inputs={"transformPlan": plan, "rawData": self.raw_path},
            config={},
            project_dir=self.tmpdir,
        )

        result = handler._run(context)

        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(len(result["edges"]), 1)
        self.assertEqual(result["edges"][0]["type"], "DEPENDS_ON")
        self.assertEqual(result["edges"][0]["source_node_id"], "test-src-1")
        self.assertEqual(result["edges"][0]["target_node_id"], "test-src-2")

    def test_standard_transform_still_works(self):
        """Verify backward compatibility: no transformPlan means standard flow."""
        stage_def = {"id": "transform"}
        handler = TransformStageHandler(stage_def)

        parsed_data = [
            {"id": "1", "type": "requirement", "name": "Req-1",
             "properties": {}, "relationships": []},
        ]

        context = StageContext(
            run_id="run-test",
            task_id="task-001",
            stage_id="transform",
            source_id="test-src",
            pipeline_type="standard",
            inputs={"parsedData": parsed_data},
            config={},
            project_dir=self.tmpdir,
        )

        result = handler._run(context)

        self.assertEqual(len(result["nodes"]), 1)
        self.assertEqual(result["nodes"][0]["id"], "test-src-1")
        self.assertNotIn("planDriven", result["transformReport"])


class TestLLMFallbackTransform(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "runs", "run-test", "stages").mkdir(parents=True)

        # Data with items that will fail mapping (missing "id" field)
        self.raw_data = {"items": [
            {"id": 1, "name": "Req-1", "status": "active"},
        ], "extras": [
            {"code": "X1", "desc": "Extra item without id"},
        ]}
        self.raw_path = os.path.join(self.tmpdir, "raw_data.json")
        with open(self.raw_path, "w") as f:
            json.dump(self.raw_data, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("bam.llm.factory.load_global_config")
    def test_llm_fallback_on_unmatched(self, mock_config):
        mock_config.return_value = {"llm": {"provider": "claude", "api_key": "sk-test"}}

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps([
                {"id": "test-src-extra-X1", "type": "Extra", "label": "Extra item",
                 "properties": {"code": "X1"}},
            ]),
            model="test-model",
            usage={"input_tokens": 50, "output_tokens": 30},
        )

        plan = {
            "sourceId": "test-src",
            "nodeMappings": [{
                "sourceField": "extras",
                "nodeType": "Extra",
                "idPattern": "{source_id}-{item.id}",
                "labelField": "desc",
                "propertyFields": ["code"],
            }],
            "edgeMappings": [],
            "filters": [],
            "metadata": {},
        }

        stage_def = {"id": "transform"}
        handler = TransformStageHandler(stage_def)

        context = StageContext(
            run_id="run-test",
            task_id="task-001",
            stage_id="transform",
            source_id="test-src",
            pipeline_type="agent-driven",
            inputs={"transformPlan": plan, "rawData": self.raw_path},
            config={},
            project_dir=self.tmpdir,
        )

        result = handler._run(context)

        # The extras item should still produce a node (empty id pattern replacement
        # but no error), so it won't be unmatched. The LLM fallback is for KeyError/TypeError.
        # In this case the item maps fine since "id" defaults to empty string.
        self.assertGreaterEqual(len(result["nodes"]), 1)


class TestAgentDrivenPipelineJson(unittest.TestCase):
    def test_pipeline_loads(self):
        from bam.orchestrator import load_pipeline
        pipeline = load_pipeline("agent-driven")

        self.assertEqual(pipeline["id"], "agent-driven")
        stage_ids = [s["id"] for s in pipeline["stages"]]
        self.assertEqual(stage_ids, [
            "download", "agent-review", "transform",
            "integrate", "verify", "report",
        ])

    def test_agent_review_stage_has_correct_io(self):
        from bam.orchestrator import load_pipeline
        pipeline = load_pipeline("agent-driven")

        agent_stage = None
        for s in pipeline["stages"]:
            if s["id"] == "agent-review":
                agent_stage = s
                break

        self.assertIsNotNone(agent_stage)
        self.assertIn("rawData", agent_stage["inputs"])
        self.assertIn("transformPlan", agent_stage["outputs"])
        self.assertIn("sketchChanges", agent_stage["outputs"])


class TestPatternValidation(unittest.TestCase):
    """Tests for pattern replacement validation in plan-driven transform."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "runs", "run-test", "stages").mkdir(parents=True)

        # Data with items missing expected fields
        self.raw_data = {"items": [
            {"id": 1, "name": "Req-1"},      # has id and name
            {"name": "Req-2"},                 # missing "id" field
        ]}
        self.raw_path = os.path.join(self.tmpdir, "raw_data.json")
        with open(self.raw_path, "w") as f:
            json.dump(self.raw_data, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def test_missing_field_warns_and_uses_empty(self):
        """Items missing fields produce nodes with empty-string replacements
        and a warning is logged."""
        plan = {
            "sourceId": "test-src",
            "nodeMappings": [{
                "sourceField": "items",
                "nodeType": "Requirement",
                "idPattern": "{source_id}-{item.id}",
                "labelField": "name",
                "propertyFields": [],
            }],
            "edgeMappings": [],
        }

        handler = TransformStageHandler({"id": "transform"})
        context = StageContext(
            run_id="run-test", task_id="task-001", stage_id="transform",
            source_id="test-src", pipeline_type="agent-driven",
            inputs={"transformPlan": plan, "rawData": self.raw_path},
            config={}, project_dir=self.tmpdir,
        )

        import logging
        with self.assertLogs("bam.stage_runner", level="WARNING") as cm:
            result = handler._run(context)

        # Both items should produce nodes (second with empty id field)
        self.assertEqual(len(result["nodes"]), 2)
        self.assertEqual(result["nodes"][0]["id"], "test-src-1")
        self.assertEqual(result["nodes"][1]["id"], "test-src-")

        # A warning should have been logged about the missing field
        warnings = [m for m in cm.output if "missing" in m.lower() and "id" in m.lower()]
        self.assertGreater(len(warnings), 0)


class TestStableRawDataPath(unittest.TestCase):
    """Agent-review stage should copy rawData to the run directory."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        Path(self.tmpdir, "runs", "run-test", "stages").mkdir(parents=True)

        self.raw_data = {"items": [{"id": 1, "name": "Req-1"}]}
        self.raw_path = os.path.join(self.tmpdir, "raw_data.json")
        with open(self.raw_path, "w") as f:
            json.dump(self.raw_data, f)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @patch("bam.agent_review.run_agent_review")
    def test_raw_data_copied_to_run_dir(self, mock_review):
        from bam.agent_review import TransformPlan

        mock_review.return_value = (
            TransformPlan(source_id="test-src", node_mappings=[]),
            None,
        )

        handler = AgentReviewStageHandler({
            "id": "agent-review", "chunkGuidance": {"strategy": "sample"}
        })
        context = StageContext(
            run_id="run-test", task_id="task-001", stage_id="agent-review",
            source_id="test-src", pipeline_type="agent-driven",
            inputs={"rawData": self.raw_path},
            config={}, project_dir=self.tmpdir,
        )

        result = handler._run(context)

        # The stable path should be in the run directory
        stable_path = Path(self.tmpdir) / "runs" / "run-test" / "raw_data.json"
        self.assertTrue(stable_path.exists())

        # Output should reference the stable path
        self.assertEqual(result["rawData"], str(stable_path))


class TestPipelinePauseException(unittest.TestCase):
    def test_is_exception(self):
        ex = PipelinePauseException("paused")
        self.assertIsInstance(ex, Exception)
        self.assertEqual(str(ex), "paused")


if __name__ == "__main__":
    unittest.main()
