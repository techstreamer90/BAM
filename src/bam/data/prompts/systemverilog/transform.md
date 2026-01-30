# SystemVerilog Transformation Rules

## Overview
Transforms extracted SystemVerilog data into BAM graph nodes and edges.

## Node Type Mapping

| Source Type | BAM Node Type | Color |
|-------------|---------------|-------|
| RTLModule | RTLModule | design |
| RTLInterface | RTLInterface | design |
| RTLPackage | RTLPackage | design |
| VerificationClass | VerificationClass | verification |

## Node ID Patterns

Generate deterministic IDs using these patterns:

| Node Type | ID Pattern | Example |
|-----------|------------|---------|
| RTLModule | `{source_id}-module-{name}` | `ibex-rtl-module-ibex_core` |
| RTLInterface | `{source_id}-interface-{name}` | `ibex-rtl-interface-axi_if` |
| RTLPackage | `{source_id}-package-{name}` | `ibex-rtl-package-ibex_pkg` |
| VerificationClass | `{source_id}-class-{name}` | `ibex-dv-class-ibex_scoreboard` |

## Node Properties

### RTLModule Properties
```json
{
  "id": "{source_id}-module-{name}",
  "type": "RTLModule",
  "label": "{name}",
  "source_id": "{source_id}",
  "source_ref": "{name}",
  "properties": {
    "file_path": "...",
    "line_number": 1,
    "parameter_count": 0,
    "port_count": 0,
    "input_count": 0,
    "output_count": 0,
    "instance_count": 0
  }
}
```

### VerificationClass Properties
```json
{
  "id": "{source_id}-class-{name}",
  "type": "VerificationClass",
  "label": "{name}",
  "source_id": "{source_id}",
  "source_ref": "{name}",
  "properties": {
    "file_path": "...",
    "extends": "parent_class_name",
    "functions": ["func1", "func2"],
    "tasks": ["task1", "task2"]
  }
}
```

## Edge Type Mapping

| Relationship | BAM Edge Type | Description |
|--------------|---------------|-------------|
| INSTANTIATES | INSTANTIATES | Module A instantiates Module B |
| IMPORTS | IMPORTS | Module imports a package |
| EXTENDS | EXTENDS | Class extends parent class |
| CONTAINS | CONTAINS | Module contains function/task (implicit) |

## Edge ID Patterns

| Edge Type | ID Pattern |
|-----------|------------|
| INSTANTIATES | `{source_id}-inst-{source_module}-{target_module}-{instance_name}` |
| IMPORTS | `{source_id}-import-{source}-{target_package}` |
| EXTENDS | `{source_id}-extends-{child_class}-{parent_class}` |

## Transformation Rules

### 1. Module Instantiation Edges
For each module with `properties.instantiates`:
```
source_node_id: {source_id}-module-{module_name}
target_node_id: {source_id}-module-{instantiated_module}
edge_type: INSTANTIATES
```

Note: If the target module is not in the current source (external IP), create the edge anyway. The target node may be added later or left as a reference.

### 2. Import Edges
For each import in `properties.imports`:
```
source_node_id: {source_id}-module-{module_name}
target_node_id: {source_id}-package-{package_name}
edge_type: IMPORTS
```

### 3. Inheritance Edges
For each class with `properties.extends`:
```
source_node_id: {source_id}-class-{class_name}
target_node_id: {source_id}-class-{parent_class}
edge_type: EXTENDS
```

## Cross-References

The extractor provides a `relationships` array with pre-computed relationships. Use these directly when available:

```json
{
  "type": "INSTANTIATES",
  "source": "ibex_core",
  "target": "ibex_if_stage",
  "instance_name": "if_stage_i"
}
```

Transform to edge:
```json
{
  "id": "{source_id}-inst-ibex_core-ibex_if_stage-if_stage_i",
  "type": "INSTANTIATES",
  "source_node_id": "{source_id}-module-ibex_core",
  "target_node_id": "{source_id}-module-ibex_if_stage",
  "properties": {
    "instance_name": "if_stage_i"
  }
}
```

## Output Format

```json
{
  "nodes": [...],
  "edges": [...],
  "metadata": {
    "source_id": "...",
    "transform_timestamp": "...",
    "node_count": 0,
    "edge_count": 0
  }
}
```
