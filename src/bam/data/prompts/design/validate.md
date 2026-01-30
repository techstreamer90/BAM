# Design Document Validation Prompt

You are validating design documents for ingestion into the BAM graph model.

## Context
- Source: Design Documents (PDF, DOCX, XLSX)
- Purpose: Ensure document integrity and parseability

## Validation Rules

### 1. File Integrity
- File must be readable and not corrupted
- File format must match extension
- File must not be password protected

### 2. Content Requirements
- Document must have identifiable title or header
- Document should contain structured content (sections, tables, figures)
- Document should have parseable text (not just images)

### 3. Metadata
- Creation/modification dates should be valid
- Author information if available
- Version information if available

## Output Format

```json
{
  "valid": true/false,
  "filesChecked": <count>,
  "errors": [...],
  "warnings": [...],
  "metadata": {
    "totalSize": <bytes>,
    "fileTypes": {"pdf": N, "docx": N, ...}
  }
}
```

Proceed with validation.
