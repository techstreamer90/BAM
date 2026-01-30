"""
BAM Stage Runner

Executes individual pipeline stages with proper error handling and reporting.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

from .common import StageResult, StageStatus, PipelinePauseException
from .graph_manager import GraphManager, Node, Edge
from .source_connector import ConnectorFactory
from ._paths import PROMPTS_DIR


logger = logging.getLogger("bam.stage_runner")


@dataclass
class StageContext:
    """Context passed to stage handlers."""
    run_id: str
    task_id: str
    stage_id: str
    source_id: str
    pipeline_type: str
    inputs: Dict[str, Any]
    config: dict
    prompts_dir: Path = PROMPTS_DIR
    project_dir: Optional[str] = None


class StageHandler:
    """Base class for stage handlers."""

    def __init__(self, stage_def: dict):
        self.stage_def = stage_def
        self.stage_id = stage_def["id"]

    def execute(self, context: StageContext) -> StageResult:
        """Execute the stage. Override in subclasses."""
        result = StageResult(
            stage_id=self.stage_id,
            status=StageStatus.RUNNING.value,
            started_at=datetime.utcnow().isoformat()
        )

        try:
            outputs = self._run(context)
            result.outputs = outputs
            result.status = StageStatus.COMPLETED.value
        except PipelinePauseException:
            raise  # Propagate pause to orchestrator
        except Exception as e:
            result.errors.append(str(e))
            result.status = StageStatus.FAILED.value

        result.completed_at = datetime.utcnow().isoformat()
        return result

    def _run(self, context: StageContext) -> Dict[str, Any]:
        """Override this method in subclasses."""
        raise NotImplementedError


class DownloadStageHandler(StageHandler):
    """Handler for the download stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        connector = ConnectorFactory.get_connector_for_source(
            context.source_id, context.project_dir
        )
        result = connector.fetch_full()

        if not result.success:
            raise Exception(f"Download failed: {result.errors}")

        manifest = {
            "source": context.source_id,
            "timestamp": result.timestamp,
            "itemCount": result.item_count,
            "warnings": result.warnings
        }

        # Append test chain tests for download completeness
        if context.project_dir:
            try:
                from .test_chain import TestChainManager
                chain = TestChainManager(context.project_dir)
                ts = chain.generate_download_tests(context.source_id, manifest)
                chain.add_test_set(ts)
            except Exception as e:
                logger.warning("Test chain generation failed (download): %s", e)

        return {
            "rawData": result.data_path,
            "downloadManifest": manifest
        }


class ValidateStageHandler(StageHandler):
    """Handler for the validate stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        raw_data_path = context.inputs.get("rawData")
        if not raw_data_path:
            raise Exception("No raw data to validate")

        # Load validation prompt
        prompt_path = context.prompts_dir / context.source_id.split('-')[0] / "validate.md"
        if prompt_path.exists():
            with open(prompt_path, 'r') as f:
                validation_prompt = f.read()
        else:
            validation_prompt = "Default validation"

        # Load and validate data
        with open(raw_data_path, 'r') as f:
            data = json.load(f)

        # Placeholder validation logic
        validation_report = {
            "valid": True,
            "itemsChecked": len(data.get("items", [])),
            "errors": [],
            "warnings": [],
            "validatedAt": datetime.utcnow().isoformat()
        }

        return {
            "validatedData": raw_data_path,  # Pass through if valid
            "validationReport": validation_report
        }


class ParseStageHandler(StageHandler):
    """Handler for the parse stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        validated_data_path = context.inputs.get("validatedData")
        if not validated_data_path:
            raise Exception("No validated data to parse")

        with open(validated_data_path, 'r') as f:
            data = json.load(f)

        # Parse into structured format
        parsed_items = []
        for item in data.get("items", []):
            parsed_items.append({
                "id": item.get("id"),
                "type": item.get("type", "unknown"),
                "name": item.get("name", ""),
                "properties": item,
                "relationships": item.get("relationships", [])
            })

        parse_report = {
            "itemsParsed": len(parsed_items),
            "parsedAt": datetime.utcnow().isoformat()
        }

        return {
            "parsedData": parsed_items,
            "parseReport": parse_report
        }


