"""
BAM Backend Utilities

Common utilities used across backends.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """Get current UTC time as ISO format string."""
    return datetime.now(timezone.utc).isoformat()


def utc_now_timestamp() -> str:
    """Get current UTC time as timestamp string (for filenames)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
