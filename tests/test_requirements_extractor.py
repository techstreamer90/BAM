"""
Tests for Requirements Extractor

Tests extraction from CSV and Excel files with various column patterns.
"""

import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from bam.extractors import RequirementsExtractor, IntermediateData


# Fixture paths
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "requirements"


class TestColumnDetection:
    """Test column pattern detection."""

    def test_standard_columns(self):
        """Test detection of standard column names."""
        extractor = RequirementsExtractor("test")
        headers = ["ID", "Name", "Description", "Status", "Priority", "Traces To"]

        column_map = extractor._detect_columns(headers)

        assert 0 in column_map["id"]
        assert 1 in column_map["name"]
        assert 2 in column_map["description"]
        assert 3 in column_map["status"]
        assert 4 in column_map["priority"]
        assert 5 in column_map["traces_to"]

    def test_alternate_column_names(self):
        """Test detection of alternate column names."""
        extractor = RequirementsExtractor("test")
        headers = ["Requirement ID", "Title", "Specification", "State", "Prio", "Parent"]

        column_map = extractor._detect_columns(headers)

        assert 0 in column_map["id"]
        assert 1 in column_map["name"]
        assert 2 in column_map["description"]
        assert 3 in column_map["status"]
        assert 4 in column_map["priority"]
        assert 5 in column_map["traces_to"]

    def test_case_insensitive(self):
        """Test that column detection is case-insensitive."""
        extractor = RequirementsExtractor("test")
        headers = ["ID", "id", "Id", "iD"]

        column_map = extractor._detect_columns(headers)

        # All should be detected as ID columns
        assert len(column_map["id"]) == 4


class TestCSVExtraction:
    """Test CSV file extraction."""

    def test_extract_sample_requirements(self):
        """Test extraction from sample requirements CSV."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_file(csv_file)

        assert len(result["items"]) == 6
        assert len(result["relationships"]) > 0

        # Check first requirement
        req1 = next(r for r in result["items"] if "REQ-001" in r["id"])
        assert req1["name"] == "System Overview"
        assert "vehicle control" in req1["description"].lower()
        assert req1["properties"]["status"] == "Approved"
        assert req1["properties"]["priority"] == "High"

    def test_extract_traceability(self):
        """Test that traceability relationships are extracted."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_file(csv_file)

        # REQ-002 traces to REQ-001
        traces = [r for r in result["relationships"]
                  if r["type"] == "TRACES_TO" and r["source"] == "REQ-002"]
        assert len(traces) == 1
        assert traces[0]["target"] == "REQ-001"

        # REQ-004 traces to both REQ-002 and REQ-003
        traces = [r for r in result["relationships"]
                  if r["type"] == "TRACES_TO" and r["source"] == "REQ-004"]
        assert len(traces) == 2
        targets = {t["target"] for t in traces}
        assert targets == {"REQ-002", "REQ-003"}

    def test_extract_verification_links(self):
        """Test that verification links are extracted."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_file(csv_file)

        # REQ-003 is verified by TC-002 and TC-003
        verified = [r for r in result["relationships"]
                    if r["type"] == "VERIFIED_BY" and r["source"] == "REQ-003"]
        assert len(verified) == 2
        targets = {v["target"] for v in verified}
        assert targets == {"TC-002", "TC-003"}

    def test_alternate_columns(self):
        """Test extraction with alternate column names."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "alternate_columns.csv"

        if not csv_file.exists():
            pytest.skip("Alternate columns CSV file not found")

        result = extractor.extract_file(csv_file)

        assert len(result["items"]) == 3

        # Check that alternate names were detected
        req = next(r for r in result["items"] if "DR-100" in r["id"])
        assert req["name"] == "Motor Controller"
        assert req["properties"]["status"] == "Approved"
        assert req["properties"]["priority"] == "High"


class TestIntermediateFormat:
    """Test conversion to intermediate format."""

    def test_to_intermediate(self):
        """Test conversion to intermediate format."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_directory(csv_file.parent, recursive=False)
        intermediate = extractor.to_intermediate(result)

        assert isinstance(intermediate, IntermediateData)
        assert intermediate.source_id == "dr-source"
        assert intermediate.source_type == "requirements"
        assert len(intermediate.nodes) > 0
        assert len(intermediate.edges) > 0

        # Check node format
        node = intermediate.nodes[0]
        assert node.type == "Requirement"
        assert node.external_id.startswith("req-")
        assert node.label
        assert node.source_location

    def test_intermediate_save_load(self):
        """Test saving and loading intermediate format."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_directory(csv_file.parent, recursive=False)
        intermediate = extractor.to_intermediate(result)

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "intermediate.json"
            intermediate.save(output_path)

            # Verify file was created and is valid JSON
            assert output_path.exists()
            with open(output_path) as f:
                data = json.load(f)

            assert data["source_id"] == "dr-source"
            assert data["source_type"] == "requirements"
            assert len(data["nodes"]) > 0
            assert "summary" in data

            # Load and verify
            loaded = IntermediateData.load(output_path)
            assert len(loaded.nodes) == len(intermediate.nodes)
            assert len(loaded.edges) == len(intermediate.edges)


