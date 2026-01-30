"""
Unit tests for the TestChainManager.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from bam.test_chain import TestChainManager, _sample_items, _raw_to_datapoint


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal project directory structure."""
    # project.json
    (tmp_path / "project.json").write_text(json.dumps({
        "name": "test-project",
        "source_root": "",
        "storage": {
            "sketch": {"path": "model/sketch.json"},
            "colors": {},
            "color_backends": {
                "default": {
                    "type": "json",
                    "colors": [],
                    "path": "model/colors/default.json",
                    "snapshotsDir": "model/colors/snapshots/default",
                }
            }
        }
    }, indent=2))
    # model dir
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "sketch.json").write_text(json.dumps({
        "metadata": {"created": "2025-01-01T00:00:00Z", "lastModified": "2025-01-01T00:00:00Z"},
        "nodes": {
            "product-top": {"id": "product-top", "type": "Product", "label": "Test Product", "source_id": None},
            "subsys-cpu": {"id": "subsys-cpu", "type": "Subsystem", "label": "CPU Core", "source_id": None},
        },
        "edges": {
            "product-contains-cpu": {
                "id": "product-contains-cpu",
                "type": "CONTAINS",
                "source_node_id": "product-top",
                "target_node_id": "subsys-cpu",
                "source_id": None,
            }
        },
    }, indent=2))
    (model_dir / "version.json").write_text(json.dumps({
        "current": "1.0.0", "snapshotCount": 0, "history": []
    }))
    # Color backend dirs
    colors_dir = model_dir / "colors"
    colors_dir.mkdir()
    (colors_dir / "default.json").write_text(json.dumps({"nodes": {}, "edges": {}}, indent=2))
    (colors_dir / "snapshots").mkdir()
    (colors_dir / "snapshots" / "default").mkdir()
    # sketch snapshots dir
    (model_dir / "sketch_snapshots").mkdir()
    return tmp_path


@pytest.fixture
def hardware_template():
    """Return a hardware_product-like template for testing."""
    return {
        "id": "hardware_product",
        "exampleSketch": {
            "nodes": {
                "product-top": {
                    "id": "product-top",
                    "type": "Product",
                    "label": "Example SoC",
                    "source_id": None,
                },
                "subsys-cpu": {
                    "id": "subsys-cpu",
                    "type": "Subsystem",
                    "label": "CPU Core",
                    "source_id": None,
                },
                "subsys-periph": {
                    "id": "subsys-periph",
                    "type": "Subsystem",
                    "label": "Peripherals",
                    "source_id": None,
                },
            },
            "edges": {
                "product-contains-cpu": {
                    "id": "product-contains-cpu",
                    "type": "CONTAINS",
                    "source_node_id": "product-top",
                    "target_node_id": "subsys-cpu",
                    "source_id": None,
                },
                "product-contains-periph": {
                    "id": "product-contains-periph",
                    "type": "CONTAINS",
                    "source_node_id": "product-top",
                    "target_node_id": "subsys-periph",
                    "source_id": None,
                },
            },
        },
    }


class TestCreate:
    def test_create_produces_valid_empty_chain(self, tmp_path):
        mgr = TestChainManager.create(str(tmp_path))
        chain_path = tmp_path / "test_chain.json"
        assert chain_path.exists()

        with open(chain_path) as f:
            data = json.load(f)

        assert data["version"] == "1.0.0"
        assert data["testSets"] == []
        assert "createdAt" in data
        assert "lastModified" in data

    def test_create_and_load_roundtrip(self, tmp_path):
        mgr = TestChainManager.create(str(tmp_path))
        mgr2 = TestChainManager(str(tmp_path))
        loaded = mgr2.load()
        assert loaded["version"] == "1.0.0"
        assert loaded["testSets"] == []


