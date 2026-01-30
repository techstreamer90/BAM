"""
Tests for BAM SeedRunner.

Tests prerequisite checking, recommendation generation, and setup execution.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from bam.seed_runner import SeedRunner
from bam._paths import SEED_DIR


def _make_profile(overrides: dict = None) -> dict:
    """Create a minimal valid profile for testing."""
    profile = {
        "projectName": "TestProject",
        "projectDir": "",  # set per test
        "description": "A test project",
        "domain": "hardware",
        "subDomain": "ASIC",
        "sourceRoot": "",
        "dataSources": [
            {
                "name": "RTL Modules",
                "type": "rtl",
                "location": "rtl/",
                "format": "systemverilog",
                "estimatedSize": "50 files",
            }
        ],
        "complexity": {
            "sourceTypeCount": 1,
            "estimatedNodeCount": 500,
            "subsystemCount": 3,
            "hasCrossReferences": False,
            "hasTraceability": False,
        },
        "useCases": ["Understand module hierarchy"],
        "constraints": {
            "existingTools": [],
            "teamSize": "solo",
            "timeline": "normal",
            "preferredBackend": "",
        },
    }
    if overrides:
        profile.update(overrides)
    return profile


class TestCheckPrerequisites(unittest.TestCase):
    """Tests for SeedRunner.check_prerequisites()."""

    def test_basic_checks_structure(self):
        """Prerequisite check returns well-formed results."""
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            result = runner.check_prerequisites(backend="json")
            self.assertIn("passed", result)
            self.assertIn("results", result)
            self.assertIsInstance(result["results"], list)
            self.assertTrue(len(result["results"]) > 0)
            # Each result should have id, name, status
            for r in result["results"]:
                self.assertIn("id", r)
                self.assertIn("name", r)
                self.assertIn("status", r)

    def test_python_check_passes(self):
        """Python version check should pass on this system."""
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            result = runner.check_prerequisites(backend="json")
            python_result = next(
                (r for r in result["results"] if r["id"] == "python-version"),
                None,
            )
            self.assertIsNotNone(python_result)
            self.assertEqual(python_result["status"], "pass")

    def test_neo4j_conditional_checks_included(self):
        """Neo4j backend should include neo4j driver check."""
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            result = runner.check_prerequisites(backend="neo4j")
            ids = [r["id"] for r in result["results"]]
            self.assertIn("neo4j-driver", ids)


class TestGenerateRecommendations(unittest.TestCase):
    """Tests for SeedRunner.generate_recommendations()."""

    def test_hardware_domain_selects_hw_template(self):
        profile = _make_profile({"domain": "hardware"})
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "hardware_product")

    def test_software_domain_selects_sw_template(self):
        profile = _make_profile({"domain": "software"})
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "software_product")

    def test_other_quick_selects_minimal(self):
        profile = _make_profile({
            "domain": "other",
            "constraints": {"timeline": "quick", "preferredBackend": ""},
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "minimal")

    def test_small_project_selects_json_backend(self):
        profile = _make_profile()
        profile["complexity"]["estimatedNodeCount"] = 500
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["backend"], "json")

    def test_large_project_selects_sqlite_backend(self):
        profile = _make_profile()
        profile["complexity"]["estimatedNodeCount"] = 50000
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["backend"], "sqlite")

    def test_very_large_crossref_trace_selects_neo4j(self):
        profile = _make_profile()
        profile["complexity"]["estimatedNodeCount"] = 200000
        profile["complexity"]["hasCrossReferences"] = True
        profile["complexity"]["hasTraceability"] = True
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["backend"], "neo4j")

    def test_preferred_backend_overrides(self):
        profile = _make_profile()
        profile["complexity"]["estimatedNodeCount"] = 500
        profile["constraints"]["preferredBackend"] = "sqlite"
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["backend"], "sqlite")
            self.assertIn("User preference", rec["rationale"]["backend"])

    def test_rtl_source_selects_rtl_parser(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertIn("rtl_parser", rec["parsers"])

    def test_pipeline_is_standard(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["pipeline"], "standard")

    def test_recommendation_has_rationale(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertIn("rationale", rec)
            self.assertIn("template", rec["rationale"])
            self.assertIn("backend", rec["rationale"])
            self.assertIn("pipeline", rec["rationale"])
            self.assertIn("parsers", rec["rationale"])


class TestExecuteSetup(unittest.TestCase):
    """Tests for SeedRunner.execute_setup()."""

    def test_dry_run_creates_no_files(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            runner = SeedRunner(profile)
            report = runner.execute_setup(dry_run=True)
            self.assertTrue(report["dryRun"])
            self.assertFalse(os.path.exists(project_dir))
            for step in report["steps"]:
                self.assertEqual(step["status"], "dry_run")

    def test_execute_creates_project(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            report = runner.execute_setup()
            self.assertFalse(report["dryRun"])
            self.assertTrue(os.path.isdir(project_dir))
            # Check key files exist
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "project.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "profile.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "sources.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "checklist.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "setup_report.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "ingestion_plan.json")))
            self.assertTrue(os.path.isfile(os.path.join(project_dir, "status.md")))

    def test_execute_populates_sources(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            runner.execute_setup()
            with open(os.path.join(project_dir, "sources.json"), "r") as f:
                sources = json.load(f)
            self.assertIn("rtl_modules", sources["sources"])

    def test_execute_creates_ingestion_steps(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            runner.execute_setup()
            with open(os.path.join(project_dir, "ingestion_plan.json"), "r") as f:
                plan = json.load(f)
            total_steps = sum(len(p["steps"]) for p in plan["phases"])
            self.assertGreater(total_steps, 0)

    def test_execute_marks_auto_checklist_items(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            runner.execute_setup()
            with open(os.path.join(project_dir, "checklist.json"), "r") as f:
                checklist = json.load(f)
            for section in checklist["sections"]:
                for item in section["items"]:
                    if item.get("auto"):
                        self.assertTrue(item["done"],
                                        f"Auto item not done: {item['id']}")

    def test_execute_report_has_next_actions(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            report = runner.execute_setup()
            self.assertIn("nextActions", report)
            self.assertTrue(len(report["nextActions"]) > 0)

    def test_execute_creates_status_md_with_content(self):
        """status.md should contain project name, setup config, and next steps."""
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            runner.execute_setup()
            status_path = os.path.join(project_dir, "status.md")
            self.assertTrue(os.path.isfile(status_path))
            with open(status_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Must contain key sections
            self.assertIn("TestProject", content)
            self.assertIn("## Project Summary", content)
            self.assertIn("## Setup Configuration", content)
            self.assertIn("## Data Sources", content)
            self.assertIn("## Next Steps", content)
            self.assertIn("## Quick Commands", content)
            # Must mention the domain
            self.assertIn("hardware", content)

    def test_execute_no_errors(self):
        profile = _make_profile()
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = os.path.join(tmpdir, "test_project")
            profile["projectDir"] = project_dir
            profile["sourceRoot"] = tmpdir
            runner = SeedRunner(profile)
            report = runner.execute_setup()
            for step in report["steps"]:
                self.assertNotEqual(step["status"], "error",
                                    f"Step {step['name']} failed: {step.get('detail')}")


class TestMixedDomainSelection(unittest.TestCase):
    """Tests for mixed domain template selection edge cases."""

    def test_mixed_hw_emphasis(self):
        profile = _make_profile({"domain": "mixed", "subDomain": "ASIC"})
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "hardware_product")

    def test_mixed_sw_emphasis(self):
        profile = _make_profile({"domain": "mixed", "subDomain": "web-service"})
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "software_product")

    def test_mixed_default(self):
        profile = _make_profile({"domain": "mixed", "subDomain": "research"})
        with tempfile.TemporaryDirectory() as tmpdir:
            profile["projectDir"] = tmpdir
            runner = SeedRunner(profile)
            rec = runner.generate_recommendations()
            self.assertEqual(rec["template"], "hardware_product")


if __name__ == "__main__":
    unittest.main()
