"""
BAM Sketch/Color Architecture Tests

Tests for:
1. SketchManager - lightweight structure layer
2. ColorBackends - detail storage (JSON, SQLite)
3. ModelManager - orchestration of sketch + color
4. Consistency checking across backends
"""

import json
import pytest
from pathlib import Path

from bam.backends import (
    # Sketch
    SketchManager,
    SketchNode,
    SketchEdge,
    # Color
    NodeColor,
    EdgeColor,
    get_color_backend,
    # Model Manager
    ModelManager,
    Node,
    Edge,
)


# =============================================================================
# Sketch Tests
# =============================================================================

class TestSketchManager:
    """Tests for the lightweight sketch layer."""

    @pytest.fixture
    def sketch(self, tmp_path):
        """Create a sketch manager with temp storage."""
        sketch_path = tmp_path / "sketch.json"
        sm = SketchManager(sketch_path)
        sm.load()
        yield sm
        sm.save()

    def test_add_and_get_node(self, sketch):
        """Should add and retrieve a sketch node."""
        node = SketchNode(
            id="test-1",
            type="Requirement",
            label="Test Node",
            source_id="test-source",
        )
        sketch.add_node(node)

        retrieved = sketch.get_node("test-1")
        assert retrieved is not None
        assert retrieved.id == "test-1"
        assert retrieved.type == "Requirement"
        assert retrieved.label == "Test Node"

    def test_sketch_node_is_lightweight(self, sketch):
        """Sketch nodes should NOT have properties/content."""
        node = SketchNode(id="n1", type="T", label="L")
        sketch.add_node(node)

        # SketchNode doesn't have properties or content attributes
        assert not hasattr(node, 'properties')
        assert not hasattr(node, 'content')

    def test_add_edge_validates_nodes(self, sketch):
        """Should reject edges with missing nodes."""
        sketch.add_node(SketchNode(id="a", type="T", label="A"))

        with pytest.raises(ValueError, match="not in sketch"):
            sketch.add_edge(SketchEdge(
                id="e1",
                type="CONN",
                source_node_id="a",
                target_node_id="missing",
            ))

    def test_find_nodes_by_type(self, sketch):
        """Should find nodes by type."""
        sketch.add_node(SketchNode(id="r1", type="Requirement", label="R1"))
        sketch.add_node(SketchNode(id="r2", type="Requirement", label="R2"))
        sketch.add_node(SketchNode(id="c1", type="CodeModule", label="C1"))

        reqs = sketch.find_nodes(node_type="Requirement")
        assert len(reqs) == 2

    def test_get_connected_node_ids(self, sketch):
        """Should return connected node IDs quickly."""
        sketch.add_node(SketchNode(id="center", type="T", label="Center"))
        sketch.add_node(SketchNode(id="out1", type="T", label="Out1"))
        sketch.add_node(SketchNode(id="in1", type="T", label="In1"))

        sketch.add_edge(SketchEdge(id="e1", type="OUT", source_node_id="center", target_node_id="out1"))
        sketch.add_edge(SketchEdge(id="e2", type="IN", source_node_id="in1", target_node_id="center"))

        outgoing = sketch.get_connected_node_ids("center", direction="outgoing")
        assert outgoing == ["out1"]

        incoming = sketch.get_connected_node_ids("center", direction="incoming")
        assert incoming == ["in1"]

    def test_validate_detects_orphan_edges(self, sketch):
        """Validation should detect edges pointing to missing nodes."""
        sketch.add_node(SketchNode(id="a", type="T", label="A"))
        sketch.add_node(SketchNode(id="b", type="T", label="B"))
        sketch.add_edge(SketchEdge(id="e1", type="CONN", source_node_id="a", target_node_id="b"))

        # Manually corrupt: delete node but leave edge
        del sketch.model["nodes"]["b"]

        issues = sketch.validate()
        assert len(issues) == 1
        assert "missing target node" in issues[0]

    def test_node_from_dict_new_format(self, sketch):
        """SketchNode.from_dict should work with canonical format."""
        data = {"id": "n1", "type": "RTLModule", "label": "top_module", "source_id": "rtl"}
        node = SketchNode.from_dict(data)
        assert node.id == "n1"
        assert node.label == "top_module"
        assert node.source_id == "rtl"

    def test_node_from_dict_old_format(self, sketch):
        """SketchNode.from_dict should accept old format with 'name' and fallback_id."""
        data = {"type": "Product", "name": "Example SoC", "color": "conceptual"}
        node = SketchNode.from_dict(data, fallback_id="product-top")
        assert node.id == "product-top"
        assert node.label == "Example SoC"
        assert node.type == "Product"

    def test_edge_from_dict_new_format(self, sketch):
        """SketchEdge.from_dict should work with canonical format."""
        data = {
            "id": "e1", "type": "CONTAINS",
            "source_node_id": "a", "target_node_id": "b", "source_id": "src"
        }
        edge = SketchEdge.from_dict(data)
        assert edge.id == "e1"
        assert edge.source_node_id == "a"
        assert edge.target_node_id == "b"

    def test_edge_from_dict_old_format(self, sketch):
        """SketchEdge.from_dict should accept old format with 'source'/'target'."""
        data = {"type": "contains", "source": "product-top", "target": "subsys-cpu"}
        edge = SketchEdge.from_dict(data, fallback_id="product-contains-cpu")
        assert edge.id == "product-contains-cpu"
        assert edge.source_node_id == "product-top"
        assert edge.target_node_id == "subsys-cpu"

    def test_persistence(self, tmp_path):
        """Sketch should persist and reload correctly."""
        sketch_path = tmp_path / "persist_test.json"

        # Create and save
        sm1 = SketchManager(sketch_path)
        sm1.load()
        sm1.add_node(SketchNode(id="persist", type="T", label="Persist Me"))
        sm1.save()

        # Reload
        sm2 = SketchManager(sketch_path)
        sm2.load()

        node = sm2.get_node("persist")
        assert node is not None
        assert node.label == "Persist Me"


