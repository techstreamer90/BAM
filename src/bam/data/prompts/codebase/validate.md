# Codebase Validation Prompt

You are validating source code for ingestion into the BAM graph model.

## Context
- Source: Git repository / source code files
- Purpose: Ensure code is parseable and analyzable

## Validation Rules

### 1. Syntax Validity
- Files must have valid syntax for their language
- No fatal parse errors
- Encoding must be valid (UTF-8 preferred)

### 2. Structure
- Files should follow standard module/package structure
- Import statements should be resolvable (within scope)
- No circular imports at module level

### 3. Language Detection
- File extension should match content
- Language version should be identifiable
- Framework/library patterns should be recognizable

## Supported Languages
- Python (.py)
- TypeScript/JavaScript (.ts, .tsx, .js, .jsx)
- Java (.java)
- C/C++ (.c, .cpp, .h, .hpp)

## Output Format

```json
{
  "valid": true/false,
  "filesChecked": N,
  "byLanguage": {"python": N, "typescript": N, ...},
  "errors": [...],
  "warnings": [...]
}
```

Proceed with validation.
