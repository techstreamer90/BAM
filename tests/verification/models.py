"""
Data models for the verification testing system.

Defines dataclasses for verification queries, expected values, and results.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class VerificationType(Enum):
    """Types of verifications supported."""
    NODE_EXISTS = "node_exists"
    NODE_PROPERTIES = "node_properties"
    NODE_CONTENT = "node_content"
    EDGE_EXISTS = "edge_exists"
    NODE_COUNT = "node_count"
    RELATIONSHIP_COUNT = "relationship_count"


class VerificationStatus(Enum):
    """Status of a verification result."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class ExpectedValue:
    """Expected value for a verification."""
    exists: Optional[bool] = None
    type: Optional[str] = None
    label: Optional[str] = None
    count: Optional[int] = None
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    properties: Optional[Dict[str, Any]] = None
    content_contains: Optional[List[str]] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    edge_type: Optional[str] = None


@dataclass
class VerificationQuery:
    """Query parameters for a verification."""
    node_id: Optional[str] = None
    node_type: Optional[str] = None
    source_id: Optional[str] = None
    edge_id: Optional[str] = None
    edge_type: Optional[str] = None
    source_node_id: Optional[str] = None
    target_node_id: Optional[str] = None
    label_contains: Optional[str] = None
    type: Optional[str] = None  # Query type for Q&A database


@dataclass
class DataPoint:
    """A single data point to verify."""
    id: str
    type: VerificationType
    description: str
    query: VerificationQuery
    expected: ExpectedValue
    tags: List[str] = field(default_factory=list)
    source_file: Optional[str] = None


@dataclass
class VerificationResult:
    """Result of a single verification."""
    data_point_id: str
    status: VerificationStatus
    description: str
    expected: Any
    actual: Any
    message: str = ""
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class FixtureFile:
    """A fixture file containing data points."""
    version: str
    source_id: Optional[str]
    data_points: List[DataPoint]
    file_path: Optional[str] = None


@dataclass
class Question:
    """A question in the Q&A database."""
    id: str
    question: str
    category: str
    query: VerificationQuery
    answer: ExpectedValue
    tags: List[str] = field(default_factory=list)


@dataclass
class QuestionDatabase:
    """Collection of questions for verification."""
    questions: List[Question]
    file_path: Optional[str] = None


@dataclass
class VerificationSummary:
    """Summary of verification run results."""
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_ms: float
    results: List[VerificationResult]

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total == 0:
            return 100.0
        return (self.passed / self.total) * 100.0

    @property
    def all_passed(self) -> bool:
        """Check if all tests passed."""
        return self.failed == 0 and self.errors == 0
