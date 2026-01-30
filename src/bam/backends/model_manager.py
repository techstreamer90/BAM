"""
BAM Model Manager

Orchestrates the Sketch (structure) and Color Layer backends (details).

This is the main entry point for working with the graph model.
It maintains:
- One sketch (always JSON, lightweight, fast)
- Multiple color backends organized by colors (conceptual, design, verification, cv)

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                        ModelManager                              │
    ├─────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │  ┌────────────────────────────────────────────────────────┐     │
    │  │                      SKETCH                           │     │
    │  │              (Single source of truth)                   │     │
    │  │                                                         │     │
    │  │  • What nodes exist (id, type, label)                  │     │
    │  │  • How they connect (edges)                            │     │
    │  │  • Fast navigation                                     │     │
    │  └────────────────────────────────────────────────────────┘     │
    │                            │                                     │
    │                            │ node_type → colors                  │
    │                            ▼                                     │
    │  ┌────────────────────────────────────────────────────────┐     │
    │  │                    COLOR MANAGER                        │     │
    │  │          (Routes by node type to colors)                │     │
    │  │                                                         │     │
    │  │  ┌──────────┐ ┌────────┐ ┌────────────┐ ┌────┐        │     │
    │  │  │conceptual│ │ design │ │verification│ │ cv │        │     │
    │  │  └────┬─────┘ └───┬────┘ └─────┬──────┘ └─┬──┘        │     │
    │  │       │           │            │          │            │     │
    │  │       ▼           ▼            ▼          ▼            │     │
    │  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐       │     │
    │  │  │jama.json│  │design.db│ │verif.json│ │ cv.db │       │     │
    │  │  └────────┘  └────────┘  └────────┘  └────────┘       │     │
    │  └────────────────────────────────────────────────────────┘     │
    │                                                                  │
    └─────────────────────────────────────────────────────────────────┘
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from .sketch import SketchManager, SketchNode, SketchEdge, SketchStats
from .base import (
    ColorBackend,
    NodeColor,
    EdgeColor,
    Node,
    Edge,
    ColorStats,
    SnapshotInfo,
)
from .color_manager import ColorManager


@dataclass
class ConsistencyReport:
    """Report from consistency check across backends."""
    is_consistent: bool
    sketch_node_count: int
    sketch_edge_count: int
    backend_reports: Dict[str, Dict[str, Any]]
    issues: List[str]


@dataclass
class ModelStats:
    """Combined statistics from sketch and color."""
    sketch: SketchStats
    color_by_backend: Dict[str, ColorStats]


class ModelManager:
    """
    Orchestrates sketch and color backends.

    Usage:
        mm = ModelManager(config)
        mm.load()

        # Add a complete node (goes to sketch + all color backends)
        mm.add_node(Node(id="req-1", type="Requirement", label="Auth", properties={...}))

        # Fast navigation (sketch only)
        connected_ids = mm.get_connected_node_ids("req-1")

        # Get full details (sketch + color)
        node = mm.get_node("req-1")

        # Check consistency across backends
        report = mm.check_consistency()

        mm.save()
        mm.close()
    """

    def __init__(self, config: dict, base_path: Path):
        """
        Initialize ModelManager with configuration.

        Config should contain:
        - storage.sketch.path: Path to sketch JSON
        - storage.colors: Color definitions (node_type -> color mapping)
        - storage.color_backends: Backend definitions (color -> backend mapping)

        Args:
            config: Configuration dict
            base_path: Base path for resolving relative paths (the project directory)
        """
        self.config = config
        self.base_path = base_path
        self.sketch: Optional[SketchManager] = None
        self.color_manager: Optional[ColorManager] = None
        self._loaded = False

    def load(self) -> None:
        """Load sketch and connect to color layer backends."""
        storage = self.config.get("storage", {})

        # Load sketch
        sketch_config = storage.get("sketch", {})
        sketch_path = Path(sketch_config.get("path", "model/sketch.json"))
        if not sketch_path.is_absolute():
            sketch_path = self.base_path / sketch_path

        self.sketch = SketchManager(sketch_path)
        self.sketch.load()

        # Initialize color manager
        self.color_manager = ColorManager(self.config, self.base_path)
        self.color_manager.connect()

        self._loaded = True

    def save(self) -> None:
        """Save sketch (color backends auto-save or need explicit save)."""
        if self.sketch:
            self.sketch.save()

    def close(self) -> None:
        """Save and close all connections."""
        self.save()
        if self.color_manager:
            self.color_manager.close()
        self._loaded = False

    # === Node Operations ===

    def add_node(self, node: Node) -> str:
        """
        Add a complete node to sketch and appropriate color backend(s).

        The sketch gets: id, type, label, source_id
        Color backend(s) determined by node.type via color mapping.
        """
        # Add to sketch
        sketch_node = SketchNode(
            id=node.id,
            type=node.type,
            label=node.label,
            source_id=node.source_id,
        )
        self.sketch.add_node(sketch_node)

        # Add color via color manager (routes based on node type)
        color = NodeColor(
            id=node.id,
            properties=node.properties,
            source_ref=node.source_ref,
            content=node.content,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
        self.color_manager.store_node_color(color, node.type)

        return node.id

    def get_node(
        self,
        node_id: str,
        color: str = None,
        backend: str = None,
    ) -> Optional[Node]:
        """
        Get a complete node (sketch + color).

        Args:
            node_id: Node ID to retrieve
            color: Optional color to get color from (e.g., "conceptual", "design")
            backend: Optional specific backend name to use

        Returns:
            Complete Node with sketch + color, or None if not found
        """
        # Get sketch
        sketch_node = self.sketch.get_node(node_id)
        if not sketch_node:
            return None

        # Get color via color manager
        color = self.color_manager.get_node_color(
            node_id,
            node_type=sketch_node.type,
            color=color,
            backend_name=backend,
        )

        return Node(
            id=sketch_node.id,
            type=sketch_node.type,
            label=sketch_node.label,
            source_id=sketch_node.source_id,
            properties=color.properties if color else {},
            source_ref=color.source_ref if color else None,
            content=color.content if color else None,
            created_at=color.created_at if color else None,
            updated_at=color.updated_at if color else None,
        )

    def update_node(self, node_id: str, updates: dict, node_type: str = None) -> bool:
        """
        Update a node's sketch and/or color.

        Sketch updates: label, type
        Color updates: properties, content, source_ref

        Args:
            node_id: Node ID to update
            updates: Dict of fields to update
            node_type: Node type (for routing to correct backend). If None, fetched from sketch.
        """
        # Get node type if not provided
        if not node_type:
            sketch_node = self.sketch.get_node(node_id)
            node_type = sketch_node.type if sketch_node else None

        # Update sketch if needed
        if "label" in updates or "type" in updates:
            self.sketch.update_node(
                node_id,
                label=updates.get("label"),
                node_type=updates.get("type"),
            )

        # Update color via color manager
        color_updates = {
            k: v for k, v in updates.items()
            if k in ("properties", "content", "source_ref")
        }
        if color_updates and node_type:
            self.color_manager.update_node_color(node_id, color_updates, node_type=node_type)

        return True

    def delete_node(self, node_id: str, cascade_edges: bool = True) -> bool:
        """Delete a node from sketch and appropriate color backends."""
        # Get node type before deletion (for color routing)
        sketch_node = self.sketch.get_node(node_id)
        node_type = sketch_node.type if sketch_node else None

        # Delete from sketch (cascades edges in sketch)
        result = self.sketch.delete_node(node_id, cascade_edges)

        # Delete color via color manager
        if node_type:
            self.color_manager.delete_node_color(node_id, node_type=node_type)

        return result

    def find_nodes(
        self,
        node_type: Optional[str] = None,
        source_id: Optional[str] = None,
        label_contains: Optional[str] = None,
        limit: Optional[int] = None,
        include_color: bool = False,
        color: str = None,
        backend: str = None,
    ) -> List[Node]:
        """
        Find nodes matching criteria.

        By default returns sketch-only nodes (fast).
        Set include_color=True to also fetch properties/content.

        Args:
            node_type: Filter by node type
            source_id: Filter by source ID
            label_contains: Filter by label substring
            limit: Max number of results
            include_color: Whether to include color data
            color: Optional color to fetch color from
            backend: Optional specific backend name
        """
        sketch_nodes = self.sketch.find_nodes(
            node_type=node_type,
            source_id=source_id,
            label_contains=label_contains,
            limit=limit,
        )

        if not include_color:
            # Return sketch-only nodes
            return [
                Node(
                    id=sn.id,
                    type=sn.type,
                    label=sn.label,
                    source_id=sn.source_id,
                )
                for sn in sketch_nodes
            ]

        # Fetch color for each node via color manager
        nodes = []
        for sn in sketch_nodes:
            color = self.color_manager.get_node_color(
                sn.id,
                node_type=sn.type,
                color=color,
                backend_name=backend,
            )
            nodes.append(Node(
                id=sn.id,
                type=sn.type,
                label=sn.label,
                source_id=sn.source_id,
                properties=color.properties if color else {},
                source_ref=color.source_ref if color else None,
                content=color.content if color else None,
                created_at=color.created_at if color else None,
                updated_at=color.updated_at if color else None,
            ))
        return nodes

    # === Edge Operations ===

    def add_edge(self, edge: Edge) -> str:
        """Add a complete edge to sketch and default color backend."""
        # Add to sketch
        sketch_edge = SketchEdge(
            id=edge.id,
            type=edge.type,
            source_node_id=edge.source_node_id,
            target_node_id=edge.target_node_id,
            source_id=edge.source_id,
        )
        self.sketch.add_edge(sketch_edge)

        # Add color via color manager (edges go to default backend)
        color = EdgeColor(
            id=edge.id,
            properties=edge.properties,
            created_at=edge.created_at,
        )
        self.color_manager.store_edge_color(color)

        return edge.id

    def get_edge(self, edge_id: str, backend: str = None) -> Optional[Edge]:
        """Get a complete edge (sketch + color)."""
        sketch_edge = self.sketch.get_edge(edge_id)
        if not sketch_edge:
            return None

        color = self.color_manager.get_edge_color(edge_id, backend_name=backend)

        return Edge(
            id=sketch_edge.id,
            type=sketch_edge.type,
            source_node_id=sketch_edge.source_node_id,
            target_node_id=sketch_edge.target_node_id,
            source_id=sketch_edge.source_id,
            properties=color.properties if color else {},
            created_at=color.created_at if color else None,
        )

    def delete_edge(self, edge_id: str) -> bool:
        """Delete an edge from sketch and all color backends."""
        result = self.sketch.delete_edge(edge_id)
        self.color_manager.delete_edge_color(edge_id)
        return result

    # === Bulk Operations ===

    def bulk_add_nodes(self, nodes: List[Node]) -> List[str]:
        """Add multiple nodes efficiently."""
        # Add to sketch
        sketch_nodes = [
            SketchNode(id=n.id, type=n.type, label=n.label, source_id=n.source_id)
            for n in nodes
        ]
        added_ids = self.sketch.bulk_add_nodes(sketch_nodes)

        # Add color via color manager (one node at a time for proper routing)
        for n in nodes:
            if n.id in added_ids:
                color = NodeColor(
                    id=n.id,
                    properties=n.properties,
                    source_ref=n.source_ref,
                    content=n.content,
                    created_at=n.created_at,
                    updated_at=n.updated_at,
                )
                self.color_manager.store_node_color(color, n.type)

        return added_ids

    def bulk_add_edges(self, edges: List[Edge]) -> List[str]:
        """Add multiple edges efficiently."""
        # Add to sketch
        sketch_edges = [
            SketchEdge(
                id=e.id,
                type=e.type,
                source_node_id=e.source_node_id,
                target_node_id=e.target_node_id,
                source_id=e.source_id,
            )
            for e in edges
        ]
        added_ids = self.sketch.bulk_add_edges(sketch_edges)

        # Add color via color manager
        for e in edges:
            if e.id in added_ids:
                color = EdgeColor(id=e.id, properties=e.properties, created_at=e.created_at)
                self.color_manager.store_edge_color(color)

        return added_ids

    # === Navigation (Sketch-only, fast) ===

    def get_connected_node_ids(
        self,
        node_id: str,
        direction: str = "both",
        edge_type: Optional[str] = None,
    ) -> List[str]:
        """Fast navigation: get connected node IDs from sketch."""
        return self.sketch.get_connected_node_ids(node_id, direction, edge_type)

    def get_subgraph_ids(self, root_node_id: str, max_depth: int = 3) -> Dict[str, Set[str]]:
        """Fast navigation: get subgraph node/edge IDs from sketch."""
        return self.sketch.get_subgraph_ids(root_node_id, max_depth)

    def has_node(self, node_id: str) -> bool:
        """Fast check: does node exist in sketch?"""
        return self.sketch.has_node(node_id)

    def has_edge(self, edge_id: str) -> bool:
        """Fast check: does edge exist in sketch?"""
        return self.sketch.has_edge(edge_id)

    # === Bulk Fetch Operations ===

    def get_all_nodes(self, include_color: bool = True) -> List[Node]:
        """
        Get all nodes efficiently in a single operation.

        Args:
            include_color: Whether to include color data (default True)

        Returns:
            List of all nodes
        """
        sketch_nodes = list(self.sketch.model["nodes"].values())

        if not include_color:
            return [
                Node(
                    id=sn["id"],
                    type=sn["type"],
                    label=sn["label"],
                    source_id=sn.get("source_id"),
                )
                for sn in sketch_nodes
            ]

        # Bulk fetch all color from all backends
        all_node_ids = [sn["id"] for sn in sketch_nodes]
        color_map = {}
        for backend in self.color_manager.backends.values():
            backend_color = backend.get_nodes_color_by_ids(all_node_ids)
            # Merge (later backends don't overwrite)
            for nid, color in backend_color.items():
                if nid not in color_map:
                    color_map[nid] = color

        return [
            Node(
                id=sn["id"],
                type=sn["type"],
                label=sn["label"],
                source_id=sn.get("source_id"),
                properties=color_map.get(sn["id"], NodeColor(id=sn["id"])).properties,
                source_ref=color_map.get(sn["id"], NodeColor(id=sn["id"])).source_ref,
                content=color_map.get(sn["id"], NodeColor(id=sn["id"])).content,
                created_at=color_map.get(sn["id"], NodeColor(id=sn["id"])).created_at,
                updated_at=color_map.get(sn["id"], NodeColor(id=sn["id"])).updated_at,
            )
            for sn in sketch_nodes
        ]

    def get_all_edges(self, include_color: bool = True) -> List[Edge]:
        """
        Get all edges efficiently in a single operation.

        Args:
            include_color: Whether to include color data (default True)

        Returns:
            List of all edges
        """
        sketch_edges = list(self.sketch.model["edges"].values())

        if not include_color:
            return [
                Edge(
                    id=se["id"],
                    type=se["type"],
                    source_node_id=se["source_node_id"],
                    target_node_id=se["target_node_id"],
                    source_id=se.get("source_id"),
                )
                for se in sketch_edges
            ]

        # Bulk fetch all edge color
        all_edge_ids = [se["id"] for se in sketch_edges]
        color_map = {}
        for backend in self.color_manager.backends.values():
            for eid in all_edge_ids:
                if eid not in color_map:
                    color = backend.get_edge_color(eid)
                    if color:
                        color_map[eid] = color

        return [
            Edge(
                id=se["id"],
                type=se["type"],
                source_node_id=se["source_node_id"],
                target_node_id=se["target_node_id"],
                source_id=se.get("source_id"),
                properties=color_map.get(se["id"], EdgeColor(id=se["id"])).properties,
                created_at=color_map.get(se["id"], EdgeColor(id=se["id"])).created_at,
            )
            for se in sketch_edges
        ]

    def get_nodes_by_ids(self, node_ids: List[str], include_color: bool = True) -> List[Node]:
        """
        Get multiple nodes by their IDs efficiently.

        Args:
            node_ids: List of node IDs to fetch
            include_color: Whether to include color data

        Returns:
            List of nodes (only those that exist)
        """
        nodes = []
        color_map = {}

        if include_color:
            # Bulk fetch color from all backends
            for backend in self.color_manager.backends.values():
                backend_color = backend.get_nodes_color_by_ids(node_ids)
                for nid, color in backend_color.items():
                    if nid not in color_map:
                        color_map[nid] = color

        for nid in node_ids:
            sketch_node = self.sketch.get_node(nid)
            if not sketch_node:
                continue

            if include_color:
                color = color_map.get(nid, NodeColor(id=nid))
                nodes.append(Node(
                    id=sketch_node.id,
                    type=sketch_node.type,
                    label=sketch_node.label,
                    source_id=sketch_node.source_id,
                    properties=color.properties,
                    source_ref=color.source_ref,
                    content=color.content,
                    created_at=color.created_at,
                    updated_at=color.updated_at,
                ))
            else:
                nodes.append(Node(
                    id=sketch_node.id,
                    type=sketch_node.type,
                    label=sketch_node.label,
                    source_id=sketch_node.source_id,
                ))

        return nodes

    # === Statistics ===

    def get_statistics(self) -> ModelStats:
        """Get combined statistics from sketch and all color backends."""
        sketch_stats = self.sketch.get_statistics()

        color_stats = {}
        for name, backend in self.color_manager.backends.items():
            color_stats[name] = backend.get_statistics()

        return ModelStats(
            sketch=sketch_stats,
            color_by_backend=color_stats,
        )

    # === Consistency Checking ===

    def check_consistency(self) -> ConsistencyReport:
        """
        Check that sketch and all color backends are consistent.

        Note: With color-layered architecture, not all backends need all nodes.
        Nodes are only expected in backends that serve their color.
        """
        issues = []
        backend_reports = {}

        sketch_node_ids = set(self.sketch.list_node_ids())
        sketch_edge_ids = set(self.sketch.list_edge_ids())

        for name, backend in self.color_manager.backends.items():
            color_node_ids = set(backend.list_node_ids())
            color_edge_ids = set(backend.list_edge_ids())

            # Nodes in color but not in sketch (orphans) - always invalid
            orphan_node_color = color_node_ids - sketch_node_ids
            if orphan_node_color:
                issues.append(f"{name}: {len(orphan_node_color)} orphan node color entries")

            # Edges in color but not in sketch (orphans) - always invalid
            orphan_edge_color = color_edge_ids - sketch_edge_ids
            if orphan_edge_color:
                issues.append(f"{name}: {len(orphan_edge_color)} orphan edge color entries")

            backend_reports[name] = {
                "node_count": len(color_node_ids),
                "edge_count": len(color_edge_ids),
                "orphan_nodes": len(orphan_node_color),
                "orphan_edges": len(orphan_edge_color),
            }

        return ConsistencyReport(
            is_consistent=len(issues) == 0,
            sketch_node_count=len(sketch_node_ids),
            sketch_edge_count=len(sketch_edge_ids),
            backend_reports=backend_reports,
            issues=issues,
        )

    def repair_consistency(self) -> Dict[str, int]:
        """
        Repair consistency issues.

        - Removes orphan color (color without sketch entry)
        - Does NOT add missing color (that requires source data)
        """
        repaired = {"orphan_nodes_removed": 0, "orphan_edges_removed": 0}

        sketch_node_ids = set(self.sketch.list_node_ids())
        sketch_edge_ids = set(self.sketch.list_edge_ids())

        for backend in self.color_manager.backends.values():
            color_node_ids = set(backend.list_node_ids())
            color_edge_ids = set(backend.list_edge_ids())

            # Remove orphan nodes
            for nid in color_node_ids - sketch_node_ids:
                backend.delete_node_color(nid)
                repaired["orphan_nodes_removed"] += 1

            # Remove orphan edges
            for eid in color_edge_ids - sketch_edge_ids:
                backend.delete_edge_color(eid)
                repaired["orphan_edges_removed"] += 1

        return repaired

    # === Source Operations ===

    def clear_source(self, source_id: str) -> Dict[str, int]:
        """Remove all nodes and edges from a specific source."""
        # Get IDs before clearing
        nodes_to_clear = [n.id for n in self.sketch.find_nodes(source_id=source_id)]
        edges_to_clear = [e.id for e in self.sketch.find_edges()
                         if self.sketch.get_edge(e.id).source_id == source_id]

        # Clear from sketch
        result = self.sketch.clear_source(source_id)

        # Clear from all color backends
        for backend in self.color_manager.backends.values():
            backend.clear_source(source_id, nodes_to_clear, edges_to_clear)

        return result

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """
        Create snapshots in sketch and all color backends.

        Returns:
            The sketch snapshot ID (used as the primary identifier)
        """
        # Create sketch snapshot first
        sketch_snapshot_id = self.sketch.create_snapshot(label)

        # Snapshot each color backend with same label
        for name, backend in self.color_manager.backends.items():
            backend.create_snapshot(label)

        return sketch_snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> Dict[str, bool]:
        """
        Restore sketch and all color backends from snapshots.

        Args:
            snapshot_id: The sketch snapshot ID to restore

        Returns:
            Dict mapping component name to success status
        """
        results = {}

        # Restore sketch
        results["sketch"] = self.sketch.restore_snapshot(snapshot_id)

        # Try to restore each color backend
        # Extract label from sketch snapshot ID if present
        # Format: sketch-YYYYMMDD-HHMMSS[-label]
        parts = snapshot_id.split("-", 3)
        label = parts[3] if len(parts) > 3 else None

        for name, backend in self.color_manager.backends.items():
            try:
                # List snapshots and find matching one by timestamp/label
                backend_snapshots = backend.list_snapshots()
                matching = None
                for snap in backend_snapshots:
                    if label and snap.get("label") == label:
                        matching = snap["id"]
                        break
                    # Also try matching by similar timestamp
                    if snap["id"].endswith(f"-{label}") if label else True:
                        matching = snap["id"]

                if matching:
                    backend.restore_snapshot(matching)
                    results[name] = True
                else:
                    results[name] = False
            except Exception:
                results[name] = False

        return results

    # === Color Information ===

    def list_backends(self) -> List[str]:
        """List active color backend names."""
        return list(self.color_manager.backends.keys())

    def list_colors(self) -> Dict[str, dict]:
        """List all colors with their node types and backends."""
        return self.color_manager.list_colors()

    def get_color_for_type(self, node_type: str) -> Set[str]:
        """Get colors that a node type belongs to."""
        return self.color_manager.get_colors_for_type(node_type)
