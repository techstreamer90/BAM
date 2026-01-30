"""
BAM Stage 2 Ingestion

Takes intermediate format data and ingests it into a BAM sketch as color.
This is the generic ingestion that works with any properly-formatted
intermediate data, regardless of original source.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .intermediate import IntermediateData, validate_against_sketch

logger = logging.getLogger("bam.extractors.ingest")


@dataclass
class IngestionResult:
    """Result of ingesting intermediate data into a sketch."""
    success: bool
    source_id: str
    nodes_added: int = 0
    nodes_updated: int = 0
    edges_added: int = 0
    edges_updated: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class IntermediateIngester:
    """Ingests intermediate format data into a BAM project.

    This is Stage 2 of the extraction pipeline:
    Source → [Stage 1: Extractor] → Intermediate → [Stage 2: Ingester] → Sketch
    """

    def __init__(self, project_dir: Path):
        """Initialize the ingester.

        Args:
            project_dir: Path to the BAM project directory.
        """
        self.project_dir = Path(project_dir)
        self.sketch_path = self.project_dir / "model" / "sketch.json"
        self._sketch: Optional[Dict[str, Any]] = None

    def ingest(
        self,
        intermediate: IntermediateData,
        validate: bool = True,
        dry_run: bool = False
    ) -> IngestionResult:
        """Ingest intermediate data into the sketch.

        Args:
            intermediate: The intermediate format data to ingest.
            validate: Whether to validate against sketch before ingesting.
            dry_run: If True, validate but don't actually modify the sketch.

        Returns:
            IngestionResult with statistics and any errors/warnings.
        """
        result = IngestionResult(
            success=False,
            source_id=intermediate.source_id
        )

        # Load sketch
        try:
            self._load_sketch()
        except Exception as e:
            result.errors.append(f"Failed to load sketch: {e}")
            return result

        # Validate if requested
        if validate and self.sketch_path.exists():
            validation_errors = validate_against_sketch(intermediate, self.sketch_path)
            if validation_errors:
                result.warnings.extend(validation_errors)
                # Continue anyway - validation is advisory

        # Process nodes
        for node in intermediate.nodes:
            try:
                added, updated = self._ingest_node(node, intermediate.source_id, dry_run)
                if added:
                    result.nodes_added += 1
                elif updated:
                    result.nodes_updated += 1
            except Exception as e:
                result.errors.append(f"Error ingesting node {node.external_id}: {e}")

        # Process edges
        for edge in intermediate.edges:
            try:
                added, updated = self._ingest_edge(edge, intermediate.source_id, dry_run)
                if added:
                    result.edges_added += 1
                elif updated:
                    result.edges_updated += 1
            except Exception as e:
                result.errors.append(f"Error ingesting edge: {e}")

        # Save sketch if not dry run
        if not dry_run:
            try:
                self._save_sketch()
            except Exception as e:
                result.errors.append(f"Failed to save sketch: {e}")
                return result

        result.success = len(result.errors) == 0
        logger.info(
            "Ingestion complete: %d nodes added, %d updated; %d edges added, %d updated",
            result.nodes_added, result.nodes_updated,
            result.edges_added, result.edges_updated
        )

        return result

    def ingest_file(
        self,
        intermediate_path: Path,
        validate: bool = True,
        dry_run: bool = False
    ) -> IngestionResult:
        """Ingest intermediate data from a JSON file.

        Args:
            intermediate_path: Path to the intermediate format JSON file.
            validate: Whether to validate against sketch.
            dry_run: If True, validate but don't modify.

        Returns:
            IngestionResult with statistics.
        """
        try:
            intermediate = IntermediateData.load(intermediate_path)
        except Exception as e:
            return IngestionResult(
                success=False,
                source_id="unknown",
                errors=[f"Failed to load intermediate file: {e}"]
            )

        return self.ingest(intermediate, validate=validate, dry_run=dry_run)

    def _load_sketch(self) -> None:
        """Load the sketch from disk."""
        if self.sketch_path.exists():
            with open(self.sketch_path, 'r') as f:
                self._sketch = json.load(f)
        else:
            # Initialize empty sketch
            self._sketch = {
                "version": "1.0.0",
                "metadata": {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "node_count": 0,
                    "edge_count": 0,
                },
                "nodes": {},
                "edges": {},
                "node_types": [],
                "edge_types": [],
            }

    def _save_sketch(self) -> None:
        """Save the sketch to disk."""
        # Update metadata
        self._sketch["metadata"]["node_count"] = len(self._sketch["nodes"])
        self._sketch["metadata"]["edge_count"] = len(self._sketch["edges"])
        self._sketch["metadata"]["updated_at"] = datetime.now(timezone.utc).isoformat()

        self.sketch_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.sketch_path, 'w') as f:
            json.dump(self._sketch, f, indent=2)

    def _ingest_node(
        self,
        node,  # IntermediateNode
        source_id: str,
        dry_run: bool
    ) -> Tuple[bool, bool]:
        """Ingest a single node.

        Returns:
            Tuple of (was_added, was_updated)
        """
        # Generate BAM node ID from source_id + external_id
        bam_id = f"{source_id}-{node.external_id}"

        existing = self._sketch["nodes"].get(bam_id)
        is_new = existing is None

        if dry_run:
            return (is_new, not is_new)

        # Build the sketch node
        sketch_node = {
            "id": bam_id,
            "type": node.type,
            "label": node.label,
            "source_id": source_id,
            "source_ref": node.external_id,
        }

        # Add to sketch
        self._sketch["nodes"][bam_id] = sketch_node

        # Track node type
        if node.type not in self._sketch.get("node_types", []):
            self._sketch.setdefault("node_types", []).append(node.type)

        # Store properties and content in color layer (separate from sketch)
        # For now, we'll store in a separate color file
        self._store_color_data(bam_id, node, source_id)

        return (is_new, not is_new)

    def _ingest_edge(
        self,
        edge,  # IntermediateEdge
        source_id: str,
        dry_run: bool
    ) -> Tuple[bool, bool]:
        """Ingest a single edge.

        Returns:
            Tuple of (was_added, was_updated)
        """
        # Generate BAM node IDs
        source_bam_id = f"{source_id}-{edge.source_external_id}"
        target_bam_id = f"{source_id}-{edge.target_external_id}"

        # Generate edge ID
        edge_id = f"{source_id}-{edge.type}-{edge.source_external_id}-{edge.target_external_id}"

        existing = self._sketch["edges"].get(edge_id)
        is_new = existing is None

        if dry_run:
            return (is_new, not is_new)

        # Build the sketch edge
        sketch_edge = {
            "id": edge_id,
            "type": edge.type,
            "source_node_id": source_bam_id,
            "target_node_id": target_bam_id,
            "source_id": source_id,
        }

        # Add to sketch
        self._sketch["edges"][edge_id] = sketch_edge

        # Track edge type
        if edge.type not in self._sketch.get("edge_types", []):
            self._sketch.setdefault("edge_types", []).append(edge.type)

        return (is_new, not is_new)

    def _store_color_data(self, bam_id: str, node, source_id: str) -> None:
        """Store node properties and content in the color layer.

        This keeps the sketch lightweight (just structure) while
        storing rich data in color files.
        """
        color_dir = self.project_dir / "model" / "colors"
        color_dir.mkdir(parents=True, exist_ok=True)

        # Use source_id as the color file name
        color_file = color_dir / f"{source_id}.json"

        # Load existing color data or initialize
        if color_file.exists():
            with open(color_file, 'r') as f:
                color_data = json.load(f)
        else:
            color_data = {"nodes": {}, "edges": {}}

        # Store node data
        color_data["nodes"][bam_id] = {
            "id": bam_id,
            "properties": node.properties,
            "content": node.content,
            "source_location": node.source_location,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Save color file
        with open(color_file, 'w') as f:
            json.dump(color_data, f, indent=2)


def ingest_intermediate(
    project_dir: Path,
    intermediate_path: Path,
    validate: bool = True,
    dry_run: bool = False
) -> IngestionResult:
    """Convenience function to ingest intermediate data.

    Args:
        project_dir: Path to BAM project.
        intermediate_path: Path to intermediate JSON file.
        validate: Whether to validate against sketch.
        dry_run: If True, validate but don't modify.

    Returns:
        IngestionResult with statistics.
    """
    ingester = IntermediateIngester(project_dir)
    return ingester.ingest_file(intermediate_path, validate=validate, dry_run=dry_run)
