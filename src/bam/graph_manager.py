"""
BAM Graph Manager

Manages the graph model state including nodes, edges, snapshots, and queries.
Wraps the ModelManager (sketch/color layer architecture).

Usage:
    gm = GraphManager(project_dir="/path/to/project")
    stats = gm.get_statistics()
    gm.close()
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
import uuid

from .backends import get_model_manager
from .backends.base import Node as BackendNode, Edge as BackendEdge, NodeType, EdgeType
from .backends.utils import utc_now_iso


@dataclass
class Node:
    """Represents a node in the graph model (legacy format)."""
    id: str
    type: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    source_ref: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass
class Edge:
    """Represents an edge in the graph model (legacy format)."""
    id: str
    type: str
    source_node_id: str
    target_node_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    source_id: Optional[str] = None
    created_at: str = field(default_factory=utc_now_iso)


class GraphManager:
    """Manages the graph model state for a project."""

    def __init__(self, project_dir: str, config: dict = None):
        """
        Args:
            project_dir: Path to the project model directory (required).
            config: Optional override config. Loaded from project.json if omitted.
        """
        self.project_dir = Path(project_dir)
        self._mm = get_model_manager(project_dir=project_dir, config=config)
        self._mm.load()
        self.version_info = self._load_version()

    @property
    def _version_path(self) -> Path:
        return self.project_dir / "model" / "version.json"

    def _load_version(self) -> dict:
        vp = self._version_path
        if vp.exists():
            with open(vp, 'r') as f:
                return json.load(f)
        return {"current": "1.0.0", "snapshotCount": 0, "history": []}

    def _save_version(self):
        vp = self._version_path
        vp.parent.mkdir(parents=True, exist_ok=True)
        with open(vp, 'w') as f:
            json.dump(self.version_info, f, indent=2)

    def close(self):
        """Close the graph manager and release resources."""
        self._mm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _node_to_legacy_dict(self, node: BackendNode) -> dict:
        """Convert a BackendNode to legacy dict format."""
        return {
            "id": node.id,
            "type": node.type,
            "label": node.label,
            "properties": node.properties or {},
            "source_id": node.source_id,
            "source_ref": node.source_ref,
            "created_at": node.created_at,
            "updated_at": node.updated_at,
        }

    def _edge_to_legacy_dict(self, edge: BackendEdge) -> dict:
        """Convert a BackendEdge to legacy dict format."""
        return {
            "id": edge.id,
            "type": edge.type,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "properties": edge.properties or {},
            "source_id": edge.source_id,
            "created_at": edge.created_at,
        }

    @property
    def model(self) -> dict:
        """
        Legacy property - returns model in old format.
        Note: This rebuilds the dict each time for compatibility.
        Uses bulk fetch for efficiency.
        """
        # Bulk fetch all nodes and edges in single operations
        all_nodes = self._mm.get_all_nodes(include_color=True)
        all_edges = self._mm.get_all_edges(include_color=True)

        nodes = {n.id: self._node_to_legacy_dict(n) for n in all_nodes}
        edges = {e.id: self._edge_to_legacy_dict(e) for e in all_edges}

        return {
            "metadata": self._mm.sketch.model.get("metadata", {}),
            "nodes": nodes,
            "edges": edges
        }

    # Node Operations

    def add_node(self, node: Node) -> str:
        """Add a node to the graph model."""
        if not node.id:
            node.id = f"node-{uuid.uuid4().hex[:12]}"

        # Check if node exists in sketch
        if self._mm.sketch.get_node(node.id):
            raise ValueError(f"Node already exists: {node.id}")

        # Convert legacy Node to BackendNode for ModelManager
        backend_node = BackendNode(
            id=node.id,
            type=node.type,
            label=node.label,
            source_id=node.source_id,
            properties=node.properties,
            source_ref=node.source_ref,
            content=node.properties.get("content"),  # Extract content if present
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
        self._mm.add_node(backend_node)
        return node.id

    def get_node(self, node_id: str, color: str = None, backend: str = None) -> Optional[dict]:
        """
        Get a node by ID.

        Args:
            node_id: Node ID to retrieve
            color: Optional color to get color from (e.g., "conceptual", "design")
            backend: Optional specific backend name to use

        Returns:
            Node as dict if found, None otherwise
        """
        node = self._mm.get_node(node_id, color=color, backend=backend)
        if node:
            return self._node_to_legacy_dict(node)
        return None

    def update_node(self, node_id: str, updates: dict) -> bool:
        """Update a node's properties."""
        node = self._mm.get_node(node_id)
        if not node:
            return False

        # Build the updates dict for ModelManager
        mm_updates = {}

        # Update label if provided
        if "label" in updates:
            mm_updates["label"] = updates["label"]

        # Build merged properties
        if "properties" in updates:
            new_properties = dict(node.properties or {})
            new_properties.update(updates["properties"])
            mm_updates["properties"] = new_properties

        # Update via ModelManager
        self._mm.update_node(node_id, mm_updates)
        return True

    def delete_node(self, node_id: str, cascade_edges: bool = True) -> bool:
        """Delete a node from the graph."""
        if not self._mm.sketch.get_node(node_id):
            return False

        # Remove connected edges if cascade
        if cascade_edges:
            connected_edge_ids = self._mm.sketch.get_connected_edge_ids(node_id)
            for edge_id in connected_edge_ids:
                self._mm.delete_edge(edge_id)

        self._mm.delete_node(node_id)
        return True

    def find_nodes(self, node_type: str = None, source_id: str = None,
                   label_contains: str = None, include_color: bool = True,
                   color: str = None, backend: str = None) -> List[dict]:
        """
        Find nodes matching criteria.

        Args:
            node_type: Filter by node type
            source_id: Filter by source ID
            label_contains: Filter by label substring
            include_color: Whether to include color data (default True for backward compat)
            color: Optional color to get color from
            backend: Optional specific backend name

        Returns:
            List of matching nodes as dicts
        """
        nodes = self._mm.find_nodes(
            node_type=node_type,
            source_id=source_id,
            label_contains=label_contains,
            include_color=include_color,
            color=color,
            backend=backend,
        )
        return [self._node_to_legacy_dict(n) for n in nodes]

    def find_nodes_by_label(self, label: str, node_type: str = None,
                            normalize: bool = True) -> List[dict]:
        """Find nodes whose label matches (substring, normalized).

        Args:
            label: Label to search for.
            node_type: Optional type filter.
            normalize: If True, compare lowercased/stripped labels.

        Returns:
            List of matching nodes as dicts.
        """
        results = []
        needle = label.lower().replace("_", " ").strip() if normalize else label

        for nid, node_data in self._mm.sketch.model["nodes"].items():
            if node_type and node_data["type"] != node_type:
                continue
            node_label = node_data.get("label", "")
            haystack = node_label.lower().replace("_", " ").strip() if normalize else node_label
            if needle in haystack or haystack in needle:
                node = self._mm.get_node(nid, include_color=False)
                if node:
                    results.append(self._node_to_legacy_dict(node))
        return results

    # Edge Operations

    def add_edge(self, edge: Edge) -> str:
        """Add an edge to the graph model."""
        if not edge.id:
            edge.id = f"edge-{uuid.uuid4().hex[:12]}"

        # Validate nodes exist
        if not self._mm.sketch.get_node(edge.source_node_id):
            raise ValueError(f"Source node not found: {edge.source_node_id}")
        if not self._mm.sketch.get_node(edge.target_node_id):
            raise ValueError(f"Target node not found: {edge.target_node_id}")

        if self._mm.sketch.get_edge(edge.id):
            raise ValueError(f"Edge already exists: {edge.id}")

        # Convert legacy Edge to BackendEdge for ModelManager
        backend_edge = BackendEdge(
            id=edge.id,
            type=edge.type,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            source_id=edge.source_id,
            properties=edge.properties,
            created_at=edge.created_at,
        )
        self._mm.add_edge(backend_edge)
        return edge.id

    def get_edge(self, edge_id: str) -> Optional[dict]:
        """Get an edge by ID."""
        edge = self._mm.get_edge(edge_id)
        if edge:
            return self._edge_to_legacy_dict(edge)
        return None

    def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge from the graph."""
        if not self._mm.sketch.get_edge(edge_id):
            return False
        self._mm.delete_edge(edge_id)
        return True

    def find_edges(self, edge_type: str = None, source_node_id: str = None,
                   target_node_id: str = None) -> List[dict]:
        """Find edges matching criteria."""
        results = []
        for edge_id in self._mm.sketch.list_edge_ids():
            sketch_edge = self._mm.sketch.get_edge(edge_id)
            if not sketch_edge:
                continue

            # Filter by type
            if edge_type and sketch_edge.type != edge_type:
                continue

            # Filter by source node
            if source_node_id and sketch_edge.source_node_id != source_node_id:
                continue

            # Filter by target node
            if target_node_id and sketch_edge.target_node_id != target_node_id:
                continue

            # Get full edge data
            edge = self._mm.get_edge(edge_id)
            if edge:
                results.append(self._edge_to_legacy_dict(edge))

        return results

    def get_connected_nodes(self, node_id: str, direction: str = "both",
                            edge_type: str = None) -> List[dict]:
        """Get nodes connected to a given node."""
        # First collect all connected node IDs from sketch (fast)
        connected_ids = set()

        for eid, edge in self._mm.sketch.model["edges"].items():
            if edge_type and edge["type"] != edge_type:
                continue

            if direction in ("outgoing", "both") and edge["source_node_id"] == node_id:
                connected_ids.add(edge["target_node_id"])

            if direction in ("incoming", "both") and edge["target_node_id"] == node_id:
                connected_ids.add(edge["source_node_id"])

        # Bulk fetch all connected nodes
        nodes = self._mm.get_nodes_by_ids(list(connected_ids), include_color=True)
        return [self._node_to_legacy_dict(n) for n in nodes]

    # Graph Queries

    def get_subgraph(self, root_node_id: str, max_depth: int = 3) -> dict:
        """Extract a subgraph starting from a root node."""
        # Use sketch's efficient subgraph extraction to get IDs
        node_ids, edge_ids = self._mm.sketch.get_subgraph_ids(root_node_id, max_depth)

        # Bulk fetch all nodes
        fetched_nodes = self._mm.get_nodes_by_ids(list(node_ids), include_color=True)
        nodes = {n.id: self._node_to_legacy_dict(n) for n in fetched_nodes}

        # Fetch edges (edge color is typically lighter, but could be optimized too)
        edges = {}
        for edge_id in edge_ids:
            edge = self._mm.get_edge(edge_id)
            if edge:
                edges[edge_id] = self._edge_to_legacy_dict(edge)

        return {"nodes": nodes, "edges": edges}

    def get_statistics(self) -> dict:
        """Get graph statistics."""
        # Direct access to sketch data (no individual fetches needed)
        nodes_data = self._mm.sketch.model["nodes"]
        edges_data = self._mm.sketch.model["edges"]

        node_types = {}
        for node in nodes_data.values():
            t = node["type"]
            node_types[t] = node_types.get(t, 0) + 1

        edge_types = {}
        for edge in edges_data.values():
            t = edge["type"]
            edge_types[t] = edge_types.get(t, 0) + 1

        return {
            "totalNodes": len(nodes_data),
            "totalEdges": len(edges_data),
            "nodesByType": node_types,
            "edgesByType": edge_types,
            "version": self.version_info["current"],
            "backends": self._mm.list_backends(),
            "colors": list(self._mm.list_colors().keys()),
        }

    def list_colors(self) -> dict:
        """List all colors with their node types and backends."""
        return self._mm.list_colors()

    def get_color_for_type(self, node_type: str) -> List[str]:
        """Get colors that a node type belongs to."""
        return list(self._mm.get_color_for_type(node_type))

    # Snapshot Operations
    # Note: These now delegate to ModelManager which handles sketch + all color backends

    def create_snapshot(self, label: str = None) -> str:
        """Create a point-in-time snapshot of sketch and all color backends."""
        snapshot_id = self._mm.create_snapshot(label)

        # Update version tracking
        self.version_info["lastSnapshot"] = snapshot_id
        self.version_info["snapshotCount"] = self.version_info.get("snapshotCount", 0) + 1
        self._save_version()

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore sketch and all color backends from a snapshot."""
        try:
            self._mm.restore_snapshot(snapshot_id)

            # Update version history
            self.version_info["history"].append({
                "action": "restore",
                "snapshotId": snapshot_id,
                "timestamp": utc_now_iso()
            })
            self._save_version()

            return True
        except Exception:
            return False

    def list_snapshots(self) -> List[dict]:
        """List available snapshots from sketch."""
        return self._mm.sketch.list_snapshots()

    # Version Operations

    def bump_version(self, bump_type: str = "patch") -> str:
        """Bump the model version."""
        current = self.version_info["current"]
        parts = [int(x) for x in current.split(".")]

        if bump_type == "major":
            parts[0] += 1
            parts[1] = 0
            parts[2] = 0
        elif bump_type == "minor":
            parts[1] += 1
            parts[2] = 0
        else:  # patch
            parts[2] += 1

        new_version = ".".join(str(x) for x in parts)

        self.version_info["history"].append({
            "version": self.version_info["current"],
            "bumpedTo": new_version,
            "timestamp": utc_now_iso()
        })
        self.version_info["current"] = new_version
        self._save_version()

        return new_version

    # Bulk Operations

    def bulk_add_nodes(self, nodes: List[Node]) -> List[str]:
        """Add multiple nodes at once."""
        added_ids = []
        for node in nodes:
            if not node.id:
                node.id = f"node-{uuid.uuid4().hex[:12]}"

            backend_node = BackendNode(
                id=node.id,
                type=node.type,
                label=node.label,
                source_id=node.source_id,
                properties=node.properties,
                source_ref=node.source_ref,
                content=node.properties.get("content"),
                created_at=node.created_at,
                updated_at=node.updated_at,
            )
            self._mm.add_node(backend_node)
            added_ids.append(node.id)

        return added_ids

    def bulk_add_edges(self, edges: List[Edge]) -> List[str]:
        """Add multiple edges at once."""
        added_ids = []
        for edge in edges:
            if not edge.id:
                edge.id = f"edge-{uuid.uuid4().hex[:12]}"

            # Skip if nodes don't exist
            if not self._mm.sketch.get_node(edge.source_node_id):
                continue
            if not self._mm.sketch.get_node(edge.target_node_id):
                continue

            backend_edge = BackendEdge(
                id=edge.id,
                type=edge.type,
                source_node_id=edge.source_node_id,
                target_node_id=edge.target_node_id,
                source_id=edge.source_id,
                properties=edge.properties,
                created_at=edge.created_at,
            )
            self._mm.add_edge(backend_edge)
            added_ids.append(edge.id)

        return added_ids

    def clear_source(self, source_id: str):
        """Remove all nodes and edges from a specific source."""
        # Find nodes from this source
        nodes_to_remove = []
        for node_id in self._mm.sketch.list_node_ids():
            sketch_node = self._mm.sketch.get_node(node_id)
            if sketch_node and sketch_node.source_id == source_id:
                nodes_to_remove.append(node_id)

        # Find edges from this source or connected to removed nodes
        edges_to_remove = []
        for edge_id in self._mm.sketch.list_edge_ids():
            sketch_edge = self._mm.sketch.get_edge(edge_id)
            if not sketch_edge:
                continue
            if sketch_edge.source_id == source_id:
                edges_to_remove.append(edge_id)
            elif sketch_edge.source_node_id in nodes_to_remove:
                edges_to_remove.append(edge_id)
            elif sketch_edge.target_node_id in nodes_to_remove:
                edges_to_remove.append(edge_id)

        # Remove edges first
        for edge_id in edges_to_remove:
            self._mm.delete_edge(edge_id)

        # Remove nodes
        for node_id in nodes_to_remove:
            self._mm.delete_node(node_id)

        return {
            "removedNodes": len(nodes_to_remove),
            "removedEdges": len(edges_to_remove)
        }

    # Consistency Operations (new with multi-backend support)

    def check_consistency(self) -> dict:
        """Check consistency across all color backends."""
        report = self._mm.check_consistency()
        # Convert dataclass to dict for backward compatibility
        return {
            "consistent": report.is_consistent,
            "sketch_node_count": report.sketch_node_count,
            "sketch_edge_count": report.sketch_edge_count,
            "issues": report.backend_reports,
            "messages": report.issues,
        }

    def repair_consistency(self) -> dict:
        """Repair inconsistencies (orphan color data)."""
        result = self._mm.repair_consistency()
        # Result is already a dict from ModelManager
        return result


