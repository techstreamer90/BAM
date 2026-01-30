"""
BAM Backend Tests

Tests for backend discovery and availability.

Note: Full graph operation tests (add_node, find_nodes, etc.) are in
test_sketch_color.py, which tests the ModelManager that combines
sketch (structure) with color backends (properties).
"""

import pytest
from pathlib import Path

from bam.backends import list_available_backends


class TestListBackends:
    """Tests for backend discovery."""

    def test_list_available_backends(self):
        """Should list backends with availability status."""
        backends = list_available_backends()

        assert "json" in backends
        assert "sqlite" in backends
        assert "neo4j" in backends
        assert "arango" in backends

        assert backends["json"]["available"] is True
        assert backends["sqlite"]["available"] is True


class TestEdgeNormalization:
    """Tests for edge type normalization."""

    def test_normalize_edge_type_lowercase(self):
        """Should uppercase lowercase edge types."""
        from bam.backends.sketch import normalize_edge_type
        assert normalize_edge_type("contains") == "CONTAINS"
        assert normalize_edge_type("instantiates") == "INSTANTIATES"
        assert normalize_edge_type("depends_on") == "DEPENDS_ON"

    def test_normalize_edge_type_already_upper(self):
        """Should leave already-uppercase types unchanged."""
        from bam.backends.sketch import normalize_edge_type
        assert normalize_edge_type("CONTAINS") == "CONTAINS"
        assert normalize_edge_type("HAS_PORT") == "HAS_PORT"

    def test_normalize_edge_type_mixed_case(self):
        """Should handle mixed case."""
        from bam.backends.sketch import normalize_edge_type
        assert normalize_edge_type("Contains") == "CONTAINS"
        assert normalize_edge_type("hasPort") == "HASPORT"

    def test_sketch_load_normalizes_edges(self, tmp_path):
        """Loading a sketch with lowercase edge types should auto-normalize."""
        from bam.backends.sketch import SketchManager
        sketch_path = tmp_path / "sketch.json"

        # Write a sketch with old-style lowercase edge types
        import json
        sketch_data = {
            "version": "1.0.0",
            "metadata": {"created": "2025-01-01", "lastModified": None,
                          "nodeCount": 2, "edgeCount": 1},
            "nodes": {
                "a": {"id": "a", "type": "T", "label": "A"},
                "b": {"id": "b", "type": "T", "label": "B"},
            },
            "edges": {
                "e1": {"id": "e1", "type": "contains",
                        "source_node_id": "a", "target_node_id": "b"},
            },
        }
        with open(sketch_path, 'w') as f:
            json.dump(sketch_data, f)

        sm = SketchManager(sketch_path)
        sm.load()

        edge = sm.get_edge("e1")
        assert edge.type == "CONTAINS"

    def test_init_project_produces_valid_sketch(self, tmp_path):
        """init_project with a template should produce SketchManager-compatible sketch.json."""
        from bam.project import init_project
        from bam._paths import SKETCH_TEMPLATES_DIR
        import json

        # Only run if hardware_product template exists
        template_path = SKETCH_TEMPLATES_DIR / "hardware_product.json"
        if not template_path.exists():
            pytest.skip("hardware_product template not found")

        project_dir = str(tmp_path / "test_project")
        init_project(project_dir, name="Test", sketch_template="hardware_product")

        sketch_path = tmp_path / "test_project" / "model" / "sketch.json"
        assert sketch_path.exists()

        with open(sketch_path) as f:
            sketch = json.load(f)

        # All nodes should have canonical fields
        for nid, node in sketch["nodes"].items():
            assert "id" in node, f"Node {nid} missing 'id'"
            assert "type" in node, f"Node {nid} missing 'type'"
            assert "label" in node, f"Node {nid} missing 'label'"
            # Should NOT have old 'name' or 'color' fields as primary
            assert node["id"] == nid

        # All edges should have canonical fields and UPPERCASE types
        for eid, edge in sketch["edges"].items():
            assert "id" in edge, f"Edge {eid} missing 'id'"
            assert "type" in edge, f"Edge {eid} missing 'type'"
            assert "source_node_id" in edge, f"Edge {eid} missing 'source_node_id'"
            assert "target_node_id" in edge, f"Edge {eid} missing 'target_node_id'"
            assert edge["type"] == edge["type"].upper(), \
                f"Edge {eid} type '{edge['type']}' is not UPPERCASE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
