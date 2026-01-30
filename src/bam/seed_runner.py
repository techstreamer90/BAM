"""
BAM Seed Runner

Automates the mechanical setup of a new BAM project based on a project
profile produced by the seed interview process. Handles prerequisite
checks, recommendation generation, and project setup execution.
"""

import json
import logging
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bam.seed_runner")

from ._paths import SEED_DIR

SEED_VERSION = "1.0.0"

_README_TEMPLATE_PATH = SEED_DIR / "templates" / "project_readme.md"


def generate_project_readme(
    project_name: str = "BAM Project",
    sketch_template: str = "minimal",
    backend: str = "json",
    created_at: str = "",
) -> str:
    """Render the project-level README.md from the template.

    This produces a self-contained guide that lets an agent (or human)
    work with the project without needing the BAM repository docs.
    """
    if _README_TEMPLATE_PATH.exists():
        template = _README_TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = (
            "# {project_name} — BAM Project\n\n"
            "Template: `{sketch_template}` | Backend: `{backend}`\n\n"
            "Run `python -m bam --project . info` for project details.\n"
        )

    return template.replace("{project_name}", project_name) \
                    .replace("{sketch_template}", sketch_template) \
                    .replace("{backend}", backend) \
                    .replace("{created_at}", created_at or "unknown")