class TestGenerateSketchTests:
    def test_generates_node_and_edge_checks(self, hardware_template):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None  # won't need persistence for generation
        ts = mgr.generate_sketch_tests(hardware_template)

        assert ts["id"] == "sketch-init"
        assert ts["gate"] == "blocking"
        assert ts["generatedBy"] == "init"

        dps = ts["dataPoints"]
        # 3 node checks + 2 edge checks + 2 count aggregates (Product:1, Subsystem:2)
        assert len(dps) == 7

        # Check node existence data points
        node_dps = [dp for dp in dps if dp["type"] == "node_exists"]
        assert len(node_dps) == 3
        node_ids = {dp["query"]["node_id"] for dp in node_dps}
        assert node_ids == {"product-top", "subsys-cpu", "subsys-periph"}

        # Check edge existence data points
        edge_dps = [dp for dp in dps if dp["type"] == "edge_exists"]
        assert len(edge_dps) == 2

        # Check node count aggregates
        count_dps = [dp for dp in dps if dp["type"] == "node_count"]
        assert len(count_dps) == 2
        types_covered = {dp["query"]["node_type"] for dp in count_dps}
        assert types_covered == {"Product", "Subsystem"}

    def test_empty_template_produces_empty_datapoints(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None
        ts = mgr.generate_sketch_tests({})
        assert ts["dataPoints"] == []


class TestGenerateTransformTests:
    def test_with_small_node_list(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None

        nodes = [
            {"id": f"src-{i}", "type": "Requirement", "label": f"Req {i}", "source_id": "jama"}
            for i in range(5)
        ]
        edges = [
            {
                "id": f"edge-{i}",
                "type": "TRACES_TO",
                "source_node_id": f"src-{i}",
                "target_node_id": f"src-{i+1}",
                "source_id": "jama",
            }
            for i in range(4)
        ]

        ts = mgr.generate_transform_tests("jama", nodes, edges)

        assert ts["id"] == "transform-jama"
        assert ts["gate"] == "blocking"

        dps = ts["dataPoints"]
        node_checks = [dp for dp in dps if dp["type"] == "node_exists"]
        edge_checks = [dp for dp in dps if dp["type"] == "edge_exists"]
        count_checks = [dp for dp in dps if dp["type"] == "node_count"]

        # All 5 nodes (under 20 threshold) + 4 edges + 1 type aggregate
        assert len(node_checks) == 5
        assert len(edge_checks) == 4
        assert len(count_checks) == 1
        assert count_checks[0]["expected"]["min_count"] == 5

    def test_sampling_large_node_list(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None

        nodes = [
            {"id": f"n-{i}", "type": "Requirement", "label": f"Req {i}"}
            for i in range(60)
        ]
        ts = mgr.generate_transform_tests("big-src", nodes, [])

        node_checks = [dp for dp in ts["dataPoints"] if dp["type"] == "node_exists"]
        # Should be sampled down to 20
        assert len(node_checks) == 20


class TestGenerateIntegrateTests:
    def test_creates_baseline_per_type(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None

        report = {"nodesAdded": 10, "edgesAdded": 5}
        stats = {
            "totalNodes": 50,
            "nodesByType": {"Requirement": 30, "Feature": 20},
        }

        ts = mgr.generate_integrate_tests("jama-core", report, stats)

        assert ts["id"] == "integrate-jama-core"
        assert ts["gate"] == "warning"

        dps = ts["dataPoints"]
        assert len(dps) == 2
        types = {dp["query"]["node_type"] for dp in dps}
        assert types == {"Requirement", "Feature"}

        req_dp = next(dp for dp in dps if dp["query"]["node_type"] == "Requirement")
        assert req_dp["expected"]["min_count"] == 30


class TestGenerateDownloadTests:
    def test_creates_count_check(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None

        manifest = {"source": "jama-core", "itemCount": 42, "warnings": []}
        ts = mgr.generate_download_tests("jama-core", manifest)

        assert ts["id"] == "download-jama-core"
        assert ts["gate"] == "blocking"
        assert len(ts["dataPoints"]) == 1
        assert ts["dataPoints"][0]["expected"]["min_count"] == 42

    def test_empty_download_no_checks(self):
        mgr = TestChainManager.__new__(TestChainManager)
        mgr._chain = None

        manifest = {"source": "empty", "itemCount": 0}
        ts = mgr.generate_download_tests("empty", manifest)
        assert len(ts["dataPoints"]) == 0


class TestAddManualCheck:
    def test_persists_manual_check(self, tmp_path):
        mgr = TestChainManager.create(str(tmp_path))
        mgr.add_manual_check(
            description="Product node must exist",
            verification_type="node_exists",
            query={"node_id": "product-top"},
            expected={"exists": True, "type": "Product"},
            gate="blocking",
            tags=["manual", "critical"],
        )

        # Reload and verify
        mgr2 = TestChainManager(str(tmp_path))
        mgr2.load()
        sets = mgr2.get_test_sets()
        assert len(sets) == 1
        assert sets[0]["generatedBy"] == "manual"
        assert sets[0]["gate"] == "blocking"
        assert len(sets[0]["dataPoints"]) == 1
        assert sets[0]["dataPoints"][0]["description"] == "Product node must exist"


class TestGateFiltering:
    def test_get_test_sets_by_gate(self, tmp_path):
        mgr = TestChainManager.create(str(tmp_path))

        blocking_set = {
            "id": "blocking-set",
            "name": "Blocking tests",
            "generatedAt": "2025-01-01T00:00:00Z",
            "generatedBy": "test",
            "source_id": None,
            "gate": "blocking",
            "dataPoints": [{"id": "dp1", "type": "node_exists", "description": "test",
                            "query": {"node_id": "x"}, "expected": {"exists": True}}],
        }
        warning_set = {
            "id": "warning-set",
            "name": "Warning tests",
            "generatedAt": "2025-01-01T00:00:00Z",
            "generatedBy": "test",
            "source_id": None,
            "gate": "warning",
            "dataPoints": [{"id": "dp2", "type": "node_count", "description": "count test",
                            "query": {"node_type": "X"}, "expected": {"min_count": 1}}],
        }

        mgr.add_test_set(blocking_set)
        mgr.add_test_set(warning_set)

        all_sets = mgr.get_test_sets()
        assert len(all_sets) == 2

        blocking_only = [ts for ts in all_sets if ts["gate"] == "blocking"]
        warning_only = [ts for ts in all_sets if ts["gate"] == "warning"]
        assert len(blocking_only) == 1
        assert len(warning_only) == 1


class TestRunAll:
    def test_run_all_with_real_project(self, project_dir):
        """Test running the chain against a real project with sketch nodes."""
        mgr = TestChainManager.create(str(project_dir))

        # Add a test set that checks for existing nodes
        test_set = {
            "id": "test-run",
            "name": "Run test",
            "generatedAt": "2025-01-01T00:00:00Z",
            "generatedBy": "test",
            "source_id": None,
            "gate": "blocking",
            "dataPoints": [
                {
                    "id": "check-product",
                    "type": "node_exists",
                    "description": "Product node exists",
                    "query": {"node_id": "product-top"},
                    "expected": {"exists": True, "type": "Product"},
                    "tags": ["test"],
                },
                {
                    "id": "check-count",
                    "type": "node_count",
                    "description": "At least 1 Product",
                    "query": {"node_type": "Product"},
                    "expected": {"min_count": 1},
                    "tags": ["test"],
                },
            ],
        }
        mgr.add_test_set(test_set)

        summary = mgr.run_all(project_dir=str(project_dir))

        assert summary.total == 2
        assert summary.passed == 2
        assert summary.failed == 0
        assert summary.all_passed


class TestSampling:
    def test_small_list_unchanged(self):
        items = list(range(15))
        assert _sample_items(items, max_samples=20) == items

    def test_large_list_sampled(self):
        items = list(range(100))
        result = _sample_items(items, max_samples=20)
        assert len(result) == 20
        # First 5 preserved
        assert result[:5] == [0, 1, 2, 3, 4]
        # Last 5 preserved
        assert result[5:10] == [95, 96, 97, 98, 99]

    def test_exact_threshold(self):
        items = list(range(20))
        result = _sample_items(items, max_samples=20)
        assert result == items


class TestRawToDatapoint:
    def test_converts_node_exists(self):
        raw = {
            "id": "dp-1",
            "type": "node_exists",
            "description": "Node exists",
            "query": {"node_id": "foo"},
            "expected": {"exists": True, "type": "Product"},
            "tags": ["test"],
        }
        dp = _raw_to_datapoint(raw)
        assert dp.id == "dp-1"
        assert dp.type.value == "node_exists"
        assert dp.query.node_id == "foo"
        assert dp.expected.exists is True
        assert dp.expected.type == "Product"

    def test_converts_node_count(self):
        raw = {
            "id": "dp-2",
            "type": "node_count",
            "description": "Count check",
            "query": {"node_type": "Requirement", "source_id": "jama"},
            "expected": {"min_count": 10},
        }
        dp = _raw_to_datapoint(raw)
        assert dp.type.value == "node_count"
        assert dp.query.node_type == "Requirement"
        assert dp.query.source_id == "jama"
        assert dp.expected.min_count == 10


class TestFormatting:
    def test_format_chain_overview(self, tmp_path):
        mgr = TestChainManager.create(str(tmp_path))
        mgr.add_test_set({
            "id": "s1", "name": "Test Set 1",
            "generatedAt": "2025-01-01T00:00:00Z",
            "generatedBy": "test", "source_id": None,
            "gate": "blocking",
            "dataPoints": [
                {"id": "dp1", "type": "node_exists", "description": "t",
                 "query": {}, "expected": {}}
            ],
        })
        overview = mgr.format_chain_overview()
        assert "Test Chain Overview" in overview
        assert "Test Set 1" in overview
        assert "1 checks" in overview
        assert "[blocking]" in overview
