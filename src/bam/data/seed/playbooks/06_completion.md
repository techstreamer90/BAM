# Playbook 06: Completion

## Purpose

Summarize the two-phase sketch creation process and guide next steps.

## Completion Summary

```
"Model creation complete!

**Project:** {projectName}
**Location:** {projectDir}

## What Happened

### Phase 1: Structure Discovery
- Spawned AI for each input folder
- Each AI analyzed their folder and proposed sketch structure
- Consolidated proposals into unified schema
- You approved the node types and edge types

### Phase 2: Coloring
- Spawned AI for each input folder (with full sketch context)
- Each AI populated the model with actual data
- Created nodes, edges, and semantic connections
- Merged all results into final model

## Model Statistics

| Metric | Value |
|--------|-------|
| Node Types | {node_type_count} |
| Edge Types | {edge_type_count} |
| Total Nodes | {node_count} |
| Total Edges | {edge_count} |
| Sources | {source_count} |

## Files Created

```
{projectDir}/
├── project_input/              # Your source data (unchanged)
├── workflows/
│   ├── sketch_structure.json   # Phase 1 workflow
│   └── sketch_coloring.json    # Phase 2 workflow
├── model/
│   ├── sketch.json             # Complete model with nodes & edges
│   └── semantic_notes.json     # AI observations for future agents
└── extraction_results/
    └── *.json                  # Raw outputs from each AI spawn
```

## Semantic Notes

The coloring AIs captured these observations:

{semantic_notes from each AI}

These notes help future agents understand the model context.
"
```

## What the Model Enables

Now that the model is populated:

### Query Examples
```bash
# Find all requirements
python -m bam graph find --type Requirement

# What does REQ-001 trace to?
python -m bam graph traverse --from REQ-001 --edge TRACES_TO

# What implements DR-050?
python -m bam graph traverse --to DR-050 --edge IMPLEMENTS

# Full trace: requirement → design → implementation
python -m bam graph path --from REQ-001 --to top_module
```

### Future Agent Queries
Future agents can:
- Ask "What modules implement security requirements?"
- Ask "Show me the test coverage for the crypto subsystem"
- Navigate relationships to understand impact
- Use semantic notes for context

## Re-running the Process

If source data changes:

```bash
# Re-run Phase 1 (if structure changes)
spawnie workflow workflows/sketch_structure.json -i project_dir=.

# Re-run Phase 2 (to update data)
spawnie workflow workflows/sketch_coloring.json \
  -i project_dir=. \
  --inputs-json '{"sketch_schema": ...}'
```

## Spawnie Tips

```bash
# Monitor any workflow
spawnie monitor

# Take screenshots for documentation
# (Press 's' in monitor)

# Check workflow history
spawnie status

# Kill a stuck workflow
spawnie kill wf-{id}
```

## Next Steps

1. **Query the model** — explore what's there
2. **Add more sources** — create new input folders, re-run
3. **Refine semantic connections** — update coloring prompts
4. **Build on top** — use the model for impact analysis, coverage, etc.

## Agent Notes

- The model is now queryable by other agents
- Semantic notes provide context beyond raw data
- Workflows are saved and reproducible
- The sketch can evolve — add types as needed
