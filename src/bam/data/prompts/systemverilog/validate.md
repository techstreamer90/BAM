# SystemVerilog Data Validation

## Overview
Validates extracted SystemVerilog/Verilog data from the SystemVerilog extractor.

## Expected Data Structure

The extractor produces JSON with:
```json
{
  "fetchedAt": "ISO timestamp",
  "source": "source-id",
  "extractor": "systemverilog",
  "items": [...],
  "relationships": [...]
}
```

## Item Types

### RTLModule
Required fields:
- `id`: Unique identifier (format: `module-{name}`)
- `name`: Module name (valid SystemVerilog identifier)
- `type`: Must be "RTLModule"
- `file_path`: Path to source file

Optional fields:
- `properties.parameters`: List of module parameters
- `properties.ports`: List of port declarations
- `properties.imports`: Package imports
- `properties.instantiates`: List of instantiated modules

### RTLInterface
Required fields:
- `id`: Unique identifier (format: `interface-{name}`)
- `name`: Interface name
- `type`: Must be "RTLInterface"
- `file_path`: Path to source file

### RTLPackage
Required fields:
- `id`: Unique identifier (format: `package-{name}`)
- `name`: Package name
- `type`: Must be "RTLPackage"
- `file_path`: Path to source file

### VerificationClass
Required fields:
- `id`: Unique identifier (format: `class-{name}`)
- `name`: Class name
- `type`: Must be "VerificationClass"
- `file_path`: Path to source file

Optional fields:
- `properties.extends`: Parent class name

## Relationship Types

### INSTANTIATES
- Source: Module that contains the instantiation
- Target: Module being instantiated
- Required: `source`, `target`, `type`

### IMPORTS
- Source: Module/package that imports
- Target: Package being imported
- Required: `source`, `target`, `type`

### EXTENDS
- Source: Child class
- Target: Parent class
- Required: `source`, `target`, `type`

## Validation Rules

1. **Unique IDs**: All items must have unique `id` values
2. **Valid Names**: Names must be valid SystemVerilog identifiers (`[a-zA-Z_][a-zA-Z0-9_]*`)
3. **File Paths**: All items must reference a valid `file_path`
4. **Relationship Integrity**: Relationship sources and targets should reference existing items
5. **Type Consistency**: Item `type` must match one of the defined node types

## Output Format

```json
{
  "valid": true|false,
  "errors": [
    {"severity": "error", "item_id": "...", "message": "..."}
  ],
  "warnings": [
    {"severity": "warning", "item_id": "...", "message": "..."}
  ]
}
```
