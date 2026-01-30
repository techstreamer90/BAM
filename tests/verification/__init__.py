# BAM Data Verification Testing System
"""
Verification testing system for validating data survives the ingestion pipeline.

Two complementary approaches:
1. Fixture-based verification: Define expected data points BEFORE ingestion
2. Question/Answer database: Human-readable test questions with expected answers
"""

from .models import DataPoint, ExpectedValue, VerificationQuery, VerificationResult
from .query_engine import VerificationQueryEngine
from .runner import VerificationRunner

__all__ = [
    "DataPoint",
    "ExpectedValue",
    "VerificationQuery",
    "VerificationResult",
    "VerificationQueryEngine",
    "VerificationRunner",
]
