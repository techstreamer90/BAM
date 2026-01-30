"""
BAM JSON Color Backend

Stores color (node/edge details) in a JSON file.
Simple, zero dependencies, good for development and small models.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import (
    BaseColorBackend,
    NodeColor,
    EdgeColor,
    ColorStats,
    SnapshotInfo,
)


class JsonColorBackend(BaseColorBackend):
    """
    JSON file-based color storage.

    Stores all node/edge color in a single JSON file.
    Simple but limited - loads entire file into memory.

    Auto-save behavior:
    - By default, auto_save=False for efficiency (batch operations)
    - Call save() explicitly or rely on close() to persist
    - Set auto_save=True for immediate persistence (debugging/single ops)
    """

    def __init__(self, config: dict):
        super().__init__(config, "json")

        self.color_path = Path(config.get("colorPath", "model/color.json"))
        self.snapshots_dir = Path(config.get("snapshotsDir", "model/color_snapshots"))
        self.max_snapshots = config.get("maxSnapshots", 10)
        self.auto_save = config.get("autoSave", False)  # Default: batch mode

        self.data: Dict[str, Any] = {}
        self._dirty = False  # Track if we need to save

    def connect(self) -> None:
        """Load color data from disk."""
        self.data = self._load_data()
        self._dirty = False
        self._connected = True

    def close(self) -> None:
        """Save if dirty and close."""
        if self._connected and self._dirty:
            self._save_data()
        self._dirty = False
        self._connected = False

    def save(self) -> None:
        """Explicitly save data to disk."""
        if self._dirty:
            self._save_data()
            self._dirty = False

    def _mark_dirty(self) -> None:
        """Mark data as modified. Saves immediately if auto_save is enabled."""
        self._dirty = True
        if self.auto_save:
            self._save_data()
            self._dirty = False

    def _load_data(self) -> dict:
        """Load color data from JSON file."""
        if not self.color_path.exists():
            return self._empty_data()

        with open(self.color_path, 'r') as f:
            return json.load(f)

    def _save_data(self) -> None:
        """Save color data to JSON file."""
        self.data["metadata"]["lastModified"] = datetime.now(timezone.utc).isoformat()

        self.color_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.color_path, 'w') as f:
            json.dump(self.data, f, indent=2)

    def _empty_data(self) -> dict:
        """Create empty color data structure."""
        return {
            "metadata": {
                "created": datetime.now(timezone.utc).isoformat(),
                "lastModified": None,
            },
            "nodes": {},
            "edges": {},
        }

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor) -> None:
        """Store color for a node."""
        self.data["nodes"][color.id] = color.to_dict()
        self._mark_dirty()

    def get_node_color(self, node_id: str) -> Optional[NodeColor]:
        """Get color for a node."""
        data = self.data["nodes"].get(node_id)
        return NodeColor.from_dict(data) if data else None

    def update_node_color(self, node_id: str, updates: dict) -> bool:
        """Update a node's color."""
        if node_id not in self.data["nodes"]:
            return False

        color = self.data["nodes"][node_id]

        if "properties" in updates:
            color["properties"].update(updates["properties"])
        if "content" in updates:
            color["content"] = updates["content"]
        if "source_ref" in updates:
            color["source_ref"] = updates["source_ref"]

        color["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._mark_dirty()
        return True

    def delete_node_color(self, node_id: str) -> bool:
        """Delete color for a node."""
        if node_id not in self.data["nodes"]:
            return False

        del self.data["nodes"][node_id]
        self._mark_dirty()
        return True

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Store color for multiple nodes."""
        for color in color_list:
            self.data["nodes"][color.id] = color.to_dict()

        self._mark_dirty()
        return len(color_list)

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor) -> None:
        """Store color for an edge."""
        self.data["edges"][color.id] = color.to_dict()
        self._mark_dirty()

    def get_edge_color(self, edge_id: str) -> Optional[EdgeColor]:
        """Get color for an edge."""
        data = self.data["edges"].get(edge_id)
        return EdgeColor.from_dict(data) if data else None

    def update_edge_color(self, edge_id: str, updates: dict) -> bool:
        """Update an edge's color."""
        if edge_id not in self.data["edges"]:
            return False

        color = self.data["edges"][edge_id]

        if "properties" in updates:
            color["properties"].update(updates["properties"])

        self._mark_dirty()
        return True

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete color for an edge."""
        if edge_id not in self.data["edges"]:
            return False

        del self.data["edges"][edge_id]
        self._mark_dirty()
        return True

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Store color for multiple edges."""
        for color in color_list:
            self.data["edges"][color.id] = color.to_dict()

        self._mark_dirty()
        return len(color_list)

    # === Query Operations ===

    def search_node_content(self, query: str, limit: int = 100) -> List[str]:
        """Search node content/properties for matching text."""
        results = []
        query_lower = query.lower()

        for node_id, color in self.data["nodes"].items():
            # Search in content
            content = color.get("content", "")
            if content and query_lower in content.lower():
                results.append(node_id)
                if len(results) >= limit:
                    break
                continue

            # Search in properties (convert to string)
            props_str = json.dumps(color.get("properties", {})).lower()
            if query_lower in props_str:
                results.append(node_id)
                if len(results) >= limit:
                    break

        return results

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Get color for multiple nodes efficiently (single dict lookup per node)."""
        result = {}
        for nid in node_ids:
            data = self.data["nodes"].get(nid)
            if data:
                result[nid] = NodeColor.from_dict(data)
        return result

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Get color for multiple edges efficiently (single dict lookup per edge)."""
        result = {}
        for eid in edge_ids:
            data = self.data["edges"].get(eid)
            if data:
                result[eid] = EdgeColor.from_dict(data)
        return result

    # === Statistics ===

    def get_statistics(self) -> ColorStats:
        """Get color storage statistics."""
        # Estimate storage size
        size_bytes = None
        if self.color_path.exists():
            size_bytes = self.color_path.stat().st_size

        return ColorStats(
            total_nodes=len(self.data["nodes"]),
            total_edges=len(self.data["edges"]),
            storage_size_bytes=size_bytes,
        )

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """Create a snapshot of color data."""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"color-snapshot-{timestamp}"
        if label:
            snapshot_id = f"{snapshot_id}-{label}"

        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"

        snapshot = {
            "id": snapshot_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "data": self.data,
        }

        with open(snapshot_path, 'w') as f:
            json.dump(snapshot, f, indent=2)

        self._cleanup_old_snapshots()

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore color data from a snapshot."""
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"

        if not snapshot_path.exists():
            return False

        with open(snapshot_path, 'r') as f:
            snapshot = json.load(f)

        self.data = snapshot["data"]
        self._mark_dirty()
        return True

    def list_snapshots(self) -> List[SnapshotInfo]:
        """List available snapshots."""
        if not self.snapshots_dir.exists():
            return []

        snapshots = []
        for path in sorted(self.snapshots_dir.glob("color-snapshot-*.json")):
            with open(path, 'r') as f:
                data = json.load(f)
                snapshots.append(SnapshotInfo(
                    id=data["id"],
                    created_at=data["createdAt"],
                    label=data.get("label"),
                    node_count=len(data["data"]["nodes"]),
                    edge_count=len(data["data"]["edges"]),
                ))

        return snapshots

    def _cleanup_old_snapshots(self) -> None:
        """Remove old snapshots beyond the limit."""
        if not self.snapshots_dir.exists():
            return

        snapshots = sorted(self.snapshots_dir.glob("color-snapshot-*.json"))

        while len(snapshots) > self.max_snapshots:
            oldest = snapshots.pop(0)
            oldest.unlink()

    # === Source Operations ===

    def clear_source(self, source_id: str, node_ids: List[str], edge_ids: List[str]) -> Dict[str, int]:
        """Clear color for specified nodes and edges."""
        removed_nodes = 0
        removed_edges = 0

        for nid in node_ids:
            if nid in self.data["nodes"]:
                del self.data["nodes"][nid]
                removed_nodes += 1

        for eid in edge_ids:
            if eid in self.data["edges"]:
                del self.data["edges"][eid]
                removed_edges += 1

        self._mark_dirty()

        return {
            "removed_nodes": removed_nodes,
            "removed_edges": removed_edges,
        }

    # === Sync/Verification ===

    def list_node_ids(self) -> List[str]:
        """List all node IDs that have color stored."""
        return list(self.data["nodes"].keys())

    def list_edge_ids(self) -> List[str]:
        """List all edge IDs that have color stored."""
        return list(self.data["edges"].keys())
