"""
BAM SQLite Color Backend

Stores color (node/edge details) in a SQLite database.
Good for medium-sized models with indexed queries.
"""

import json
import sqlite3
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


class SqliteColorBackend(BaseColorBackend):
    """
    SQLite-based color storage.

    Uses SQLite for persistent storage with indexing.
    Better query performance than JSON for larger datasets.

    Auto-commit behavior:
    - By default, auto_commit=False for efficiency (batch operations)
    - Call commit() explicitly or rely on close() to persist
    - Set auto_commit=True for immediate persistence (debugging/single ops)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS node_color (
        id TEXT PRIMARY KEY,
        properties TEXT DEFAULT '{}',
        source_ref TEXT,
        content TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS edge_color (
        id TEXT PRIMARY KEY,
        properties TEXT DEFAULT '{}',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS snapshots (
        id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        label TEXT,
        data TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_node_color_source_ref ON node_color(source_ref);
    """

    def __init__(self, config: dict):
        super().__init__(config, "sqlite")

        self.db_path = Path(config.get("dbPath", "model/color.db"))
        self.max_snapshots = config.get("maxSnapshots", 10)
        self.auto_commit = config.get("autoCommit", False)  # Default: batch mode
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Initialize database connection and schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

        self._connected = True

    def close(self) -> None:
        """Commit pending changes and close database connection."""
        if self.conn:
            self.conn.commit()  # Commit any pending changes
            self.conn.close()
            self.conn = None
        self._connected = False

    def commit(self) -> None:
        """Explicitly commit pending changes."""
        if self.conn:
            self.conn.commit()

    def _maybe_commit(self) -> None:
        """Commit if auto_commit is enabled."""
        if self.auto_commit and self.conn:
            self.conn.commit()

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor) -> None:
        """Store color for a node."""
        self.conn.execute(
            """INSERT OR REPLACE INTO node_color
               (id, properties, source_ref, content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                color.id,
                json.dumps(color.properties),
                color.source_ref,
                color.content,
                color.created_at,
                color.updated_at,
            )
        )
        self._maybe_commit()

    def get_node_color(self, node_id: str) -> Optional[NodeColor]:
        """Get color for a node."""
        cursor = self.conn.execute(
            "SELECT * FROM node_color WHERE id = ?", (node_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return NodeColor(
            id=row["id"],
            properties=json.loads(row["properties"]),
            source_ref=row["source_ref"],
            content=row["content"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def update_node_color(self, node_id: str, updates: dict) -> bool:
        """Update a node's color."""
        existing = self.get_node_color(node_id)
        if not existing:
            return False

        properties = existing.properties.copy()
        if "properties" in updates:
            properties.update(updates["properties"])

        content = updates.get("content", existing.content)
        source_ref = updates.get("source_ref", existing.source_ref)

        self.conn.execute(
            """UPDATE node_color
               SET properties = ?, content = ?, source_ref = ?, updated_at = ?
               WHERE id = ?""",
            (
                json.dumps(properties),
                content,
                source_ref,
                datetime.now(timezone.utc).isoformat(),
                node_id,
            )
        )
        self._maybe_commit()
        return True

    def delete_node_color(self, node_id: str) -> bool:
        """Delete color for a node."""
        cursor = self.conn.execute(
            "DELETE FROM node_color WHERE id = ?", (node_id,)
        )
        self._maybe_commit()
        return cursor.rowcount > 0

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Store color for multiple nodes."""
        self.conn.executemany(
            """INSERT OR REPLACE INTO node_color
               (id, properties, source_ref, content, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    f.id,
                    json.dumps(f.properties),
                    f.source_ref,
                    f.content,
                    f.created_at,
                    f.updated_at,
                )
                for f in color_list
            ]
        )
        self._maybe_commit()
        return len(color_list)

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor) -> None:
        """Store color for an edge."""
        self.conn.execute(
            """INSERT OR REPLACE INTO edge_color
               (id, properties, created_at)
               VALUES (?, ?, ?)""",
            (
                color.id,
                json.dumps(color.properties),
                color.created_at,
            )
        )
        self._maybe_commit()

    def get_edge_color(self, edge_id: str) -> Optional[EdgeColor]:
        """Get color for an edge."""
        cursor = self.conn.execute(
            "SELECT * FROM edge_color WHERE id = ?", (edge_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return EdgeColor(
            id=row["id"],
            properties=json.loads(row["properties"]),
            created_at=row["created_at"],
        )

    def update_edge_color(self, edge_id: str, updates: dict) -> bool:
        """Update an edge's color."""
        existing = self.get_edge_color(edge_id)
        if not existing:
            return False

        properties = existing.properties.copy()
        if "properties" in updates:
            properties.update(updates["properties"])

        self.conn.execute(
            """UPDATE edge_color SET properties = ? WHERE id = ?""",
            (json.dumps(properties), edge_id)
        )
        self._maybe_commit()
        return True

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete color for an edge."""
        cursor = self.conn.execute(
            "DELETE FROM edge_color WHERE id = ?", (edge_id,)
        )
        self._maybe_commit()
        return cursor.rowcount > 0

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Store color for multiple edges."""
        self.conn.executemany(
            """INSERT OR REPLACE INTO edge_color
               (id, properties, created_at)
               VALUES (?, ?, ?)""",
            [
                (f.id, json.dumps(f.properties), f.created_at)
                for f in color_list
            ]
        )
        self._maybe_commit()
        return len(color_list)

    # === Query Operations ===

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Get color for multiple nodes."""
        if not node_ids:
            return {}

        placeholders = ",".join("?" * len(node_ids))
        cursor = self.conn.execute(
            f"SELECT * FROM node_color WHERE id IN ({placeholders})",
            node_ids
        )

        return {
            row["id"]: NodeColor(
                id=row["id"],
                properties=json.loads(row["properties"]),
                source_ref=row["source_ref"],
                content=row["content"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in cursor
        }

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Get color for multiple edges."""
        if not edge_ids:
            return {}

        placeholders = ",".join("?" * len(edge_ids))
        cursor = self.conn.execute(
            f"SELECT * FROM edge_color WHERE id IN ({placeholders})",
            edge_ids
        )

        return {
            row["id"]: EdgeColor(
                id=row["id"],
                properties=json.loads(row["properties"]),
                created_at=row["created_at"],
            )
            for row in cursor
        }

    def search_node_content(self, query: str, limit: int = 100) -> List[str]:
        """Search node content/properties for matching text."""
        cursor = self.conn.execute(
            """SELECT id FROM node_color
               WHERE content LIKE ? OR properties LIKE ?
               LIMIT ?""",
            (f"%{query}%", f"%{query}%", limit)
        )
        return [row["id"] for row in cursor]

    # === Statistics ===

    def get_statistics(self) -> ColorStats:
        """Get color storage statistics."""
        cursor = self.conn.execute("SELECT COUNT(*) as cnt FROM node_color")
        node_count = cursor.fetchone()["cnt"]

        cursor = self.conn.execute("SELECT COUNT(*) as cnt FROM edge_color")
        edge_count = cursor.fetchone()["cnt"]

        size_bytes = None
        if self.db_path.exists():
            size_bytes = self.db_path.stat().st_size

        return ColorStats(
            total_nodes=node_count,
            total_edges=edge_count,
            storage_size_bytes=size_bytes,
        )

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """Create a snapshot of color data."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"color-snapshot-{timestamp}"
        if label:
            snapshot_id = f"{snapshot_id}-{label}"

        # Export current data
        cursor = self.conn.execute("SELECT * FROM node_color")
        nodes = {row["id"]: dict(row) for row in cursor}

        cursor = self.conn.execute("SELECT * FROM edge_color")
        edges = {row["id"]: dict(row) for row in cursor}

        data = json.dumps({"nodes": nodes, "edges": edges})

        self.conn.execute(
            """INSERT INTO snapshots (id, created_at, label, data)
               VALUES (?, ?, ?, ?)""",
            (snapshot_id, datetime.now(timezone.utc).isoformat(), label, data)
        )
        self.conn.commit()

        self._cleanup_old_snapshots()

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore color data from a snapshot."""
        cursor = self.conn.execute(
            "SELECT data FROM snapshots WHERE id = ?", (snapshot_id,)
        )
        row = cursor.fetchone()

        if not row:
            return False

        data = json.loads(row["data"])

        # Clear current data
        self.conn.execute("DELETE FROM node_color")
        self.conn.execute("DELETE FROM edge_color")

        # Restore nodes
        for node_data in data["nodes"].values():
            self.conn.execute(
                """INSERT INTO node_color
                   (id, properties, source_ref, content, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    node_data["id"],
                    node_data["properties"],
                    node_data.get("source_ref"),
                    node_data.get("content"),
                    node_data["created_at"],
                    node_data["updated_at"],
                )
            )

        # Restore edges
        for edge_data in data["edges"].values():
            self.conn.execute(
                """INSERT INTO edge_color (id, properties, created_at)
                   VALUES (?, ?, ?)""",
                (
                    edge_data["id"],
                    edge_data["properties"],
                    edge_data["created_at"],
                )
            )

        self.conn.commit()
        return True

    def list_snapshots(self) -> List[SnapshotInfo]:
        """List available snapshots."""
        cursor = self.conn.execute(
            "SELECT id, created_at, label, data FROM snapshots ORDER BY created_at"
        )

        snapshots = []
        for row in cursor:
            data = json.loads(row["data"])
            snapshots.append(SnapshotInfo(
                id=row["id"],
                created_at=row["created_at"],
                label=row["label"],
                node_count=len(data["nodes"]),
                edge_count=len(data["edges"]),
            ))

        return snapshots

    def _cleanup_old_snapshots(self) -> None:
        """Remove old snapshots beyond the limit."""
        cursor = self.conn.execute(
            "SELECT id FROM snapshots ORDER BY created_at"
        )
        snapshots = [row["id"] for row in cursor]

        while len(snapshots) > self.max_snapshots:
            oldest = snapshots.pop(0)
            self.conn.execute("DELETE FROM snapshots WHERE id = ?", (oldest,))

        self.conn.commit()

    # === Source Operations ===

    def clear_source(self, source_id: str, node_ids: List[str], edge_ids: List[str]) -> Dict[str, int]:
        """Clear color for specified nodes and edges."""
        removed_nodes = 0
        removed_edges = 0

        if node_ids:
            placeholders = ",".join("?" * len(node_ids))
            cursor = self.conn.execute(
                f"DELETE FROM node_color WHERE id IN ({placeholders})",
                node_ids
            )
            removed_nodes = cursor.rowcount

        if edge_ids:
            placeholders = ",".join("?" * len(edge_ids))
            cursor = self.conn.execute(
                f"DELETE FROM edge_color WHERE id IN ({placeholders})",
                edge_ids
            )
            removed_edges = cursor.rowcount

        self._maybe_commit()

        return {
            "removed_nodes": removed_nodes,
            "removed_edges": removed_edges,
        }

    # === Sync/Verification ===

    def list_node_ids(self) -> List[str]:
        """List all node IDs that have color stored."""
        cursor = self.conn.execute("SELECT id FROM node_color")
        return [row["id"] for row in cursor]

    def list_edge_ids(self) -> List[str]:
        """List all edge IDs that have color stored."""
        cursor = self.conn.execute("SELECT id FROM edge_color")
        return [row["id"] for row in cursor]
