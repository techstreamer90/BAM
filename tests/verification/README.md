# BAM Data Verification Testing System

A declarative testing framework for verifying the BAM graph model against expected data points and answering questions about the model state.

## Overview

The verification system allows you to:
- Define expected data points in YAML fixture files
- Create human-readable questions about the model
- Run automated verifications with detailed reporting
- Integrate with pytest for CI/CD pipelines

```
┌─────────────────────────────────────────────────────────────────┐
│                    Verification System                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Fixtures (YAML)              Questions (YAML)                 │
│   ┌─────────────┐              ┌─────────────┐                  │
│   │ data_points │              │  questions  │                  │
│   │ - node_exists│             │ - "Does X?" │                  │
│   │ - edge_exists│             │ - "How many?"│                 │
│   │ - counts    │              │ - answer    │                  │
│   └──────┬──────┘              └──────┬──────┘                  │
│          │                            │                          │
│          └──────────┬─────────────────┘                          │
│                     ▼                                            │
│          ┌─────────────────────┐                                │
│          │ VerificationRunner  │                                │
│          │  (parallel/serial)  │                                │
│          └──────────┬──────────┘                                │
│                     │                                            │
│                     ▼                                            │
│          ┌─────────────────────┐                                │
│          │  GraphManager/Model │                                │
│          └──────────┬──────────┘                                │
│                     │                                            │
│                     ▼                                            │
│          ┌─────────────────────┐                                │
│          │ VerificationSummary │                                │
│          │  PASS/FAIL/ERROR    │                                │
│          └─────────────────────┘                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Run all fixture tests
python -m tests.verification.cli run

# Run with questions database
python -m tests.verification.cli run --questions

# Filter by tags
python -m tests.verification.cli run --tags critical,safety

# List available tests
python -m tests.verification.cli list

# Show model statistics
python -m tests.verification.cli stats

# Verify a single node
python -m tests.verification.cli verify mock-jama-core-REQ-001

# Run via pytest
pytest tests/verification/test_model_verification.py -v
```

## Directory Structure

```
tests/verification/
├── README.md                 # This file
├── __init__.py               # Package exports
├── models.py                 # DataPoint, ExpectedValue, VerificationResult
├── query_engine.py           # VerificationQueryEngine (wraps GraphManager)
├── runner.py                 # VerificationRunner with parallel support
├── questions.py              # QuestionLoader for Q&A database
├── cli.py                    # CLI interface
├── test_model_verification.py    # pytest integration
│
└── fixtures/                 # Test fixture files
    ├── mock-jama-core.fixtures.yaml
    ├── mock-jama-safety.fixtures.yaml
    ├── mock-jama-specs.fixtures.yaml
    └── model-questions.yaml
```

## Verification Types

| Type | Description | Query Fields | Expected Fields |
|------|-------------|--------------|-----------------|
| `node_exists` | Check if node exists with expected type/label | `node_id` | `exists`, `type`, `label` |
| `node_properties` | Verify node color properties | `node_id` | `properties` |
| `node_content` | Check node content contains terms | `node_id` | `content_contains` |
| `edge_exists` | Check if edge exists between nodes | `source_node_id`, `target_node_id`, `edge_type` | `exists` |
| `node_count` | Count nodes matching criteria | `node_type`, `source_id` | `count`, `min_count`, `max_count` |
| `relationship_count` | Count edges for a node | `node_id`, `edge_type` | `count`, `min_count`, `max_count` |

## Writing Fixtures

Fixtures are YAML files that define data points to verify:

```yaml
# my-source.fixtures.yaml
version: "1.0"
source_id: "my-source"  # Optional: filter scope

data_points:
  # Node existence check
  - id: "dp-001"
    type: "node_exists"
    description: "Main requirement exists"
    tags: ["existence", "critical"]
    query:
      node_id: "my-source-REQ-001"
    expected:
      exists: true
      type: "Requirement"
      label: "Main Requirement"

  # Node count check
  - id: "dp-002"
    type: "node_count"
    description: "Correct number of requirements"
    tags: ["count"]
    query:
      node_type: "Requirement"
      source_id: "my-source"
    expected:
      count: 10

  # Or use range
  - id: "dp-003"
    type: "node_count"
    description: "At least 5 specifications"
    tags: ["count"]
    query:
      node_type: "Specification"
    expected:
      min_count: 5

  # Edge existence check
  - id: "dp-004"
    type: "edge_exists"
    description: "Requirement derives from parent"
    tags: ["relationships"]
    query:
      source_node_id: "my-source-REQ-002"
      target_node_id: "my-source-REQ-001"
      edge_type: "DERIVES_FROM"
    expected:
      exists: true

  # Relationship count
  - id: "dp-005"
    type: "relationship_count"
    description: "REQ-001 has child requirements"
    tags: ["relationships"]
    query:
      node_id: "my-source-REQ-001"
      edge_type: "DERIVES_FROM"
    expected:
      min_count: 2
```

Place fixture files in `fixtures/` with naming pattern `*.fixtures.yaml`.

## Writing Questions

Questions provide a human-readable way to define verifications:

```yaml
# model-questions.yaml
questions:
  - id: "q-001"
    question: "Does the System Overview requirement exist?"
    category: "existence"
    tags: ["core", "critical"]
    query:
      type: "node_exists"
      node_id: "mock-jama-core-REQ-001"
    answer:
      exists: true
      type: "Requirement"
      label: "System Overview"

  - id: "q-010"
    question: "How many core requirements are there?"
    category: "count"
    tags: ["core"]
    query:
      type: "node_count"
      node_type: "Requirement"
      source_id: "mock-jama-core"
    answer:
      count: 8

  - id: "q-020"
    question: "Is REQ-002 derived from REQ-001?"
    category: "relationships"
    tags: ["traceability"]
    query:
      type: "edge_exists"
      source_node_id: "mock-jama-core-REQ-002"
      target_node_id: "mock-jama-core-REQ-001"
      edge_type: "DERIVES_FROM"
    answer:
      exists: true
```

