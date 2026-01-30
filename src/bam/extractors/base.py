"""
Base Extractor

Abstract base class for all BAM extractors.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


logger = logging.getLogger("bam.extractors")


@dataclass
class ExtractionResult:
    """Result of an extraction operation."""
    success: bool
    source_id: str
    extractor_type: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    item_count: int = 0
    file_count: int = 0
    data_path: Optional[str] = None
    items: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseExtractor(ABC):
    """Base class for file format extractors."""

    # Subclasses should define this
    EXTRACTOR_TYPE: str = "base"
    FILE_EXTENSIONS: List[str] = []

    def __init__(self, source_id: str, project_dir: Optional[str] = None):
        """Initialize the extractor.

        Args:
            source_id: Identifier for this data source.
            project_dir: Optional project directory for output.
        """
        self.source_id = source_id
        self._project_dir = Path(project_dir) if project_dir else None

    @abstractmethod
    def extract_file(self, file_path: Path) -> Dict[str, Any]:
        """Extract structured data from a single file.

        Args:
            file_path: Path to the file to extract from.

        Returns:
            Dictionary containing extracted items and metadata.
        """
        pass

    def extract_directory(
        self,
        directory: Path,
        recursive: bool = True,
        exclude_patterns: Optional[List[str]] = None
    ) -> ExtractionResult:
        """Extract from all matching files in a directory.

        Args:
            directory: Directory to scan.
            recursive: Whether to scan subdirectories.
            exclude_patterns: Glob patterns to exclude.

        Returns:
            ExtractionResult with all extracted items.
        """
        result = ExtractionResult(
            success=False,
            source_id=self.source_id,
            extractor_type=self.EXTRACTOR_TYPE
        )

        directory = Path(directory)
        if not directory.exists():
            result.errors.append(f"Directory not found: {directory}")
            return result

        exclude_patterns = exclude_patterns or []
        all_items = []
        all_relationships = []
        files_processed = 0

        # Find all matching files
        for ext in self.FILE_EXTENSIONS:
            pattern = f"**/*.{ext}" if recursive else f"*.{ext}"
            for file_path in directory.glob(pattern):
                # Check exclusions
                if any(file_path.match(p) for p in exclude_patterns):
                    continue

                try:
                    file_result = self.extract_file(file_path)
                    if file_result.get("items"):
                        all_items.extend(file_result["items"])
                    if file_result.get("relationships"):
                        all_relationships.extend(file_result["relationships"])
                    if file_result.get("warnings"):
                        result.warnings.extend(file_result["warnings"])
                    files_processed += 1
                except Exception as e:
                    result.warnings.append(f"Error processing {file_path}: {e}")
                    logger.warning("Error processing %s: %s", file_path, e)

        result.success = True
        result.items = all_items
        result.relationships = all_relationships
        result.item_count = len(all_items)
        result.file_count = files_processed
        result.metadata["directory"] = str(directory)
        result.metadata["recursive"] = recursive

        logger.info(
            "Extracted %d items from %d files in %s",
            len(all_items), files_processed, directory
        )

        return result

    def _get_data_dir(self) -> Path:
        """Get the data directory for this source."""
        if self._project_dir:
            source_dir = self._project_dir / "data" / self.source_id
        else:
            source_dir = Path("data") / self.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir
