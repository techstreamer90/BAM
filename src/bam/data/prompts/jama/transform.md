# JAMA Data Transformation Prompt

You are transforming validated JAMA data into BAM graph model nodes and edges.

## Context
- Source: JAMA Requirements Management System
- Target: BAM Graph Model (nodes and edges)
- Purpose: Convert hierarchical requirements into graph structure

## Node Mapping

| JAMA Item Type | Graph Node Type | Properties to Extract |
|----------------|-----------------|----------------------|
| requirement | Requirement | id, name, description, status, priority |
| specification | Specification | id, name, description, version |
| test-case | TestCase | id, name, steps, expected-result |
| use-case | UseCase | id, name, actors, preconditions |

## Edge Mapping

| JAMA Relationship | Graph Edge Type | Direction |
|-------------------|-----------------|-----------|
| derivesFrom | DERIVES_FROM | child -> parent |
| satisfies | SATISFIES | impl -> req |
| verifies | VERIFIES | test -> req |
| allocatedTo | ALLOCATED_TO | req -> component |

## Transformation Rules

1. **Node Creation**
   - Generate stable node IDs: `jama-{itemType}-{jamaId}`
   - Preserve original JAMA ID in `source_ref` property
   - Set `source_id` to "jama-requirements"
   - Map all relevant properties

2. **Edge Creation**
   - Generate stable edge IDs: `jama-{relType}-{sourceId}-{targetId}`
   - Validate both endpoints exist
   - Include relationship metadata if available

3. **Hierarchy Preservation**
   - Convert parent-child to CONTAINS edges
   - Maintain document structure via PART_OF edges

## Output Format

```json
{
  "nodes": [
    {
      "id": "jama-requirement-12345",
      "type": "Requirement",
      "label": "<name>",
      "properties": {...},
      "source_id": "jama-requirements",
      "source_ref": "12345"
    }
  ],
  "edges": [
    {
      "id": "jama-derives-12345-12340",
      "type": "DERIVES_FROM",
      "source_node_id": "jama-requirement-12345",
      "target_node_id": "jama-requirement-12340",
      "source_id": "jama-requirements"
    }
  ],
  "statistics": {
    "nodesCreated": <count>,
    "edgesCreated": <count>,
    "skipped": <count>,
    "warnings": [...]
  }
}
```

## Instructions

1. Process each validated JAMA item
2. Create corresponding graph node with proper type mapping
3. Process all relationships into edges
4. Report transformation statistics
5. Flag any items that couldn't be transformed

Proceed with transformation of the provided validated data.
