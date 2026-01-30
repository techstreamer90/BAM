# JAMA Data Validation Prompt

You are validating JAMA requirements data for ingestion into the BAM graph model.

## Context
- Source: JAMA Requirements Management System
- Data Type: Requirements and Specifications
- Purpose: Ensure data quality before graph integration

## Validation Rules

### 1. Required Fields
Every requirement item MUST have:
- `id`: Unique JAMA item ID
- `name`: Human-readable title
- `documentKey`: Document reference key
- `itemType`: Type classification (requirement, specification, etc.)

### 2. Relationship Integrity
- All `derivesFrom` references must point to valid item IDs
- All `satisfiedBy` references must point to valid item IDs
- No circular dependencies allowed
- Parent-child relationships must be consistent

### 3. No Orphans
- Every item (except root) must have at least one parent relationship
- Items marked as "derived" must have a `derivesFrom` relationship
- Items marked as "satisfied" must have a `satisfiedBy` relationship

## Validation Output Format

```json
{
  "valid": true/false,
  "itemsChecked": <count>,
  "errors": [
    {
      "severity": "critical|error|warning",
      "itemId": "<id>",
      "rule": "<rule-name>",
      "message": "<description>"
    }
  ],
  "warnings": [...],
  "summary": "<brief summary>"
}
```

## Instructions

1. Check each item against the required fields
2. Validate all relationships exist and are valid
3. Identify orphaned items
4. Report findings with appropriate severity levels
5. Halt on critical errors, continue with warnings

Proceed with validation of the provided data.
