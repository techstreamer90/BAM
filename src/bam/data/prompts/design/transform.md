# Design Document Transformation Prompt

You are transforming design documents into BAM graph model nodes and edges.

## Node Mapping

| Document Element | Graph Node Type | Properties |
|-----------------|-----------------|------------|
| Document | DesignDocument | title, author, version, path |
| Section | DesignSection | heading, level, content-summary |
| Figure | Figure | caption, type, page |
| Table | DesignTable | caption, rows, columns |

## Edge Mapping

| Relationship | Edge Type | Direction |
|-------------|-----------|-----------|
| Section in Document | CONTAINS | doc -> section |
| Figure in Section | CONTAINS | section -> figure |
| Cross-reference | REFERENCES | source -> target |

## Transformation Rules

1. **Document Node**
   - ID: `design-doc-{hash of path}`
   - Extract title from first heading or filename
   - Capture file metadata as properties

2. **Section Nodes**
   - ID: `design-section-{doc-hash}-{section-number}`
   - Preserve hierarchy via level property
   - Summarize content (first 200 chars)

3. **Figure/Table Nodes**
   - ID: `design-{type}-{doc-hash}-{number}`
   - Capture caption text
   - Note page/location

## Output Format

```json
{
  "nodes": [...],
  "edges": [...],
  "statistics": {
    "documentsProcessed": N,
    "sectionsExtracted": N,
    "figuresExtracted": N
  }
}
```

Proceed with transformation.
