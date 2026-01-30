"""
BAM Color Manager

Manages colors and their backend mappings. Colors are logical groupings
of node data by perspective (conceptual, design, verification, cv).

Each color can have multiple backends, and each backend can serve multiple colors.
The color a node belongs to is determined by its type.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .base import NodeColor, EdgeColor, ColorBackend
from .json_color_backend import JsonColorBackend
from .sqlite_color_backend import SqliteColorBackend


logger = logging.getLogger("bam.color_manager")


@dataclass
class ColorConfig:
    """Configuration for a single color."""
    name: str
    description: str
    node_types: Set[str]


@dataclass
class BackendConfig:
    """Configuration for a color backend."""
    name: str
    backend_type: str
    colors: List[str]
    path: str
    snapshots_dir: str
    description: str = ""


class ColorManager:
    """
    Manages color layer storage.

    Responsibilities:
    - Map node types to colors
    - Map colors to backends
    - Route color storage/retrieval to appropriate backends
    - Merge results from multiple backends
    """

    def __init__(self, config: dict, base_path: Path):
        """
        Initialize ColorManager from config.

        Args:
            config: Full config dict (with storage.colors and storage.color_backends)
            base_path: Base path for resolving relative paths (the project directory)
        """
        self.base_path = base_path
        self.colors: Dict[str, ColorConfig] = {}
        self.backends: Dict[str, ColorBackend] = {}
        self.backend_configs: Dict[str, BackendConfig] = {}
        self.type_to_colors: Dict[str, Set[str]] = {}
        self.color_to_backends: Dict[str, List[str]] = {}

        self._load_config(config)

    def _load_config(self, config: dict):
        """Load colors and backends from config."""
        storage = config.get("storage", {})

        # Load color definitions
        colors_config = storage.get("colors", {})
        for name, fc in colors_config.items():
            self.colors[name] = ColorConfig(
                name=name,
                description=fc.get("description", ""),
                node_types=set(fc.get("node_types", []))
            )

            # Build type -> colors mapping
            for node_type in fc.get("node_types", []):
                if node_type not in self.type_to_colors:
                    self.type_to_colors[node_type] = set()
                self.type_to_colors[node_type].add(name)

        # Load backend configurations
        backends_config = storage.get("color_backends", {})
        for name, bc in backends_config.items():
            self.backend_configs[name] = BackendConfig(
                name=name,
                backend_type=bc.get("type", "json"),
                colors=bc.get("colors", []),
                path=bc.get("path", ""),
                snapshots_dir=bc.get("snapshotsDir", ""),
                description=bc.get("description", "")
            )

            # Build color -> backends mapping
            for color in bc.get("colors", []):
                if color not in self.color_to_backends:
                    self.color_to_backends[color] = []
                self.color_to_backends[color].append(name)

        logger.info("Loaded %d colors, %d backend configs",
                   len(self.colors), len(self.backend_configs))

    def connect(self):
        """Initialize and connect all backends."""
        for name, bc in self.backend_configs.items():
            backend = self._create_backend(bc)
            if backend:
                backend.connect()
                self.backends[name] = backend
                logger.debug("Connected backend: %s (%s)", name, bc.backend_type)

    def _create_backend(self, bc: BackendConfig) -> Optional[ColorBackend]:
        """Create a backend instance from config."""
        path = Path(bc.path)
        if not path.is_absolute():
            path = self.base_path / bc.path

        snapshots_dir = Path(bc.snapshots_dir)
        if not snapshots_dir.is_absolute():
            snapshots_dir = self.base_path / bc.snapshots_dir

        # Ensure directories exist
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        if bc.backend_type == "json":
            return JsonColorBackend({
                "colorPath": str(path),
                "snapshotsDir": str(snapshots_dir)
            })
        elif bc.backend_type == "sqlite":
            return SqliteColorBackend({
                "dbPath": str(path),
                "snapshotsDir": str(snapshots_dir)
            })
        else:
            logger.warning("Unknown backend type: %s", bc.backend_type)
            return None

    def close(self):
        """Close all backends."""
        for name, backend in self.backends.items():
            backend.close()
        self.backends.clear()

    def get_colors_for_type(self, node_type: str) -> Set[str]:
        """Get colors that a node type belongs to."""
        return self.type_to_colors.get(node_type, set())

    def get_backends_for_color(self, color: str) -> List[str]:
        """Get backend names that serve a color."""
        return self.color_to_backends.get(color, [])

    def get_backends_for_type(self, node_type: str) -> List[str]:
        """Get all backend names that could store color for a node type."""
        backends = set()
        for color in self.get_colors_for_type(node_type):
            backends.update(self.get_backends_for_color(color))
        return list(backends)

    def get_write_backend(self, node_type: str, preferred_color: str = None) -> Optional[str]:
        """
        Get the backend to write color for a node type.

        Uses first color's first backend, or preferred color if specified.
        """
        colors = self.get_colors_for_type(node_type)
        if not colors:
            # Fall back to 'default' backend if no color mapping
            if "default" in self.backends:
                return "default"
            return None

        target_color = preferred_color if preferred_color in colors else next(iter(colors))
        backends = self.get_backends_for_color(target_color)
        return backends[0] if backends else None

    # === Node Color Operations ===

    def store_node_color(self, color: NodeColor, node_type: str,
                         backend_name: str = None) -> bool:
        """
        Store node color in appropriate backend(s).

        Args:
            color: The color data to store
            node_type: Node type (determines color)
            backend_name: Optional specific backend to use
        """
        if backend_name:
            backends = [backend_name] if backend_name in self.backends else []
        else:
            backends = self.get_backends_for_type(node_type)
            if not backends and "default" in self.backends:
                backends = ["default"]

        if not backends:
            logger.warning("No backend for node type %s", node_type)
            return False

        success = True
        for name in backends:
            backend = self.backends.get(name)
            if backend:
                try:
                    backend.store_node_color(color)
                    logger.debug("Stored color for %s in %s", color.id, name)
                except Exception as e:
                    logger.error("Failed to store in %s: %s", name, e)
                    success = False

        return success

    def get_node_color(self, node_id: str, node_type: str = None,
                       color: str = None, backend_name: str = None) -> Optional[NodeColor]:
        """
        Get node color, optionally filtered by color or backend.

        Args:
            node_id: Node ID
            node_type: Node type (helps determine which backends to check)
            color: Optional color to filter by
            backend_name: Optional specific backend to query

        Returns:
            NodeColor if found, None otherwise
        """
        if backend_name:
            backend = self.backends.get(backend_name)
            if backend:
                return backend.get_node_color(node_id)
            return None

        # Determine which backends to check
        if color:
            backends = self.get_backends_for_color(color)
        elif node_type:
            backends = self.get_backends_for_type(node_type)
        else:
            backends = list(self.backends.keys())

        # Try each backend until we find the color
        for name in backends:
            backend = self.backends.get(name)
            if backend:
                color = backend.get_node_color(node_id)
                if color:
                    return color

        return None

    def get_node_color_all(self, node_id: str, node_type: str = None) -> Dict[str, NodeColor]:
        """
        Get node color from all backends that have it.

        Returns:
            Dict mapping backend name to color
        """
        result = {}

        if node_type:
            backends = self.get_backends_for_type(node_type)
        else:
            backends = list(self.backends.keys())

        for name in backends:
            backend = self.backends.get(name)
            if backend:
                color = backend.get_node_color(node_id)
                if color:
                    result[name] = color

        return result

    def update_node_color(self, node_id: str, updates: dict,
                          node_type: str = None, backend_name: str = None) -> bool:
        """Update node color in appropriate backend(s)."""
        if backend_name:
            backends = [backend_name] if backend_name in self.backends else []
        elif node_type:
            backends = self.get_backends_for_type(node_type)
        else:
            backends = list(self.backends.keys())

        success = False
        for name in backends:
            backend = self.backends.get(name)
            if backend:
                if backend.update_node_color(node_id, updates):
                    success = True

        return success

    def delete_node_color(self, node_id: str, node_type: str = None) -> bool:
        """Delete node color from all backends."""
        if node_type:
            backends = self.get_backends_for_type(node_type)
        else:
            backends = list(self.backends.keys())

        success = False
        for name in backends:
            backend = self.backends.get(name)
            if backend:
                if backend.delete_node_color(node_id):
                    success = True

        return success

    # === Edge Color Operations ===

    def store_edge_color(self, color: EdgeColor, backend_name: str = None) -> bool:
        """Store edge color. Edges go to default or specified backend."""
        if backend_name and backend_name in self.backends:
            backends = [backend_name]
        elif "default" in self.backends:
            backends = ["default"]
        else:
            backends = list(self.backends.keys())[:1]  # First available

        success = True
        for name in backends:
            backend = self.backends.get(name)
            if backend:
                try:
                    backend.store_edge_color(color)
                except Exception as e:
                    logger.error("Failed to store edge color in %s: %s", name, e)
                    success = False

        return success

    def get_edge_color(self, edge_id: str, backend_name: str = None) -> Optional[EdgeColor]:
        """Get edge color from backends."""
        if backend_name:
            backend = self.backends.get(backend_name)
            if backend:
                return backend.get_edge_color(edge_id)
            return None

        # Try all backends
        for name, backend in self.backends.items():
            color = backend.get_edge_color(edge_id)
            if color:
                return color

        return None

    def delete_edge_color(self, edge_id: str) -> bool:
        """Delete edge color from all backends."""
        success = False
        for backend in self.backends.values():
            if backend.delete_edge_color(edge_id):
                success = True
        return success

    # === Utility Methods ===

    def list_backends(self) -> Dict[str, dict]:
        """List all backends with their colors."""
        result = {}
        for name, bc in self.backend_configs.items():
            result[name] = {
                "type": bc.backend_type,
                "colors": bc.colors,
                "connected": name in self.backends
            }
        return result

    def list_colors(self) -> Dict[str, dict]:
        """List all colors with their node types and backends."""
        result = {}
        for name, fc in self.colors.items():
            result[name] = {
                "description": fc.description,
                "node_types": list(fc.node_types),
                "backends": self.get_backends_for_color(name)
            }
        return result

    def get_stats(self) -> dict:
        """Get statistics about colors and backends."""
        return {
            "color_count": len(self.colors),
            "backend_count": len(self.backends),
            "connected_backends": list(self.backends.keys()),
            "type_mappings": {t: list(f) for t, f in self.type_to_colors.items()}
        }
