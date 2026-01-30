"""
BAM Ingestion Plan Manager

Manages the per-project ingestion plan: creation from template, step
management, status tracking, validation, and display.

The ingestion plan is a JSON file (ingestion_plan.json) in the project
directory that tracks what to ingest, in what order, and the status of
each step.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.ingestion_plan")

from ._paths import INGESTION_PLAN_TEMPLATE


class IngestionPlanManager:
    """Manage an ingestion plan for a BAM project."""

    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.plan_path = self.project_dir / "ingestion_plan.json"

    def create(self) -> dict:
        """
        Create a new ingestion plan from the template.

        Returns:
            The created plan dict.

        Raises:
            FileExistsError: If a plan already exists (use load instead).
        """
        if self.plan_path.exists():
            with open(self.plan_path, 'r') as f:
                existing = json.load(f)
            if existing.get("status") not in (None, "empty"):
                raise FileExistsError(
                    f"Ingestion plan already exists: {self.plan_path}\n"
                    "Use 'plan show' to view it or delete it to start over."
                )

        template_path = INGESTION_PLAN_TEMPLATE
        with open(template_path, 'r') as f:
            template = json.load(f)

        now = datetime.now(timezone.utc).isoformat()
        plan = {
            "version": template["version"],
            "createdAt": now,
            "lastModified": now,
            "status": "draft",
            "phases": template["phases"],
            "globalHints": template["globalHints"],
            "nextStepId": 1
        }

        self._save(plan)
        logger.info("Created ingestion plan at %s", self.plan_path)
        return plan

    def load(self) -> dict:
        """
        Load the existing ingestion plan.

        Raises:
            FileNotFoundError: If no plan exists.
        """
        if not self.plan_path.exists():
            raise FileNotFoundError(
                f"No ingestion plan found at {self.plan_path}\n"
                "Use 'plan create' to create one."
            )
        with open(self.plan_path, 'r') as f:
            return json.load(f)

    def add_step(self, phase_id: str, name: str, description: str = "",
                 source: str = "", agent_tier: str = "standard",
                 max_batch_size: int = 100, group_by: str = "",
                 process_hints: List[str] = None,
                 pre_checks: List[str] = None,
                 post_checks: List[str] = None) -> dict:
        """
        Add a step to a phase in the ingestion plan.

        Args:
            phase_id: Which phase to add the step to (backbone, enrichment,
                      cross-references, validation).
            name: Human-readable step name.
            description: What this step does.
            source: Source identifier.
            agent_tier: low/standard/high.
            max_batch_size: Maximum items per batch.
            group_by: How to group items within a batch.
            process_hints: Advisory hints for this step.
            pre_checks: Checks to run before the step.
            post_checks: Checks to run after the step.

        Returns:
            The created step dict.
        """
        plan = self.load()

        # Find the target phase
        phase = None
        for p in plan["phases"]:
            if p["id"] == phase_id:
                phase = p
                break

        if phase is None:
            valid = [p["id"] for p in plan["phases"]]
            raise ValueError(
                f"Unknown phase '{phase_id}'. Valid phases: {', '.join(valid)}"
            )

        step_id = str(plan["nextStepId"])
        plan["nextStepId"] += 1

        step = {
            "id": step_id,
            "name": name,
            "description": description,
            "source": source,
            "status": "pending",
            "agentTier": agent_tier,
            "chunkStrategy": {
                "maxBatchSize": max_batch_size,
                "groupBy": group_by
            },
            "processHints": process_hints or [],
            "preChecks": pre_checks or [],
            "postChecks": post_checks or [],
            "result": None
        }

        phase["steps"].append(step)
        plan["lastModified"] = datetime.now(timezone.utc).isoformat()
        self._save(plan)

        logger.info("Added step '%s' (id=%s) to phase '%s'",
                     name, step_id, phase_id)
        return step

    def complete_step(self, step_id: str, result: str = None) -> dict:
        """
        Mark a step as completed.

        Args:
            step_id: The step ID to complete.
            result: Optional result summary.

        Returns:
            The updated step dict.
        """
        plan = self.load()
        step = self._find_step(plan, step_id)

        if step["status"] == "completed":
            raise ValueError(f"Step '{step_id}' is already completed")

        step["status"] = "completed"
        step["result"] = result or "completed"
        step["completedAt"] = datetime.now(timezone.utc).isoformat()

        plan["lastModified"] = datetime.now(timezone.utc).isoformat()

        # Update plan status if all steps done
        all_done = all(
            s["status"] == "completed"
            for phase in plan["phases"]
            for s in phase["steps"]
        )
        total_steps = sum(len(p["steps"]) for p in plan["phases"])
        if all_done and total_steps > 0:
            plan["status"] = "completed"

        self._save(plan)
        logger.info("Completed step '%s'", step_id)
        return step

    def next_step(self) -> Optional[dict]:
        """
        Get the next pending step in plan order.

        Returns:
            The next pending step dict, or None if all steps are done.
        """
        plan = self.load()

        for phase in sorted(plan["phases"], key=lambda p: p["order"]):
            for step in phase["steps"]:
                if step["status"] == "pending":
                    return {
                        "phase": phase["id"],
                        "phaseName": phase["name"],
                        "step": step
                    }

        return None

    def validate(self) -> dict:
        """
        Validate the ingestion plan for completeness and ordering.

        Returns:
            A validation report dict with 'valid', 'warnings', 'errors'.
        """
        plan = self.load()
        errors = []
        warnings = []

        # Check that at least the backbone phase has steps
        backbone = None
        for phase in plan["phases"]:
            if phase["id"] == "backbone":
                backbone = phase
                break

        if backbone and len(backbone["steps"]) == 0:
            warnings.append(
                "Backbone phase has no steps. Most projects need backbone "
                "ingestion before other phases."
            )

        # Check that all phases are in order
        total_steps = 0
        for phase in plan["phases"]:
            total_steps += len(phase["steps"])
            for step in phase["steps"]:
                # Validate agent tier
                if step.get("agentTier") not in ("low", "standard", "high"):
                    errors.append(
                        f"Step '{step['name']}' has invalid agentTier: "
                        f"'{step.get('agentTier')}'. Must be low/standard/high."
                    )
                # Warn on missing description
                if not step.get("description"):
                    warnings.append(
                        f"Step '{step['name']}' has no description."
                    )

        if total_steps == 0:
            errors.append(
                "Plan has no steps. Add steps with 'plan add-step'."
            )

        # Check cross-references phase doesn't have steps without
        # backbone steps existing
        cross_ref = None
        for phase in plan["phases"]:
            if phase["id"] == "cross-references":
                cross_ref = phase
                break
        if cross_ref and len(cross_ref["steps"]) > 0:
            if backbone and len(backbone["steps"]) == 0:
                warnings.append(
                    "Cross-references phase has steps but backbone phase is "
                    "empty. Cross-references need both endpoints to exist first."
                )

        valid = len(errors) == 0
        return {
            "valid": valid,
            "totalSteps": total_steps,
            "errors": errors,
            "warnings": warnings
        }

    def show(self) -> str:
        """
        Generate a human-readable summary of the plan.

        Returns:
            Formatted string summary.
        """
        plan = self.load()
        lines = []
        lines.append(f"Ingestion Plan — Status: {plan['status']}")
        lines.append(f"Created: {plan['createdAt']}")
        lines.append(f"Modified: {plan['lastModified']}")
        lines.append("")

        total = 0
        completed = 0
        for phase in sorted(plan["phases"], key=lambda p: p["order"]):
            phase_steps = phase["steps"]
            phase_done = sum(1 for s in phase_steps if s["status"] == "completed")
            total += len(phase_steps)
            completed += phase_done

            status_str = (
                f"({phase_done}/{len(phase_steps)} done)"
                if phase_steps else "(no steps)"
            )
            lines.append(f"Phase {phase['order']}: {phase['name']} {status_str}")

            for step in phase_steps:
                icon = "[x]" if step["status"] == "completed" else "[ ]"
                tier = step.get("agentTier", "?")
                lines.append(
                    f"  {icon} {step['id']}. {step['name']} "
                    f"(tier={tier}, source={step.get('source', '-')})"
                )

            lines.append("")

        lines.append(f"Progress: {completed}/{total} steps completed")

        if plan.get("globalHints"):
            lines.append("")
            lines.append("Global Hints:")
            for hint in plan["globalHints"]:
                lines.append(f"  - {hint}")

        return "\n".join(lines)

    def _find_step(self, plan: dict, step_id: str) -> dict:
        """Find a step by ID across all phases."""
        for phase in plan["phases"]:
            for step in phase["steps"]:
                if step["id"] == step_id:
                    return step
        raise ValueError(f"Step '{step_id}' not found in plan")

    def _save(self, plan: dict):
        """Write plan to disk."""
        self.plan_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.plan_path, 'w') as f:
            json.dump(plan, f, indent=2)
            f.write('\n')
