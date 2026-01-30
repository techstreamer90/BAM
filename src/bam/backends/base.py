"""
BAM Storage Backend Base

Defines the ColorBackend protocol - backends that store the full details
(properties, content, timestamps) for nodes and edges.

The Sketch (structure) is managed separately by SketchManager.
The Color (details) is managed by ColorBackend implementations.

Architecture:
    ┌─────────────────────────────────────────┐
    │              SKETCH                    │
    │  (SketchManager - always JSON)        │
    │                                          │
    │  Node: id, type, label                  │
    │  Edge: id, type, source, target         │
    └────────────────┬────────────────────────┘
                     │ references
                     ▼
    ┌─────────────────────────────────────────┐
    │               COLOR                      │
    │  (ColorBackend - JSON/SQLite/Neo4j/...) │
    │                                          │
    │  NodeColor: properties, timestamps, ... │
    │  EdgeColor: properties, timestamps, ... │
    └─────────────────────────────────────────┘
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable
from enum import Enum

from .utils import utc_now_iso


# === Type Enums (shared between sketch and color) ===

class NodeType(Enum):
    """Standard node types in the graph model."""
    REQUIREMENT = "Requirement"
    SPECIFICATION = "Specification"
    DESIGN_DOCUMENT = "DesignDocument"
    DESIGN_SECTION = "DesignSection"
    CODE_MODULE = "CodeModule"
    CODE_CLASS = "CodeClass"
    CODE_FUNCTION = "CodeFunction"
    TEST_RESULT = "TestResult"
    MEASUREMENT = "Measurement"
    FIGURE = "Figure"


class EdgeType(Enum):
    """Standard edge types in the graph model."""
    DERIVES_FROM = "DERIVES_FROM"
    SATISFIES = "SATISFIES"
    IMPLEMENTS = "IMPLEMENTS"
    TESTS = "TESTS"
    CONTAINS = "CONTAINS"
    REFERENCES = "REFERENCES"
    DEPENDS_ON = "DEPENDS_ON"
    CALLS = "CALLS"


# === Color Data Classes ===

@dataclass
class NodeColor:
    """
    Full details for a node - stored in color backends.

    The node's id, type, and label are in the sketch.
    The color contains everything else.
    """
    id: str  # Must match sketch node ID
    properties: Dict[str, Any] = field(default_factory=dict)
    source_ref: Optional[str] = None  # Reference in source system
    content: Optional[str] = None  # Full text content if applicable
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "properties": self.properties,
            "source_ref": self.source_ref,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NodeColor":
        return cls(
            id=data["id"],
            properties=data.get("properties", {}),
            source_ref=data.get("source_ref"),
            content=data.get("content"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
        )


@dataclass
class EdgeColor:
    """
    Full details for an edge - stored in color backends.

    The edge's id, type, and endpoints are in the sketch.
    The color contains properties and metadata.
    """
    id: str  # Must match sketch edge ID
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "properties": self.properties,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EdgeColor":
        return cls(
            id=data["id"],
            properties=data.get("properties", {}),
            created_at=data.get("created_at", utc_now_iso()),
        )


# === Full Node/Edge (Sketch + Color combined for convenience) ===

@dataclass
class Node:
    """Complete node combining sketch and color data."""
    id: str
    type: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    source_ref: Optional[str] = None
    content: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "properties": self.properties,
            "source_id": self.source_id,
            "source_ref": self.source_ref,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Node":
        return cls(
            id=data["id"],
            type=data["type"],
            label=data["label"],
            properties=data.get("properties", {}),
            source_id=data.get("source_id"),
            source_ref=data.get("source_ref"),
            content=data.get("content"),
            created_at=data.get("created_at", utc_now_iso()),
            updated_at=data.get("updated_at", utc_now_iso()),
        )


@dataclass
class Edge:
    """Complete edge combining sketch and color data."""
    id: str
    type: str
    source_node_id: str
    target_node_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "properties": self.properties,
            "source_id": self.source_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Edge":
        return cls(
            id=data["id"],
            type=data["type"],
            source_node_id=data["source_node_id"],
            target_node_id=data["target_node_id"],
            properties=data.get("properties", {}),
            source_id=data.get("source_id"),
            created_at=data.get("created_at", utc_now_iso()),
        )


# === Statistics ===

@dataclass
class ColorStats:
    """Statistics about color storage."""
    total_nodes: int
    total_edges: int
    storage_size_bytes: Optional[int] = None


@dataclass
class SnapshotInfo:
    """Metadata about a snapshot."""
    id: str
    created_at: str
    label: Optional[str]
    node_count: int
    edge_count: int


# === Color Backend Protocol ===

@runtime_checkable
class ColorBackend(Protocol):
    """
    Protocol defining the interface for color storage backends.

    Color backends store the detailed data for nodes and edges.
    The structure (IDs, types, connections) is in the sketch.
    """

    # === Lifecycle ===

    def connect(self) -> None:
        """Initialize connection to the storage backend."""
        ...

    def close(self) -> None:
        """Close connection and cleanup resources."""
        ...

    def is_connected(self) -> bool:
        """Check if backend is connected and ready."""
        ...

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor) -> None:
        """Store color for a node (node must exist in sketch)."""
        ...

    def get_node_color(self, node_id: str) -> Optional[NodeColor]:
        """Get color for a node by ID."""
        ...

    def update_node_color(self, node_id: str, updates: dict) -> bool:
        """Update a node's color (properties, content, etc.)."""
        ...

    def delete_node_color(self, node_id: str) -> bool:
        """Delete color for a node."""
        ...

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Store color for multiple nodes. Returns count stored."""
        ...

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor) -> None:
        """Store color for an edge (edge must exist in sketch)."""
        ...

    def get_edge_color(self, edge_id: str) -> Optional[EdgeColor]:
        """Get color for an edge by ID."""
        ...

    def update_edge_color(self, edge_id: str, updates: dict) -> bool:
        """Update an edge's color (properties)."""
        ...

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete color for an edge."""
        ...

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Store color for multiple edges. Returns count stored."""
        ...

    # === Query Operations ===

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Get color for multiple nodes by ID."""
        ...

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Get color for multiple edges by ID."""
        ...

    def search_node_content(self, query: str, limit: int = 100) -> List[str]:
        """Search node content/properties. Returns matching node IDs."""
        ...

    # === Statistics ===

    def get_statistics(self) -> ColorStats:
        """Get color storage statistics."""
        ...

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """Create a point-in-time snapshot of color data."""
        ...

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore color data from a snapshot."""
        ...

    def list_snapshots(self) -> List[SnapshotInfo]:
        """List available snapshots."""
        ...

    # === Source Operations ===

    def clear_source(self, source_id: str, node_ids: List[str], edge_ids: List[str]) -> Dict[str, int]:
        """Clear color for nodes/edges from a specific source."""
        ...

    # === Sync/Verification ===

    def list_node_ids(self) -> List[str]:
        """List all node IDs that have color stored."""
        ...

    def list_edge_ids(self) -> List[str]:
        """List all edge IDs that have color stored."""
        ...

    def get_backend_name(self) -> str:
        """Get the name of this backend (json, sqlite, neo4j, arango)."""
        ...


# === Base Implementation ===

class BaseColorBackend(ABC):
    """
    Abstract base class providing common functionality for color backends.
    """

    def __init__(self, config: dict, backend_name: str):
        self.config = config
        self._backend_name = backend_name
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def get_backend_name(self) -> str:
        return self._backend_name

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Default implementation: store one by one."""
        count = 0
        for color in color_list:
            try:
                self.store_node_color(color)
                count += 1
            except Exception:
                pass
        return count

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Default implementation: store one by one."""
        count = 0
        for color in color_list:
            try:
                self.store_edge_color(color)
                count += 1
            except Exception:
                pass
        return count

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Default implementation: get one by one."""
        result = {}
        for nid in node_ids:
            color = self.get_node_color(nid)
            if color:
                result[nid] = color
        return result

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Default implementation: get one by one."""
        result = {}
        for eid in edge_ids:
            color = self.get_edge_color(eid)
            if color:
                result[eid] = color
        return result


# === Legacy compatibility - ColorBackend alias ===
# For backwards compatibility during transition
ColorBackend = ColorBackend
BaseColorBackend = BaseColorBackend
ColorStats = ColorStats