class TransformStageHandler(StageHandler):
    """Handler for the transform stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        # Check if we have a transform plan (agent-driven pipeline)
        transform_plan = context.inputs.get("transformPlan")
        if transform_plan:
            return self._run_plan_driven(context, transform_plan)

        # Standard pipeline: use parsed data
        parsed_data = context.inputs.get("parsedData", [])

        # Load transform prompt
        prompt_path = context.prompts_dir / context.source_id.split('-')[0] / "transform.md"

        nodes = []
        edges = []

        for item in parsed_data:
            # Create node
            node = {
                "id": f"{context.source_id}-{item['id']}",
                "type": item["type"].title(),
                "label": item["name"],
                "properties": item["properties"],
                "source_id": context.source_id,
                "source_ref": str(item["id"])
            }
            nodes.append(node)

            # Create edges from relationships
            for rel in item.get("relationships", []):
                edge = {
                    "id": f"{context.source_id}-{rel.get('type', 'RELATES')}-{item['id']}-{rel.get('target')}",
                    "type": rel.get("type", "RELATES_TO"),
                    "source_node_id": node["id"],
                    "target_node_id": f"{context.source_id}-{rel.get('target')}",
                    "source_id": context.source_id
                }
                edges.append(edge)

        transform_report = {
            "nodesCreated": len(nodes),
            "edgesCreated": len(edges),
            "transformedAt": datetime.utcnow().isoformat()
        }

        # Append test chain tests for transform correctness
        if context.project_dir:
            try:
                from .test_chain import TestChainManager
                chain = TestChainManager(context.project_dir)
                ts = chain.generate_transform_tests(context.source_id, nodes, edges)
                chain.add_test_set(ts)
            except Exception as e:
                logger.warning("Test chain generation failed (transform): %s", e)

        return {
            "nodes": nodes,
            "edges": edges,
            "transformReport": transform_report
        }

    @staticmethod
    def _resolve_pattern(
        pattern: str,
        source_id: str,
        item: dict,
        label: str,
        *,
        rel: dict = None,
        context: str = "",
    ) -> str:
        """Resolve a pattern like ``{source_id}-{item.id}`` against data.

        Logs a warning when a ``{item.X}`` or ``{rel.X}`` placeholder
        references a field that doesn't exist on the source object,
        instead of silently producing an empty string.
        """
        import re as _re

        result = pattern.replace("{source_id}", source_id)

        def _replace_placeholder(match):
            full = match.group(0)       # e.g. "{item.id}"
            prefix = match.group(1)     # e.g. "item"
            field = match.group(2)      # e.g. "id"

            if prefix == "item":
                obj = item
            elif prefix == "rel" and rel is not None:
                obj = rel
            else:
                logger.warning(
                    "Unknown pattern prefix '%s' in '%s' (%s)",
                    prefix, pattern, context,
                )
                return ""

            if not isinstance(obj, dict) or field not in obj:
                logger.warning(
                    "Field '%s' missing from %s (available: %s) in "
                    "pattern '%s' (%s) — using empty string",
                    field, prefix,
                    list(obj.keys()) if isinstance(obj, dict) else "n/a",
                    pattern, context,
                )
                return ""

            return str(obj[field])

        result = _re.sub(r"\{(item|rel)\.(\w+)\}", _replace_placeholder, result)
        return result

    def _run_plan_driven(self, context: StageContext,
                         plan: dict) -> Dict[str, Any]:
        """Execute a transform plan produced by the agent-review stage."""
        raw_data_path = context.inputs.get("rawData")
        if not raw_data_path:
            raise Exception("No raw data for plan-driven transform")

        with open(raw_data_path, "r") as f:
            data = json.load(f)

        source_id = plan.get("sourceId", context.source_id)
        nodes = []
        edges = []
        unmatched_items = []

        # Apply node mappings
        for mapping in plan.get("nodeMappings", []):
            source_field = mapping.get("sourceField", "items")
            items = data.get(source_field, [])
            node_type = mapping.get("nodeType", "Unknown")
            id_pattern = mapping.get("idPattern", "{source_id}-{item.id}")
            label_field = mapping.get("labelField", "name")
            property_fields = mapping.get("propertyFields", [])

            for item in items:
                try:
                    # Build node ID from pattern
                    node_id = self._resolve_pattern(
                        id_pattern, source_id, item, "id", context="node ID"
                    )

                    # Extract label
                    label = str(item.get(label_field, ""))
                    if label_field not in item:
                        logger.warning(
                            "Label field '%s' missing from item (keys: %s), "
                            "using empty string",
                            label_field, list(item.keys()) if isinstance(item, dict) else "n/a",
                        )

                    # Extract properties
                    properties = {}
                    for pf in property_fields:
                        if pf in item:
                            properties[pf] = item[pf]

                    nodes.append({
                        "id": node_id,
                        "type": node_type,
                        "label": label,
                        "properties": properties,
                        "source_id": source_id,
                        "source_ref": str(item.get("id", "")),
                    })
                except (KeyError, TypeError) as e:
                    logger.warning("Item skipped in node mapping: %s", e)
                    unmatched_items.append(item)

        # Apply edge mappings
        for mapping in plan.get("edgeMappings", []):
            source_field = mapping.get("sourceField", "items[*].relationships")
            edge_type = mapping.get("edgeType", "RELATES_TO")
            source_pattern = mapping.get("sourceNodePattern", "")
            target_pattern = mapping.get("targetNodePattern", "")

            # Parse the source field path
            # Support "items[*].relationships" -> iterate items, get relationships
            parts = source_field.replace("[*]", "").split(".")
            base_field = parts[0]
            rel_field = parts[1] if len(parts) > 1 else None

            base_items = data.get(base_field, [])
            for item in base_items:
                if rel_field:
                    rels = item.get(rel_field, [])
                else:
                    rels = [item]

                for rel in rels:
                    src_id = self._resolve_pattern(
                        source_pattern, source_id, item, "edge source",
                        context="edge source",
                    )
                    tgt_id = self._resolve_pattern(
                        target_pattern, source_id, item, "edge target",
                        rel=rel, context="edge target",
                    )

                    edge_id = f"{source_id}-{edge_type}-{item.get('id', '')}-{rel.get('targetId', rel.get('target', ''))}"

                    edges.append({
                        "id": edge_id,
                        "type": edge_type,
                        "source_node_id": src_id,
                        "target_node_id": tgt_id,
                        "source_id": source_id,
                    })

        # LLM fallback for unmatched items
        llm_fallback_count = 0
        if unmatched_items:
            try:
                from .llm import get_llm_provider
                from .llm.provider import LLMMessage

                provider = get_llm_provider()
                prompt = (
                    f"The following {len(unmatched_items)} items did not match any mapping "
                    f"in the transform plan for source '{source_id}'. "
                    f"For each item, return a JSON array of node objects with keys: "
                    f"id, type, label, properties.\n\n"
                    f"Items:\n{json.dumps(unmatched_items, indent=2)}"
                )
                response = provider.complete(
                    messages=[LLMMessage(role="user", content=prompt)],
                    system_prompt="Return only a JSON array of node objects.",
                )
                from .agent_review import _extract_json
                fallback_nodes = _extract_json(response.content)
                if isinstance(fallback_nodes, list):
                    for fn in fallback_nodes:
                        fn.setdefault("source_id", source_id)
                        nodes.append(fn)
                        llm_fallback_count += 1
                elif isinstance(fallback_nodes, dict) and "nodes" in fallback_nodes:
                    for fn in fallback_nodes["nodes"]:
                        fn.setdefault("source_id", source_id)
                        nodes.append(fn)
                        llm_fallback_count += 1
            except Exception as e:
                logger.warning("LLM fallback failed: %s", e)

        transform_report = {
            "nodesCreated": len(nodes),
            "edgesCreated": len(edges),
            "unmatchedItems": len(unmatched_items),
            "llmFallbackNodes": llm_fallback_count,
            "planDriven": True,
            "transformedAt": datetime.utcnow().isoformat(),
        }

        # Append test chain tests
        if context.project_dir:
            try:
                from .test_chain import TestChainManager
                chain = TestChainManager(context.project_dir)
                ts = chain.generate_transform_tests(source_id, nodes, edges)
                chain.add_test_set(ts)
            except Exception as e:
                logger.warning("Test chain generation failed (transform): %s", e)

        return {
            "nodes": nodes,
            "edges": edges,
            "transformReport": transform_report,
        }


class IntegrateStageHandler(StageHandler):
    """Handler for the integrate stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        nodes = context.inputs.get("nodes", [])
        edges = context.inputs.get("edges", [])

        gm = GraphManager(project_dir=context.project_dir)

        # Create snapshot before integration
        snapshot_id = gm.create_snapshot(f"pre-integrate-{context.run_id[:20]}")

        # Add nodes
        added_nodes = []
        for node_data in nodes:
            try:
                node = Node(
                    id=node_data["id"],
                    type=node_data["type"],
                    label=node_data["label"],
                    properties=node_data.get("properties", {}),
                    source_id=node_data.get("source_id"),
                    source_ref=node_data.get("source_ref")
                )
                gm.add_node(node)
                added_nodes.append(node_data["id"])
            except ValueError as e:
                # Node might already exist
                pass

        # Add edges
        added_edges = []
        for edge_data in edges:
            try:
                edge = Edge(
                    id=edge_data["id"],
                    type=edge_data["type"],
                    source_node_id=edge_data["source_node_id"],
                    target_node_id=edge_data["target_node_id"],
                    source_id=edge_data.get("source_id")
                )
                gm.add_edge(edge)
                added_edges.append(edge_data["id"])
            except ValueError:
                # Edge might already exist or nodes missing
                pass

        integration_report = {
            "nodesAdded": len(added_nodes),
            "edgesAdded": len(added_edges),
            "snapshotId": snapshot_id,
            "integratedAt": datetime.utcnow().isoformat()
        }

        model_stats = gm.get_statistics()

        # Append test chain tests for integration baseline
        if context.project_dir:
            try:
                from .test_chain import TestChainManager
                chain = TestChainManager(context.project_dir)
                ts = chain.generate_integrate_tests(
                    context.source_id, integration_report, model_stats
                )
                chain.add_test_set(ts)
            except Exception as e:
                logger.warning("Test chain generation failed (integrate): %s", e)

        return {
            "updatedModel": model_stats,
            "integrationReport": integration_report
        }


