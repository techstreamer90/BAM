"""
BAM Storage Backends - Sketch/Color Architecture

The graph model is split into two layers:

1. SKETCH (always JSON, fast, lightweight)
   - Node: id, type, label, source_id
   - Edge: id, type, source_node_id, target_node_id, source_id
   - Fast navigation and structure queries

2. COLOR (multiple backend options)
   - NodeColor: properties, content, timestamps
   - EdgeColor: properties, timestamps
   - Full details stored in JSON, SQLite, Neo4j, or ArangoDB

Usage:
    from backends import get_model_manager, Node, Edge

    # Get the model manager (orchestrates sketch + color)
    mm = get_model_manager()
    mm.load()

    # Add a complete node (goes to sketch + all configured color backends)
    mm.add_node(Node(
        id="req-001",
        type="Requirement",
        label="User Authentication",
        properties={"priority": "high", "status": "approved"},
        content="The system shall provide secure user authentication...",
    ))

    # Fast navigation (sketch only)
    connected = mm.get_connected_node_ids("req-001")

    # Get full details (sketch + color)
    node = mm.get_node("req-001")

    # Check consistency across backends
    report = mm.check_consistency()
    print(f"Consistent: {report.is_consistent}")

    mm.save()
    mm.close()

Available color backends:
- json: Simple JSON file storage (default, zero dependencies)
- sqlite: SQLite database (built-in Python, indexed queries)
- neo4j: Neo4j graph database (requires neo4j driver and server)
- arango: ArangoDB multi-model database (requires python-arango and server)
"""

# Sketch
from .sketch import SketchManager, SketchNode, SketchEdge, SketchStats

# Color data types
from .base import (
    ColorBackend,
    BaseColorBackend,
    NodeColor,
    EdgeColor,
    ColorStats,
    SnapshotInfo,
    # Complete node/edge (sketch + color combined)
    Node,
    Edge,
    # Type enums
    NodeType,
    EdgeType,
)

# Color manager (handles multiple backends per color)
from .color_manager import ColorManager

# Model manager (main entry point)
from .model_manager import ModelManager, ConsistencyReport, ModelStats

# Factory functions
from .factory import (
    get_model_manager,
    get_sketch_manager,
    get_color_backend,
    list_available_backends,
    load_config,
    BackendNotFoundError,
    BackendNotAvailableError,
)

__all__ = [
    # Main entry point
    "get_model_manager",
    "load_config",
    "ModelManager",
    "ConsistencyReport",
    "ModelStats",
    # Colors
    "ColorManager",
    # Sketch
    "get_sketch_manager",
    "SketchManager",
    "SketchNode",
    "SketchEdge",
    "SketchStats",
    # Color
    "get_color_backend",
    "ColorBackend",
    "BaseColorBackend",
    "NodeColor",
    "EdgeColor",
    "ColorStats",
    "SnapshotInfo",
    # Complete types
    "Node",
    "Edge",
    "NodeType",
    "EdgeType",
    # Utilities
    "list_available_backends",
    "BackendNotFoundError",
    "BackendNotAvailableError",
]