def main():
    """CLI entry point for graph operations."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Graph Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Stats command
    subparsers.add_parser("stats", help="Show graph statistics")

    # Snapshot commands
    snap_create = subparsers.add_parser("snapshot", help="Create a snapshot")
    snap_create.add_argument("--label", "-l", help="Snapshot label")

    subparsers.add_parser("snapshots", help="List snapshots")

    restore_parser = subparsers.add_parser("restore", help="Restore from snapshot")
    restore_parser.add_argument("snapshot_id", help="Snapshot ID to restore")

    # Find command
    find_parser = subparsers.add_parser("find", help="Find nodes")
    find_parser.add_argument("--type", "-t", help="Node type")
    find_parser.add_argument("--source", "-s", help="Source ID")
    find_parser.add_argument("--label", "-l", help="Label contains")

    # Consistency commands (new)
    subparsers.add_parser("check", help="Check consistency across backends")
    subparsers.add_parser("repair", help="Repair inconsistencies")

    parser.add_argument("--project", "-p", required=True,
                        help="Path to the BAM project directory")

    args = parser.parse_args()

    # Use context manager to ensure proper cleanup
    with GraphManager(project_dir=args.project) as gm:
        if args.command == "stats":
            stats = gm.get_statistics()
            print("Graph Statistics:")
            print(f"  Version: {stats['version']}")
            print(f"  Total Nodes: {stats['totalNodes']}")
            print(f"  Total Edges: {stats['totalEdges']}")
            print(f"  Backends: {', '.join(stats.get('backends', ['json']))}")
            if stats['nodesByType']:
                print("  Nodes by Type:")
                for t, c in stats['nodesByType'].items():
                    print(f"    {t}: {c}")
            if stats['edgesByType']:
                print("  Edges by Type:")
                for t, c in stats['edgesByType'].items():
                    print(f"    {t}: {c}")

        elif args.command == "snapshot":
            snapshot_id = gm.create_snapshot(args.label)
            print(f"Created snapshot: {snapshot_id}")

        elif args.command == "snapshots":
            snapshots = gm.list_snapshots()
            if snapshots:
                print("Available snapshots:")
                for s in snapshots:
                    node_count = s.get('nodeCount', s.get('node_count', '?'))
                    edge_count = s.get('edgeCount', s.get('edge_count', '?'))
                    print(f"  {s['id']} - {node_count} nodes, {edge_count} edges")
            else:
                print("No snapshots available")

        elif args.command == "restore":
            if gm.restore_snapshot(args.snapshot_id):
                print(f"Restored from: {args.snapshot_id}")
            else:
                print(f"Snapshot not found: {args.snapshot_id}")

        elif args.command == "find":
            nodes = gm.find_nodes(
                node_type=args.type,
                source_id=args.source,
                label_contains=args.label
            )
            if nodes:
                print(f"Found {len(nodes)} nodes:")
                for n in nodes[:20]:  # Limit output
                    print(f"  {n['id']}: {n['label']} ({n['type']})")
                if len(nodes) > 20:
                    print(f"  ... and {len(nodes) - 20} more")
            else:
                print("No nodes found")

        elif args.command == "check":
            result = gm.check_consistency()
            print("Consistency Check:")
            if result["consistent"]:
                print("  All backends are consistent")
            else:
                print("  Inconsistencies found:")
                for backend, report in result.get("issues", {}).items():
                    orphan_nodes = report.get("orphan_nodes", [])
                    orphan_edges = report.get("orphan_edges", [])
                    missing_nodes = report.get("missing_nodes", [])
                    missing_edges = report.get("missing_edges", [])
                    if orphan_nodes or orphan_edges or missing_nodes or missing_edges:
                        print(f"    {backend}:")
                        if orphan_nodes:
                            print(f"      Orphan nodes: {len(orphan_nodes)}")
                        if orphan_edges:
                            print(f"      Orphan edges: {len(orphan_edges)}")
                        if missing_nodes:
                            print(f"      Missing nodes: {len(missing_nodes)}")
                        if missing_edges:
                            print(f"      Missing edges: {len(missing_edges)}")

        elif args.command == "repair":
            result = gm.repair_consistency()
            print("Repair Results:")
            for backend, counts in result.items():
                if counts["nodes_removed"] or counts["edges_removed"]:
                    print(f"  {backend}:")
                    print(f"    Nodes removed: {counts['nodes_removed']}")
                    print(f"    Edges removed: {counts['edges_removed']}")
            if not any(c["nodes_removed"] or c["edges_removed"] for c in result.values()):
                print("  No repairs needed")

        else:
            parser.print_help()


if __name__ == "__main__":
    main()
