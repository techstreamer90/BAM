"""
BAM Neo4j Color Backend

Stores color (node/edge details) in Neo4j graph database.
Best for large graphs with complex traversal queries.

Requires:
    pip install neo4j
    Neo4j server running (bolt://localhost:7687)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    from neo4j import GraphDatabase
    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False
    GraphDatabase = None

from .base import (
    BaseColorBackend,
    NodeColor,
    EdgeColor,
    ColorStats,
    SnapshotInfo,
)


class Neo4jColorBackend(BaseColorBackend):
    """
    Neo4j-based color storage backend.

    Stores node/edge color as properties on Neo4j nodes/relationships.
    The sketch structure is managed separately - this only stores color.

    Advantages:
    - Native graph storage optimized for traversals
    - Cypher query language for complex searches
    - Scales to millions of nodes
    - ACID transactions

    Note: This stores COLOR only. The sketch (structure) remains in JSON.
    Neo4j nodes here are keyed by the sketch node ID.
    """

    def __init__(self, config: dict):
        if not NEO4J_AVAILABLE:
            raise ImportError(
                "Neo4j backend requires 'neo4j' package. "
                "Install with: pip install neo4j"
            )

        super().__init__(config, "neo4j")

        self.uri = config.get("uri", "bolt://localhost:7687")
        self.database = config.get("database", "neo4j")
        self.credentials = config.get("credentials", "")

        self.driver = None

    def connect(self) -> None:
        """Connect to Neo4j server."""
        import os
        import certifi

        auth = self._parse_credentials()

        # Set SSL certificate path for Windows compatibility with Neo4j Aura
        # This ensures Python can verify the SSL certificates
        os.environ.setdefault('SSL_CERT_FILE', certifi.where())
        os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())

        self.driver = GraphDatabase.driver(self.uri, auth=auth)

        # Verify connection and create constraints
        with self.driver.session(database=self.database) as session:
            session.run("RETURN 1")

            # Create unique constraint on color node IDs
            try:
                session.run("""
                    CREATE CONSTRAINT color_node_id IF NOT EXISTS
                    FOR (n:ColorNode) REQUIRE n.id IS UNIQUE
                """)
                session.run("""
                    CREATE CONSTRAINT color_edge_id IF NOT EXISTS
                    FOR (e:ColorEdge) REQUIRE e.id IS UNIQUE
                """)
            except Exception:
                pass  # Constraints may already exist

        self._connected = True

    def close(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            self.driver = None
        self._connected = False

    def _parse_credentials(self):
        """Parse credentials from config."""
        import os

        creds = self.credentials
        if creds.startswith("env:"):
            env_var = creds[4:]
            creds = os.environ.get(env_var, "")

        if ":" in creds:
            user, password = creds.split(":", 1)
            return (user, password)

        return ("neo4j", "neo4j")  # Default credentials

    def _run_query(self, query: str, parameters: dict = None):
        """Run a Cypher query."""
        with self.driver.session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return list(result)

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor) -> None:
        """Store color for a node."""
        query = """
            MERGE (n:ColorNode {id: $id})
            SET n.properties = $properties,
                n.source_ref = $source_ref,
                n.content = $content,
                n.created_at = $created_at,
                n.updated_at = $updated_at
        """
        self._run_query(query, {
            "id": color.id,
            "properties": json.dumps(color.properties),
            "source_ref": color.source_ref,
            "content": color.content,
            "created_at": color.created_at,
            "updated_at": color.updated_at,
        })

    def get_node_color(self, node_id: str) -> Optional[NodeColor]:
        """Get color for a node by ID."""
        query = """
            MATCH (n:ColorNode {id: $id})
            RETURN n.id as id, n.properties as properties, n.source_ref as source_ref,
                   n.content as content, n.created_at as created_at, n.updated_at as updated_at
        """
        results = self._run_query(query, {"id": node_id})

        if not results:
            return None

        record = results[0]
        return NodeColor(
            id=record["id"],
            properties=json.loads(record["properties"]) if record["properties"] else {},
            source_ref=record["source_ref"],
            content=record["content"],
            created_at=record["created_at"],
            updated_at=record["updated_at"],
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

        query = """
            MATCH (n:ColorNode {id: $id})
            SET n.properties = $properties,
                n.content = $content,
                n.source_ref = $source_ref,
                n.updated_at = $updated_at
        """
        self._run_query(query, {
            "id": node_id,
            "properties": json.dumps(properties),
            "content": content,
            "source_ref": source_ref,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return True

    def delete_node_color(self, node_id: str) -> bool:
        """Delete color for a node."""
        query = """
            MATCH (n:ColorNode {id: $id})
            DELETE n
            RETURN count(n) as deleted
        """
        results = self._run_query(query, {"id": node_id})
        return results[0]["deleted"] > 0 if results else False

    def bulk_store_node_color(self, color_list: List[NodeColor]) -> int:
        """Store color for multiple nodes."""
        query = """
            UNWIND $items as item
            MERGE (n:ColorNode {id: item.id})
            SET n.properties = item.properties,
                n.source_ref = item.source_ref,
                n.content = item.content,
                n.created_at = item.created_at,
                n.updated_at = item.updated_at
        """
        items = [
            {
                "id": f.id,
                "properties": json.dumps(f.properties),
                "source_ref": f.source_ref,
                "content": f.content,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
            }
            for f in color_list
        ]
        self._run_query(query, {"items": items})
        return len(color_list)

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor) -> None:
        """Store color for an edge."""
        query = """
            MERGE (e:ColorEdge {id: $id})
            SET e.properties = $properties,
                e.created_at = $created_at
        """
        self._run_query(query, {
            "id": color.id,
            "properties": json.dumps(color.properties),
            "created_at": color.created_at,
        })

    def get_edge_color(self, edge_id: str) -> Optional[EdgeColor]:
        """Get color for an edge by ID."""
        query = """
            MATCH (e:ColorEdge {id: $id})
            RETURN e.id as id, e.properties as properties, e.created_at as created_at
        """
        results = self._run_query(query, {"id": edge_id})

        if not results:
            return None

        record = results[0]
        return EdgeColor(
            id=record["id"],
            properties=json.loads(record["properties"]) if record["properties"] else {},
            created_at=record["created_at"],
        )

    def update_edge_color(self, edge_id: str, updates: dict) -> bool:
        """Update an edge's color."""
        existing = self.get_edge_color(edge_id)
        if not existing:
            return False

        properties = existing.properties.copy()
        if "properties" in updates:
            properties.update(updates["properties"])

        query = """
            MATCH (e:ColorEdge {id: $id})
            SET e.properties = $properties
        """
        self._run_query(query, {
            "id": edge_id,
            "properties": json.dumps(properties),
        })
        return True

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete color for an edge."""
        query = """
            MATCH (e:ColorEdge {id: $id})
            DELETE e
            RETURN count(e) as deleted
        """
        results = self._run_query(query, {"id": edge_id})
        return results[0]["deleted"] > 0 if results else False

    def bulk_store_edge_color(self, color_list: List[EdgeColor]) -> int:
        """Store color for multiple edges."""
        query = """
            UNWIND $items as item
            MERGE (e:ColorEdge {id: item.id})
            SET e.properties = item.properties,
                e.created_at = item.created_at
        """
        items = [
            {
                "id": f.id,
                "properties": json.dumps(f.properties),
                "created_at": f.created_at,
            }
            for f in color_list
        ]
        self._run_query(query, {"items": items})
        return len(color_list)

    # === Query Operations ===

    def get_nodes_color_by_ids(self, node_ids: List[str]) -> Dict[str, NodeColor]:
        """Get color for multiple nodes by ID."""
        if not node_ids:
            return {}

        query = """
            MATCH (n:ColorNode)
            WHERE n.id IN $ids
            RETURN n.id as id, n.properties as properties, n.source_ref as source_ref,
                   n.content as content, n.created_at as created_at, n.updated_at as updated_at
        """
        results = self._run_query(query, {"ids": node_ids})

        return {
            record["id"]: NodeColor(
                id=record["id"],
                properties=json.loads(record["properties"]) if record["properties"] else {},
                source_ref=record["source_ref"],
                content=record["content"],
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            )
            for record in results
        }

    def get_edges_color_by_ids(self, edge_ids: List[str]) -> Dict[str, EdgeColor]:
        """Get color for multiple edges by ID."""
        if not edge_ids:
            return {}

        query = """
            MATCH (e:ColorEdge)
            WHERE e.id IN $ids
            RETURN e.id as id, e.properties as properties, e.created_at as created_at
        """
        results = self._run_query(query, {"ids": edge_ids})

        return {
            record["id"]: EdgeColor(
                id=record["id"],
                properties=json.loads(record["properties"]) if record["properties"] else {},
                created_at=record["created_at"],
            )
            for record in results
        }

    def search_node_content(self, query_text: str, limit: int = 100) -> List[str]:
        """Search node content/properties for matching text."""
        query = """
            MATCH (n:ColorNode)
            WHERE n.content CONTAINS $query OR n.properties CONTAINS $query
            RETURN n.id as id
            LIMIT $limit
        """
        results = self._run_query(query, {"query": query_text, "limit": limit})
        return [record["id"] for record in results]

    # === Statistics ===

    def get_statistics(self) -> ColorStats:
        """Get color storage statistics."""
        node_query = "MATCH (n:ColorNode) RETURN count(n) as count"
        edge_query = "MATCH (e:ColorEdge) RETURN count(e) as count"

        node_results = self._run_query(node_query)
        edge_results = self._run_query(edge_query)

        return ColorStats(
            total_nodes=node_results[0]["count"] if node_results else 0,
            total_edges=edge_results[0]["count"] if edge_results else 0,
            storage_size_bytes=None,  # Not easily available in Neo4j
        )

    # === Snapshot Operations ===

    def create_snapshot(self, label: Optional[str] = None) -> str:
        """Create a snapshot of color data."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        snapshot_id = f"color-snapshot-{timestamp}"
        if label:
            snapshot_id = f"{snapshot_id}-{label}"

        # Export all color data
        nodes = self._run_query("MATCH (n:ColorNode) RETURN n")
        edges = self._run_query("MATCH (e:ColorEdge) RETURN e")

        data = {
            "nodes": {record["n"]["id"]: dict(record["n"]) for record in nodes},
            "edges": {record["e"]["id"]: dict(record["e"]) for record in edges},
        }

        # Store snapshot as a node
        query = """
            CREATE (s:ColorSnapshot {
                id: $id,
                created_at: $created_at,
                label: $label,
                data: $data
            })
        """
        self._run_query(query, {
            "id": snapshot_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "data": json.dumps(data),
        })

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore color data from a snapshot."""
        query = """
            MATCH (s:ColorSnapshot {id: $id})
            RETURN s.data as data
        """
        results = self._run_query(query, {"id": snapshot_id})

        if not results:
            return False

        data = json.loads(results[0]["data"])

        # Clear current color data
        self._run_query("MATCH (n:ColorNode) DELETE n")
        self._run_query("MATCH (e:ColorEdge) DELETE e")

        # Restore nodes
        for node_data in data["nodes"].values():
            # Ensure all required fields have values
            params = {
                "id": node_data.get("id"),
                "properties": node_data.get("properties", "{}"),
                "source_ref": node_data.get("source_ref"),
                "content": node_data.get("content"),
                "created_at": node_data.get("created_at"),
                "updated_at": node_data.get("updated_at"),
            }
            self._run_query("""
                CREATE (n:ColorNode {
                    id: $id, properties: $properties, source_ref: $source_ref,
                    content: $content, created_at: $created_at, updated_at: $updated_at
                })
            """, params)

        # Restore edges
        for edge_data in data["edges"].values():
            params = {
                "id": edge_data.get("id"),
                "properties": edge_data.get("properties", "{}"),
                "created_at": edge_data.get("created_at"),
            }
            self._run_query("""
                CREATE (e:ColorEdge {
                    id: $id, properties: $properties, created_at: $created_at
                })
            """, params)

        return True

    def list_snapshots(self) -> List[SnapshotInfo]:
        """List available snapshots."""
        query = """
            MATCH (s:ColorSnapshot)
            RETURN s.id as id, s.created_at as created_at, s.label as label, s.data as data
            ORDER BY s.created_at
        """
        results = self._run_query(query)

        snapshots = []
        for record in results:
            data = json.loads(record["data"])
            snapshots.append(SnapshotInfo(
                id=record["id"],
                created_at=record["created_at"],
                label=record["label"],
                node_count=len(data["nodes"]),
                edge_count=len(data["edges"]),
            ))

        return snapshots

    # === Source Operations ===

    def clear_source(self, source_id: str, node_ids: List[str], edge_ids: List[str]) -> Dict[str, int]:
        """Clear color for specified nodes and edges."""
        removed_nodes = 0
        removed_edges = 0

        if node_ids:
            query = """
                MATCH (n:ColorNode)
                WHERE n.id IN $ids
                DELETE n
                RETURN count(n) as deleted
            """
            results = self._run_query(query, {"ids": node_ids})
            removed_nodes = results[0]["deleted"] if results else 0

        if edge_ids:
            query = """
                MATCH (e:ColorEdge)
                WHERE e.id IN $ids
                DELETE e
                RETURN count(e) as deleted
            """
            results = self._run_query(query, {"ids": edge_ids})
            removed_edges = results[0]["deleted"] if results else 0

        return {
            "removed_nodes": removed_nodes,
            "removed_edges": removed_edges,
        }

    # === Sync/Verification ===

    def list_node_ids(self) -> List[str]:
        """List all node IDs that have color stored."""
        query = "MATCH (n:ColorNode) RETURN n.id as id"
        results = self._run_query(query)
        return [record["id"] for record in results]

    def list_edge_ids(self) -> List[str]:
        """List all edge IDs that have color stored."""
        query = "MATCH (e:ColorEdge) RETURN e.id as id"
        results = self._run_query(query)
        return [record["id"] for record in results]
