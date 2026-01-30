"""Tests for the agent_review module."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from bam.agent_review import (
    TransformPlan,
    SketchChangeProposal,
    build_data_sample,
    build_sketch_summary,
    _extract_json,
    run_agent_review,
)
from bam.llm.provider import LLMMessage, LLMResponse


class TestTransformPlan(unittest.TestCase):
    def test_to_dict_from_dict_roundtrip(self):
        plan = TransformPlan(
            source_id="test-src",
            node_mappings=[{
                "sourceField": "items",
                "nodeType": "Requirement",
                "idPattern": "{source_id}-{item.id}",
                "labelField": "name",
                "propertyFields": ["status"],
            }],
            edge_mappings=[{
                "sourceField": "items[*].relationships",
                "edgeType": "DERIVES_FROM",
                "sourceNodePattern": "{source_id}-{item.id}",
                "targetNodePattern": "{source_id}-{rel.targetId}",
            }],
            filters=[],
            metadata={"strategy": "sample"},
        )

        d = plan.to_dict()
        self.assertEqual(d["sourceId"], "test-src")
        self.assertEqual(len(d["nodeMappings"]), 1)
        self.assertEqual(d["nodeMappings"][0]["nodeType"], "Requirement")

        restored = TransformPlan.from_dict(d)
        self.assertEqual(restored.source_id, "test-src")
        self.assertEqual(len(restored.node_mappings), 1)
        self.assertEqual(restored.to_dict(), d)


class TestSketchChangeProposal(unittest.TestCase):
    def test_classify_minor(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "Requirement"}],
            new_edges=[],
            type_changes=[],
            rationale="Adding requirement nodes",
        )

        current_sketch = {
            "nodes": {"n1": {"type": "Requirement"}},
            "edges": {},
        }

        self.assertEqual(proposal.classify(current_sketch), "minor")

    def test_classify_major_new_type(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "NewType"}],
            new_edges=[],
            type_changes=[],
            rationale="New type needed",
        )

        current_sketch = {
            "nodes": {"n1": {"type": "Requirement"}},
            "edges": {},
        }

        self.assertEqual(proposal.classify(current_sketch), "major")

    def test_classify_major_type_change(self):
        proposal = SketchChangeProposal(
            new_nodes=[],
            new_edges=[],
            type_changes=[{"node_id": "n1", "old_type": "Req", "new_type": "Spec"}],
            rationale="Renaming",
        )

        current_sketch = {"nodes": {}, "edges": {}}
        self.assertEqual(proposal.classify(current_sketch), "major")

    def test_classify_major_new_edge_type(self):
        proposal = SketchChangeProposal(
            new_nodes=[],
            new_edges=[{"type": "BRAND_NEW_EDGE"}],
            type_changes=[],
        )

        current_sketch = {
            "nodes": {},
            "edges": {"e1": {"type": "RELATES_TO"}},
        }

        self.assertEqual(proposal.classify(current_sketch), "major")

    def test_to_dict_from_dict(self):
        proposal = SketchChangeProposal(
            new_nodes=[{"type": "Test"}],
            new_edges=[],
            type_changes=[],
            rationale="test",
        )
        d = proposal.to_dict()
        restored = SketchChangeProposal.from_dict(d)
        self.assertEqual(restored.rationale, "test")
        self.assertEqual(len(restored.new_nodes), 1)


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        text = '{"key": "value"}'
        result = _extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_code_fenced_json(self):
        text = '```json\n{"key": "value"}\n```'
        result = _extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_code_fenced_no_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = _extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_malformed_raises(self):
        with self.assertRaises(ValueError):
            _extract_json("this is not json at all")

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"key": "value"}\nDone.'
        result = _extract_json(text)
        self.assertEqual(result, {"key": "value"})


class TestBuildDataSample(unittest.TestCase):
    def test_small_data_returns_all(self):
        data = {"items": [{"id": i, "name": f"item-{i}"} for i in range(5)]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("Total items: 5", result)
        self.assertIn("Collection: items", result)
        self.assertIn("item-0", result)
        os.unlink(f.name)

    def test_large_data_samples(self):
        data = {"items": [{"id": i, "name": f"item-{i}"} for i in range(50)]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("Total items: 50", result)
        # Should include first and last items
        self.assertIn("item-0", result)
        self.assertIn("item-49", result)
        # 10 of 50 sampled
        self.assertIn("10 of 50", result)
        os.unlink(f.name)

    def test_full_strategy(self):
        data = {"items": [{"id": i, "name": f"item-{i}"} for i in range(50)]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name, strategy="full")

        self.assertIn("Total items: 50", result)
        self.assertIn("50 of 50", result)
        os.unlink(f.name)

    def test_root_array(self):
        """JSON array at root level should be handled."""
        data = [{"id": 1, "name": "item-1"}, {"id": 2, "name": "item-2"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("Collection: (root)", result)
        self.assertIn("Total items: 2", result)
        self.assertIn("item-1", result)
        os.unlink(f.name)

    def test_multiple_collections(self):
        """Object with multiple list keys should produce multiple collections."""
        data = {
            "requirements": [{"id": 1}],
            "tests": [{"id": 2}, {"id": 3}],
            "version": "1.0",  # non-list value, should be skipped
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("Collection: requirements", result)
        self.assertIn("Collection: tests", result)
        self.assertNotIn("Collection: version", result)
        os.unlink(f.name)

    def test_non_json_file(self):
        """Non-JSON files should return a raw text preview."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("id,name\n1,item-1\n2,item-2\n")
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("non-JSON", result)
        self.assertIn("id,name", result)
        os.unlink(f.name)

    def test_object_without_lists(self):
        """JSON object with no list values should be treated as single item."""
        data = {"id": 1, "name": "single-item", "status": "active"}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            result = build_data_sample(f.name)

        self.assertIn("Collection: (root)", result)
        self.assertIn("Total items: 1", result)
        self.assertIn("single-item", result)
        os.unlink(f.name)


