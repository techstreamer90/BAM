"""
BAM ArangoDB Color Backend

Stores color (node/edge details) in ArangoDB multi-model database.
Good for graphs that also need document queries.

Requires:
    pip install python-arango
    ArangoDB server running (http://localhost:8529)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from arango import ArangoClient
    from arango.exceptions import DocumentInsertError
    ARANGO_AVAILABLE = True
except ImportError:
    ARANGO_AVAILABLE = False
    ArangoClient = None

from .base import (
    BaseColorBackend,
    NodeColor,
    EdgeColor,
    ColorStats,
    SnapshotInfo,
)


class ArangoColorBackend(BaseColorBackend):
    """
    ArangoDB-based color storage backend.

    Stores node/edge color as documents in ArangoDB collections.
    The sketch structure is managed separately - this only stores color.

    Advantages:
    - Multi-model: document + graph + key-value in one
    - AQL query language (SQL-like, powerful)
    - Good for mixed workloads (document queries + graph traversals)
    - Scales horizontally with sharding

    Note: This stores COLOR only. The sketch (structure) remains in JSON.
    ArangoDB documents here are keyed by the sketch node/edge ID.
    """

    def __init__(self, config: dict):
        if not ARANGO_AVAILABLE:
            raise ImportError(
                "ArangoDB backend requires 'python-arango' package. "
                "Install with: pip install python-arango"
            )

        super().__init__(config, "arango")

        self.url = config.get("url", "http://localhost:8529")
        self.database_name = config.get("database", "bam")
        self.credentials = config.get("credentials", "")

        self.client = None
        self.db = None

    def connect(self) -> None:
        """Connect to ArangoDB server."""
        self.client = ArangoClient(hosts=self.url)

        user, password = self._parse_credentials()

        # Connect to system DB first to create database if needed
        sys_db = self.client.db("_system", username=user, password=password)

        if not sys_db.has_database(self.database_name):
            sys_db.create_database(self.database_name)

        self.db = self.client.db(self.database_name, username=user, password=password)

        # Create collections if needed
        self._ensure_collections()

        self._connected = True

    def close(self) -> None:
        """Close ArangoDB connection."""
        self.client = None
        self.db = None
        self._connected = False

    def _parse_credentials(self):
        """Parse credentials from config."""
        import os

        creds = self.credentials
        if creds.startswith("env:"):
            env_var = creds[4:]
            creds = os.environ.get(env_var, "")

        if ":" in creds:
            return creds.split(":", 1)

        return ("root", "")  # Default credentials

    def _ensure_collections(self):
        """Create collections if they don't exist."""
        if not self.db.has_collection("node_color"):
            self.db.create_collection("node_color")

        if not self.db.has_collection("edge_color"):
            self.db.create_collection("edge_color")

        if not self.db.has_collection("snapshots"):
            self.db.create_collection("snapshots")

        # Create indexes for common queries
        node_col = self.db.collection("node_color")
        try:
            node_col.add_hash_index(fields=["source_ref"], unique=False)
        except Exception:
            pass  # Index may already exist

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor) -> None:
        """Store color for a node."""
        collection = self.db.collection("node_color")

        doc = {
            "_key": color.id,
            "id": color.id,
            "properties": color.properties,
            "source_ref": color.source_ref,
            "content": color.content,
            "created_at": color.created_at,
            "updated_at": color.updated_at,
        }

        # Use insert with overwrite to handle both insert and update
        try:
            collection.insert(doc, overwrite=True)
        except DocumentInsertError:
            collection.update(doc)

    def get_node_color(self, node_id: str) -> Optional[NodeColor]:
        """Get color for a node by ID."""
        collection = self.db.collection("node_color")

        try:
            doc = collection.get(node_id)
            if not doc:
                return None

            return NodeColor(
                id=doc["id"],
                properties=doc.get("properties", {}),
                source_ref=doc.get("source_ref"),
                content=doc.get("content"),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
            )
        except Exception:
            return None

    def update_node_color(self, node_id: str, updates: dict) -> bool:
        """Update a node's color."""
        existing = self.get_node_color(node_id)
        if not existing:
            return False

        properties = existing.properties.copy()
        if "properties" in updates:
            properties.update(updates["properties"])

        collection = self.db.collection("node_color")
        collection.update({
            "_key": node_id,
            "properties": properties,
            "content": updates.get("content", existing.content),
            "source_ref": updates.get("source_ref", existing.source_ref),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return True

    def delete_node_color(self, node_id: str) -> bool:
        """Delete color for a node."""
        collection = self.db.collection("node_color")
        try:
            collection.delete(node_id)
            return True
        except Exception:
            return False

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Store color for multiple nodes."""
        collection = self.db.collection("node_color")

        docs = [
            {
                "_key": f.id,
                "id": f.id,
                "properties": f.properties,
                "source_ref": f.source_ref,
                "content": f.content,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
            }
            for f in color_list
        ]

        result = collection.import_bulk(docs, on_duplicate="replace")
        return result.get("created", 0) + result.get("updated", 0)

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor) -> None:
        """Store color for an edge."""
        collection = self.db.collection("edge_color")

        doc = {
            "_key": color.id,
            "id": color.id,
            "properties": color.properties,
            "created_at": color.created_at,
        }

        try:
            collection.insert(doc, overwrite=True)
        except DocumentInsertError:
            collection.update(doc)

    def get_edge_color(self, edge_id: str) -> Optional[EdgeColor]:
        """Get color for an edge by ID."""
        collection = self.db.collection("edge_color")

        try:
            doc = collection.get(edge_id)
            if not doc:
                return None

            return EdgeColor(
                id=doc["id"],
                properties=doc.get("properties", {}),
                created_at=doc.get("created_at"),
            )
        except Exception:
            return None

    def update_edge_color(self, edge_id: str, updates: dict) -> bool:
        """Update an edge's color."""
        existing = self.get_edge_color(edge_id)
        if not existing:
            return False

        properties = existing.properties.copy()
        if "properties" in updates:
            properties.update(updates["properties"])

        collection = self.db.collection("edge_color")
        collection.update({
            "_key": edge_id,
            "properties": properties,
        })
        return True

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete color for an edge."""
        collection = self.db.collection("edge_color")
        try:
            collection.delete(edge_id)
            return True
        except Exception:
            return False

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Store color for multiple edges."""
        collection = self.db.collection("edge_color")

        docs = [
            {
                "_key": f.id,
                "id": f.id,
                "properties": f.properties,
                "created_at": f.created_at,
            }
            for f in color_list
        ]

        result = collection.import_bulk(docs, on_duplicate="replace")
        return result.get("created", 0) + result.get("updated", 0)

    # === Query Operations ===

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Get color for multiple nodes by ID."""
        if not node_ids:
            return {}

        collection = self.db.collection("node_color")
        docs = collection.get_many(node_ids)

        return {
            doc["id"]: NodeColor(
                id=doc["id"],
                properties=doc.get("properties", {}),
                source_ref=doc.get("source_ref"),
                content=doc.get("content"),
                created_at=doc.get("created_at"),
                updated_at=doc.get("updated_at"),
            )
            for doc in docs if doc
        }

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Get color for multiple edges by ID."""
        if not edge_ids:
            return {}

        collection = self.db.collection("edge_color")
        docs = collection.get_many(edge_ids)

        return {
            doc["id"]: EdgeColor(
                id=doc["id"],
                properties=doc.get("properties", {}),
                created_at=doc.get("created_at"),
            )
            for doc in docs if doc
        }

    def search_node_content(self, query_text: str, limit: int = 100) -> List[str]:
        """Search node content/properties for matching text."""
        aql = """
            FOR doc IN node_color
                FILTER CONTAINS(LOWER(doc.content), LOWER(@query))
                    OR CONTAINS(LOWER(TO_STRING(doc.properties)), LOWER(@query))
                LIMIT @limit
                RETURN doc.id
        """
        cursor = self.db.aql.execute(aql, bind_vars={"query": query_text, "limit": limit})
        return list(cursor)

    # === Statistics ===

    def get_statistics(self) -> ColorStats:
        """Get color storage statistics."""
        node_count = self.db.collection("node_color").count()
        edge_count = self.db.collection("edge_color").count()

        return ColorStats(
            total_nodes=node_count,
            total_edges=edge_count,
            storage_size_bytes=None,  # Would need to query collection figures
        )

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """Create a snapshot of color data."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"color-snapshot-{timestamp}"
        if label:
            snapshot_id = f"{snapshot_id}-{label}"

        # Export all color data
        nodes = {doc["id"]: doc for doc in self.db.collection("node_color").all()}
        edges = {doc["id"]: doc for doc in self.db.collection("edge_color").all()}

        # Remove ArangoDB internal fields
        for doc in nodes.values():
            doc.pop("_key", None)
            doc.pop("_id", None)
            doc.pop("_rev", None)

        for doc in edges.values():
            doc.pop("_key", None)
            doc.pop("_id", None)
            doc.pop("_rev", None)

        snapshot = {
            "_key": snapshot_id,
            "id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "data": {"nodes": nodes, "edges": edges},
        }

        self.db.collection("snapshots").insert(snapshot, overwrite=True)

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore color data from a snapshot."""
        try:
            snapshot = self.db.collection("snapshots").get(snapshot_id)
            if not snapshot:
                return False

            data = snapshot["data"]

            # Clear current color data
            self.db.collection("node_color").truncate()
            self.db.collection("edge_color").truncate()

            # Restore nodes
            node_docs = [
                {**doc, "_key": doc["id"]}
                for doc in data["nodes"].values()
            ]
            if node_docs:
                self.db.collection("node_color").import_bulk(node_docs)

            # Restore edges
            edge_docs = [
                {**doc, "_key": doc["id"]}
                for doc in data["edges"].values()
            ]
            if edge_docs:
                self.db.collection("edge_color").import_bulk(edge_docs)

            return True
        except Exception:
            return False

    def list_snapshots(self) -> List[SnapshotInfo]:
        """List available snapshots."""
        aql = """
            FOR s IN snapshots
                SORT s.created_at
                RETURN s
        """
        cursor = self.db.aql.execute(aql)

        snapshots = []
        for doc in cursor:
            data = doc.get("data", {"nodes": {}, "edges": {}})
            snapshots.append(SnapshotInfo(
                id=doc["id"],
                created_at=doc["created_at"],
                label=doc.get("label"),
                node_count=len(data.get("nodes", {})),
                edge_count=len(data.get("edges", {})),
            ))

        return snapshots

    # === Source Operations ===

    def clear_source(self, source_id: str, node_ids: List[str], edge_ids: List[str]) -> Dict[str, int]:
        """Clear color for specified nodes and edges."""
        removed_nodes = 0
        removed_edges = 0

        if node_ids:
            for nid in node_ids:
                if self.delete_node_color(nid):
                    removed_nodes += 1

        if edge_ids:
            for eid in edge_ids:
                if self.delete_edge_color(eid):
                    removed_edges += 1

        return {
            "removed_nodes": removed_nodes,
            "removed_edges": removed_edges,
        }

    # === Sync/Verification ===

    def list_node_ids(self) -> List[str]:
        """List all node IDs that have color stored."""
        aql = "FOR doc IN node_color RETURN doc.id"
        cursor = self.db.aql.execute(aql)
        return list(cursor)

    def list_edge_ids(self) -> List[str]:
        """List all edge IDs that have color stored."""
        aql = "FOR doc IN edge_color RETURN doc.id"
        cursor = self.db.aql.execute(aql)
        return list(cursor)
