# Measurements Transformation Prompt

You are transforming measurement data into BAM graph model nodes and edges.

## Node Mapping

| Data Element | Graph Node Type | Properties |
|-------------|-----------------|------------|
| Test Run | TestRun | id, name, date, status |
| Test Case | TestCase | id, name, expected-result |
| Measurement | Measurement | id, value, unit, timestamp |
| Equipment | Equipment | id, name, calibration-date |

## Edge Mapping

| Relationship | Edge Type | Direction |
|-------------|-----------|-----------|
| Run contains Case | CONTAINS | run -> case |
| Case produces Measurement | PRODUCES | case -> measurement |
| Measurement uses Equipment | USES_EQUIPMENT | measurement -> equipment |
| Measurement verifies Requirement | VERIFIES | measurement -> requirement |

## Transformation Rules

1. **Test Run Nodes**
   - ID: `test-run-{run-id}`
   - Aggregate pass/fail statistics
   - Link to test plan if available

2. **Test Case Nodes**
   - ID: `test-case-{case-id}`
   - Include expected vs actual comparison
   - Link to requirements if traceable

3. **Measurement Nodes**
   - ID: `measurement-{measurement-id}`
   - Store value with unit
   - Include uncertainty if available
   - Flag out-of-spec values

4. **Cross-Source Linking**
   - Link to requirements via test case traceability
   - Link to design via verification matrix

## Output Format

```json
{
  "nodes": [...],
  "edges": [...],
  "statistics": {
    "testRunsProcessed": N,
    "testCasesProcessed": N,
    "measurementsProcessed": N,
    "crossLinksCreated": N
  }
}
```

Proceed with transformation.