class TestBuildSketchSummary(unittest.TestCase):
    @patch("bam.graph_manager.get_model_manager")
    def test_empty_model(self, mock_get_mm):
        mock_mm = MagicMock()
        mock_mm.sketch.model = {"metadata": {}, "nodes": {}, "edges": {}}
        mock_mm.list_backends.return_value = ["json"]
        mock_mm.list_colors.return_value = {}
        mock_get_mm.return_value = mock_mm

        result = build_sketch_summary("/fake/project")
        self.assertIn("Total nodes: 0", result)
        self.assertIn("Total edges: 0", result)

    @patch("bam.graph_manager.get_model_manager")
    def test_populated_model(self, mock_get_mm):
        mock_mm = MagicMock()
        mock_mm.sketch.model = {
            "metadata": {},
            "nodes": {
                "n1": {"type": "Requirement"}, "n2": {"type": "Requirement"},
                "n3": {"type": "Requirement"}, "n4": {"type": "Requirement"},
                "n5": {"type": "Requirement"}, "n6": {"type": "Requirement"},
                "n7": {"type": "Requirement"},
                "n8": {"type": "Module"}, "n9": {"type": "Module"},
                "n10": {"type": "Module"},
            },
            "edges": {
                "e1": {"type": "TRACES_TO"}, "e2": {"type": "TRACES_TO"},
                "e3": {"type": "TRACES_TO"}, "e4": {"type": "TRACES_TO"},
                "e5": {"type": "TRACES_TO"},
            },
        }
        mock_mm.list_backends.return_value = ["json"]
        mock_mm.list_colors.return_value = {"conceptual": {}, "design": {}}
        mock_get_mm.return_value = mock_mm

        result = build_sketch_summary("/fake/project")
        self.assertIn("Total nodes: 10", result)
        self.assertIn("Requirement: 7", result)
        self.assertIn("TRACES_TO: 5", result)
        self.assertIn("conceptual", result)