## CLI Reference

### `run` - Execute verifications

```bash
python -m tests.verification.cli run [OPTIONS]

Options:
  --parallel        Run verifications in parallel (faster, but may have
                    race conditions with JSON backend)
  --workers N       Number of parallel workers (default: 4)
  --tags T1,T2      Only run data points with these tags
  --questions       Include questions from model-questions.yaml
  --quiet           Suppress progress output
```

### `list` - Show available tests

```bash
python -m tests.verification.cli list

Output:
  Fixture Data Points:
    core-001: System Overview requirement exists [existence, core, critical]
    core-002: Propulsion Control requirement exists [existence, core]
    ...
```

### `stats` - Show model statistics

```bash
python -m tests.verification.cli stats

Output:
  Model Statistics:
    Nodes: 21
    Edges: 14
    Node Types: Requirement (14), Specification (7)
    ...
```

### `verify` - Check single node

```bash
python -m tests.verification.cli verify <node-id>

Example:
  python -m tests.verification.cli verify mock-jama-core-REQ-001
```

## Pytest Integration

The `test_model_verification.py` file integrates with pytest:

```bash
# Run all verification tests
pytest tests/verification/test_model_verification.py -v

# Run specific test classes
pytest tests/verification/test_model_verification.py::TestNodeExistence -v
pytest tests/verification/test_model_verification.py::TestNodeCounts -v

# Run with tags (using pytest markers)
pytest tests/verification/ -m "critical" -v
```

### Test Classes

| Class | Description |
|-------|-------------|
| `TestNodeExistence` | Verifies critical nodes exist |
| `TestNodeCounts` | Verifies node counts per source |
| `TestEdgeExistence` | Verifies critical relationships |
| `TestRelationshipCounts` | Verifies relationship counts |
| `TestFixtureLoader` | Tests fixture loading mechanism |
| `TestQuestionDatabase` | Tests question loading |
| `TestParallelExecution` | Compares parallel vs sequential |

## Programmatic Usage

```python
from tests.verification.runner import VerificationRunner
from tests.verification.models import DataPoint, VerificationType, VerificationQuery, ExpectedValue

# Create runner
runner = VerificationRunner(parallel=False)

# Load fixtures
runner.load_fixtures(tags=["critical"])

# Or add custom data points
dp = DataPoint(
    id="custom-001",
    type=VerificationType.NODE_EXISTS,
    description="Custom verification",
    query=VerificationQuery(node_id="my-node-id"),
    expected=ExpectedValue(exists=True, type="Requirement"),
    tags=["custom"]
)
runner.add_data_points([dp])

# Run and get results
summary = runner.run()

print(f"Passed: {summary.passed}/{summary.total}")
print(f"Success rate: {summary.success_rate:.1f}%")

if not summary.all_passed:
    for result in summary.results:
        if result.status != VerificationStatus.PASS:
            print(f"FAILED: {result.data_point_id}")
            print(f"  Expected: {result.expected}")
            print(f"  Actual: {result.actual}")
```

## Relationship to the Test Chain

BAM also includes an **accumulating test chain** (`test_chain.json` in each
project directory) that automatically generates verification data points during
project init and pipeline stages. The test chain reuses the same
`VerificationType`, `VerificationQuery`, `ExpectedValue`, and `DataPoint`
schemas defined in `models.py`, and executes them via `VerificationQueryEngine`.

The key differences:

| | Verification Framework | Test Chain |
|---|---|---|
| **Source** | Hand-written YAML fixtures | Auto-generated from pipeline stages |
| **Scope** | Standalone, project-agnostic | Per-project, grows with ingestion |
| **When run** | On demand (`cli run`, pytest) | Automatically during verify stage + `bam test run` |
| **Gate behavior** | N/A | blocking (halts pipeline) or warning (reported only) |

See `src/bam/test_chain.py` for the `TestChainManager` implementation.

## Best Practices

### Tagging Strategy

Use consistent tags to organize and filter tests:

| Tag | Purpose |
|-----|---------|
| `critical` | Must pass for release |
| `existence` | Node existence checks |
| `count` | Count verifications |
| `relationships` | Edge/traceability checks |
| `core` | Core requirements source |
| `safety` | Safety requirements source |
| `specs` | Specifications source |

### Fixture Organization

- One fixture file per source: `{source-id}.fixtures.yaml`
- Group related data points together
- Use descriptive IDs: `{source}-{number}` or `{category}-{number}`
- Always include `description` for debugging

### Parallel Execution Note

The `--parallel` flag enables concurrent verification for faster execution. However, the JSON color backend may experience race conditions when multiple workers access the same file. For reliable results:

- Use sequential mode (default) with JSON backend
- Use parallel mode with SQLite backend
- Run parallel tests in read-only scenarios

## Example Output

```
BAM Data Verification
============================================================
Loaded 47 fixture data points
Loaded 15 questions

Running 62 verifications...
------------------------------------------------------------
[PASS] core-001: System Overview requirement exists
[PASS] core-002: Propulsion Control requirement exists
[PASS] core-003: Brake Control requirement exists
...
[PASS] q-001: Does the System Overview requirement exist?
[PASS] q-010: How many core requirements are there?

============================================================
VERIFICATION SUMMARY
============================================================
Total:    62
Passed:   62
Failed:   0
Errors:   0
Skipped:  0
Duration: 156.3ms
Success:  100.0%
============================================================
```
