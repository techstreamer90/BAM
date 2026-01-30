"""
BAM Intermediate Format

The canonical format that all extractors produce and Stage 2 ingestion consumes.
This is the "contract" between source-specific extraction and sketch ingestion.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.extractors.intermediate")

# Current schema version
INTERMEDIATE_FORMAT_VERSION = "1.0"


@dataclass
class IntermediateNode:
    """A node in the intermediate format.

    Attributes:
        type: Must match a node type defined in the target sketch
        external_id: Unique ID from the source system (e.g., "JAMA-REQ-001")
        label: Human-readable label/title
        properties: Arbitrary properties - sketch defines what's expected
        content: Optional long-form content (description, body text, etc.)
        source_location: Where this came from (file path, URL, etc.)
    """
    type: str
    external_id: str
    label: str
    properties: Dict[str, Any] = field(default_factory=dict)
    content: Optional[str] = None
    source_location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting None values."""
        d = {
            "type": self.type,
            "external_id": self.external_id,
            "label": self.label,
        }
        if self.properties:
            d["properties"] = self.properties
        if self.content is not None:
            d["content"] = self.content
        if self.source_location is not None:
            d["source_location"] = self.source_location
        return d


@dataclass
class IntermediateEdge:
    """An edge in the intermediate format.

    Attributes:
        type: Must match an edge type defined in the target sketch
        source_external_id: External ID of the source node
        target_external_id: External ID of the target node
        properties: Optional edge properties
    """
    type: str
    source_external_id: str
    target_external_id: str
    properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, omitting empty values."""
        d = {
            "type": self.type,
            "source_external_id": self.source_external_id,
            "target_external_id": self.target_external_id,
        }
        if self.properties:
            d["properties"] = self.properties
        return d


@dataclass
class IntermediateData:
    """The complete intermediate format structure.

    This is what extractors produce and Stage 2 ingestion consumes.
    """
    # Metadata
    format_version: str = INTERMEDIATE_FORMAT_VERSION
    source_id: str = ""  # BAM source ID
    source_type: str = ""  # e.g., "jama", "pdf", "docx", "systemverilog"
    extracted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Optional: path to sketch for validation
    target_sketch: Optional[str] = None

    # The actual data
    nodes: List[IntermediateNode] = field(default_factory=list)
    edges: List[IntermediateEdge] = field(default_factory=list)

    # Extraction metadata
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def add_node(self, node: IntermediateNode) -> None:
        """Add a node to the data."""
        self.nodes.append(node)

    def add_edge(self, edge: IntermediateEdge) -> None:
        """Add an edge to the data."""
        self.edges.append(edge)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "format_version": self.format_version,
            "source_id": self.source_id,
            "source_type": self.source_type,
            "extracted_at": self.extracted_at,
            "target_sketch": self.target_sketch,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "extraction_metadata": self.extraction_metadata,
            "warnings": self.warnings,
            "summary": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "node_types": self._count_by_type(self.nodes),
                "edge_types": self._count_by_type(self.edges),
            }
        }

    def _count_by_type(self, items: List) -> Dict[str, int]:
        """Count items by type."""
        counts = {}
        for item in items:
            t = item.type
            counts[t] = counts.get(t, 0) + 1
        return counts

    def save(self, path: Path) -> None:
        """Save to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Saved intermediate data to %s (%d nodes, %d edges)",
                    path, len(self.nodes), len(self.edges))

    @classmethod
    def load(cls, path: Path) -> "IntermediateData":
        """Load from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        intermediate = cls(
            format_version=data.get("format_version", INTERMEDIATE_FORMAT_VERSION),
            source_id=data.get("source_id", ""),
            source_type=data.get("source_type", ""),
            extracted_at=data.get("extracted_at", ""),
            target_sketch=data.get("target_sketch"),
            extraction_metadata=data.get("extraction_metadata", {}),
            warnings=data.get("warnings", []),
        )

        for node_data in data.get("nodes", []):
            intermediate.nodes.append(IntermediateNode(
                type=node_data["type"],
                external_id=node_data["external_id"],
                label=node_data["label"],
                properties=node_data.get("properties", {}),
                content=node_data.get("content"),
                source_location=node_data.get("source_location"),
            ))

        for edge_data in data.get("edges", []):
            intermediate.edges.append(IntermediateEdge(
                type=edge_data["type"],
                source_external_id=edge_data["source_external_id"],
                target_external_id=edge_data["target_external_id"],
                properties=edge_data.get("properties", {}),
            ))

        return intermediate


@dataclass
class SourceMapping:
    """Defines how to map source data to intermediate format.

    This is configured per source type during sketch design.
    The AI helps create this mapping by examining source data + sketch.
    """
    # What source this mapping applies to
    source_type: str  # e.g., "jama", "pdf", "docx"
    source_id: str  # Specific source ID

    # Node mappings: source field/pattern → intermediate node
    node_mappings: List[Dict[str, Any]] = field(default_factory=list)
    # Example node mapping:
    # {
    #     "source_pattern": "items[*]",  # JSONPath or similar
    #     "condition": "item.type == 'requirement'",  # Optional filter
    #     "node_type": "DesignRequirement",  # Target sketch node type
    #     "external_id_field": "id",  # Field to use as external_id
    #     "label_field": "name",  # Field to use as label
    #     "content_field": "description",  # Optional
    #     "property_mappings": {
    #         "status": "item.status",
    #         "priority": "item.priority",
    #         "owner": "item.assigned_to.name"
    #     }
    # }

    # Edge mappings: how to create relationships
    edge_mappings: List[Dict[str, Any]] = field(default_factory=list)
    # Example edge mapping:
    # {
    #     "source_pattern": "items[*].parent_id",
    #     "edge_type": "DERIVES_FROM",
    #     "source_id_field": "id",  # Current item's ID
    #     "target_id_field": "parent_id",  # Field containing target ID
    #     "condition": "item.parent_id != null"
    # }

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: str = "ai"  # "ai" or "human"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> None:
        """Save mapping to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "SourceMapping":
        """Load mapping from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls(**data)


def validate_against_sketch(
    intermediate: IntermediateData,
    sketch_path: Path
) -> List[str]:
    """Validate intermediate data against a sketch schema.

    Returns list of validation errors (empty if valid).
    """
    errors = []

    try:
        with open(sketch_path, 'r') as f:
            sketch = json.load(f)
    except Exception as e:
        return [f"Could not load sketch: {e}"]

    # Get valid node and edge types from sketch
    valid_node_types = set()
    valid_edge_types = set()

    # Node types from existing nodes
    for node in sketch.get("nodes", {}).values():
        valid_node_types.add(node.get("type"))

    # Edge types from existing edges
    for edge in sketch.get("edges", {}).values():
        valid_edge_types.add(edge.get("type"))

    # Also check schema definitions if present
    if "node_types" in sketch:
        valid_node_types.update(sketch["node_types"])
    if "edge_types" in sketch:
        valid_edge_types.update(sketch["edge_types"])

    # Validate nodes
    for node in intermediate.nodes:
        if valid_node_types and node.type not in valid_node_types:
            errors.append(f"Unknown node type '{node.type}' for node '{node.external_id}'")

    # Validate edges
    node_ids = {n.external_id for n in intermediate.nodes}
    for edge in intermediate.edges:
        if valid_edge_types and edge.type not in valid_edge_types:
            errors.append(f"Unknown edge type '{edge.type}'")
        # Note: We don't validate source/target existence here because
        # they might reference nodes from other sources

    return errors
