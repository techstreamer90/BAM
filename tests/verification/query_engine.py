"""
Verification Query Engine

Wraps GraphManager to execute verification queries and compare against expected values.
"""

import time
from typing import Any, Dict, List, Optional

from .models import (
    DataPoint,
    ExpectedValue,
    VerificationQuery,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)


class VerificationQueryEngine:
    """
    Executes verification queries against the graph model.

    Wraps GraphManager to provide a clean interface for verification operations.
    """

    def __init__(self, graph_manager=None, config: dict = None, project_dir: str = None):
        """
        Initialize the query engine.

        Args:
            graph_manager: Optional GraphManager instance. If not provided, creates one.
            config: Optional config dict for creating GraphManager.
            project_dir: Optional project directory path. Passed to GraphManager
                when creating internally.
        """
        self._owns_manager = graph_manager is None
        if graph_manager is None:
            from bam.graph_manager import GraphManager
            self._gm = GraphManager(project_dir=project_dir, config=config)
        else:
            self._gm = graph_manager

    def close(self):
        """Close the query engine and release resources."""
        if self._owns_manager:
            self._gm.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def verify(self, data_point: DataPoint) -> VerificationResult:
        """
        Execute a verification for a single data point.

        Args:
            data_point: The data point to verify.

        Returns:
            VerificationResult with pass/fail status.
        """
        start_time = time.perf_counter()

        try:
            if data_point.type == VerificationType.NODE_EXISTS:
                result = self._verify_node_exists(data_point)
            elif data_point.type == VerificationType.NODE_PROPERTIES:
                result = self._verify_node_properties(data_point)
            elif data_point.type == VerificationType.NODE_CONTENT:
                result = self._verify_node_content(data_point)
            elif data_point.type == VerificationType.EDGE_EXISTS:
                result = self._verify_edge_exists(data_point)
            elif data_point.type == VerificationType.NODE_COUNT:
                result = self._verify_node_count(data_point)
            elif data_point.type == VerificationType.RELATIONSHIP_COUNT:
                result = self._verify_relationship_count(data_point)
            else:
                result = VerificationResult(
                    data_point_id=data_point.id,
                    status=VerificationStatus.ERROR,
                    description=data_point.description,
                    expected=None,
                    actual=None,
                    error=f"Unknown verification type: {data_point.type}"
                )
        except Exception as e:
            result = VerificationResult(
                data_point_id=data_point.id,
                status=VerificationStatus.ERROR,
                description=data_point.description,
                expected=None,
                actual=None,
                error=str(e)
            )

        end_time = time.perf_counter()
        result.duration_ms = (end_time - start_time) * 1000
        return result

    def _verify_node_exists(self, dp: DataPoint) -> VerificationResult:
        """Verify that a node exists with expected type/label."""
        node_id = dp.query.node_id
        node = self._gm.get_node(node_id)

        exists = node is not None
        expected_exists = dp.expected.exists if dp.expected.exists is not None else True

        if exists != expected_exists:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected={"exists": expected_exists},
                actual={"exists": exists},
                message=f"Node '{node_id}' existence mismatch"
            )

        if not exists:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.PASS,
                description=dp.description,
                expected={"exists": expected_exists},
                actual={"exists": exists},
                message="Node correctly does not exist"
            )

        # Check type if specified
        if dp.expected.type and node.get("type") != dp.expected.type:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected={"type": dp.expected.type},
                actual={"type": node.get("type")},
                message=f"Node type mismatch for '{node_id}'"
            )

        # Check label if specified
        if dp.expected.label and node.get("label") != dp.expected.label:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected={"label": dp.expected.label},
                actual={"label": node.get("label")},
                message=f"Node label mismatch for '{node_id}'"
            )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected={"exists": True, "type": dp.expected.type, "label": dp.expected.label},
            actual={"exists": True, "type": node.get("type"), "label": node.get("label")},
            message="Node exists with expected attributes"
        )

    def _verify_node_properties(self, dp: DataPoint) -> VerificationResult:
        """Verify that a node has expected properties."""
        node_id = dp.query.node_id
        node = self._gm.get_node(node_id)

        if node is None:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected=dp.expected.properties,
                actual=None,
                message=f"Node '{node_id}' not found"
            )

        node_props = node.get("properties", {})
        expected_props = dp.expected.properties or {}

        mismatches = []
        for key, expected_val in expected_props.items():
            actual_val = node_props.get(key)
            if actual_val != expected_val:
                mismatches.append(f"{key}: expected '{expected_val}', got '{actual_val}'")

        if mismatches:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected=expected_props,
                actual=node_props,
                message=f"Property mismatches: {'; '.join(mismatches)}"
            )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected=expected_props,
            actual=node_props,
            message="Node properties match"
        )

    def _verify_node_content(self, dp: DataPoint) -> VerificationResult:
        """Verify that a node's content contains expected terms."""
        node_id = dp.query.node_id
        node = self._gm.get_node(node_id)

        if node is None:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected=dp.expected.content_contains,
                actual=None,
                message=f"Node '{node_id}' not found"
            )

        # Get content from properties or dedicated content field
        content = node.get("properties", {}).get("content", "")
        if not content:
            content = node.get("content", "")

        content_lower = content.lower() if content else ""
        expected_terms = dp.expected.content_contains or []

        missing_terms = []
        for term in expected_terms:
            if term.lower() not in content_lower:
                missing_terms.append(term)

        if missing_terms:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected=expected_terms,
                actual=f"Content (length={len(content)})",
                message=f"Missing terms in content: {missing_terms}"
            )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected=expected_terms,
            actual=f"Content (length={len(content)})",
            message="Content contains all expected terms"
        )

    def _verify_edge_exists(self, dp: DataPoint) -> VerificationResult:
        """Verify that an edge exists between nodes."""
        source_id = dp.expected.source_node_id or dp.query.source_node_id
        target_id = dp.expected.target_node_id or dp.query.target_node_id
        edge_type = dp.expected.edge_type or dp.query.edge_type

        edges = self._gm.find_edges(
            edge_type=edge_type,
            source_node_id=source_id,
            target_node_id=target_id
        )

        exists = len(edges) > 0
        expected_exists = dp.expected.exists if dp.expected.exists is not None else True

        if exists != expected_exists:
            return VerificationResult(
                data_point_id=dp.id,
                status=VerificationStatus.FAIL,
                description=dp.description,
                expected={"exists": expected_exists, "source": source_id, "target": target_id, "type": edge_type},
                actual={"exists": exists, "count": len(edges)},
                message=f"Edge existence mismatch"
            )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected={"exists": expected_exists},
            actual={"exists": exists, "count": len(edges)},
            message="Edge existence verified"
        )

    def _verify_node_count(self, dp: DataPoint) -> VerificationResult:
        """Verify the count of nodes matching criteria."""
        nodes = self._gm.find_nodes(
            node_type=dp.query.node_type,
            source_id=dp.query.source_id,
            label_contains=dp.query.label_contains
        )

        actual_count = len(nodes)

        # Check exact count
        if dp.expected.count is not None:
            if actual_count != dp.expected.count:
                return VerificationResult(
                    data_point_id=dp.id,
                    status=VerificationStatus.FAIL,
                    description=dp.description,
                    expected={"count": dp.expected.count},
                    actual={"count": actual_count},
                    message=f"Node count mismatch"
                )

        # Check min count
        if dp.expected.min_count is not None:
            if actual_count < dp.expected.min_count:
                return VerificationResult(
                    data_point_id=dp.id,
                    status=VerificationStatus.FAIL,
                    description=dp.description,
                    expected={"min_count": dp.expected.min_count},
                    actual={"count": actual_count},
                    message=f"Node count below minimum"
                )

        # Check max count
        if dp.expected.max_count is not None:
            if actual_count > dp.expected.max_count:
                return VerificationResult(
                    data_point_id=dp.id,
                    status=VerificationStatus.FAIL,
                    description=dp.description,
                    expected={"max_count": dp.expected.max_count},
                    actual={"count": actual_count},
                    message=f"Node count above maximum"
                )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected={"count": dp.expected.count, "min": dp.expected.min_count, "max": dp.expected.max_count},
            actual={"count": actual_count},
            message="Node count verified"
        )

    def _verify_relationship_count(self, dp: DataPoint) -> VerificationResult:
        """Verify the count of relationships for a node."""
        node_id = dp.query.node_id
        edge_type = dp.query.edge_type

        # Find outgoing edges
        outgoing = self._gm.find_edges(source_node_id=node_id, edge_type=edge_type)
        # Find incoming edges
        incoming = self._gm.find_edges(target_node_id=node_id, edge_type=edge_type)

        actual_count = len(outgoing) + len(incoming)

        # Check exact count
        if dp.expected.count is not None:
            if actual_count != dp.expected.count:
                return VerificationResult(
                    data_point_id=dp.id,
                    status=VerificationStatus.FAIL,
                    description=dp.description,
                    expected={"count": dp.expected.count},
                    actual={"count": actual_count, "outgoing": len(outgoing), "incoming": len(incoming)},
                    message=f"Relationship count mismatch"
                )

        # Check min count
        if dp.expected.min_count is not None:
            if actual_count < dp.expected.min_count:
                return VerificationResult(
                    data_point_id=dp.id,
                    status=VerificationStatus.FAIL,
                    description=dp.description,
                    expected={"min_count": dp.expected.min_count},
                    actual={"count": actual_count},
                    message=f"Relationship count below minimum"
                )

        return VerificationResult(
            data_point_id=dp.id,
            status=VerificationStatus.PASS,
            description=dp.description,
            expected={"count": dp.expected.count, "min": dp.expected.min_count},
            actual={"count": actual_count, "outgoing": len(outgoing), "incoming": len(incoming)},
            message="Relationship count verified"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get current graph statistics."""
        return self._gm.get_statistics()
