"""
BAM Backend Factory

Creates and configures the ModelManager, SketchManager, and ColorBackends.

All project data lives outside BAM. Every function that touches data
requires an explicit `project_dir` — the project model directory
containing project.json, model/, etc.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .base import ColorBackend
from .sketch import SketchManager


load_dotenv()  # auto-discovers .env in current or parent directories


class BackendNotAvailableError(Exception):
    pass


class BackendNotFoundError(Exception):
    pass


def load_config(project_dir: str) -> dict:
    """Load project.json from a project directory."""
    project_path = Path(project_dir) / "project.json"
    with open(project_path, 'r') as f:
        return json.load(f)


def get_color_backend(backend_name: str, config: dict = None) -> ColorBackend:
    """Get a color backend instance by name."""
    config = config or {}

    if backend_name == "json":
        from .json_color_backend import JsonColorBackend
        return JsonColorBackend(config)
    elif backend_name == "sqlite":
        from .sqlite_color_backend import SqliteColorBackend
        return SqliteColorBackend(config)
    elif backend_name == "neo4j":
        try:
            from .neo4j_color_backend import Neo4jColorBackend
            return Neo4jColorBackend(config)
        except ImportError:
            raise BackendNotAvailableError(
                "Neo4j backend requires 'neo4j' package. Install with: pip install neo4j"
            )
    elif backend_name == "arango":
        try:
            from .arango_color_backend import ArangoColorBackend
            return ArangoColorBackend(config)
        except ImportError:
            raise BackendNotAvailableError(
                "ArangoDB backend requires 'python-arango' package. Install with: pip install python-arango"
            )
    else:
        raise BackendNotFoundError(f"Unknown backend: {backend_name}")


def get_model_manager(project_dir: str, config: dict = None):
    """
    Get a configured ModelManager for a project.

    Args:
        project_dir: Path to the project model directory (required).
        config: Optional override config. Loaded from project.json if omitted.
    """
    if config is None:
        config = load_config(project_dir)

    base_path = Path(project_dir)

    from .model_manager import ModelManager
    return ModelManager(config, base_path=base_path)


def get_sketch_manager(project_dir: str, config: dict = None) -> SketchManager:
    """Get a SketchManager for a project."""
    if config is None:
        config = load_config(project_dir)

    sketch_path = config.get("storage", {}).get("sketch", {}).get(
        "path", "model/sketch.json"
    )
    sketch_path = _resolve_path(sketch_path, Path(project_dir))
    return SketchManager(Path(sketch_path))


def _resolve_path(path: str, base: Path) -> str:
    """Resolve a relative path to absolute using given base."""
    if os.path.isabs(path):
        return path
    return str(base / path)


def list_available_backends() -> dict:
    """List all color backends and their availability."""
    backends = {
        "json": {"available": True, "description": "JSON file storage (zero dependencies)"},
        "sqlite": {"available": True, "description": "SQLite database (built-in Python)"},
        "neo4j": {"available": False, "description": "Neo4j graph database", "install": "pip install neo4j"},
        "arango": {"available": False, "description": "ArangoDB multi-model database", "install": "pip install python-arango"},
    }
    try:
        import neo4j
        backends["neo4j"]["available"] = True
    except ImportError:
        pass
    try:
        import arango
        backends["arango"]["available"] = True
    except ImportError:
        pass
    return backends