class TestRunAgentReview(unittest.TestCase):
    @patch("bam.agent_review.build_sketch_summary")
    @patch("bam.agent_review.build_data_sample")
    def test_plan_only(self, mock_sample, mock_sketch):
        mock_sketch.return_value = "Sketch: empty"
        mock_sample.return_value = "Data: 5 items"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps({
                "transformPlan": {
                    "sourceId": "test-src",
                    "nodeMappings": [{"sourceField": "items", "nodeType": "Req"}],
                    "edgeMappings": [],
                    "filters": [],
                    "metadata": {},
                },
                "sketchChanges": None,
            }),
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        plan, changes = run_agent_review(
            raw_data_path="/fake/data.json",
            source_id="test-src",
            project_dir="/fake/project",
            provider=mock_provider,
        )

        self.assertEqual(plan.source_id, "test-src")
        self.assertEqual(len(plan.node_mappings), 1)
        self.assertIsNone(changes)

    @patch("bam.agent_review.build_sketch_summary")
    @patch("bam.agent_review.build_data_sample")
    def test_plan_with_minor_changes(self, mock_sample, mock_sketch):
        mock_sketch.return_value = "Sketch: has Requirement type"
        mock_sample.return_value = "Data: 5 items"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps({
                "transformPlan": {
                    "sourceId": "test-src",
                    "nodeMappings": [],
                    "edgeMappings": [],
                },
                "sketchChanges": {
                    "newNodes": [{"type": "Requirement"}],
                    "newEdges": [],
                    "typeChanges": [],
                    "rationale": "Existing type",
                },
            }),
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        plan, changes = run_agent_review(
            raw_data_path="/fake/data.json",
            source_id="test-src",
            project_dir="/fake/project",
            provider=mock_provider,
        )

        self.assertIsNotNone(changes)
        self.assertEqual(len(changes.new_nodes), 1)
        self.assertEqual(changes.rationale, "Existing type")

    @patch("bam.agent_review.build_sketch_summary")
    @patch("bam.agent_review.build_data_sample")
    def test_plan_with_major_changes(self, mock_sample, mock_sketch):
        mock_sketch.return_value = "Sketch: empty"
        mock_sample.return_value = "Data: items"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps({
                "transformPlan": {
                    "sourceId": "test-src",
                    "nodeMappings": [],
                    "edgeMappings": [],
                },
                "sketchChanges": {
                    "newNodes": [{"type": "BrandNewType"}],
                    "newEdges": [{"type": "NEW_EDGE"}],
                    "typeChanges": [],
                    "rationale": "New types needed",
                },
            }),
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        plan, changes = run_agent_review(
            raw_data_path="/fake/data.json",
            source_id="test-src",
            project_dir="/fake/project",
            provider=mock_provider,
        )

        self.assertIsNotNone(changes)
        self.assertEqual(len(changes.new_nodes), 1)
        self.assertEqual(changes.new_nodes[0]["type"], "BrandNewType")

    @patch("bam.agent_review.build_sketch_summary")
    @patch("bam.agent_review.build_data_sample")
    def test_prior_feedback_included_in_prompt(self, mock_sample, mock_sketch):
        """Verify that prior_feedback is appended to the LLM prompt."""
        mock_sketch.return_value = "Sketch: empty"
        mock_sample.return_value = "Data: items"

        mock_provider = MagicMock()
        mock_provider.complete.return_value = LLMResponse(
            content=json.dumps({
                "transformPlan": {
                    "sourceId": "test-src",
                    "nodeMappings": [],
                    "edgeMappings": [],
                },
                "sketchChanges": None,
            }),
            model="test-model",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        run_agent_review(
            raw_data_path="/fake/data.json",
            source_id="test-src",
            project_dir="/fake/project",
            provider=mock_provider,
            prior_feedback="Use existing types instead",
        )

        # Check that the feedback was included in the user message
        call_args = mock_provider.complete.call_args
        messages = call_args.kwargs.get("messages", call_args[0][0] if call_args[0] else [])
        user_content = messages[0].content
        self.assertIn("Prior Review Feedback", user_content)
        self.assertIn("Use existing types instead", user_content)


if __name__ == "__main__":
    unittest.main()
