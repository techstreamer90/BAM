"""
BAM Common Types and Utilities

Shared enums, dataclasses, and utility functions used across the BAM system.
"""

import logging
import re
from datetime import datetime
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import List, Optional


# Configure module logger
logger = logging.getLogger("bam")


def _snake_to_camel(name: str) -> str:
    """Convert snake_case to camelCase."""
    components = name.split('_')
    return components[0] + ''.join(c.title() for c in components[1:])


def to_camel_dict(obj) -> dict:
    """Convert a dataclass instance to a dict with camelCase keys."""
    return {_snake_to_camel(k): v for k, v in asdict(obj).items()}


class IssueType(Enum):
    """Types of issues that can occur during ingestion."""
    DATA_INCONSISTENCY = "data-inconsistency"
    MODEL_CONFLICT = "model-conflict"
    VALIDATION_FAILURE = "validation-failure"
    STAGE_FAILURE = "stage-failure"
    CONNECTION_ERROR = "connection-error"
    TRANSFORM_ERROR = "transform-error"


class IssueSeverity(Enum):
    """Severity levels for issues."""
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueStatus(Enum):
    """Status of an issue in its lifecycle."""
    OPEN = "open"
    BLOCKING = "blocking"
    IN_PROGRESS = "in-progress"
    RESOLVED = "resolved"
    WONT_FIX = "wont-fix"


class TodoType(Enum):
    """Types of todo items."""
    CLEANUP = "cleanup"
    BUG = "bug"
    FEATURE = "feature"
    IMPROVEMENT = "improvement"
    TASK = "task"


class TodoPriority(Enum):
    """Priority levels for todo items."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TodoStatus(Enum):
    """Status of a todo item in its lifecycle."""
    OPEN = "open"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"
    WONT_FIX = "wont-fix"


class TaskStatus(Enum):
    """Status of a pipeline task."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class FeedbackKind(Enum):
    """Kinds of user feedback on the model."""
    REINGEST = "reingest"          # Source has new data, re-run pipeline
    CORRECTION = "correction"      # Something in the model is wrong
    GAP = "gap"                    # Something is missing from the model
    GENERAL = "general"            # Free-form observation


class StageStatus(Enum):
    """Status of a pipeline stage."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Issue:
    """Represents an issue in the tracker."""
    id: str = ""
    type: str = IssueType.DATA_INCONSISTENCY.value
    severity: str = IssueSeverity.ERROR.value
    status: str = IssueStatus.OPEN.value
    title: str = ""
    description: str = ""
    source_id: Optional[str] = None
    run_id: Optional[str] = None
    stage_id: Optional[str] = None
    affected_nodes: List[str] = field(default_factory=list)
    affected_edges: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
    assigned_to: Optional[str] = None
    comments: List[dict] = field(default_factory=list)


@dataclass
class Todo:
    """Represents a todo item in the tracker."""
    id: str = ""
    title: str = ""
    description: str = ""
    type: str = TodoType.TASK.value
    priority: str = TodoPriority.MEDIUM.value
    status: str = TodoStatus.OPEN.value
    assigned_to: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None


@dataclass
class StageResult:
    """Result of stage execution."""
    stage_id: str
    status: str = "pending"
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    outputs: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


class PipelinePauseException(Exception):
    """Raised when a stage needs to pause for human review."""
    pass


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """
    Set up logging for BAM modules.

    Args:
        level: Logging level (default: INFO)

    Returns:
        Configured logger instance
    """
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))

    bam_logger = logging.getLogger("bam")
    if not bam_logger.handlers:
        bam_logger.addHandler(handler)
    bam_logger.setLevel(level)

    return bam_logger
