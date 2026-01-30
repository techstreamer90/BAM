"""
BAM Agent Review Module

LLM-driven analysis of incoming data to produce a TransformPlan
and optional SketchChangeProposal for the agent-driven pipeline.
"""

import json
import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bam.agent_review")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TransformPlan:
    """Plan describing how source data maps to graph nodes and edges."""
    source_id: str
    node_mappings: List[dict] = field(default_factory=list)
    edge_mappings: List[dict] = field(default_factory=list)
    filters: List[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "sourceId": self.source_id,
            "nodeMappings": self.node_mappings,
            "edgeMappings": self.edge_mappings,
            "filters": self.filters,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TransformPlan":
        return cls(
            source_id=d.get("sourceId", ""),
            node_mappings=d.get("nodeMappings", []),
            edge_mappings=d.get("edgeMappings", []),
            filters=d.get("filters", []),
            metadata=d.get("metadata", {}),
        )


@dataclass
class SketchChangeProposal:
    """Proposed changes to the graph sketch (node/edge types)."""
    new_nodes: List[dict] = field(default_factory=list)
    new_edges: List[dict] = field(default_factory=list)
    type_changes: List[dict] = field(default_factory=list)
    rationale: str = ""

    def classify(self, current_sketch: dict) -> str:
        """Classify the proposal as 'minor' or 'major'.

        Minor: all new nodes use existing node types, no type changes,
               no new edge types.
        Major: any new node type, any type change, or any new edge type.
        """
        existing_node_types = set()
        for node in current_sketch.get("nodes", {}).values():
            existing_node_types.add(node.get("type", ""))

        existing_edge_types = set()
        for edge in current_sketch.get("edges", {}).values():
            existing_edge_types.add(edge.get("type", ""))

        if self.type_changes:
            return "major"

        for node in self.new_nodes:
            if node.get("type", "") not in existing_node_types:
                return "major"

        for edge in self.new_edges:
            if edge.get("type", "") not in existing_edge_types:
                return "major"

        return "minor"

    def to_dict(self) -> dict:
        return {
            "newNodes": self.new_nodes,
            "newEdges": self.new_edges,
            "typeChanges": self.type_changes,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SketchChangeProposal":
        return cls(
            new_nodes=d.get("newNodes", []),
            new_edges=d.get("newEdges", []),
            type_changes=d.get("typeChanges", []),
            rationale=d.get("rationale", ""),
        )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

AGENT_REVIEW_SYSTEM_PROMPT = """\
You are BAM's data review agent. You analyse incoming data and decide how it \
maps to an existing graph model (the "sketch").

You will receive:
1. A summary of the current sketch (node types, edge types, counts, colors).
2. A sample (or full dump) of the raw source data.

Return a single JSON object with two top-level keys:

{
  "transformPlan": {
    "sourceId": "<source-id>",
    "nodeMappings": [
      {
        "sourceField": "<path to array in source data, e.g. 'items'>",
        "nodeType": "<PascalCase node type>",
        "idPattern": "<deterministic ID pattern, e.g. '{source_id}-{item.id}'>",
        "labelField": "<field name used as label>",
        "propertyFields": ["<field1>", "<field2>"]
      }
    ],
    "edgeMappings": [
      {
        "sourceField": "<path to relationships, e.g. 'items[*].relationships'>",
        "edgeType": "<SCREAMING_SNAKE_CASE edge type>",
        "sourceNodePattern": "<ID pattern for source node>",
        "targetNodePattern": "<ID pattern for target node>"
      }
    ],
    "filters": [],
    "metadata": {}
  },
  "sketchChanges": null
}

If the data requires node types or edge types that do not exist in the current \
sketch, populate "sketchChanges" instead of null:

{
  "sketchChanges": {
    "newNodes": [{"type": "...", "description": "..."}],
    "newEdges": [{"type": "...", "description": "..."}],
    "typeChanges": [],
    "rationale": "..."
  }
}

Rules:
- IDs MUST be deterministic: use patterns like {source_id}-{item.id}
- Prefer existing node/edge types from the sketch
- Edge types must be SCREAMING_SNAKE_CASE
- Only propose sketch changes when strictly necessary
- Return valid JSON only — no markdown, no explanation outside the JSON
"""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def build_sketch_summary(project_dir: str) -> str:
    """Build a text summary of the current sketch for the LLM prompt."""
    from .graph_manager import GraphManager

    gm = GraphManager(project_dir=project_dir)
    stats = gm.get_statistics()
    gm.close()

    lines = [
        "=== Current Sketch Summary ===",
        f"Total nodes: {stats['totalNodes']}",
        f"Total edges: {stats['totalEdges']}",
    ]

    if stats.get("nodesByType"):
        lines.append("Node types:")
        for ntype, count in sorted(stats["nodesByType"].items()):
            lines.append(f"  {ntype}: {count}")

    if stats.get("edgesByType"):
        lines.append("Edge types:")
        for etype, count in sorted(stats["edgesByType"].items()):
            lines.append(f"  {etype}: {count}")

    if stats.get("colors"):
        lines.append(f"Colors: {', '.join(stats['colors'])}")

    return "\n".join(lines)


def build_data_sample(raw_data_path: str, strategy: str = "sample") -> str:
    """Build a text representation of the source data for the LLM prompt.

    Handles multiple data formats:
    - JSON object with any top-level keys (each key with a list value
      is treated as an item collection)
    - JSON array at the root
    - Non-JSON files (returns a raw text preview)

    Strategies:
        sample: first 5 + last 5 items per collection, schema inference
        full: all data
    """
    raw_text = Path(raw_data_path).read_text(encoding="utf-8", errors="replace")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        # Not JSON — return a raw preview
        preview = raw_text[:2000]
        total_lines = raw_text.count("\n") + 1
        return (
            "=== Source Data (non-JSON) ===\n"
            f"File: {raw_data_path}\n"
            f"Total lines: {total_lines}\n"
            f"Preview (first 2000 chars):\n{preview}"
        )

    # Determine the item collections to sample
    if isinstance(data, list):
        collections = {"(root)": data}
    elif isinstance(data, dict):
        # Collect every top-level key whose value is a list
        collections = {}
        for key, value in data.items():
            if isinstance(value, list):
                collections[key] = value
        # If no list values found, treat the whole object as a single item
        if not collections:
            collections = {"(root)": [data]}
    else:
        collections = {"(root)": [data]}

    lines = ["=== Source Data ==="]

    for coll_name, items in collections.items():
        total = len(items)

        if strategy == "full" or total <= 10:
            sample_items = items
        else:
            sample_items = items[:5] + items[-5:]

        # Infer schema from first item
        schema = {}
        if items and isinstance(items[0], dict):
            for key, value in items[0].items():
                schema[key] = type(value).__name__

        lines.append(f"\nCollection: {coll_name}")
        lines.append(f"Total items: {total}")
        if schema:
            lines.append(f"Inferred schema: {json.dumps(schema)}")
        lines.append(f"Sample ({len(sample_items)} of {total}):")
        lines.append(json.dumps(sample_items, indent=2))

    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Extract a JSON object from LLM output, handling code fences."""
    # Try stripping markdown code fences
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Fallback: find the first { ... } block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_agent_review(
    raw_data_path: str,
    source_id: str,
    project_dir: str,
    config: dict = None,
    provider=None,
    strategy: str = "sample",
    prior_feedback: str = "",
) -> Tuple[TransformPlan, Optional[SketchChangeProposal]]:
    """Run the LLM agent review on raw source data.

    Args:
        raw_data_path: Path to the downloaded raw data JSON.
        source_id: Source identifier.
        project_dir: Path to the BAM project directory.
        config: Optional project config.
        provider: Optional pre-configured LLMProvider instance.
        strategy: "sample" (default) or "full".
        prior_feedback: Feedback from a rejected sketch review. When
            provided, this is included in the LLM prompt so the agent
            can adjust its proposal accordingly.

    Returns:
        Tuple of (TransformPlan, optional SketchChangeProposal).
    """
    if provider is None:
        from .llm import get_llm_provider
        provider = get_llm_provider()

    # Build context for the LLM
    sketch_summary = build_sketch_summary(project_dir)
    data_sample = build_data_sample(raw_data_path, strategy=strategy)

    user_content = (
        f"Source ID: {source_id}\n\n"
        f"{sketch_summary}\n\n"
        f"{data_sample}"
    )

    if prior_feedback:
        user_content += (
            f"\n\n=== Prior Review Feedback ===\n"
            f"A previous attempt was rejected by the human reviewer with "
            f"this feedback:\n{prior_feedback}\n\n"
            f"Please adjust your transform plan and sketch change proposal "
            f"to address this feedback."
        )

    from .llm.provider import LLMMessage

    messages = [LLMMessage(role="user", content=user_content)]

    logger.info("Sending agent review request to LLM (strategy=%s)", strategy)
    response = provider.complete(
        messages=messages,
        system_prompt=AGENT_REVIEW_SYSTEM_PROMPT,
    )
    logger.info("LLM response received (model=%s, tokens=%s)",
                response.model, response.usage)

    # Parse the response
    result = _extract_json(response.content)

    # Build TransformPlan
    plan_data = result.get("transformPlan", {})
    plan_data.setdefault("sourceId", source_id)
    plan_data.setdefault("metadata", {})
    plan_data["metadata"]["strategy"] = strategy
    plan_data["metadata"]["llmModel"] = response.model
    plan_data["metadata"]["reviewedAt"] = datetime.utcnow().isoformat()

    transform_plan = TransformPlan.from_dict(plan_data)

    # Build SketchChangeProposal if present
    sketch_changes = None
    changes_data = result.get("sketchChanges")
    if changes_data:
        sketch_changes = SketchChangeProposal.from_dict(changes_data)

    return transform_plan, sketch_changes