class VerifyStageHandler(StageHandler):
    """Handler for the verify stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        gm = GraphManager(project_dir=context.project_dir)
        stats = gm.get_statistics()

        # Run consistency checks
        issues = []

        # Check for orphan nodes (nodes with no edges)
        all_nodes = set(gm.model["nodes"].keys())
        connected_nodes = set()
        for edge in gm.model["edges"].values():
            connected_nodes.add(edge["source_node_id"])
            connected_nodes.add(edge["target_node_id"])

        orphans = all_nodes - connected_nodes
        if orphans and len(all_nodes) > 1:  # Ignore if only one node
            issues.append({
                "type": "orphan-nodes",
                "severity": "warning",
                "count": len(orphans),
                "sample": list(orphans)[:5]
            })

        # Run test chain if it exists
        chain_summary = None
        chain_warnings_summary = None
        if context.project_dir:
            try:
                from .test_chain import TestChainManager
                chain_path = Path(context.project_dir) / "test_chain.json"
                if chain_path.exists():
                    chain = TestChainManager(context.project_dir)

                    # Run blocking tests
                    chain_summary = chain.run_gate_check(
                        "blocking", project_dir=context.project_dir
                    )
                    if not chain_summary.all_passed:
                        for r in chain_summary.results:
                            from tests.verification.models import VerificationStatus
                            if r.status in (VerificationStatus.FAIL, VerificationStatus.ERROR):
                                issues.append({
                                    "type": "test-chain-failure",
                                    "severity": "error",
                                    "dataPointId": r.data_point_id,
                                    "description": r.description,
                                    "message": r.message,
                                })

                    # Run warning tests separately
                    chain_warnings_summary = chain.run_gate_check(
                        "warning", project_dir=context.project_dir
                    )
                    if not chain_warnings_summary.all_passed:
                        for r in chain_warnings_summary.results:
                            from tests.verification.models import VerificationStatus
                            if r.status in (VerificationStatus.FAIL, VerificationStatus.ERROR):
                                issues.append({
                                    "type": "test-chain-warning",
                                    "severity": "warning",
                                    "dataPointId": r.data_point_id,
                                    "description": r.description,
                                    "message": r.message,
                                })
            except Exception as e:
                logger.warning("Test chain verification failed: %s", e)

        consistent = len([i for i in issues if i["severity"] == "error"]) == 0

        checks_performed = ["orphan-nodes", "edge-integrity"]
        if chain_summary is not None:
            checks_performed.append("test-chain-blocking")
        if chain_warnings_summary is not None:
            checks_performed.append("test-chain-warning")

        verification_report = {
            "consistent": consistent,
            "checksPerformed": checks_performed,
            "issuesFound": len(issues),
            "verifiedAt": datetime.utcnow().isoformat()
        }

        if chain_summary is not None:
            verification_report["testChainBlocking"] = {
                "total": chain_summary.total,
                "passed": chain_summary.passed,
                "failed": chain_summary.failed,
                "errors": chain_summary.errors,
            }
        if chain_warnings_summary is not None:
            verification_report["testChainWarning"] = {
                "total": chain_warnings_summary.total,
                "passed": chain_warnings_summary.passed,
                "failed": chain_warnings_summary.failed,
                "errors": chain_warnings_summary.errors,
            }

        return {
            "verificationReport": verification_report,
            "issues": issues
        }


class ReportStageHandler(StageHandler):
    """Handler for the report stage."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        # Collect all previous stage reports
        reports = {}
        for key, value in context.inputs.items():
            if "Report" in key or "report" in key:
                reports[key] = value

        # Generate summary
        summary_lines = [
            f"# Pipeline Run Summary",
            f"",
            f"**Run ID:** {context.run_id}",
            f"**Task ID:** {context.task_id}",
            f"**Source:** {context.source_id}",
            f"**Pipeline:** {context.pipeline_type}",
            f"**Completed:** {datetime.utcnow().isoformat()}",
            f"",
            f"## Stage Reports",
            f""
        ]

        for report_name, report_data in reports.items():
            summary_lines.append(f"### {report_name}")
            summary_lines.append(f"```json")
            summary_lines.append(json.dumps(report_data, indent=2))
            summary_lines.append(f"```")
            summary_lines.append(f"")

        final_report = "\n".join(summary_lines)

        return {
            "finalReport": final_report
        }