class SeedRunner:
    """Execute BAM project setup from a project profile."""

    def __init__(self, profile: dict):
        self.profile = profile
        self.project_dir = Path(profile["projectDir"])
        self.rules = self._load_json(SEED_DIR / "profiles" / "recommendation_rules.json")
        self.backend_matrix = self._load_json(SEED_DIR / "profiles" / "backend_decision_matrix.json")
        self.prereq_checks = self._load_json(SEED_DIR / "checklists" / "prerequisite_checks.json")

    def check_prerequisites(self, backend: str = "json") -> dict:
        """
        Run system prerequisite checks.

        Args:
            backend: The target backend (determines conditional checks).

        Returns:
            {passed: bool, results: [{id, name, status, message}]}
        """
        results = []

        # Run base checks
        for check in self.prereq_checks["checks"]:
            result = self._run_check(check)
            results.append(result)

        # Run conditional checks for the selected backend
        conditional = self.prereq_checks.get("conditionalChecks", {})
        for check in conditional.get(backend, []):
            result = self._run_check(check)
            results.append(result)

        passed = all(
            r["status"] == "pass" or not r.get("required", True)
            for r in results
        )

        return {"passed": passed, "results": results}

    def generate_recommendations(self) -> dict:
        """
        Generate setup recommendations based on the profile.

        Returns:
            {template, backend, pipeline, parsers[], colorOverrides{}, rationale{}}
        """
        profile = self.profile
        complexity = profile.get("complexity", {})
        constraints = profile.get("constraints", {})
        domain = profile.get("domain", "other")
        sub_domain = profile.get("subDomain", "")
        timeline = constraints.get("timeline", "normal")
        node_count = complexity.get("estimatedNodeCount", 0)
        has_crossrefs = complexity.get("hasCrossReferences", False)
        has_trace = complexity.get("hasTraceability", False)

        # Template selection
        template, template_rationale = self._select_template(
            domain, sub_domain, timeline
        )

        # Backend selection
        backend, backend_rationale = self._select_backend(
            node_count, has_crossrefs, has_trace
        )

        # Override with preference if set
        preferred = constraints.get("preferredBackend", "")
        if preferred:
            if preferred != backend:
                backend_rationale = (
                    f"User preference: {preferred} "
                    f"(recommendation was {backend}: {backend_rationale})"
                )
                backend = preferred
            else:
                backend_rationale += " (matches user preference)"

        # Pipeline selection (always standard for new projects)
        pipeline = "standard"
        pipeline_rationale = "New project uses standard (full) pipeline"

        # Parser selection
        parsers, parser_rationale = self._select_parsers(
            profile.get("dataSources", [])
        )

        return {
            "template": template,
            "backend": backend,
            "pipeline": pipeline,
            "parsers": parsers,
            "colorOverrides": {},
            "rationale": {
                "template": template_rationale,
                "backend": backend_rationale,
                "pipeline": pipeline_rationale,
                "parsers": parser_rationale,
            },
        }

    def execute_setup(self, setup_plan: dict = None, dry_run: bool = False) -> dict:
        """
        Execute the full project setup.

        Args:
            setup_plan: Recommendations dict (from generate_recommendations).
                        If None, generates fresh recommendations.
            dry_run: If True, report what would be done without doing it.

        Returns:
            Setup report dict.
        """
        if setup_plan is None:
            setup_plan = self.generate_recommendations()

        steps = []
        now = datetime.now(timezone.utc).isoformat()

        if dry_run:
            steps.append(self._dry_step(
                "init_project",
                f"Would create project at {self.project_dir} "
                f"with template={setup_plan['template']} "
                f"(includes profile.json and sources.json)"
            ))
            if setup_plan["backend"] != "json":
                steps.append(self._dry_step(
                    "configure_backend",
                    f"Would configure {setup_plan['backend']} backend"
                ))
            steps.append(self._dry_step(
                "create_ingestion_steps",
                f"Would create ingestion plan steps from data sources"
            ))
            steps.append(self._dry_step(
                "instantiate_checklist",
                f"Would copy {setup_plan['template']} checklist"
            ))
            steps.append(self._dry_step(
                "write_status_md",
                "Would write status.md"
            ))
            steps.append(self._dry_step(
                "write_readme_md",
                "Would write README.md (project-level agent guide)"
            ))
            steps.append(self._dry_step(
                "write_setup_report",
                "Would write setup_report.json"
            ))
        else:
            # Step 1: Initialize project (also writes profile.json and
            # sources.json when a profile is provided)
            steps.append(self._exec_init_project(setup_plan))

            # Step 4: Configure backend (if non-json)
            if setup_plan["backend"] != "json":
                steps.append(self._exec_configure_backend(setup_plan["backend"]))

            # Step 5: Create ingestion plan steps
            steps.append(self._exec_create_ingestion_steps())

            # Step 6: Instantiate checklist
            steps.append(self._exec_instantiate_checklist(setup_plan["template"]))

            # Step 7: Write status.md
            steps.append(self._exec_write_status_md(setup_plan))

            # Step 8: Write README.md (project-level agent guide)
            steps.append(self._exec_write_readme_md(setup_plan))

            # Step 9: Write setup report (done below)

        report = {
            "seedVersion": SEED_VERSION,
            "executedAt": now,
            "dryRun": dry_run,
            "profileRef": str(self.project_dir / "profile.json"),
            "recommendations": setup_plan,
            "steps": steps,
            "nextActions": [
                "Review checklist.json and complete manual items",
                "Design the sketch (docs/agent_guide.md Phase 2)",
                "Refine the ingestion plan (docs/agent_guide.md Phase 3)",
                "Execute ingestion (docs/agent_guide.md Phase 4)",
            ],
        }

        if not dry_run:
            # Write the report as the final step
            report_path = self.project_dir / "setup_report.json"
            self._write_json(report_path, report)
            steps.append({
                "name": "write_setup_report",
                "status": "done",
                "detail": f"Wrote {report_path}",
            })

        return report

    # ── Template selection ──────────────────────────────────────────

    def _select_template(self, domain: str, sub_domain: str,
                         timeline: str) -> tuple:
        hw_hints = {"asic", "fpga", "soc", "mixed-signal", "analog", "rtl",
                     "hardware", "chip", "silicon"}
        sw_hints = {"web-service", "microservice", "application", "library",
                     "api", "software", "frontend", "backend", "embedded-sw"}

        if domain == "hardware":
            return "hardware_product", "Hardware domain maps to hardware_product template"
        if domain == "software":
            return "software_product", "Software domain maps to software_product template"
        if domain == "mixed":
            lower_sub = sub_domain.lower()
            if any(h in lower_sub for h in hw_hints):
                return "hardware_product", "Mixed project with hardware emphasis"
            if any(s in lower_sub for s in sw_hints):
                return "software_product", "Mixed project with software emphasis"
            return "hardware_product", "Mixed project defaults to hardware_product"
        # domain == "other"
        if timeline == "quick":
            return "minimal", "Quick timeline with unknown domain uses minimal template"
        return "software_product", "Unknown domain defaults to software_product"

    # ── Backend selection ───────────────────────────────────────────

    def _select_backend(self, node_count: int, has_crossrefs: bool,
                        has_trace: bool) -> tuple:
        if node_count < 1000:
            return "json", f"Under 1K nodes ({node_count}) — JSON is sufficient"
        if node_count < 10000:
            if has_crossrefs:
                return "sqlite", (
                    f"{node_count} nodes with cross-references — "
                    "SQLite indexing helps"
                )
            return "json", f"{node_count} nodes without heavy cross-refs — JSON works"
        if node_count < 100000:
            return "sqlite", f"{node_count} nodes — SQLite for query performance"
        # 100K+
        if has_crossrefs and has_trace:
            return "neo4j", (
                f"{node_count} nodes with cross-refs and traceability — "
                "Neo4j graph queries excel"
            )
        return "sqlite", f"{node_count} nodes — SQLite handles this scale"

    # ── Parser selection ────────────────────────────────────────────

    def _select_parsers(self, data_sources: list) -> tuple:
        parser_rules = self.rules.get("parserRules", [])
        selected = []
        matched_types = []

        for source in data_sources:
            src_type = source.get("type", "").lower()
            src_format = source.get("format", "").lower()

            for rule in parser_rules:
                if (src_type in rule.get("sourceTypes", []) or
                        src_format in rule.get("formats", [])):
                    parser = rule["parser"]
                    if parser not in selected:
                        selected.append(parser)
                        matched_types.append(src_type)
                    break

        if not selected:
            rationale = "No parsers matched the data source types"
        else:
            rationale = f"Matched parsers for source types: {', '.join(matched_types)}"

        return selected, rationale

    # ── Execution helpers ───────────────────────────────────────────

    def _exec_init_project(self, plan: dict) -> dict:
        try:
            from .project import init_project
            init_project(
                project_dir=str(self.project_dir),
                name=self.profile.get("projectName"),
                source_root=self.profile.get("sourceRoot", ""),
                sketch_template=plan["template"],
                profile=self.profile,
            )
            return {
                "name": "init_project",
                "status": "done",
                "detail": f"Created project at {self.project_dir} "
                          f"with template={plan['template']}",
            }
        except Exception as e:
            return {"name": "init_project", "status": "error", "detail": str(e)}

    def _exec_configure_backend(self, backend: str) -> dict:
        try:
            config_path = self.project_dir / "project.json"
            with open(config_path, "r") as f:
                config = json.load(f)

            # Update color_backends to use the selected backend type
            for name, be in config.get("storage", {}).get("color_backends", {}).items():
                be["type"] = backend

            self._write_json(config_path, config)
            return {
                "name": "configure_backend",
                "status": "done",
                "detail": f"Configured all color backends to use {backend}",
            }
        except Exception as e:
            return {"name": "configure_backend", "status": "error", "detail": str(e)}

    def _exec_create_ingestion_steps(self) -> dict:
        try:
            from .ingestion_plan import IngestionPlanManager

            mgr = IngestionPlanManager(str(self.project_dir))
            # Create plan from template
            mgr.create()

            phase_map = self.rules.get("phaseMapping", {})
            backbone_types = phase_map.get("backbone", [])
            enrichment_types = phase_map.get("enrichment", [])
            crossref_types = phase_map.get("cross-references", [])

            step_count = 0
            for ds in self.profile.get("dataSources", []):
                src_type = ds.get("type", "other").lower()

                if src_type in backbone_types:
                    phase = "backbone"
                elif src_type in crossref_types:
                    phase = "cross-references"
                elif src_type in enrichment_types:
                    phase = "enrichment"
                else:
                    phase = "enrichment"

                mgr.add_step(
                    phase_id=phase,
                    name=f"Ingest {ds['name']}",
                    description=f"Parse {ds.get('format', '')} files from {ds.get('location', '')}",
                    source=ds.get("name", "").lower().replace(" ", "_"),
                    agent_tier="standard",
                )
                step_count += 1

            return {
                "name": "create_ingestion_steps",
                "status": "done",
                "detail": f"Created ingestion plan with {step_count} step(s)",
            }
        except Exception as e:
            return {"name": "create_ingestion_steps", "status": "error", "detail": str(e)}

    def _exec_instantiate_checklist(self, template: str) -> dict:
        try:
            # Map template to checklist file
            checklist_map = {
                "hardware_product": "hardware_checklist.json",
                "software_product": "software_checklist.json",
                "minimal": "minimal_checklist.json",
            }
            checklist_file = checklist_map.get(template, "minimal_checklist.json")
            src = SEED_DIR / "checklists" / checklist_file
            if not src.exists():
                return {
                    "name": "instantiate_checklist",
                    "status": "error",
                    "detail": f"Checklist template not found: {src}",
                }

            with open(src, "r") as f:
                checklist = json.load(f)

            # Mark auto items as done
            for section in checklist.get("sections", []):
                for item in section.get("items", []):
                    if item.get("auto"):
                        item["done"] = True

            dest = self.project_dir / "checklist.json"
            self._write_json(dest, checklist)
            return {
                "name": "instantiate_checklist",
                "status": "done",
                "detail": f"Copied {checklist_file}, marked auto items as done",
            }
        except Exception as e:
            return {"name": "instantiate_checklist", "status": "error", "detail": str(e)}

    def _exec_write_status_md(self, plan: dict) -> dict:
        try:
            md = self._generate_status_md(plan)
            path = self.project_dir / "status.md"
            path.write_text(md, encoding="utf-8")
            return {
                "name": "write_status_md",
                "status": "done",
                "detail": f"Wrote {path}",
            }
        except Exception as e:
            return {"name": "write_status_md", "status": "error", "detail": str(e)}

    def _exec_write_readme_md(self, plan: dict) -> dict:
        try:
            md = generate_project_readme(
                project_name=self.profile.get("projectName", "BAM Project"),
                sketch_template=plan.get("template", "minimal"),
                backend=plan.get("backend", "json"),
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )
            path = self.project_dir / "README.md"
            path.write_text(md, encoding="utf-8")
            return {
                "name": "write_readme_md",
                "status": "done",
                "detail": f"Wrote {path}",
            }
        except Exception as e:
            return {"name": "write_readme_md", "status": "error", "detail": str(e)}

    def _generate_status_md(self, plan: dict) -> str:
        p = self.profile
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        sources = p.get("dataSources", [])
        complexity = p.get("complexity", {})
        rationale = plan.get("rationale", {})

        lines = [
            f"# {p.get('projectName', 'BAM Project')} — Status",
            "",
            f"_Generated by BAM_seed v{SEED_VERSION} on {now}_",
            "",
            "## Project Summary",
            "",
            f"- **Name:** {p.get('projectName', '')}",
            f"- **Domain:** {p.get('domain', '')} ({p.get('subDomain', '')})"
            if p.get("subDomain") else
            f"- **Domain:** {p.get('domain', '')}",
            f"- **Description:** {p.get('description', '')}",
            f"- **Source root:** `{p.get('sourceRoot', '')}`",
            f"- **Project directory:** `{p.get('projectDir', '')}`",
            "",
            "## Setup Configuration",
            "",
            f"| Setting | Value | Rationale |",
            f"|---------|-------|-----------|",
            f"| Template | `{plan.get('template', '')}` | {rationale.get('template', '')} |",
            f"| Backend | `{plan.get('backend', '')}` | {rationale.get('backend', '')} |",
            f"| Pipeline | `{plan.get('pipeline', '')}` | {rationale.get('pipeline', '')} |",
            f"| Parsers | {', '.join(f'`{x}`' for x in plan.get('parsers', [])) or '(none)'} | {rationale.get('parsers', '')} |",
            "",
            "## Data Sources",
            "",
            f"| # | Name | Type | Location | Format | Est. Size |",
            f"|---|------|------|----------|--------|-----------|",
        ]

        for i, ds in enumerate(sources, 1):
            lines.append(
                f"| {i} | {ds.get('name', '')} | {ds.get('type', '')} "
                f"| `{ds.get('location', '')}` | {ds.get('format', '')} "
                f"| {ds.get('estimatedSize', '')} |"
            )

        lines.extend([
            "",
            "## Complexity",
            "",
            f"- **Source types:** {complexity.get('sourceTypeCount', 0)}",
            f"- **Estimated nodes:** {complexity.get('estimatedNodeCount', 0):,}",
            f"- **Subsystems:** {complexity.get('subsystemCount', 0)}",
            f"- **Cross-references:** {'Yes' if complexity.get('hasCrossReferences') else 'No'}",
            f"- **Traceability required:** {'Yes' if complexity.get('hasTraceability') else 'No'}",
        ])

        use_cases = p.get("useCases", [])
        if use_cases:
            lines.extend(["", "## Use Cases", ""])
            for uc in use_cases:
                lines.append(f"- {uc}")

        lines.extend([
            "",
            "## Files Created",
            "",
            "| File | Purpose |",
            "|------|---------|",
            "| `project.json` | Project configuration |",
            "| `profile.json` | Interview answers and project profile |",
            "| `sources.json` | Data source definitions |",
            "| `ingestion_plan.json` | Ingestion steps (auto-generated from sources) |",
            "| `checklist.json` | Setup and readiness checklist |",
            "| `setup_report.json` | Machine-readable setup record |",
            "| `README.md` | Project guide for agents and humans |",
            "| `status.md` | This file |",
            f"| `model/sketch.json` | Graph sketch (`{plan.get('template', '')}` template) |",
            "",
            "## Next Steps",
            "",
            "1. **Review the checklist** — Open `checklist.json` and work through unchecked items",
            "2. **Design the sketch** — Follow `docs/agent_guide.md` Phase 2:",
            f"   - Answer the sketch design questions from the `{plan.get('template', '')}` template",
            "   - Define node types, edge types, and hierarchy for your project",
            "   - Edit `model/sketch.json` with agreed-upon structure",
            "3. **Refine the ingestion plan** — Follow `docs/agent_guide.md` Phase 3:",
            "   - Review the auto-generated steps in `ingestion_plan.json`",
            "   - Add detail, adjust batch sizes, set process hints",
            "   - Validate with `python -m bam --project . plan validate`",
            "4. **Execute ingestion** — Follow `docs/agent_guide.md` Phase 4:",
            "   - Run each step: `python -m bam --project . plan next`",
            "   - Verify after each phase: `python -m bam --project . stats`",
            "",
            "## Quick Commands",
            "",
            "```bash",
            f"bam --project \"{p.get('projectDir', '.')}\" info",
            f"bam --project \"{p.get('projectDir', '.')}\" plan show",
            f"bam --project \"{p.get('projectDir', '.')}\" plan validate",
            f"bam --project \"{p.get('projectDir', '.')}\" stats",
            "```",
            "",
        ])

        return "\n".join(lines)

    # ── Check runner ────────────────────────────────────────────────

    def _run_check(self, check: dict) -> dict:
        check_type = check.get("type", "")
        result = {
            "id": check["id"],
            "name": check["name"],
            "required": check.get("required", True),
        }

        if check_type == "command":
            result.update(self._check_command(check))
        elif check_type == "disk_space":
            result.update(self._check_disk_space(check))
        elif check_type == "python_import":
            result.update(self._check_python_import(check))
        elif check_type == "note":
            result["status"] = "info"
            result["message"] = check.get("message_pass", "Manual check required")
        else:
            result["status"] = "skip"
            result["message"] = f"Unknown check type: {check_type}"

        return result

    def _check_command(self, check: dict) -> dict:
        try:
            proc = subprocess.run(
                check["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = proc.stdout.strip()

            if check.get("comparison") == "exists":
                if proc.returncode == 0:
                    return {"status": "pass", "message": check["message_pass"]}
                return {"status": "fail", "message": check["message_fail"]}

            if check.get("comparison") == "version_gte":
                # Extract version numbers from output
                import re
                match = re.search(r"(\d+\.\d+)", output)
                if match:
                    found = match.group(1)
                    expected = check.get("expect", "0.0")
                    found_parts = [int(x) for x in found.split(".")]
                    expected_parts = [int(x) for x in expected.split(".")]
                    if found_parts >= expected_parts:
                        return {
                            "status": "pass",
                            "message": f"{check['message_pass']} (found {found})",
                        }
                    return {
                        "status": "fail",
                        "message": f"{check['message_fail']} (found {found})",
                    }
                return {
                    "status": "fail",
                    "message": f"Could not parse version from: {output}",
                }

            # Default: just check exit code
            if proc.returncode == 0:
                return {"status": "pass", "message": check["message_pass"]}
            return {"status": "fail", "message": check["message_fail"]}

        except subprocess.TimeoutExpired:
            return {"status": "fail", "message": f"Command timed out: {check['command']}"}
        except Exception as e:
            return {"status": "fail", "message": f"Error running check: {e}"}

    def _check_disk_space(self, check: dict) -> dict:
        try:
            min_mb = check.get("min_mb", 100)
            usage = shutil.disk_usage(str(self.project_dir.parent))
            free_mb = usage.free / (1024 * 1024)
            if free_mb >= min_mb:
                return {
                    "status": "pass",
                    "message": f"{check['message_pass']} ({free_mb:.0f} MB free)",
                }
            return {
                "status": "fail",
                "message": f"{check['message_fail']} ({free_mb:.0f} MB free)",
            }
        except Exception as e:
            return {"status": "fail", "message": f"Could not check disk space: {e}"}

    def _check_python_import(self, check: dict) -> dict:
        try:
            __import__(check["module"])
            return {"status": "pass", "message": check["message_pass"]}
        except ImportError:
            return {"status": "fail", "message": check["message_fail"]}

    # ── Utilities ───────────────────────────────────────────────────

    @staticmethod
    def _load_json(path: Path) -> dict:
        with open(path, "r") as f:
            return json.load(f)

    @staticmethod
    def _write_json(path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    @staticmethod
    def _dry_step(name: str, detail: str) -> dict:
        return {"name": name, "status": "dry_run", "detail": detail}