class TestSummaryGeneration:
    """Test summary generation for agents."""

    def test_generate_summary(self):
        """Test summary generation."""
        extractor = RequirementsExtractor("dr-source")
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        # Extract just the one file to get predictable results
        file_result = extractor.extract_file(csv_file)
        # Create an ExtractionResult for the summary
        from bam.extractors import ExtractionResult
        result = ExtractionResult(
            success=True,
            source_id="dr-source",
            extractor_type="requirements",
            items=file_result["items"],
            relationships=file_result["relationships"],
            file_count=1,
        )
        summary = extractor.generate_summary(result)

        assert summary["total_requirements"] == 6
        assert "by_status" in summary
        assert "by_priority" in summary
        assert "traceability" in summary
        assert "top_level_requirements" in summary

        # REQ-001 should be a top-level requirement (not traced to by others)
        assert "REQ-001" in summary["top_level_requirements"]


class TestCustomNodeTypes:
    """Test custom node and edge type configuration."""

    def test_custom_node_type(self):
        """Test using custom node type."""
        extractor = RequirementsExtractor(
            "dr-source",
            node_type="DesignRequirement"
        )
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_file(csv_file)

        # All items should have the custom type
        for item in result["items"]:
            assert item["type"] == "DesignRequirement"

    def test_custom_edge_types(self):
        """Test using custom edge types."""
        extractor = RequirementsExtractor(
            "dr-source",
            traces_edge_type="DERIVES_FROM",
            verified_edge_type="TESTED_BY"
        )
        csv_file = FIXTURES_DIR / "sample_requirements.csv"

        if not csv_file.exists():
            pytest.skip("Sample CSV file not found")

        result = extractor.extract_file(csv_file)

        # Check edge types
        edge_types = {r["type"] for r in result["relationships"]}
        assert "DERIVES_FROM" in edge_types or "TESTED_BY" in edge_types
        assert "TRACES_TO" not in edge_types


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_csv(self):
        """Test handling of empty CSV file."""
        extractor = RequirementsExtractor("test")

        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "empty.csv"
            csv_path.write_text("ID,Name,Description\n")

            result = extractor.extract_file(csv_path)
            assert result["items"] == []

    def test_missing_id_column(self):
        """Test handling when ID column is missing."""
        extractor = RequirementsExtractor("test")

        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "no_id.csv"
            csv_path.write_text("Name,Description\nTest,Testing\n")

            result = extractor.extract_file(csv_path)
            assert result["items"] == []
            assert any("No ID column" in w for w in result["warnings"])

    def test_delimiter_detection(self):
        """Test that different delimiters are handled."""
        extractor = RequirementsExtractor("test")

        with TemporaryDirectory() as tmpdir:
            # Semicolon-delimited
            csv_path = Path(tmpdir) / "semicolon.csv"
            csv_path.write_text("ID;Name;Description\nREQ-001;Test;Testing\n")

            result = extractor.extract_file(csv_path)
            assert len(result["items"]) == 1
            assert "REQ-001" in result["items"][0]["id"]

    def test_multivalue_traces(self):
        """Test handling of multiple trace targets in one cell."""
        extractor = RequirementsExtractor("test")

        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "multi.csv"
            csv_path.write_text(
                "ID,Name,Traces To\n"
                "REQ-001,First,\n"
                "REQ-002,Second,REQ-001\n"
                "REQ-003,Third,REQ-001;REQ-002\n"
                "REQ-004,Fourth,REQ-001|REQ-002|REQ-003\n"
            )

            result = extractor.extract_file(csv_path)

            # REQ-003 should have 2 traces
            req3_traces = [r for r in result["relationships"]
                          if r["source"] == "REQ-003"]
            assert len(req3_traces) == 2

            # REQ-004 should have 3 traces
            req4_traces = [r for r in result["relationships"]
                          if r["source"] == "REQ-004"]
            assert len(req4_traces) == 3