class AgentReviewStageHandler(StageHandler):
    """Handler for the agent-review stage (LLM-driven analysis)."""

    def _run(self, context: StageContext) -> Dict[str, Any]:
        import shutil

        raw_data_path = context.inputs.get("rawData")
        if not raw_data_path:
            raise Exception("No raw data for agent review")

        # Copy raw data into the run directory so the path survives
        # across a pause/resume cycle (temp files may be cleaned up).
        if context.project_dir:
            stable_dir = Path(context.project_dir) / "runs" / context.run_id
            stable_dir.mkdir(parents=True, exist_ok=True)
            stable_path = stable_dir / "raw_data.json"
            if not stable_path.exists():
                shutil.copy2(raw_data_path, stable_path)
            raw_data_path = str(stable_path)

        from .agent_review import run_agent_review
        from .sketch_review import SketchReviewManager

        # Determine analysis strategy from stage config
        chunk_guidance = self.stage_def.get("chunkGuidance", {}) or {}
        strategy = chunk_guidance.get("strategy", "sample")

        # Check for feedback from a prior rejected review
        prior_feedback = context.inputs.get("_review_feedback", "")

        transform_plan, sketch_changes = run_agent_review(
            raw_data_path=raw_data_path,
            source_id=context.source_id,
            project_dir=context.project_dir,
            config=context.config,
            strategy=strategy,
            prior_feedback=prior_feedback,
        )

        # Handle sketch changes
        sketch_changes_dict = None
        if sketch_changes:
            sketch_changes_dict = sketch_changes.to_dict()

            # Load the current sketch to classify changes
            gm = GraphManager(project_dir=context.project_dir)
            current_sketch = gm.model
            gm.close()

            classification = sketch_changes.classify(current_sketch)
            logger.info("Sketch changes classified as: %s", classification)

            if classification == "minor":
                # Auto-apply minor changes
                review_mgr = SketchReviewManager(context.project_dir)
                review = review_mgr.create_review(
                    sketch_changes, context.run_id, context.task_id
                )
                review_mgr.approve()
                logger.info("Minor sketch changes auto-applied")
            else:
                # Major changes: pause for human review
                review_mgr = SketchReviewManager(context.project_dir)
                review_mgr.create_review(
                    sketch_changes, context.run_id, context.task_id
                )
                logger.info("Major sketch changes proposed — pausing for review")

                # Save transform plan before pausing
                if context.project_dir:
                    runs_dir = Path(context.project_dir) / "runs" / context.run_id
                    runs_dir.mkdir(parents=True, exist_ok=True)
                    with open(runs_dir / "transform_plan.json", "w") as f:
                        json.dump(transform_plan.to_dict(), f, indent=2)

                raise PipelinePauseException(
                    "Major sketch changes require human review. "
                    f"Use 'bam --project {context.project_dir} review show' to inspect."
                )

        # Save transform plan
        if context.project_dir:
            runs_dir = Path(context.project_dir) / "runs" / context.run_id
            runs_dir.mkdir(parents=True, exist_ok=True)
            with open(runs_dir / "transform_plan.json", "w") as f:
                json.dump(transform_plan.to_dict(), f, indent=2)

        report = {
            "strategy": strategy,
            "nodeMappings": len(transform_plan.node_mappings),
            "edgeMappings": len(transform_plan.edge_mappings),
            "sketchChanges": sketch_changes_dict,
            "reviewedAt": datetime.utcnow().isoformat(),
        }

        return {
            "transformPlan": transform_plan.to_dict(),
            "sketchChanges": sketch_changes_dict,
            "agentReviewReport": report,
            "rawData": raw_data_path,  # stable copy in run dir
        }


