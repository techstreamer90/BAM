"""
Verification Test Runner

Executes verification tests with support for parallel execution using ThreadPoolExecutor.

Note: Parallel execution requires a thread-safe backend (e.g., SQLite, database).
The JSON backend may experience race conditions during parallel execution.
For JSON backend, use sequential mode (parallel=False) for reliable results.
"""

import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, List, Optional

import yaml

from .models import (
    DataPoint,
    ExpectedValue,
    FixtureFile,
    VerificationQuery,
    VerificationResult,
    VerificationStatus,
    VerificationSummary,
    VerificationType,
)
from .query_engine import VerificationQueryEngine


class VerificationRunner:
    """
    Runs verification tests with parallel execution support.

    Each parallel worker gets its own GraphManager instance for thread safety.
    """

    def __init__(
        self,
        fixtures_dir: Optional[Path] = None,
        config: dict = None,
        parallel: bool = False,
        max_workers: int = 4,
        progress_callback: Optional[Callable[[VerificationResult], None]] = None
    ):
        """
        Initialize the verification runner.

        Args:
            fixtures_dir: Directory containing fixture YAML files.
            config: Optional config dict for GraphManager.
            parallel: Enable parallel execution.
            max_workers: Number of parallel workers (default 4).
            progress_callback: Optional callback for real-time progress.
        """
        self.fixtures_dir = fixtures_dir or self._default_fixtures_dir()
        self.config = config
        self.parallel = parallel
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self._data_points: List[DataPoint] = []

    def _default_fixtures_dir(self) -> Path:
        """Get the default fixtures directory."""
        return Path(__file__).parent / "fixtures"

    def load_fixtures(self, tags: Optional[List[str]] = None) -> int:
        """
        Load data points from all fixture files.

        Args:
            tags: Optional list of tags to filter by.

        Returns:
            Number of data points loaded.
        """
        self._data_points = []

        if not self.fixtures_dir.exists():
            return 0

        for fixture_path in self.fixtures_dir.glob("*.fixtures.yaml"):
            fixture_file = self._load_fixture_file(fixture_path)
            if fixture_file:
                for dp in fixture_file.data_points:
                    if tags is None or any(t in dp.tags for t in tags):
                        self._data_points.append(dp)

        return len(self._data_points)

    def _load_fixture_file(self, path: Path) -> Optional[FixtureFile]:
        """Load a single fixture file."""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)

            if not data:
                return None

            data_points = []
            for dp_data in data.get("data_points", []):
                dp = self._parse_data_point(dp_data, str(path))
                if dp:
                    data_points.append(dp)

            return FixtureFile(
                version=data.get("version", "1.0"),
                source_id=data.get("source_id"),
                data_points=data_points,
                file_path=str(path)
            )
        except Exception as e:
            print(f"Error loading fixture {path}: {e}", file=sys.stderr)
            return None

    def _parse_data_point(self, data: dict, source_file: str) -> Optional[DataPoint]:
        """Parse a data point from YAML data."""
        try:
            # Parse verification type
            type_str = data.get("type", "node_exists")
            try:
                ver_type = VerificationType(type_str)
            except ValueError:
                print(f"Unknown verification type: {type_str}", file=sys.stderr)
                return None

            # Parse query
            query_data = data.get("query", {})
            query = VerificationQuery(
                node_id=query_data.get("node_id"),
                node_type=query_data.get("node_type"),
                source_id=query_data.get("source_id"),
                edge_id=query_data.get("edge_id"),
                edge_type=query_data.get("edge_type"),
                source_node_id=query_data.get("source_node_id"),
                target_node_id=query_data.get("target_node_id"),
                label_contains=query_data.get("label_contains"),
                type=query_data.get("type"),
            )

            # Parse expected values
            expected_data = data.get("expected", {})
            expected = ExpectedValue(
                exists=expected_data.get("exists"),
                type=expected_data.get("type"),
                label=expected_data.get("label"),
                count=expected_data.get("count"),
                min_count=expected_data.get("min_count"),
                max_count=expected_data.get("max_count"),
                properties=expected_data.get("properties"),
                content_contains=expected_data.get("content_contains"),
                source_node_id=expected_data.get("source_node_id"),
                target_node_id=expected_data.get("target_node_id"),
                edge_type=expected_data.get("edge_type"),
            )

            return DataPoint(
                id=data.get("id", "unknown"),
                type=ver_type,
                description=data.get("description", ""),
                query=query,
                expected=expected,
                tags=data.get("tags", []),
                source_file=source_file
            )
        except Exception as e:
            print(f"Error parsing data point: {e}", file=sys.stderr)
            return None

    def add_data_point(self, data_point: DataPoint):
        """Add a single data point to run."""
        self._data_points.append(data_point)

    def add_data_points(self, data_points: List[DataPoint]):
        """Add multiple data points to run."""
        self._data_points.extend(data_points)

    def run(self) -> VerificationSummary:
        """
        Run all loaded verifications.

        Returns:
            VerificationSummary with results.
        """
        start_time = time.perf_counter()

        if not self._data_points:
            return VerificationSummary(
                total=0,
                passed=0,
                failed=0,
                errors=0,
                skipped=0,
                duration_ms=0,
                results=[]
            )

        if self.parallel:
            results = self._run_parallel()
        else:
            results = self._run_sequential()

        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000

        # Count results by status
        passed = sum(1 for r in results if r.status == VerificationStatus.PASS)
        failed = sum(1 for r in results if r.status == VerificationStatus.FAIL)
        errors = sum(1 for r in results if r.status == VerificationStatus.ERROR)
        skipped = sum(1 for r in results if r.status == VerificationStatus.SKIP)

        return VerificationSummary(
            total=len(results),
            passed=passed,
            failed=failed,
            errors=errors,
            skipped=skipped,
            duration_ms=duration_ms,
            results=results
        )

    def _run_sequential(self) -> List[VerificationResult]:
        """Run verifications sequentially."""
        results = []
        with VerificationQueryEngine(config=self.config) as engine:
            for dp in self._data_points:
                result = engine.verify(dp)
                results.append(result)
                if self.progress_callback:
                    self.progress_callback(result)
        return results

    def _run_parallel(self) -> List[VerificationResult]:
        """Run verifications in parallel using ThreadPoolExecutor."""
        results = []
        result_order = {dp.id: i for i, dp in enumerate(self._data_points)}

        def verify_one(dp: DataPoint) -> VerificationResult:
            # Each worker creates its own GraphManager instance
            with VerificationQueryEngine(config=self.config) as engine:
                return engine.verify(dp)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_dp = {executor.submit(verify_one, dp): dp for dp in self._data_points}

            for future in as_completed(future_to_dp):
                dp = future_to_dp[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = VerificationResult(
                        data_point_id=dp.id,
                        status=VerificationStatus.ERROR,
                        description=dp.description,
                        expected=None,
                        actual=None,
                        error=str(e)
                    )
                results.append(result)
                if self.progress_callback:
                    self.progress_callback(result)

        # Sort results back to original order
        results.sort(key=lambda r: result_order.get(r.data_point_id, 999))
        return results

    def run_single(self, data_point: DataPoint) -> VerificationResult:
        """Run a single verification."""
        with VerificationQueryEngine(config=self.config) as engine:
            return engine.verify(data_point)


def print_progress(result: VerificationResult):
    """Default progress callback that prints results."""
    # Use ASCII-safe symbols for Windows compatibility
    status_symbol = {
        VerificationStatus.PASS: "PASS",
        VerificationStatus.FAIL: "FAIL",
        VerificationStatus.ERROR: "ERR!",
        VerificationStatus.SKIP: "SKIP",
    }.get(result.status, "????")

    status_color = {
        VerificationStatus.PASS: "\033[92m",  # Green
        VerificationStatus.FAIL: "\033[91m",  # Red
        VerificationStatus.ERROR: "\033[93m",  # Yellow
        VerificationStatus.SKIP: "\033[90m",  # Gray
    }.get(result.status, "")
    reset = "\033[0m"

    print(f"  {status_color}{status_symbol}{reset} [{result.data_point_id}] {result.description} ({result.duration_ms:.1f}ms)")
    if result.status == VerificationStatus.FAIL:
        print(f"        Expected: {result.expected}")
        print(f"        Actual:   {result.actual}")
    if result.error:
        print(f"        Error: {result.error}")


def print_summary(summary: VerificationSummary):
    """Print a summary of verification results."""
    print("\n" + "=" * 60)
    print(f"Verification Summary")
    print("=" * 60)
    print(f"  Total:   {summary.total}")
    print(f"  Passed:  \033[92m{summary.passed}\033[0m")
    print(f"  Failed:  \033[91m{summary.failed}\033[0m")
    print(f"  Errors:  \033[93m{summary.errors}\033[0m")
    print(f"  Skipped: {summary.skipped}")
    print(f"  Duration: {summary.duration_ms:.1f}ms")
    print(f"  Success Rate: {summary.success_rate:.1f}%")
    print("=" * 60)

    if summary.all_passed:
        print("\033[92mAll verifications passed!\033[0m")
    else:
        print("\033[91mSome verifications failed.\033[0m")
