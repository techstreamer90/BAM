"""
BAM Source Connector

Handles connections to various data sources for ingestion.
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


logger = logging.getLogger("bam.source_connector")


@dataclass
class FetchResult:
    """Result of a data fetch operation."""
    success: bool
    source_id: str
    fetch_type: str  # "full" or "delta"
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    item_count: int = 0
    data_path: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseConnector(ABC):
    """Base class for source connectors."""

    def __init__(self, source_config: dict, project_dir: str = None):
        self.config = source_config
        self.source_id = source_config["id"]
        self.connection = source_config["connection"]
        self._project_dir = Path(project_dir) if project_dir else None

    @abstractmethod
    def test_connection(self) -> bool:
        """Test if the connection can be established."""
        pass

    @abstractmethod
    def fetch_full(self) -> FetchResult:
        """Fetch all data from the source."""
        pass

    @abstractmethod
    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch data changed since a timestamp."""
        pass

    def _get_data_dir(self) -> Path:
        """Get the data directory for this source.

        Uses the project's ``data/`` directory when a project_dir was
        provided, otherwise falls back to a ``data/`` directory next to
        the current working directory.
        """
        if self._project_dir:
            source_dir = self._project_dir / "data" / self.source_id
        else:
            source_dir = Path("data") / self.source_id
        source_dir.mkdir(parents=True, exist_ok=True)
        return source_dir