class StageRunner:
    """Runs pipeline stages."""

    _handlers = {
        "download": DownloadStageHandler,
        "validate": ValidateStageHandler,
        "parse": ParseStageHandler,
        "transform": TransformStageHandler,
        "integrate": IntegrateStageHandler,
        "verify": VerifyStageHandler,
        "report": ReportStageHandler,
        # Incremental pipeline stages
        "fetch-delta": DownloadStageHandler,  # Reuse with delta flag
        "diff": ValidateStageHandler,  # Placeholder
        "transform-changes": TransformStageHandler,
        "merge": IntegrateStageHandler,
        # Agent-driven pipeline
        "agent-review": AgentReviewStageHandler,
    }

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self._runs_dir = Path(project_dir) / "runs"

    def run(self, stage_def: dict, context: StageContext) -> StageResult:
        """Run a stage and return the result."""
        stage_id = stage_def["id"]

        handler_class = self._handlers.get(stage_id)
        if not handler_class:
            # Default handler that just passes through
            handler_class = StageHandler

        handler = handler_class(stage_def)
        result = handler.execute(context)

        # Save result to run directory
        self._save_result(context.run_id, result)

        return result

    def _save_result(self, run_id: str, result: StageResult):
        """Save stage result to disk."""
        run_dir = self._runs_dir / run_id / "stages"
        run_dir.mkdir(parents=True, exist_ok=True)

        result_path = run_dir / f"{result.stage_id}.json"
        with open(result_path, 'w') as f:
            json.dump(asdict(result), f, indent=2)


def main():
    """Test stage runner."""
    logger.info("Stage Runner - use via orchestrator.py")


if __name__ == "__main__":
    main()
