"""
pytest integration for the verification testing system.

Tests the verification infrastructure itself (fixture loading, question parsing,
data-point model construction). Project-specific data verification (node
existence, counts, edges) is handled by the per-project test chain — see
``bam test run`` and ``src/bam/test_chain.py``.

Run with:
    pytest tests/verification/test_model_verification.py -v
"""

import pytest
from pathlib import Path

from .models import (
    DataPoint,
    ExpectedValue,
    VerificationQuery,
    VerificationResult,
    VerificationStatus,
    VerificationType,
)
from .runner import VerificationRunner
from .questions import QuestionLoader


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def runner():
    """Create a verification runner for the module."""
    return VerificationRunner()


class TestFixtureLoader:
    """Tests for fixture loading functionality."""

    def test_load_fixtures(self, runner):
        """Test that fixtures can be loaded."""
        count = runner.load_fixtures()
        # Should load data points from fixture files
        assert count >= 0, "Should be able to load fixtures"

    def test_loaded_data_points_are_well_formed(self, runner):
        """Every loaded data point has the required fields."""
        runner.load_fixtures()
        for dp in runner._data_points:
            assert dp.id is not None
            assert dp.type is not None
            assert dp.query is not None
            assert dp.expected is not None


class TestQuestionDatabase:
    """Tests for question database functionality."""

    def test_load_questions(self):
        """Test that questions can be loaded."""
        loader = QuestionLoader()
        questions = loader.load_all()
        # Questions may or may not exist
        assert isinstance(questions, list)

    def test_convert_questions_to_datapoints(self):
        """Test converting questions to data points."""
        loader = QuestionLoader()
        data_points = loader.to_data_points()
        # Each data point should be valid
        for dp in data_points:
            assert dp.id is not None
            assert dp.type is not None
            assert dp.query is not None


class TestDataPointConstruction:
    """Tests for building DataPoint objects programmatically."""

    def test_node_exists_datapoint(self):
        """Build a node_exists data point."""
        dp = DataPoint(
            id="unit-node-exists",
            type=VerificationType.NODE_EXISTS,
            description="Check node exists",
            query=VerificationQuery(node_id="some-node"),
            expected=ExpectedValue(exists=True, type="Requirement"),
        )
        assert dp.type == VerificationType.NODE_EXISTS
        assert dp.query.node_id == "some-node"
        assert dp.expected.exists is True

    def test_node_count_datapoint(self):
        """Build a node_count data point."""
        dp = DataPoint(
            id="unit-node-count",
            type=VerificationType.NODE_COUNT,
            description="Count nodes by type",
            query=VerificationQuery(node_type="Specification", source_id="src"),
            expected=ExpectedValue(min_count=3),
        )
        assert dp.expected.min_count == 3
        assert dp.query.source_id == "src"

    def test_edge_exists_datapoint(self):
        """Build an edge_exists data point."""
        dp = DataPoint(
            id="unit-edge-exists",
            type=VerificationType.EDGE_EXISTS,
            description="Check edge",
            query=VerificationQuery(
                source_node_id="a",
                target_node_id="b",
                edge_type="DERIVES_FROM",
            ),
            expected=ExpectedValue(exists=True),
        )
        assert dp.query.edge_type == "DERIVES_FROM"

    def test_verification_result_statuses(self):
        """VerificationResult can represent all status values."""
        for status in VerificationStatus:
            result = VerificationResult(
                data_point_id="x",
                status=status,
                description="test",
                expected=None,
                actual=None,
            )
            assert result.status == status
