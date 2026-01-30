"""
BAM Project Manager

Manages project lifecycle: initialization, loading, listing.
A project is a self-contained directory with its own model, sources,
configuration, and run history. BAM tool code (scripts, pipelines,
prompts) is shared across all projects.

Directory layout for a project:
    <project_dir>/
        project.json        # Project config (storage, colors, sources)
        sources.json        # Source definitions
        tasks.json          # Task queue
        issues.json         # Issue tracker
        human-queue.json    # Human intervention queue
        history.json        # Run history
        model/
            sketch.json
            version.json
            colors/          # Color backends (json, sqlite)
                snapshots/
            sketch_snapshots/
        runs/                # Pipeline run outputs
        data/                # Downloaded source data
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.project")

from ._paths import SKETCH_TEMPLATES_DIR

# Compatibility alias used by some references
TOOL_DIR = SKETCH_TEMPLATES_DIR.parent


# Default storage config for new projects
DEFAULT_STORAGE = {
    "sketch": {
        "path": "model/sketch.json"
    },
    "colors": {
        "conceptual": {
            "description": "Requirements, specifications, conceptual artifacts",
            "node_types": ["Requirement", "Specification", "Feature", "UserStory", "DocSection"]
        },
        "design": {
            "description": "Design artifacts, RTL, schematics",
            "node_types": [
                "Specification", "DesignDocument", "DesignSection",
                "RTLModule", "Configuration", "AnalogBlock",
                "CodeModule", "CodeClass", "CodeFunction"
            ]
        },
        "verification": {
            "description": "Testbenches, assertions, coverage",
            "node_types": ["Testbench", "Assertion", "CoverageGroup", "TestPlan", "TestCase"]
        },
        "cv": {
            "description": "Characterization and validation measurements",
            "node_types": ["Measurement", "TestResult", "CVReport"]
        }
    },
    "color_backends": {
        "conceptual": {
            "type": "json",
            "colors": ["conceptual"],
            "path": "model/colors/conceptual.json",
            "snapshotsDir": "model/colors/snapshots/conceptual",
            "description": "Conceptual artifacts color"
        },
        "design": {
            "type": "json",
            "colors": ["design"],
            "path": "model/colors/design.json",
            "snapshotsDir": "model/colors/snapshots/design",
            "description": "Design artifacts color"
        },
        "verification": {
            "type": "json",
            "colors": ["verification"],
            "path": "model/colors/verification.json",
            "snapshotsDir": "model/colors/snapshots/verification",
            "description": "Verification artifacts color"
        },
        "cv": {
            "type": "json",
            "colors": ["cv"],
            "path": "model/colors/cv.json",
            "snapshotsDir": "model/colors/snapshots/cv",
            "description": "Characterization & validation color"
        },
        "default": {
            "type": "json",
            "colors": [],
            "path": "model/colors/default.json",
            "snapshotsDir": "model/colors/snapshots/default",
            "description": "Fallback backend"
        }
    }
}

EMPTY_SKETCH = {
    "metadata": {
        "created": None,
        "lastModified": None
    },
    "nodes": {},
    "edges": {}
}

EMPTY_LIST = {"version": "1.0.0"}


def get_tool_dir() -> Path:
    """Get the BAM data directory."""
    return TOOL_DIR


def init_project(project_dir: str, name: str = None,
                 source_root: str = None,
                 sketch_template: str = None,
                 profile: dict = None) -> dict:
    """
    Initialize a new BAM project directory.

    Args:
        project_dir: Path to the project model directory.
        name: Human-readable project name.
        source_root: Path to the source code/data being modeled.
        sketch_template: Optional sketch template ID (e.g. 'hardware_product',
                          'software_product', 'minimal'). Loads suggested colors
                          and design questions from the template.
        profile: Optional project profile dict from the seed interview process.
                 If provided, writes profile.json and populates sources.json
                 from profile['dataSources'].

    Returns:
        The project.json dict that was written.
    """
    pdir = Path(project_dir)
    pdir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc).isoformat()

    # Create project.json
    project_config = {
        "name": name or pdir.name,
        "source_root": source_root or "",
        "created_at": now,
        "storage": DEFAULT_STORAGE,
        "orchestrator": {
            "maxConcurrentTasks": 1,
            "defaultTimeout": 300000,
            "retryAttempts": 3,
            "retryDelay": 5000
        },
        "haltPolicy": {
            "onValidationError": "halt",
            "onTransformError": "halt",
            "onIntegrationError": "halt",
            "onConsistencyError": "warn",
            "maxErrorsBeforeHalt": 10
        },
        "feedback": {
            "autoReingestSources": [],
            "autoApproveKinds": ["reingest"],
            "requireReviewKinds": ["correction", "gap", "general"]
        }
    }

    # Load sketch template if specified
    template_data = None
    if sketch_template:
        template_path = SKETCH_TEMPLATES_DIR / f"{sketch_template}.json"
        if not template_path.exists():
            available = [
                p.stem for p in SKETCH_TEMPLATES_DIR.glob("*.json")
            ]
            raise FileNotFoundError(
                f"Sketch template '{sketch_template}' not found. "
                f"Available: {', '.join(available)}"
            )
        with open(template_path, 'r') as f:
            template_data = json.load(f)

        project_config["sketchTemplate"] = sketch_template
        project_config["sketchDesignQuestions"] = template_data.get(
            "sketchDesignQuestions", []
        )

    _write_json(pdir / "project.json", project_config)

    # Create empty state files
    _write_json(pdir / "sources.json", {
        "version": "1.0.0",
        "sources": {}
    })
    _write_json(pdir / "tasks.json", {
        "version": "1.0.0",
        "lastTaskId": 0,
        "tasks": []
    })
    _write_json(pdir / "issues.json", {
        "version": "1.0.0",
        "lastIssueId": 0,
        "issues": []
    })
    _write_json(pdir / "human-queue.json", {
        "version": "1.0.0",
        "items": []
    })
    _write_json(pdir / "history.json", {
        "version": "1.0.0",
        "runs": []
    })

    # Create empty ingestion plan
    _write_json(pdir / "ingestion_plan.json", {
        "version": "1.0.0",
        "createdAt": now,
        "lastModified": now,
        "status": "empty",
        "phases": [],
        "globalHints": [],
        "nextStepId": 1
    })

    # Create sketch (from template example or empty)
    sketch = dict(EMPTY_SKETCH)
    sketch["metadata"]["created"] = now
    sketch["metadata"]["lastModified"] = now
    if template_data and "exampleSketch" in template_data:
        sketch["nodes"] = _convert_template_nodes(
            template_data["exampleSketch"].get("nodes", {})
        )
        sketch["edges"] = _convert_template_edges(
            template_data["exampleSketch"].get("edges", {})
        )

    model_dir = pdir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    _write_json(model_dir / "sketch.json", sketch)
    _write_json(model_dir / "version.json", {
        "current": "1.0.0",
        "snapshotCount": 0,
        "history": []
    })

    # Create color directories
    colors_dir = model_dir / "colors"
    colors_dir.mkdir(exist_ok=True)
    (colors_dir / "snapshots").mkdir(exist_ok=True)
    for backend_name in DEFAULT_STORAGE["color_backends"]:
        (colors_dir / "snapshots" / backend_name).mkdir(exist_ok=True)

    # Create sketch snapshots dir
    (model_dir / "sketch_snapshots").mkdir(exist_ok=True)

    # Create runs and data dirs
    (pdir / "runs").mkdir(exist_ok=True)
    (pdir / "data").mkdir(exist_ok=True)

    # Create test chain and generate sketch tests if template exists
    from .test_chain import TestChainManager
    chain_mgr = TestChainManager.create(str(pdir))
    if template_data:
        sketch_tests = chain_mgr.generate_sketch_tests(template_data)
        chain_mgr.add_test_set(sketch_tests)

    # Write project README (self-contained agent guide)
    try:
        from .seed_runner import generate_project_readme
        readme_text = generate_project_readme(
            project_name=project_config.get("name", pdir.name),
            sketch_template=sketch_template or "minimal",
            backend="json",
            created_at=now[:10],
        )
        (pdir / "README.md").write_text(readme_text, encoding="utf-8")
    except Exception as e:
        logger.warning("Could not write project README.md: %s", e)

    # Write profile and populate sources if a profile was provided
    if profile:
        _write_json(pdir / "profile.json", profile)
        logger.info("Wrote profile.json from seed interview")

        # Populate sources.json from profile dataSources
        data_sources = profile.get("dataSources", [])
        if data_sources:
            sources = {"version": "1.0.0", "sources": {}}
            for ds in data_sources:
                source_id = ds["name"].lower().replace(" ", "_")
                sources["sources"][source_id] = {
                    "name": ds["name"],
                    "type": ds.get("type", ""),
                    "location": ds.get("location", ""),
                    "format": ds.get("format", ""),
                    "estimatedSize": ds.get("estimatedSize", ""),
                }
            _write_json(pdir / "sources.json", sources)
            logger.info("Populated sources.json with %d source(s)",
                        len(data_sources))

    logger.info("Initialized project '%s' at %s", project_config["name"], pdir)
    return project_config


def load_project_config(project_dir: str) -> dict:
    """
    Load project configuration from project.json.

    Args:
        project_dir: Path to the project model directory.

    Returns:
        The project config dict (same format that storage backends expect).

    Raises:
        FileNotFoundError: If project.json doesn't exist.
    """
    pdir = Path(project_dir)
    project_path = pdir / "project.json"
    if not project_path.exists():
        raise FileNotFoundError(
            f"Not a BAM project directory (no project.json): {pdir}"
        )
    with open(project_path, 'r') as f:
        return json.load(f)


def load_project_sources(project_dir: str) -> dict:
    """Load sources.json from a project directory."""
    pdir = Path(project_dir)
    sources_path = pdir / "sources.json"
    if not sources_path.exists():
        return {"version": "1.0.0", "sources": {}}
    with open(sources_path, 'r') as f:
        return json.load(f)


def save_project_sources(project_dir: str, sources: dict):
    """Save sources.json to a project directory."""
    _write_json(Path(project_dir) / "sources.json", sources)


def list_projects(projects_dir: str) -> List[dict]:
    """
    List all BAM projects found under a directory.

    Scans for subdirectories containing project.json.
    """
    projects = []
    pdir = Path(projects_dir)
    if not pdir.exists():
        return projects

    for child in sorted(pdir.iterdir()):
        if child.is_dir() and (child / "project.json").exists():
            try:
                config = load_project_config(str(child))
                projects.append({
                    "path": str(child),
                    "name": config.get("name", child.name),
                    "source_root": config.get("source_root", ""),
                    "created_at": config.get("created_at", ""),
                })
            except Exception as e:
                logger.warning("Failed to load project at %s: %s", child, e)

    return projects


def _convert_template_nodes(raw_nodes: dict) -> dict:
    """Convert template nodes to canonical SketchManager format.

    Template format: {node_id: {type, name, color, ...}}
    Canonical format: {node_id: {id, type, label, source_id}}
    """
    converted = {}
    for node_id, node_data in raw_nodes.items():
        converted[node_id] = {
            "id": node_data.get("id", node_id),
            "type": node_data["type"],
            "label": node_data.get("label") or node_data.get("name", ""),
            "source_id": node_data.get("source_id"),
        }
    return converted


def _convert_template_edges(raw_edges: dict) -> dict:
    """Convert template edges to canonical SketchManager format.

    Template format: {edge_id: {type, source, target, ...}}
    Canonical format: {edge_id: {id, type, source_node_id, target_node_id, source_id}}
    """
    converted = {}
    for edge_id, edge_data in raw_edges.items():
        edge_type = edge_data["type"].upper()
        converted[edge_id] = {
            "id": edge_data.get("id", edge_id),
            "type": edge_type,
            "source_node_id": edge_data.get("source_node_id") or edge_data.get("source", ""),
            "target_node_id": edge_data.get("target_node_id") or edge_data.get("target", ""),
            "source_id": edge_data.get("source_id"),
        }
    return converted


def _write_json(path: Path, data: dict):
    """Write JSON file, creating parent dirs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