# =============================================================================
# Color Backend Tests
# =============================================================================

class TestColorBackends:
    """Tests for color storage backends."""

    @pytest.fixture(params=["json", "sqlite", "neo4j"])
    def color_backend(self, request, tmp_path):
        """Create a color backend for testing."""
        backend_name = request.param

        if backend_name == "json":
            config = {
                "colorPath": str(tmp_path / "color.json"),
                "snapshotsDir": str(tmp_path / "snapshots"),
            }
        elif backend_name == "sqlite":
            config = {
                "dbPath": str(tmp_path / "color.db"),
            }
        elif backend_name == "neo4j":
            # Neo4j uses real connection - skip if not configured
            from bam.backends.factory import load_config
            try:
                full_config = load_config()
                backends = full_config.get("storage", {}).get("color_backends", {})
                # Look for any neo4j backend in the config
                neo4j_config = None
                for name, bc in backends.items():
                    if bc.get("type") == "neo4j":
                        neo4j_config = bc
                        break
                if not neo4j_config:
                    pytest.skip("No neo4j backend configured")
                config = neo4j_config
            except Exception:
                pytest.skip("Neo4j config not available")
        else:
            pytest.skip(f"Unknown backend: {backend_name}")

        backend = get_color_backend(backend_name, config)
        backend.connect()

        yield backend

        # Clean up test data for neo4j (shared instance)
        if backend_name == "neo4j":
            # Clear test data
            for nid in backend.list_node_ids():
                backend.delete_node_color(nid)
            for eid in backend.list_edge_ids():
                backend.delete_edge_color(eid)

        backend.close()

    def test_store_and_get_node_color(self, color_backend):
        """Should store and retrieve node color."""
        color = NodeColor(
            id="n1",
            properties={"priority": "high", "status": "approved"},
            source_ref="JAMA-123",
            content="Full requirement text here...",
        )
        color_backend.store_node_color(color)

        retrieved = color_backend.get_node_color("n1")
        assert retrieved is not None
        assert retrieved.properties["priority"] == "high"
        assert retrieved.content == "Full requirement text here..."

    def test_store_and_get_edge_color(self, color_backend):
        """Should store and retrieve edge color."""
        color = EdgeColor(
            id="e1",
            properties={"confidence": 0.95, "verified": True},
        )
        color_backend.store_edge_color(color)

        retrieved = color_backend.get_edge_color("e1")
        assert retrieved is not None
        assert retrieved.properties["confidence"] == 0.95

    def test_update_node_color(self, color_backend):
        """Should update node color properties."""
        color_backend.store_node_color(NodeColor(
            id="upd",
            properties={"status": "draft"},
            content="Original content",
        ))

        color_backend.update_node_color("upd", {
            "properties": {"status": "approved"},
            "content": "Updated content",
        })

        updated = color_backend.get_node_color("upd")
        assert updated.properties["status"] == "approved"
        assert updated.content == "Updated content"

    def test_delete_node_color(self, color_backend):
        """Should delete node color."""
        color_backend.store_node_color(NodeColor(id="del", properties={}))

        result = color_backend.delete_node_color("del")
        assert result is True

        assert color_backend.get_node_color("del") is None

    def test_bulk_store_node_color(self, color_backend):
        """Should store multiple node color entries."""
        color_list = [
            NodeColor(id=f"bulk-{i}", properties={"index": i})
            for i in range(50)
        ]

        count = color_backend.bulk_store_node_color(color_list)
        assert count == 50

        stats = color_backend.get_statistics()
        assert stats.total_nodes == 50

    def test_search_node_content(self, color_backend):
        """Should search node content."""
        color_backend.store_node_color(NodeColor(
            id="auth",
            content="The system shall authenticate users via OAuth2",
        ))
        color_backend.store_node_color(NodeColor(
            id="logging",
            content="The system shall log all transactions",
        ))

        results = color_backend.search_node_content("authenticate")
        assert "auth" in results
        assert "logging" not in results

    def test_list_node_ids(self, color_backend):
        """Should list all stored node IDs."""
        color_backend.store_node_color(NodeColor(id="a", properties={}))
        color_backend.store_node_color(NodeColor(id="b", properties={}))
        color_backend.store_node_color(NodeColor(id="c", properties={}))

        ids = color_backend.list_node_ids()
        assert set(ids) == {"a", "b", "c"}

    def test_snapshot_and_restore(self, color_backend):
        """Should snapshot and restore color data."""
        color_backend.store_node_color(NodeColor(id="snap", properties={"v": 1}))

        snapshot_id = color_backend.create_snapshot("test")

        # Modify
        color_backend.update_node_color("snap", {"properties": {"v": 2}})
        assert color_backend.get_node_color("snap").properties["v"] == 2

        # Restore
        color_backend.restore_snapshot(snapshot_id)
        assert color_backend.get_node_color("snap").properties["v"] == 1


