# Measurements Validation Prompt

You are validating test measurement data for ingestion into the BAM graph model.

## Context
- Source: Test/measurement database or files
- Purpose: Ensure data quality and validity

## Validation Rules

### 1. Required Fields
Every measurement record MUST have:
- `id`: Unique measurement identifier
- `timestamp`: When measurement was taken
- `value`: The measured value
- `unit`: Unit of measurement

### 2. Numeric Ranges
- Values should be within expected physical ranges
- No NaN or Infinity values (unless explicitly allowed)
- Precision should be appropriate for measurement type

### 3. Timestamp Validity
- Timestamps must be valid ISO format or Unix timestamp
- Timestamps should not be in the future
- Timestamps should be within expected test window

### 4. Referential Integrity
- Test case references should exist
- Equipment references should be valid
- Operator references should be valid

## Output Format

```json
{
  "valid": true/false,
  "recordsChecked": N,
  "errors": [
    {
      "recordId": "...",
      "field": "...",
      "issue": "..."
    }
  ],
  "warnings": [...],
  "statistics": {
    "valueRange": {"min": N, "max": N},
    "timeRange": {"start": "...", "end": "..."}
  }
}
```

Proceed with validation.