class JAMAConnector(BaseConnector):
    """Connector for JAMA Requirements Management."""

    def test_connection(self) -> bool:
        """Test JAMA API connection."""
        # NOTE: Placeholder - would use actual JAMA API
        logger.debug("Testing JAMA connection to: %s", self.connection.get('baseUrl', 'not configured'))
        return self.connection.get("baseUrl") is not None

    def fetch_full(self) -> FetchResult:
        """Fetch all requirements from JAMA."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="full"
        )

        try:
            # Placeholder for actual JAMA API calls
            # In real implementation:
            # 1. Authenticate using credentials
            # 2. Query for all items matching filters
            # 3. Download item data and relationships
            # 4. Save to data directory

            data_dir = self._get_data_dir()
            data_file = data_dir / f"jama-full-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            # Mock data for testing
            mock_data = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "source": self.source_id,
                "items": []
            }

            with open(data_file, 'w') as f:
                json.dump(mock_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(mock_data["items"])
            result.warnings.append("Using mock data - JAMA API not configured")

        except Exception as e:
            result.errors.append(str(e))

        return result

    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch requirements changed since timestamp."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="delta"
        )

        try:
            data_dir = self._get_data_dir()
            data_file = data_dir / f"jama-delta-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            mock_data = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "since": since,
                "source": self.source_id,
                "added": [],
                "modified": [],
                "deleted": []
            }

            with open(data_file, 'w') as f:
                json.dump(mock_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.metadata["since"] = since

        except Exception as e:
            result.errors.append(str(e))

        return result


class FilesystemConnector(BaseConnector):
    """Connector for filesystem-based sources."""

    def test_connection(self) -> bool:
        """Test if the base path exists."""
        base_path = Path(self.connection.get("basePath", ""))
        return base_path.exists()

    def fetch_full(self) -> FetchResult:
        """Scan and catalog all files matching patterns."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="full"
        )

        try:
            base_path = Path(self.connection.get("basePath", ""))
            patterns = self.connection.get("patterns", ["*"])

            files = []
            for pattern in patterns:
                for file_path in base_path.glob(pattern):
                    if file_path.is_file():
                        files.append({
                            "path": str(file_path),
                            "name": file_path.name,
                            "size": file_path.stat().st_size,
                            "modified": datetime.fromtimestamp(
                                file_path.stat().st_mtime
                            ).isoformat()
                        })

            data_dir = self._get_data_dir()
            data_file = data_dir / f"files-full-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            catalog = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "source": self.source_id,
                "basePath": str(base_path),
                "files": files
            }

            with open(data_file, 'w') as f:
                json.dump(catalog, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(files)

        except Exception as e:
            result.errors.append(str(e))

        return result

    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch files modified since timestamp."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="delta"
        )

        try:
            base_path = Path(self.connection.get("basePath", ""))
            patterns = self.connection.get("patterns", ["*"])
            since_dt = datetime.fromisoformat(since)

            added = []
            modified = []

            for pattern in patterns:
                for file_path in base_path.glob(pattern):
                    if file_path.is_file():
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if mtime > since_dt:
                            file_info = {
                                "path": str(file_path),
                                "name": file_path.name,
                                "size": file_path.stat().st_size,
                                "modified": mtime.isoformat()
                            }
                            # Simplified: treat all as modified
                            modified.append(file_info)

            data_dir = self._get_data_dir()
            data_file = data_dir / f"files-delta-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            delta = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "since": since,
                "source": self.source_id,
                "added": added,
                "modified": modified,
                "deleted": []
            }

            with open(data_file, 'w') as f:
                json.dump(delta, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(added) + len(modified)
            result.metadata["since"] = since

        except Exception as e:
            result.errors.append(str(e))

        return result


class GitConnector(BaseConnector):
    """Connector for Git repositories."""

    def test_connection(self) -> bool:
        """Test if the repository is accessible."""
        # Would use git commands or API to test
        return bool(self.connection.get("repoUrl"))

    def fetch_full(self) -> FetchResult:
        """Clone or pull the repository."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="full"
        )

        try:
            repo_url = self.connection.get("repoUrl")
            branch = self.connection.get("branch", "main")

            # Placeholder - would use git commands
            result.warnings.append(f"Git clone not implemented - would clone {repo_url}")
            result.success = True

        except Exception as e:
            result.errors.append(str(e))

        return result

    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch commits since timestamp."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="delta"
        )

        try:
            # Placeholder - would use git log
            result.warnings.append("Git delta fetch not implemented")
            result.success = True
            result.metadata["since"] = since

        except Exception as e:
            result.errors.append(str(e))

        return result


class MockJamaConnector(BaseConnector):
    """Connector for mock JAMA data from local JSON files."""

    def test_connection(self) -> bool:
        """Test if mock data directory exists."""
        mock_dir = Path(self.connection.get("mockDataDir", ""))
        return mock_dir.exists()

    def fetch_full(self) -> FetchResult:
        """Fetch all items from mock JSON files."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="full"
        )

        try:
            mock_dir = Path(self.connection.get("mockDataDir", "data/mock-jama"))
            if not mock_dir.is_absolute() and self._project_dir:
                mock_dir = self._project_dir / mock_dir

            # Find the specified chunk file or all files
            chunk_file = self.config.get("extraction", {}).get("chunkFile")
            if chunk_file:
                files = [mock_dir / chunk_file]
            else:
                files = sorted(mock_dir.glob("*.json"))

            all_items = []
            for f in files:
                if f.exists():
                    with open(f, 'r') as fp:
                        data = json.load(fp)
                        all_items.extend(data.get("items", []))
                    logger.info("Loaded %d items from %s", len(data.get("items", [])), f.name)

            # Save combined data to data directory
            data_dir = self._get_data_dir()
            data_file = data_dir / f"mock-jama-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            output_data = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "source": self.source_id,
                "items": all_items
            }

            with open(data_file, 'w') as f:
                json.dump(output_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(all_items)
            logger.info("Fetched %d total items from mock JAMA data", len(all_items))

        except Exception as e:
            logger.error("Mock JAMA fetch failed: %s", e)
            result.errors.append(str(e))

        return result

    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch a specific chunk as delta (for testing incremental)."""
        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="delta"
        )

        try:
            mock_dir = Path(self.connection.get("mockDataDir", "data/mock-jama"))
            if not mock_dir.is_absolute() and self._project_dir:
                mock_dir = self._project_dir / mock_dir

            chunk_file = self.config.get("extraction", {}).get("chunkFile")
            if not chunk_file:
                result.errors.append("No chunkFile specified for delta fetch")
                return result

            file_path = mock_dir / chunk_file
            if not file_path.exists():
                result.errors.append(f"Chunk file not found: {chunk_file}")
                return result

            with open(file_path, 'r') as fp:
                data = json.load(fp)

            data_dir = self._get_data_dir()
            data_file = data_dir / f"mock-jama-delta-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            output_data = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "since": since,
                "source": self.source_id,
                "added": data.get("items", []),
                "modified": [],
                "deleted": []
            }

            with open(data_file, 'w') as f:
                json.dump(output_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(data.get("items", []))
            result.metadata["since"] = since
            result.metadata["chunk"] = chunk_file
            logger.info("Fetched %d items from chunk %s", result.item_count, chunk_file)

        except Exception as e:
            logger.error("Mock JAMA delta fetch failed: %s", e)
            result.errors.append(str(e))

        return result


class SystemVerilogConnector(BaseConnector):
    """Connector for SystemVerilog/Verilog source files.

    Uses the SystemVerilog extractor to parse .sv/.v files and extract
    structural information (modules, interfaces, packages, classes).
    """

    def test_connection(self) -> bool:
        """Test if the source path exists."""
        base_path = Path(self.connection.get("basePath", ""))
        return base_path.exists()

    def fetch_full(self) -> FetchResult:
        """Extract all SystemVerilog entities from the source."""
        from bam.extractors import SystemVerilogExtractor

        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="full"
        )

        try:
            base_path = Path(self.connection.get("basePath", ""))
            recursive = self.config.get("extraction", {}).get("recursive", True)
            exclude_patterns = self.config.get("extraction", {}).get("exclude", [])

            # Create extractor and run extraction
            extractor = SystemVerilogExtractor(
                source_id=self.source_id,
                project_dir=str(self._project_dir) if self._project_dir else None
            )

            extraction_result = extractor.extract_directory(
                directory=base_path,
                recursive=recursive,
                exclude_patterns=exclude_patterns
            )

            if not extraction_result.success:
                result.errors.extend(extraction_result.errors)
                return result

            # Convert to BAM format and save
            bam_data = extractor.to_bam_format(extraction_result)

            data_dir = self._get_data_dir()
            data_file = data_dir / f"systemverilog-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            with open(data_file, 'w') as f:
                json.dump(bam_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = extraction_result.item_count
            result.warnings.extend(extraction_result.warnings)
            result.metadata["file_count"] = extraction_result.file_count
            result.metadata["relationship_count"] = len(extraction_result.relationships)

            logger.info(
                "Extracted %d items from %d files in %s",
                result.item_count, extraction_result.file_count, base_path
            )

        except Exception as e:
            logger.error("SystemVerilog extraction failed: %s", e)
            result.errors.append(str(e))

        return result

    def fetch_delta(self, since: str) -> FetchResult:
        """Fetch SystemVerilog files modified since timestamp."""
        from bam.extractors import SystemVerilogExtractor

        result = FetchResult(
            success=False,
            source_id=self.source_id,
            fetch_type="delta"
        )

        try:
            base_path = Path(self.connection.get("basePath", ""))
            recursive = self.config.get("extraction", {}).get("recursive", True)
            exclude_patterns = self.config.get("extraction", {}).get("exclude", [])
            since_dt = datetime.fromisoformat(since)

            # Find modified files
            extractor = SystemVerilogExtractor(
                source_id=self.source_id,
                project_dir=str(self._project_dir) if self._project_dir else None
            )

            modified_items = []
            modified_relationships = []
            files_processed = 0

            for ext in extractor.FILE_EXTENSIONS:
                pattern = f"**/*.{ext}" if recursive else f"*.{ext}"
                for file_path in base_path.glob(pattern):
                    if any(file_path.match(p) for p in exclude_patterns):
                        continue

                    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if mtime > since_dt:
                        file_result = extractor.extract_file(file_path)
                        if file_result.get("items"):
                            modified_items.extend(file_result["items"])
                        if file_result.get("relationships"):
                            modified_relationships.extend(file_result["relationships"])
                        files_processed += 1

            data_dir = self._get_data_dir()
            data_file = data_dir / f"systemverilog-delta-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"

            delta_data = {
                "fetchedAt": datetime.utcnow().isoformat(),
                "since": since,
                "source": self.source_id,
                "extractor": "systemverilog",
                "added": modified_items,  # Treat all as modified for now
                "modified": [],
                "deleted": [],
                "relationships": modified_relationships
            }

            with open(data_file, 'w') as f:
                json.dump(delta_data, f, indent=2)

            result.success = True
            result.data_path = str(data_file)
            result.item_count = len(modified_items)
            result.metadata["since"] = since
            result.metadata["file_count"] = files_processed

            logger.info("Fetched %d modified items from %d files", len(modified_items), files_processed)

        except Exception as e:
            logger.error("SystemVerilog delta fetch failed: %s", e)
            result.errors.append(str(e))

        return result


class ConnectorFactory:
    """Factory for creating source connectors."""

    _connector_types = {
        "jama": JAMAConnector,
        "mock-jama": MockJamaConnector,
        "filesystem": FilesystemConnector,
        "design": FilesystemConnector,
        "git": GitConnector,
        "codebase": GitConnector,
        "systemverilog": SystemVerilogConnector,
        "sv": SystemVerilogConnector,
        "rtl": SystemVerilogConnector,
    }

    @classmethod
    def create(cls, source_config: dict, project_dir: str = None) -> BaseConnector:
        """Create a connector for the given source configuration."""
        source_type = source_config.get("type", "")
        connection_type = source_config.get("connection", {}).get("type", "")

        # Try source type first, then connection type
        connector_class = cls._connector_types.get(source_type)
        if not connector_class:
            connector_class = cls._connector_types.get(connection_type)

        if not connector_class:
            raise ValueError(f"Unknown source type: {source_type}/{connection_type}")

        return connector_class(source_config, project_dir=project_dir)

    @classmethod
    def get_connector_for_source(cls, source_id: str,
                                  project_dir: str) -> BaseConnector:
        """Get a connector for a source by ID.

        Args:
            source_id: Source ID to look up.
            project_dir: Project directory containing sources.json.
        """
        sources_path = Path(project_dir) / "sources.json"

        with open(sources_path, 'r') as f:
            sources = json.load(f)

        source_config = sources.get("sources", {}).get(source_id)
        if not source_config:
            raise ValueError(f"Source not found: {source_id}")

        # Ensure source_config has an "id" field (sources.json uses the key)
        if "id" not in source_config:
            source_config["id"] = source_id
        # Ensure connection dict exists (some sources may not have one)
        source_config.setdefault("connection", {})

        return cls.create(source_config, project_dir=project_dir)


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="BAM Source Connector")
    parser.add_argument("--project", "-p", required=True, help="Project directory")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Test command
    test_parser = subparsers.add_parser("test", help="Test source connection")
    test_parser.add_argument("source_id", help="Source ID")

    # Fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch from source")
    fetch_parser.add_argument("source_id", help="Source ID")
    fetch_parser.add_argument("--delta", "-d", help="Fetch delta since timestamp")

    # List command
    subparsers.add_parser("list", help="List configured sources")

    args = parser.parse_args()
    project_dir = args.project

    if args.command == "test":
        connector = ConnectorFactory.get_connector_for_source(args.source_id, project_dir)
        if connector.test_connection():
            print(f"Connection OK: {args.source_id}")
        else:
            print(f"Connection FAILED: {args.source_id}")

    elif args.command == "fetch":
        connector = ConnectorFactory.get_connector_for_source(args.source_id, project_dir)
        if args.delta:
            result = connector.fetch_delta(args.delta)
        else:
            result = connector.fetch_full()

        print(f"Fetch {'succeeded' if result.success else 'failed'}")
        print(f"  Items: {result.item_count}")
        if result.data_path:
            print(f"  Data: {result.data_path}")
        if result.errors:
            print(f"  Errors: {result.errors}")
        if result.warnings:
            print(f"  Warnings: {result.warnings}")

    elif args.command == "list":
        sources_path = Path(project_dir) / "sources.json"
        with open(sources_path, 'r') as f:
            sources = json.load(f)

        print("Configured sources:")
        for source_id, config in sources.get("sources", {}).items():
            enabled = "enabled" if config.get("enabled") else "disabled"
            print(f"  {source_id}: {config['name']} ({config['type']}) [{enabled}]")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