# =============================================================================
# Model Manager Tests
# =============================================================================

class TestModelManager:
    """Tests for the model manager orchestration layer."""

    @pytest.fixture
    def model_manager(self, tmp_path):
        """Create a model manager with temp storage."""
        config = {
            "storage": {
                "sketch": {
                    "path": str(tmp_path / "sketch.json"),
                },
                "colors": {
                    "conceptual": {
                        "description": "Requirements and specifications",
                        "node_types": ["Requirement", "Specification"],
                    },
                    "design": {
                        "description": "Design artifacts",
                        "node_types": ["DesignDocument", "RTLModule"],
                    },
                },
                "color_backends": {
                    "default": {
                        "type": "json",
                        "colors": ["conceptual", "design"],
                        "path": str(tmp_path / "default.json"),
                        "snapshotsDir": str(tmp_path / "default_snapshots"),
                    },
                    "design_db": {
                        "type": "sqlite",
                        "colors": ["design"],
                        "path": str(tmp_path / "design.db"),
                        "snapshotsDir": str(tmp_path / "design_snapshots"),
                    },
                },
            },
        }

        mm = ModelManager(config, base_path=tmp_path)
        mm.load()

        yield mm

        mm.save()
        mm.close()

    def test_add_node_goes_to_sketch_and_all_color(self, model_manager):
        """Adding a node should populate sketch and appropriate color backend."""
        node = Node(
            id="req-001",
            type="Requirement",
            label="User Authentication",
            source_id="jama",
            properties={"priority": "high"},
            content="Full text here",
        )
        model_manager.add_node(node)

        # Check sketch
        assert model_manager.sketch.has_node("req-001")
        skel = model_manager.sketch.get_node("req-001")
        assert skel.type == "Requirement"
        assert skel.label == "User Authentication"

        # Check color is in the default backend (serves conceptual color for Requirement type)
        color = model_manager.color_manager.get_node_color("req-001", node_type="Requirement")
        assert color is not None
        assert color.properties["priority"] == "high"
        assert color.content == "Full text here"

    def test_get_node_combines_sketch_and_color(self, model_manager):
        """Getting a node should combine sketch and color data."""
        model_manager.add_node(Node(
            id="combo",
            type="DesignDocument",  # Valid type in design color
            label="Architecture Doc",
            properties={"version": "2.0"},
        ))

        full_node = model_manager.get_node("combo")

        # From sketch
        assert full_node.type == "DesignDocument"
        assert full_node.label == "Architecture Doc"

        # From color
        assert full_node.properties["version"] == "2.0"

    def test_fast_navigation_uses_sketch_only(self, model_manager):
        """Navigation queries should use sketch (no color fetch)."""
        model_manager.add_node(Node(id="a", type="T", label="A"))
        model_manager.add_node(Node(id="b", type="T", label="B"))
        model_manager.add_edge(Edge(id="e", type="CONN", source_node_id="a", target_node_id="b"))

        # This should be fast - sketch only
        connected = model_manager.get_connected_node_ids("a")
        assert connected == ["b"]

    def test_find_nodes_without_color_is_fast(self, model_manager):
        """Finding nodes without color should be fast sketch-only query."""
        for i in range(100):
            model_manager.add_node(Node(id=f"n{i}", type="Req", label=f"Req {i}"))

        # Without color - should be fast
        nodes = model_manager.find_nodes(node_type="Req", include_color=False)
        assert len(nodes) == 100
        assert nodes[0].properties == {}  # No color loaded

    def test_find_nodes_with_color_includes_details(self, model_manager):
        """Finding nodes with color should include full details."""
        model_manager.add_node(Node(
            id="detailed",
            type="Requirement",  # Valid type in conceptual color
            label="Detailed",
            properties={"status": "approved"},
        ))

        nodes = model_manager.find_nodes(node_type="Requirement", include_color=True)
        assert len(nodes) == 1
        assert nodes[0].properties["status"] == "approved"

    def test_consistency_check_passes_when_synced(self, model_manager):
        """Consistency check should pass when all backends are in sync."""
        model_manager.add_node(Node(id="sync", type="T", label="Synced"))

        report = model_manager.check_consistency()

        assert report.is_consistent
        assert len(report.issues) == 0

    def test_consistency_check_detects_orphan_color(self, model_manager):
        """Should detect orphan color (color without sketch entry)."""
        # Add color directly without sketch via color_manager
        model_manager.color_manager.backends["default"].store_node_color(
            NodeColor(id="orphan", properties={})
        )

        report = model_manager.check_consistency()

        assert not report.is_consistent
        assert any("orphan" in issue for issue in report.issues)

    def test_repair_removes_orphan_color(self, model_manager):
        """Repair should remove orphan color entries."""
        # Add orphan directly to backend
        model_manager.color_manager.backends["default"].store_node_color(
            NodeColor(id="orphan", properties={})
        )

        # Repair
        result = model_manager.repair_consistency()

        assert result["orphan_nodes_removed"] >= 1

        # Should be clean now
        report = model_manager.check_consistency()
        assert report.is_consistent

    def test_delete_node_removes_from_all(self, model_manager):
        """Deleting a node should remove from sketch and appropriate color backends."""
        model_manager.add_node(Node(id="del", type="Requirement", label="Delete Me"))
        model_manager.delete_node("del")

        assert not model_manager.has_node("del")

        # Should be gone from the appropriate backend
        color = model_manager.color_manager.get_node_color("del", node_type="Requirement")
        assert color is None

    def test_bulk_operations(self, model_manager):
        """Bulk operations should work efficiently."""
        nodes = [
            Node(id=f"bulk-{i}", type="Requirement", label=f"Bulk {i}", properties={"i": i})
            for i in range(100)
        ]

        ids = model_manager.bulk_add_nodes(nodes)
        assert len(ids) == 100

        stats = model_manager.get_statistics()
        assert stats.sketch.total_nodes == 100

        # At least one backend should have the nodes (default for Requirement type)
        total_color = sum(bs.total_nodes for bs in stats.color_by_backend.values())
        assert total_color >= 100

    def test_get_node_from_specific_backend(self, model_manager):
        """Should be able to specify which color backend to use."""
        # DesignDocument goes to both default (json) and design_db (sqlite)
        model_manager.add_node(Node(id="multi", type="DesignDocument", label="Multi", properties={"x": 1}))

        node_default = model_manager.get_node("multi", backend="default")
        node_design = model_manager.get_node("multi", backend="design_db")

        # Both should have the same data
        assert node_default.properties == node_design.properties

    def test_list_backends(self, model_manager):
        """Should list active backends."""
        backends = model_manager.list_backends()
        assert "default" in backends
        assert "design_db" in backends


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """End-to-end integration tests."""

    @pytest.fixture
    def model_manager(self, tmp_path):
        """Create a model manager for integration tests."""
        config = {
            "storage": {
                "sketch": {"path": str(tmp_path / "sketch.json")},
                "colors": {
                    "conceptual": {
                        "node_types": ["Requirement", "Specification"],
                    },
                    "design": {
                        "node_types": ["CodeModule", "DesignDocument"],
                    },
                },
                "color_backends": {
                    "default": {
                        "type": "json",
                        "colors": ["conceptual", "design"],
                        "path": str(tmp_path / "default.json"),
                        "snapshotsDir": str(tmp_path / "snapshots"),
                    },
                },
            },
        }
        mm = ModelManager(config, base_path=tmp_path)
        mm.load()
        yield mm
        mm.save()
        mm.close()

    def test_full_workflow(self, model_manager):
        """Test a complete workflow: add, query, update, delete."""
        # Add requirements
        model_manager.add_node(Node(
            id="REQ-001",
            type="Requirement",
            label="User Login",
            source_id="jama",
            properties={"priority": "high"},
            content="Users shall be able to log in with email/password",
        ))
        model_manager.add_node(Node(
            id="REQ-002",
            type="Requirement",
            label="Session Timeout",
            source_id="jama",
            properties={"priority": "medium"},
        ))

        # Add code module
        model_manager.add_node(Node(
            id="CODE-auth",
            type="CodeModule",
            label="auth_service.py",
            source_id="codebase",
            properties={"path": "src/auth/auth_service.py", "lines": 245},
        ))

        # Add traceability edge
        model_manager.add_edge(Edge(
            id="impl-001",
            type="IMPLEMENTS",
            source_node_id="CODE-auth",
            target_node_id="REQ-001",
        ))

        # Fast navigation: what implements REQ-001?
        implementors = model_manager.get_connected_node_ids("REQ-001", direction="incoming")
        assert "CODE-auth" in implementors

        # Full details
        req = model_manager.get_node("REQ-001")
        assert req.properties["priority"] == "high"
        assert "email/password" in req.content

        # Update
        model_manager.update_node("REQ-001", {"properties": {"priority": "critical"}})
        updated = model_manager.get_node("REQ-001")
        assert updated.properties["priority"] == "critical"

        # Verify consistency
        report = model_manager.check_consistency()
        assert report.is_consistent

        # Statistics
        stats = model_manager.get_statistics()
        assert stats.sketch.total_nodes == 3
        assert stats.sketch.total_edges == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
