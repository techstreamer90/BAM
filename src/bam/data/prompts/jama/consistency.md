# JAMA Consistency Check Prompt

You are verifying consistency of JAMA-sourced data within the BAM graph model.

## Context
- Source: JAMA Requirements Management System
- Model: BAM Graph Model (post-integration)
- Purpose: Ensure data consistency and integrity after integration

## Consistency Checks

### 1. ID Uniqueness
- Every node ID must be unique across the entire graph
- JAMA-sourced nodes should have IDs matching pattern: `jama-{type}-{originalId}`
- No duplicate `source_ref` values within JAMA source

### 2. Relationship Integrity
- All edges must connect existing nodes
- No dangling references (edges to non-existent nodes)
- Bidirectional relationships (if any) must be symmetric

### 3. Hierarchy Validity
- Requirements hierarchy must form a valid tree (no cycles)
- Every derived requirement must trace back to a root requirement
- CONTAINS relationships must form proper containment tree

### 4. Cross-Source Consistency
- If requirement references external item, that item should exist
- Traceability links should be complete (bidirectional where expected)
- No conflicting information between sources

### 5. Data Completeness
- Required properties must be present on all nodes
- Status values must be from allowed set
- Priority values must be from allowed set

## Consistency Report Format

```json
{
  "consistent": true/false,
  "checksPerformed": [
    {
      "check": "id-uniqueness",
      "passed": true/false,
      "details": "..."
    }
  ],
  "issues": [
    {
      "type": "data-inconsistency",
      "severity": "error|warning",
      "check": "<check-name>",
      "affectedNodes": ["node-id-1", "node-id-2"],
      "description": "<what is inconsistent>",
      "suggestedAction": "<how to fix>"
    }
  ],
  "statistics": {
    "nodesChecked": <count>,
    "edgesChecked": <count>,
    "issuesFound": <count>
  }
}
```

## Issue Types

| Type | Description | Severity |
|------|-------------|----------|
| data-inconsistency | Data doesn't match expected constraints | error |
| model-conflict | Conflicting data from different sources | error |
| missing-reference | Expected relationship target not found | warning |
| incomplete-trace | Traceability chain is broken | warning |

## Instructions

1. Load the current graph model state
2. Filter to JAMA-sourced nodes and edges
3. Perform each consistency check
4. Collect and categorize all issues found
5. Generate suggested actions for each issue
6. Produce comprehensive consistency report

Report all findings with appropriate severity levels.
