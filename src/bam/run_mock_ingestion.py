#!/usr/bin/env python
"""
Mock Ingestion Test Script

Demonstrates the BAM ingestion flow using mock JAMA data.
This bypasses the placeholder pipeline stages and directly exercises
the connectors and graph manager.
"""

import json
import logging
from pathlib import Path

from .source_connector import ConnectorFactory
from .graph_manager import GraphManager, Node, Edge

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def transform_items_to_nodes_and_edges(items: list, source_id: str, gm: GraphManager = None) -> tuple:
    """Transform JAMA items to graph nodes and edges.

    Args:
        items: List of JAMA items to transform
        source_id: Source identifier for these items
        gm: Optional GraphManager to resolve cross-references
    """
    nodes = []
    edges = []

    # Build a map of original IDs to node IDs for this batch
    local_id_map = {}
    for item in items:
        node_id = f"{source_id}-{item['id']}"
        local_id_map[item['id']] = node_id

    for item in items:
        # Create node
        node_id = f"{source_id}-{item['id']}"
        node_type = "Requirement" if item["type"] == "requirement" else "Specification"

        node = Node(
            id=node_id,
            type=node_type,
            label=item["name"],
            properties={
                "description": item.get("description", ""),
                "status": item.get("status", ""),
                "priority": item.get("priority", ""),
                "level": item.get("level", ""),
                "original_id": item["id"],
            },
            source_id=source_id,
            source_ref=item["id"],
        )
        nodes.append(node)

        # Create edges from relationships
        for rel in item.get("relationships", []):
            edge_type = "DERIVES_FROM" if rel["type"] == "derives" else "SATISFIES"
            target_ref = rel['target']

            # Try to resolve target: first in local batch, then in existing graph
            if target_ref in local_id_map:
                target_node_id = local_id_map[target_ref]
            elif gm:
                # Search existing nodes by source_ref
                existing = gm.find_nodes(label_contains=target_ref)
                # Find one with matching original_id in properties
                target_node_id = None
                for n in existing:
                    if n.get('properties', {}).get('original_id') == target_ref:
                        target_node_id = n['id']
                        break
                if not target_node_id:
                    # Fallback: try common prefixes
                    for prefix in ['mock-jama-core', 'mock-jama-safety', 'mock-jama-specs']:
                        candidate = f"{prefix}-{target_ref}"
                        if gm.get_node(candidate):
                            target_node_id = candidate
                            break
                if not target_node_id:
                    logger.debug("Cannot resolve target %s for edge from %s", target_ref, node_id)
                    continue
            else:
                target_node_id = f"{source_id}-{target_ref}"

            edge = Edge(
                id=f"edge-{node_id}-{edge_type}-{target_ref}",
                type=edge_type,
                source_node_id=node_id,
                target_node_id=target_node_id,
                properties={},
                source_id=source_id,
            )
            edges.append(edge)

    return nodes, edges


def ingest_source(source_id: str, gm: GraphManager) -> dict:
    """Ingest a single source into the graph."""
    logger.info("=" * 60)
    logger.info("Ingesting source: %s", source_id)
    logger.info("=" * 60)

    # 1. Fetch data
    connector = ConnectorFactory.get_connector_for_source(source_id)
    result = connector.fetch_full()

    if not result.success:
        logger.error("Fetch failed: %s", result.errors)
        return {"success": False, "errors": result.errors}

    logger.info("Fetched %d items from %s", result.item_count, result.data_path)

    # 2. Load and transform
    with open(result.data_path, 'r') as f:
        data = json.load(f)

    nodes, edges = transform_items_to_nodes_and_edges(data["items"], source_id, gm)
    logger.info("Transformed to %d nodes and %d edges", len(nodes), len(edges))

    # 3. Add to graph
    nodes_added = 0
    edges_added = 0

    for node in nodes:
        try:
            gm.add_node(node)
            nodes_added += 1
        except ValueError as e:
            logger.warning("Skip node %s: %s", node.id, e)

    for edge in edges:
        try:
            gm.add_edge(edge)
            edges_added += 1
        except ValueError as e:
            logger.debug("Skip edge %s: %s", edge.id, e)

    logger.info("Added %d nodes, %d edges", nodes_added, edges_added)

    return {
        "success": True,
        "nodes_added": nodes_added,
        "edges_added": edges_added,
    }


def main():
    """Run the mock ingestion test."""
    print("\n" + "=" * 60)
    print("BAM Mock Ingestion Test")
    print("=" * 60 + "\n")

    # Create a snapshot before we start
    with GraphManager() as gm:
        # Show initial state
        stats = gm.get_statistics()
        print(f"Initial state: {stats['totalNodes']} nodes, {stats['totalEdges']} edges\n")

        # Ingest chunk 1: Core requirements (backbone)
        print("\n>>> PHASE 1: Core Requirements (Backbone)")
        result1 = ingest_source("mock-jama-core", gm)

        # Show state after chunk 1
        stats = gm.get_statistics()
        print(f"\nAfter core: {stats['totalNodes']} nodes, {stats['totalEdges']} edges")
        print(f"  By type: {stats['nodesByType']}")

        # Ingest chunk 2: Safety requirements
        print("\n>>> PHASE 2: Safety Requirements (Incremental)")
        result2 = ingest_source("mock-jama-safety", gm)

        # Show state after chunk 2
        stats = gm.get_statistics()
        print(f"\nAfter safety: {stats['totalNodes']} nodes, {stats['totalEdges']} edges")
        print(f"  By type: {stats['nodesByType']}")

        # Ingest chunk 3: Specifications
        print("\n>>> PHASE 3: Specifications (Incremental)")
        result3 = ingest_source("mock-jama-specs", gm)

        # Final state
        stats = gm.get_statistics()
        print("\n" + "=" * 60)
        print("FINAL STATE")
        print("=" * 60)
        print(f"Total Nodes: {stats['totalNodes']}")
        print(f"Total Edges: {stats['totalEdges']}")
        print(f"Nodes by Type: {stats['nodesByType']}")
        print(f"Edges by Type: {stats['edgesByType']}")
        print(f"Backends: {stats['backends']}")

        # Show some example nodes
        print("\n--- Sample Nodes ---")
        reqs = gm.find_nodes(node_type="Requirement")[:3]
        for req in reqs:
            print(f"  {req['id']}: {req['label']}")

        specs = gm.find_nodes(node_type="Specification")[:3]
        for spec in specs:
            print(f"  {spec['id']}: {spec['label']}")

        # Show traceability example
        print("\n--- Traceability Example ---")
        # Find what derives from REQ-001
        deriving = gm.get_connected_nodes("mock-jama-core-REQ-001", direction="incoming")
        print(f"Items deriving from REQ-001 (System Overview):")
        for node in deriving[:5]:
            print(f"  <- {node['id']}: {node['label']}")

        # Find what satisfies SAF-001
        satisfying = gm.get_connected_nodes("mock-jama-safety-SAF-001", direction="incoming")
        print(f"\nItems satisfying SAF-001 (Fault Detection):")
        for node in satisfying[:5]:
            print(f"  <- {node['id']}: {node['label']}")

        print("\n" + "=" * 60)
        print("Ingestion complete!")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
