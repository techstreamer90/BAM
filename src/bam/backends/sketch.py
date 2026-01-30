"""
BAM Sketch Manager

The Sketch is the lightweight navigation layer of the digital twin.
It contains only structural information:
- Node: id, type, label
- Edge: id, type, source_node_id, target_node_id

The Sketch is always JSON, always fast, always available.
Full details (properties, content) live in the Color backends.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict


def normalize_edge_type(edge_type: str) -> str:
    """Normalize an edge type to UPPERCASE convention.

    Examples: 'contains' -> 'CONTAINS', 'INSTANTIATES' -> 'INSTANTIATES'
    """
    return edge_type.upper()


@dataclass
class SketchNode:
    """Lightweight node in the sketch - just structure, no details."""
    id: str
    type: str
    label: str
    source_id: Optional[str] = None  # Which source created this node

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "label": self.label,
            "source_id": self.source_id,
        }

    @classmethod
    def from_dict(cls, data: dict, fallback_id: str = None) -> "SketchNode":
        """Create SketchNode from dict, accepting both old and new formats.

        Old format: {type, name, color} with dict key as implicit id
        New format: {id, type, label, source_id}
        """
        node_id = data.get("id") or fallback_id
        if not node_id:
            raise ValueError("SketchNode requires an 'id' field or fallback_id")
        label = data.get("label") or data.get("name", "")
        return cls(
            id=node_id,
            type=data["type"],
            label=label,
            source_id=data.get("source_id"),
        )


@dataclass
class SketchEdge:
    """Lightweight edge in the sketch - just connections, no details."""
    id: str
    type: str
    source_node_id: str
    target_node_id: str
    source_id: Optional[str] = None  # Which source created this edge

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "source_node_id": self.source_node_id,
            "target_node_id": self.target_node_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_dict(cls, data: dict, fallback_id: str = None) -> "SketchEdge":
        """Create SketchEdge from dict, accepting both old and new formats.

        Old format: {type, source, target} with dict key as implicit id
        New format: {id, type, source_node_id, target_node_id, source_id}
        """
        edge_id = data.get("id") or fallback_id
        if not edge_id:
            raise ValueError("SketchEdge requires an 'id' field or fallback_id")
        source = data.get("source_node_id") or data.get("source", "")
        target = data.get("target_node_id") or data.get("target", "")
        return cls(
            id=edge_id,
            type=data["type"],
            source_node_id=source,
            target_node_id=target,
            source_id=data.get("source_id"),
        )


@dataclass
class SketchStats:
    """Statistics about the sketch structure."""
    total_nodes: int
    total_edges: int
    nodes_by_type: Dict[str, int]
    edges_by_type: Dict[str, int]
    nodes_by_source: Dict[str, int]
    version: str


class SketchManager:
    """
    Manages the sketch - the lightweight structural layer.

    The sketch provides:
    - Fast navigation (what exists, how it connects)
    - Structure validation (are all referenced nodes present?)
    - Source tracking (which source created each node/edge)

    It does NOT contain:
    - Full properties/content (that's in the color)
    - Timestamps (color tracks those)
    - Large text fields
    """

    def __init__(self, sketch_path: Path):
        self.sketch_path = Path(sketch_path)
        self.model: Dict = {}
        self._loaded = False
        self._adjacency_index: Optional[Dict[str, List[tuple]]] = None

    def load(self) -> None:
        """Load sketch from disk."""
        if self.sketch_path.exists():
            with open(self.sketch_path, 'r') as f:
                self.model = json.load(f)
        else:
            self.model = self._empty_sketch()
        self._normalize_edge_types()
        self._loaded = True
        self._adjacency_index = None  # Reset index on load

    def _normalize_edge_types(self) -> None:
        """Normalize all edge types to UPPERCASE convention."""
        for edge in self.model.get("edges", {}).values():
            edge["type"] = normalize_edge_type(edge["type"])

    def save(self) -> None:
        """Save sketch to disk."""
        self.model["metadata"]["lastModified"] = datetime.now(timezone.utc).isoformat()
        self.model["metadata"]["nodeCount"] = len(self.model["nodes"])
        self.model["metadata"]["edgeCount"] = len(self.model["edges"])

        self.sketch_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.sketch_path, 'w') as f:
            json.dump(self.model, f, indent=2)

    def _empty_sketch(self) -> dict:
        """Create empty sketch structure."""
        return {
            "version": "1.0.0",
            "metadata": {
                "created": datetime.now(timezone.utc).isoformat(),
                "lastModified": None,
                "nodeCount": 0,
                "edgeCount": 0,
            },
            "nodes": {},
            "edges": {},
        }

    # === Adjacency Index for Fast Navigation ===

    def _build_adjacency_index(self) -> Dict[str, List[tuple]]:
        """
        Build adjacency index mapping node_id -> [(edge_id, other_node_id, direction), ...].

        Direction is "outgoing" if this node is source, "incoming" if target.
        """
        index: Dict[str, List[tuple]] = {}
        for eid, edge in self.model["edges"].items():
            src = edge["source_node_id"]
            tgt = edge["target_node_id"]
            edge_type = edge["type"]

            if src not in index:
                index[src] = []
            index[src].append((eid, tgt, "outgoing", edge_type))

            if tgt not in index:
                index[tgt] = []
            index[tgt].append((eid, src, "incoming", edge_type))

        return index

    def _get_adjacency_index(self) -> Dict[str, List[tuple]]:
        """Get adjacency index, building if needed."""
        if self._adjacency_index is None:
            self._adjacency_index = self._build_adjacency_index()
        return self._adjacency_index

    def _invalidate_adjacency_index(self) -> None:
        """Invalidate the adjacency index (call when edges change)."""
        self._adjacency_index = None

    # === Node Operations ===

    def add_node(self, node: SketchNode) -> str:
        """Add a node to the sketch."""
        if node.id in self.model["nodes"]:
            raise ValueError(f"Node already exists in sketch: {node.id}")

        self.model["nodes"][node.id] = node.to_dict()
        return node.id

    def get_node(self, node_id: str) -> Optional[SketchNode]:
        """Get a node from the sketch."""
        data = self.model["nodes"].get(node_id)
        return SketchNode.from_dict(data) if data else None

    def has_node(self, node_id: str) -> bool:
        """Check if node exists in sketch."""
        return node_id in self.model["nodes"]

    def update_node(self, node_id: str, label: str = None, node_type: str = None) -> bool:
        """Update a node's label or type."""
        if node_id not in self.model["nodes"]:
            return False

        if label is not None:
            self.model["nodes"][node_id]["label"] = label
        if node_type is not None:
            self.model["nodes"][node_id]["type"] = node_type

        return True

    def delete_node(self, node_id: str, cascade_edges: bool = True) -> bool:
        """Delete a node from the sketch."""
        if node_id not in self.model["nodes"]:
            return False

        if cascade_edges:
            edges_to_remove = [
                eid for eid, edge in self.model["edges"].items()
                if edge["source_node_id"] == node_id or edge["target_node_id"] == node_id
            ]
            for eid in edges_to_remove:
                del self.model["edges"][eid]

        del self.model["nodes"][node_id]
        return True

    def find_nodes(
        self,
        node_type: Optional[str] = None,
        source_id: Optional[str] = None,
        label_contains: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SketchNode]:
        """Find nodes matching criteria."""
        results = []

        for node_data in self.model["nodes"].values():
            if node_type and node_data["type"] != node_type:
                continue
            if source_id and node_data.get("source_id") != source_id:
                continue
            if label_contains and label_contains.lower() not in node_data["label"].lower():
                continue

            results.append(SketchNode.from_dict(node_data))

            if limit and len(results) >= limit:
                break

        return results

    def list_node_ids(self) -> List[str]:
        """Get all node IDs."""
        return list(self.model["nodes"].keys())

    # === Edge Operations ===

    def add_edge(self, edge: SketchEdge) -> str:
        """Add an edge to the sketch."""
        # Validate nodes exist
        if edge.source_node_id not in self.model["nodes"]:
            raise ValueError(f"Source node not in sketch: {edge.source_node_id}")
        if edge.target_node_id not in self.model["nodes"]:
            raise ValueError(f"Target node not in sketch: {edge.target_node_id}")

        if edge.id in self.model["edges"]:
            raise ValueError(f"Edge already exists in sketch: {edge.id}")

        self.model["edges"][edge.id] = edge.to_dict()
        self._invalidate_adjacency_index()
        return edge.id

    def get_edge(self, edge_id: str) -> Optional[SketchEdge]:
        """Get an edge from the sketch."""
        data = self.model["edges"].get(edge_id)
        return SketchEdge.from_dict(data) if data else None

    def has_edge(self, edge_id: str) -> bool:
        """Check if edge exists in sketch."""
        return edge_id in self.model["edges"]

    def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge from the sketch."""
        if edge_id not in self.model["edges"]:
            return False
        del self.model["edges"][edge_id]
        self._invalidate_adjacency_index()
        return True

    def find_edges(
        self,
        edge_type: Optional[str] = None,
        source_node_id: Optional[str] = None,
        target_node_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[SketchEdge]:
        """Find edges matching criteria."""
        results = []

        for edge_data in self.model["edges"].values():
            if edge_type and edge_data["type"] != edge_type:
                continue
            if source_node_id and edge_data["source_node_id"] != source_node_id:
                continue
            if target_node_id and edge_data["target_node_id"] != target_node_id:
                continue

            results.append(SketchEdge.from_dict(edge_data))

            if limit and len(results) >= limit:
                break

        return results

    def list_edge_ids(self) -> List[str]:
        """Get all edge IDs."""
        return list(self.model["edges"].keys())

    def get_connected_edge_ids(self, node_id: str) -> List[str]:
        """Get IDs of edges connected to a node (incoming and outgoing)."""
        index = self._get_adjacency_index()
        if node_id not in index:
            return []
        return [entry[0] for entry in index[node_id]]

    # === Navigation Queries ===

    def get_connected_node_ids(
        self,
        node_id: str,
        direction: str = "both",
        edge_type: Optional[str] = None,
    ) -> List[str]:
        """Get IDs of nodes connected to a given node. Uses adjacency index for O(1) lookups."""
        index = self._get_adjacency_index()
        if node_id not in index:
            return []

        connected = []
        for eid, other_node, edge_dir, etype in index[node_id]:
            if edge_type and etype != edge_type:
                continue
            if direction == "both" or direction == edge_dir:
                connected.append(other_node)

        return connected

    def get_subgraph_ids(
        self,
        root_node_id: str,
        max_depth: int = 3,
    ) -> tuple:
        """
        Get IDs of nodes and edges in a subgraph. Uses adjacency index for efficiency.

        Returns:
            Tuple of (node_ids: Set[str], edge_ids: Set[str])
        """
        index = self._get_adjacency_index()
        visited_nodes: Set[str] = set()
        visited_edges: Set[str] = set()

        def traverse(nid: str, depth: int):
            if depth > max_depth or nid in visited_nodes:
                return
            visited_nodes.add(nid)

            if nid not in index:
                return

            for eid, other_node, edge_dir, etype in index[nid]:
                visited_edges.add(eid)
                traverse(other_node, depth + 1)

        traverse(root_node_id, 0)

        return (visited_nodes, visited_edges)

    # === Statistics ===

    def get_statistics(self) -> SketchStats:
        """Get sketch statistics."""
        nodes_by_type: Dict[str, int] = {}
        edges_by_type: Dict[str, int] = {}
        nodes_by_source: Dict[str, int] = {}

        for node in self.model["nodes"].values():
            t = node["type"]
            nodes_by_type[t] = nodes_by_type.get(t, 0) + 1

            s = node.get("source_id", "unknown")
            nodes_by_source[s] = nodes_by_source.get(s, 0) + 1

        for edge in self.model["edges"].values():
            t = edge["type"]
            edges_by_type[t] = edges_by_type.get(t, 0) + 1

        return SketchStats(
            total_nodes=len(self.model["nodes"]),
            total_edges=len(self.model["edges"]),
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
            nodes_by_source=nodes_by_source,
            version=self.model.get("version", "1.0.0"),
        )

    # === Bulk Operations ===

    def bulk_add_nodes(self, nodes: List[SketchNode]) -> List[str]:
        """Add multiple nodes at once."""
        added = []
        for node in nodes:
            if node.id not in self.model["nodes"]:
                self.model["nodes"][node.id] = node.to_dict()
                added.append(node.id)
        return added

    def bulk_add_edges(self, edges: List[SketchEdge]) -> List[str]:
        """Add multiple edges at once (skips invalid)."""
        added = []
        for edge in edges:
            if edge.source_node_id in self.model["nodes"] and \
               edge.target_node_id in self.model["nodes"] and \
               edge.id not in self.model["edges"]:
                self.model["edges"][edge.id] = edge.to_dict()
                added.append(edge.id)
        if added:
            self._invalidate_adjacency_index()
        return added

    # === Source Operations ===

    def clear_source(self, source_id: str) -> Dict[str, int]:
        """Remove all nodes and edges from a specific source."""
        nodes_to_remove = [
            nid for nid, node in self.model["nodes"].items()
            if node.get("source_id") == source_id
        ]

        edges_to_remove = [
            eid for eid, edge in self.model["edges"].items()
            if edge.get("source_id") == source_id
            or edge["source_node_id"] in nodes_to_remove
            or edge["target_node_id"] in nodes_to_remove
        ]

        for eid in edges_to_remove:
            del self.model["edges"][eid]

        for nid in nodes_to_remove:
            del self.model["nodes"][nid]

        if edges_to_remove:
            self._invalidate_adjacency_index()

        return {
            "removed_nodes": len(nodes_to_remove),
            "removed_edges": len(edges_to_remove),
        }

    # === Validation ===

    def validate(self) -> List[str]:
        """Validate sketch integrity. Returns list of issues."""
        issues = []

        # Check all edge endpoints exist
        for eid, edge in self.model["edges"].items():
            if edge["source_node_id"] not in self.model["nodes"]:
                issues.append(f"Edge {eid} references missing source node: {edge['source_node_id']}")
            if edge["target_node_id"] not in self.model["nodes"]:
                issues.append(f"Edge {eid} references missing target node: {edge['target_node_id']}")

        return issues

    # === Snapshot/Export ===

    def export_structure(self) -> dict:
        """Export sketch structure for comparison."""
        return {
            "node_ids": sorted(self.model["nodes"].keys()),
            "edge_ids": sorted(self.model["edges"].keys()),
            "node_types": sorted(set(n["type"] for n in self.model["nodes"].values())),
            "edge_types": sorted(set(e["type"] for e in self.model["edges"].values())),
        }

    def create_snapshot(self, label: str = None) -> str:
        """
        Create a point-in-time snapshot of the sketch.

        Returns:
            Snapshot ID
        """
        snapshots_dir = self.sketch_path.parent / "sketch_snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"sketch-{timestamp}"
        if label:
            snapshot_id = f"{snapshot_id}-{label}"

        snapshot_path = snapshots_dir / f"{snapshot_id}.json"

        snapshot = {
            "id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "node_count": len(self.model["nodes"]),
            "edge_count": len(self.model["edges"]),
            "model": self.model,
        }

        with open(snapshot_path, 'w') as f:
            json.dump(snapshot, f, indent=2)

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        Restore sketch from a snapshot.

        Returns:
            True if restored successfully, False if snapshot not found
        """
        snapshots_dir = self.sketch_path.parent / "sketch_snapshots"
        snapshot_path = snapshots_dir / f"{snapshot_id}.json"

        if not snapshot_path.exists():
            return False

        with open(snapshot_path, 'r') as f:
            snapshot = json.load(f)

        self.model = snapshot["model"]
        self.save()
        return True

    def list_snapshots(self) -> List[dict]:
        """List available sketch snapshots."""
        snapshots_dir = self.sketch_path.parent / "sketch_snapshots"
        if not snapshots_dir.exists():
            return []

        snapshots = []
        for path in sorted(snapshots_dir.glob("sketch-*.json")):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    snapshots.append({
                        "id": data["id"],
                        "created_at": data["created_at"],
                        "label": data.get("label"),
                        "node_count": data.get("node_count", 0),
                        "edge_count": data.get("edge_count", 0),
                    })
            except (json.JSONDecodeError, KeyError):
                continue

        return snapshots
