# Codebase Transformation Prompt

You are transforming source code into BAM graph model nodes and edges.

## Node Mapping

| Code Element | Graph Node Type | Properties |
|-------------|-----------------|------------|
| Module/File | CodeModule | path, language, lines |
| Class | CodeClass | name, docstring, methods-count |
| Function | CodeFunction | name, signature, docstring |
| Interface | CodeInterface | name, methods |

## Edge Mapping

| Relationship | Edge Type | Direction |
|-------------|-----------|-----------|
| Import | IMPORTS | importer -> imported |
| Inheritance | EXTENDS | child -> parent |
| Implementation | IMPLEMENTS | class -> interface |
| Contains | CONTAINS | module -> class/function |
| Calls | CALLS | caller -> callee |

## Transformation Rules

1. **Module Nodes**
   - ID: `code-module-{normalized-path}`
   - Detect language from extension/content
   - Count lines of code

2. **Class Nodes**
   - ID: `code-class-{module-id}-{class-name}`
   - Extract docstring/comments
   - List method names

3. **Function Nodes**
   - ID: `code-func-{module-id}-{func-name}`
   - Parse signature (parameters, return type)
   - Extract docstring

4. **Relationship Extraction**
   - Parse import statements
   - Identify class hierarchies
   - Track function calls (static analysis)

## Output Format

```json
{
  "nodes": [...],
  "edges": [...],
  "statistics": {
    "modulesProcessed": N,
    "classesFound": N,
    "functionsFound": N,
    "relationshipsFound": N
  }
}
```

Proceed with transformation.
