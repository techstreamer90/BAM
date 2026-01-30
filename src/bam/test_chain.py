"""
BAM Test Chain Manager

Manages an accumulating regression test suite (test chain) for BAM projects.
Tests are generated at project init and during each pipeline ingestion stage.
All accumulated tests run during every subsequent verify stage, catching
regressions where a later ingestion breaks earlier data.
"""

import json
import logging
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.test_chain")

CHAIN_VERSION = "1.0.0"
CHAIN_FILENAME = "test_chain.json"


class TestChainManager:
    """Manages the accumulating test chain for a BAM project."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.chain_path = self.project_dir / CHAIN_FILENAME
        self._chain = None

    # -- Persistence ----------------------------------------------------------

    @classmethod
    def create(cls, project_dir: str) -> "TestChainManager":
        """Create a new empty test chain file and return a manager."""
        mgr = cls(project_dir)
        now = datetime.now(timezone.utc).isoformat()
        mgr._chain = {
            "version": CHAIN_VERSION,
            "createdAt": now,
            "lastModified": now,
            "testSets": [],
        }
        mgr._save()
        return mgr

    def load(self) -> dict:
        """Load test chain from disk."""
        if not self.chain_path.exists():
            raise FileNotFoundError(
                f"No test chain found at {self.chain_path}. "
                "Run project init first."
            )
        with open(self.chain_path, "r") as f:
            self._chain = json.load(f)
        return self._chain

    def _ensure_loaded(self):
        if self._chain is None:
            self.load()

    def _save(self):
        self._chain["lastModified"] = datetime.now(timezone.utc).isoformat()
        self.chain_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.chain_path, "w") as f:
            json.dump(self._chain, f, indent=2)
            f.write("\n")

    # -- Test set management --------------------------------------------------

    def add_test_set(self, test_set: dict):
        """Append a test set to the chain and save."""
        self._ensure_loaded()
        self._chain["testSets"].append(test_set)
        self._save()
        logger.info(
            "Added test set '%s' with %d data points",
            test_set.get("name", test_set["id"]),
            len(test_set.get("dataPoints", [])),
        )

    def get_all_data_points(self) -> List[dict]:
        """Return all data points across all test sets."""
        self._ensure_loaded()
        points = []
        for ts in self._chain["testSets"]:
            points.extend(ts.get("dataPoints", []))
        return points

    def get_test_sets(self) -> List[dict]:
        """Return all test sets."""
        self._ensure_loaded()
        return self._chain["testSets"]

    # -- Manual check ---------------------------------------------------------

    def add_manual_check(
        self,
        description: str,
        verification_type: str,
        query: dict,
        expected: dict,
        gate: str = "blocking",
        tags: Optional[List[str]] = None,
    ):
        """Add a single manual check as its own test set."""
        dp = {
            "id": f"manual-{uuid.uuid4().hex[:8]}",
            "type": verification_type,
            "description": description,
            "query": query,
            "expected": expected,
            "tags": tags or ["manual"],
        }
        test_set = {
            "id": f"manual-{uuid.uuid4().hex[:8]}",
            "name": f"Manual: {description[:60]}",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "manual",
            "source_id": None,
            "gate": gate,
            "dataPoints": [dp],
        }
        self.add_test_set(test_set)

    # -- Auto-generation: sketch ----------------------------------------------

    def generate_sketch_tests(self, template_data: dict) -> dict:
        """Generate structural tests from a sketch template.

        Returns a test set dict (caller should add via add_test_set).
        """
        data_points = []
        example = template_data.get("exampleSketch", {})
        nodes = example.get("nodes", {})
        edges = example.get("edges", {})

        # Node existence checks
        for node_id, node_data in nodes.items():
            dp = {
                "id": f"sketch-node-{node_id}",
                "type": "node_exists",
                "description": f"Sketch node '{node_id}' exists with type {node_data.get('type', '?')}",
                "query": {"node_id": node_id},
                "expected": {
                    "exists": True,
                    "type": node_data.get("type"),
                    "label": node_data.get("label") or node_data.get("name"),
                },
                "tags": ["sketch", "structural"],
            }
            data_points.append(dp)

        # Edge existence checks
        for edge_id, edge_data in edges.items():
            source_nid = edge_data.get("source_node_id") or edge_data.get("source", "")
            target_nid = edge_data.get("target_node_id") or edge_data.get("target", "")
            dp = {
                "id": f"sketch-edge-{edge_id}",
                "type": "edge_exists",
                "description": (
                    f"Sketch edge '{edge_id}' ({edge_data.get('type', '?')}) "
                    f"from {source_nid} to {target_nid}"
                ),
                "query": {
                    "source_node_id": source_nid,
                    "target_node_id": target_nid,
                    "edge_type": edge_data.get("type", "").upper(),
                },
                "expected": {
                    "exists": True,
                    "source_node_id": source_nid,
                    "target_node_id": target_nid,
                    "edge_type": edge_data.get("type", "").upper(),
                },
                "tags": ["sketch", "structural"],
            }
            data_points.append(dp)

        # Aggregate node count per type
        type_counts = Counter(n.get("type") for n in nodes.values())
        for node_type, count in type_counts.items():
            dp = {
                "id": f"sketch-count-{node_type}",
                "type": "node_count",
                "description": f"At least {count} node(s) of type {node_type}",
                "query": {"node_type": node_type},
                "expected": {"min_count": count},
                "tags": ["sketch", "aggregate"],
            }
            data_points.append(dp)

        return {
            "id": "sketch-init",
            "name": "Sketch structural checks",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "init",
            "source_id": None,
            "gate": "blocking",
            "dataPoints": data_points,
        }

    # -- Auto-generation: download --------------------------------------------

    def generate_download_tests(self, source_id: str, download_manifest: dict) -> dict:
        """Generate tests from a download stage manifest."""
        data_points = []
        item_count = download_manifest.get("itemCount", 0)

        if item_count > 0:
            dp = {
                "id": f"download-count-{source_id}",
                "type": "node_count",
                "description": (
                    f"Source '{source_id}' has at least {item_count} node(s) after download"
                ),
                "query": {"source_id": source_id},
                "expected": {"min_count": item_count},
                "tags": ["download", "completeness", source_id],
            }
            data_points.append(dp)

        return {
            "id": f"download-{source_id}",
            "name": f"Download completeness: {source_id}",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "download",
            "source_id": source_id,
            "gate": "blocking",
            "dataPoints": data_points,
        }

    # -- Auto-generation: transform -------------------------------------------

    def generate_transform_tests(
        self, source_id: str, nodes: List[dict], edges: List[dict]
    ) -> dict:
        """Generate tests from transform stage outputs."""
        data_points = []

        # Sample nodes for existence checks
        sampled = _sample_items(nodes, max_samples=20)
        for node in sampled:
            nid = node.get("id", "")
            dp = {
                "id": f"transform-node-{nid}",
                "type": "node_exists",
                "description": (
                    f"Transform node '{nid}' of type {node.get('type', '?')} exists"
                ),
                "query": {"node_id": nid},
                "expected": {
                    "exists": True,
                    "type": node.get("type"),
                    "label": node.get("label"),
                },
                "tags": ["transform", "node", source_id],
            }
            data_points.append(dp)

        # All edges get existence checks
        for edge in edges:
            eid = edge.get("id", "")
            dp = {
                "id": f"transform-edge-{eid}",
                "type": "edge_exists",
                "description": (
                    f"Transform edge '{eid}' ({edge.get('type', '?')}) exists"
                ),
                "query": {
                    "source_node_id": edge.get("source_node_id", ""),
                    "target_node_id": edge.get("target_node_id", ""),
                    "edge_type": edge.get("type", ""),
                },
                "expected": {
                    "exists": True,
                    "source_node_id": edge.get("source_node_id", ""),
                    "target_node_id": edge.get("target_node_id", ""),
                    "edge_type": edge.get("type", ""),
                },
                "tags": ["transform", "edge", source_id],
            }
            data_points.append(dp)

        # Per-type node count aggregates
        type_counts = Counter(n.get("type") for n in nodes)
        for node_type, count in type_counts.items():
            dp = {
                "id": f"transform-count-{source_id}-{node_type}",
                "type": "node_count",
                "description": (
                    f"At least {count} node(s) of type {node_type} from {source_id}"
                ),
                "query": {"node_type": node_type, "source_id": source_id},
                "expected": {"min_count": count},
                "tags": ["transform", "aggregate", source_id],
            }
            data_points.append(dp)

        return {
            "id": f"transform-{source_id}",
            "name": f"Transform correctness: {source_id}",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "transform",
            "source_id": source_id,
            "gate": "blocking",
            "dataPoints": data_points,
        }

    # -- Auto-generation: integrate -------------------------------------------

    def generate_integrate_tests(
        self,
        source_id: str,
        integration_report: dict,
        model_stats: dict,
    ) -> dict:
        """Generate regression baseline tests from integration results."""
        data_points = []

        nodes_by_type = model_stats.get("nodesByType", {})
        for node_type, count in nodes_by_type.items():
            dp = {
                "id": f"integrate-baseline-{source_id}-{node_type}",
                "type": "node_count",
                "description": (
                    f"Model has at least {count} node(s) of type {node_type} "
                    f"(baseline after {source_id})"
                ),
                "query": {"node_type": node_type},
                "expected": {"min_count": count},
                "tags": ["integrate", "baseline", source_id],
            }
            data_points.append(dp)

        return {
            "id": f"integrate-{source_id}",
            "name": f"Integration baseline: {source_id}",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "generatedBy": "integrate",
            "source_id": source_id,
            "gate": "warning",
            "dataPoints": data_points,
        }

    # -- Running --------------------------------------------------------------

    def run_all(self, project_dir: str = None):
        """Run all data points in the chain.

        Returns a VerificationSummary-compatible dict.
        """
        return self._run_filtered(gate=None, project_dir=project_dir)

    def run_gate_check(self, gate: str, project_dir: str = None):
        """Run only data points at the specified gate level.

        Args:
            gate: "blocking" or "warning"
        """
        return self._run_filtered(gate=gate, project_dir=project_dir)

    def _run_filtered(self, gate: Optional[str], project_dir: str = None):
        self._ensure_loaded()
        pdir = project_dir or str(self.project_dir)

        from tests.verification.query_engine import VerificationQueryEngine
        from tests.verification.models import (
            DataPoint,
            ExpectedValue,
            VerificationQuery,
            VerificationStatus,
            VerificationSummary,
            VerificationType,
        )

        engine = VerificationQueryEngine(project_dir=pdir)
        results = []
        start = time.perf_counter()

        try:
            for ts in self._chain["testSets"]:
                if gate and ts.get("gate") != gate:
                    continue
                for raw_dp in ts.get("dataPoints", []):
                    dp = _raw_to_datapoint(raw_dp)
                    result = engine.verify(dp)
                    results.append(result)
        finally:
            engine.close()

        elapsed = (time.perf_counter() - start) * 1000
        passed = sum(1 for r in results if r.status == VerificationStatus.PASS)
        failed = sum(1 for r in results if r.status == VerificationStatus.FAIL)
        errors = sum(1 for r in results if r.status == VerificationStatus.ERROR)
        skipped = sum(1 for r in results if r.status == VerificationStatus.SKIP)

        return VerificationSummary(
            total=len(results),
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_ms=elapsed,
            results=results,
        )

    # -- Reporting ------------------------------------------------------------

    def format_chain_overview(self) -> str:
        """Return a human-readable overview of the test chain."""
        self._ensure_loaded()
        lines = ["Test Chain Overview", "=" * 40]
        lines.append(f"Version: {self._chain.get('version')}")
        lines.append(f"Created: {self._chain.get('createdAt')}")
        lines.append(f"Modified: {self._chain.get('lastModified')}")
        lines.append(f"Test sets: {len(self._chain['testSets'])}")

        total_dp = 0
        for ts in self._chain["testSets"]:
            count = len(ts.get("dataPoints", []))
            total_dp += count
            gate_label = f"[{ts.get('gate', '?')}]"
            lines.append(
                f"  {ts['id']}: {ts.get('name', '')} "
                f"({count} checks) {gate_label}"
            )

        lines.append(f"\nTotal data points: {total_dp}")
        return "\n".join(lines)

    def format_summary(self, summary) -> str:
        """Format a VerificationSummary for display."""
        lines = [
            "Test Chain Results",
            "=" * 40,
            f"Total:   {summary.total}",
            f"Passed:  {summary.passed}",
            f"Failed:  {summary.failed}",
            f"Errors:  {summary.errors}",
            f"Skipped: {summary.skipped}",
            f"Time:    {summary.duration_ms:.1f}ms",
            f"Rate:    {summary.success_rate:.1f}%",
        ]

        if summary.failed > 0 or summary.errors > 0:
            lines.append("\nFailures/Errors:")
            from tests.verification.models import VerificationStatus

            for r in summary.results:
                if r.status in (VerificationStatus.FAIL, VerificationStatus.ERROR):
                    lines.append(f"  [{r.status.value.upper()}] {r.description}")
                    if r.message:
                        lines.append(f"         {r.message}")

        return "\n".join(lines)


# -- Helpers ------------------------------------------------------------------


def _sample_items(items: list, max_samples: int = 20) -> list:
    """Sample representative items from a list.

    When len > max_samples: first 5, last 5, 10 evenly spaced from middle.
    """
    if len(items) <= max_samples:
        return list(items)

    sampled = []
    sampled.extend(items[:5])
    sampled.extend(items[-5:])

    middle = items[5:-5]
    if middle:
        step = max(1, len(middle) // 10)
        for i in range(0, len(middle), step):
            sampled.append(middle[i])
            if len(sampled) >= max_samples:
                break

    return sampled[:max_samples]


def _raw_to_datapoint(raw: dict):
    """Convert a raw JSON data point dict to a DataPoint object."""
    from tests.verification.models import (
        DataPoint,
        ExpectedValue,
        VerificationQuery,
        VerificationType,
    )

    vtype_map = {
        "node_exists": VerificationType.NODE_EXISTS,
        "node_properties": VerificationType.NODE_PROPERTIES,
        "node_content": VerificationType.NODE_CONTENT,
        "edge_exists": VerificationType.EDGE_EXISTS,
        "node_count": VerificationType.NODE_COUNT,
        "relationship_count": VerificationType.RELATIONSHIP_COUNT,
    }

    raw_query = raw.get("query", {})
    raw_expected = raw.get("expected", {})

    query = VerificationQuery(
        node_id=raw_query.get("node_id"),
        node_type=raw_query.get("node_type"),
        source_id=raw_query.get("source_id"),
        edge_id=raw_query.get("edge_id"),
        edge_type=raw_query.get("edge_type"),
        source_node_id=raw_query.get("source_node_id"),
        target_node_id=raw_query.get("target_node_id"),
        label_contains=raw_query.get("label_contains"),
    )

    expected = ExpectedValue(
        exists=raw_expected.get("exists"),
        type=raw_expected.get("type"),
        label=raw_expected.get("label"),
        count=raw_expected.get("count"),
        min_count=raw_expected.get("min_count"),
        max_count=raw_expected.get("max_count"),
        properties=raw_expected.get("properties"),
        content_contains=raw_expected.get("content_contains"),
        source_node_id=raw_expected.get("source_node_id"),
        target_node_id=raw_expected.get("target_node_id"),
        edge_type=raw_expected.get("edge_type"),
    )

    return DataPoint(
        id=raw["id"],
        type=vtype_map.get(raw["type"], VerificationType.NODE_EXISTS),
        description=raw.get("description", ""),
        query=query,
        expected=expected,
        tags=raw.get("tags", []),
    )
