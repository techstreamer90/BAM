# SystemVerilog Consistency Checks

## Overview
Verifies consistency of SystemVerilog data after integration into the BAM graph.

## Structural Checks

### 1. Module Hierarchy Integrity
- All INSTANTIATES edges should have valid source and target nodes
- No circular instantiation dependencies (A→B→C→A)
- Top-level modules should have no incoming INSTANTIATES edges

### 2. Package Import Integrity
- All IMPORTS edges should reference existing package nodes
- Packages should not import themselves

### 3. Class Hierarchy Integrity
- All EXTENDS edges should have valid target (parent) nodes
- No circular inheritance (A extends B extends A)
- Verify base classes exist (or mark as external reference)

## Content Checks

### 1. Naming Conventions
- Module names should follow project conventions (e.g., `{prefix}_*`)
- Interface names typically end with `_if` or `_intf`
- Package names typically end with `_pkg`
- Class names typically use CamelCase or snake_case

### 2. File Organization
- Each file should contain at most one primary entity (module/interface/package)
- File names should match entity names (e.g., `ibex_core.sv` contains `ibex_core`)

### 3. Port Completeness
- Modules should have clock (`clk*`) and reset (`rst*`) ports
- Input/output counts should be reasonable for the module type

## Cross-Reference Checks

### 1. Design-Verification Traceability
- Testbench modules should reference DUT modules
- Verification classes should have corresponding interfaces

### 2. External References
- Track references to modules/packages not in the current source
- Flag as "external" or "missing" for follow-up

## Output Format

```json
{
  "consistent": true|false,
  "checks": [
    {
      "name": "module_hierarchy",
      "status": "pass|fail|warning",
      "details": "..."
    }
  ],
  "issues": [
    {
      "severity": "error|warning|info",
      "type": "missing_reference|circular_dependency|naming_violation",
      "entities": ["entity1", "entity2"],
      "message": "Description of the issue"
    }
  ],
  "statistics": {
    "modules": 30,
    "interfaces": 5,
    "packages": 2,
    "classes": 50,
    "instantiation_edges": 100,
    "import_edges": 20,
    "inheritance_edges": 45,
    "external_references": 5
  }
}
```

## Severity Levels

| Level | Action |
|-------|--------|
| error | Blocks pipeline, requires resolution |
| warning | Logged, pipeline continues |
| info | Informational, no action required |
