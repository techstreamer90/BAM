# BAM Agent Onboarding Guide

This guide walks an AI agent through building a digital twin model with BAM.
The process is AI-driven with human collaboration at key decision points.

---

## The Four Phases

| Phase | Goal | AI Role | Human Role |
|-------|------|---------|------------|
| 1. Understand | Learn BAM concepts | Read docs | Answer questions |
| 2. Design Sketch | Define graph schema | Propose node/edge types | Approve/refine |
| 3. Configure Sources | Set up extraction | Analyze data, propose mappings | Approve mappings |
| 4. Extract & Ingest | Populate the model | Run extractors, ingest data | Review, approve changes |

---

## Phase 1: Understand BAM

**Goal:** Learn BAM's two-stage architecture.

### Key Concepts

1. **Sketch**: The graph structure (nodes + edges). Lightweight — just IDs, types, labels.
2. **Color**: Rich properties attached to nodes. Stored separately from sketch.
3. **Two-Stage Pipeline**:
   - **Stage 1 (Extraction)**: Source-specific extractors → Intermediate format
   - **Stage 2 (Ingestion)**: Intermediate format → Sketch + Color
4. **Intermediate Format**: Canonical JSON that all extractors produce. Reviewable.
5. **Source Mapping**: Configuration that tells extractors how to map source data.

### Architecture Overview

```
Source Files → [Extractor] → Intermediate JSON → [Ingester] → Sketch + Color
                   ↑                                  ↑
            Source Mapping                    Can propose sketch changes
         (configured in Phase 3)              (approved in Phase 4)
```

**Checkpoint:** You can explain the two-stage flow and why intermediate format exists.

---

## Phase 2: Design the Sketch

**Goal:** Define the graph schema with the human.

### Step 1: Interview About the Project

Ask the human:
- What does this project do? (domain context)
- What types of things do you track? (node types)
- What relationships matter? (edge types)
- What properties are important for each type?

### Step 2: Propose Node Types

Based on the interview, propose node types:

```
Example for a hardware project:
- DesignRequirement (status, priority, owner)
- RTLModule (parameters, ports, file_path)
- VerificationTest (status, pass_rate, coverage)
- CoverageItem (hits, goal, status)
```

### Step 3: Propose Edge Types

```
Example edges:
- TRACES_TO: Requirement → RTLModule
- IMPLEMENTS: RTLModule → Requirement
- VERIFIES: VerificationTest → Requirement
- MEASURES: CoverageItem → VerificationTest
- INSTANTIATES: RTLModule → RTLModule (hierarchy)
```

### Step 4: Create Initial Sketch

Either use a template from `src/bam/data/sketch_templates/` or create custom:

```json
{
  "version": "1.0.0",
  "metadata": {"node_count": 0, "edge_count": 0},
  "nodes": {},
  "edges": {},
  "node_types": ["DesignRequirement", "RTLModule", "VerificationTest"],
  "edge_types": ["TRACES_TO", "IMPLEMENTS", "VERIFIES", "INSTANTIATES"]
}
```

**Checkpoint:** `model/sketch.json` exists with agreed node/edge types.

---

## Phase 3: Configure Sources

**Goal:** For each data source, create a mapping configuration.

### Step 1: Identify Data Sources

Ask the human:
- What data sources exist? (RTL files, docs, requirements DB, etc.)
- Where is each source located?
- What format is each source?

### Step 2: Analyze Each Source

For each source, examine sample data:

```python
# Example: Analyzing SystemVerilog files
from bam.extractors import SystemVerilogExtractor

extractor = SystemVerilogExtractor('rtl-source')
result = extractor.extract_directory(Path('/path/to/rtl'))

# Show summary to human
print(f"Found: {result.item_count} items")
print(f"Types: {result.metadata.get('by_type', {})}")
```

### Step 3: Propose Source Mapping

Based on analysis, propose how source data maps to sketch:

```
SystemVerilog → Sketch Mapping:
- module → RTLModule
- interface → RTLInterface (new type needed?)
- class extends uvm_* → VerificationTest
- INSTANTIATES edges for module hierarchy
- IMPORTS edges for package dependencies
```

### Step 4: Handle New Types

If source data needs types not in sketch:
1. Propose adding new node/edge types
2. Get human approval
3. Update sketch with new types

### Step 5: Save Source Mapping

```json
{
  "source_type": "systemverilog",
  "source_id": "rtl-source",
  "node_mappings": [
    {"source_pattern": "module", "node_type": "RTLModule"},
    {"source_pattern": "class", "node_type": "VerificationClass"}
  ],
  "edge_mappings": [
    {"relationship": "INSTANTIATES", "edge_type": "INSTANTIATES"}
  ]
}
```

**Checkpoint:** `source_mappings/{source_id}.json` exists for each source.

---

## Phase 4: Extract & Ingest

**Goal:** Run the two-stage pipeline for each source.

### Stage 1: Extraction

Run the appropriate extractor:

```python
from bam.extractors import SystemVerilogExtractor

extractor = SystemVerilogExtractor('rtl-source')
result = extractor.extract_directory(Path('/path/to/rtl'))
intermediate = extractor.to_intermediate(result)

# Save for review
intermediate.save(Path('intermediate/rtl-source.json'))
```

**Tell the human:** "Extracted {N} nodes and {M} edges. Intermediate file ready for review."

### Review Point

Before ingestion, offer to show:
- Summary statistics
- Sample nodes/edges
- Any warnings from extraction

### Stage 2: Ingestion

Ingest into the sketch:

```python
from bam.extractors import IntermediateIngester

ingester = IntermediateIngester(Path('./project'))

# Dry run first
result = ingester.ingest(intermediate, dry_run=True)
print(f"Would add: {result.nodes_added} nodes, {result.edges_added} edges")

# If human approves, do real ingestion
result = ingester.ingest(intermediate)
```

### Handling Sketch Changes

If ingestion encounters unknown types:

```
AI: "The intermediate data has node type 'RTLInterface' which isn't in the sketch."
AI: "Options:
     1. Add RTLInterface as a new node type
     2. Map RTLInterface → RTLModule (merge types)
     3. Skip these nodes"
Human: "Add it as a new type"
AI: "Updated sketch with RTLInterface. Continuing ingestion..."
```

### Verification

After ingestion:

```bash
# Check model statistics
python -m bam --project ./project stats

# Verify structure
python -m bam --project ./project graph check
```

**Checkpoint:** Model populated, stats look correct, no errors.

---

## Quick Reference

### Intermediate Format

```json
{
  "format_version": "1.0",
  "source_id": "source-name",
  "nodes": [
    {"type": "NodeType", "external_id": "...", "label": "...", "properties": {...}}
  ],
  "edges": [
    {"type": "EDGE_TYPE", "source_external_id": "...", "target_external_id": "..."}
  ]
}
```

### Node ID Convention

All ingested node IDs follow: `{source_id}-{external_id}`

Example: `rtl-source-module-ibex_core`

### Edge ID Convention

Edge IDs follow: `{source_id}-{edge_type}-{source_external_id}-{target_external_id}`

### Available Extractors

| Extractor | File Types | Use For |
|-----------|------------|---------|
| `SystemVerilogExtractor` | `.sv`, `.v` | RTL, testbenches |
| `RequirementsExtractor` | `.xlsx`, `.csv` | Design requirements in spreadsheets |
| *(planned)* `PDFExtractor` | `.pdf` | Specifications, requirements |
| *(planned)* `WordExtractor` | `.docx` | Design documents |

---

## Troubleshooting

### "Unknown node type" during ingestion

The intermediate data has a type not in the sketch. Options:
1. Add the type to sketch
2. Edit intermediate file to use existing type
3. Update source mapping to map to existing type

### "Edge references unknown node"

The edge points to a node not yet ingested. Options:
1. Ingest the source containing that node first
2. Create placeholder node in sketch
3. Skip edge (will be a warning)

### Extraction produces unexpected results

1. Check the source mapping configuration
2. Review extractor output with `--verbose`
3. Examine intermediate file directly
4. Adjust mapping and re-extract

---

## Files Reference

| File | Location | Purpose |
|------|----------|---------|
| `model/sketch.json` | `<project>/model/` | Graph structure |
| `model/colors/*.json` | `<project>/model/colors/` | Node properties |
| `source_mappings/*.json` | `<project>/source_mappings/` | Extraction config |
| `intermediate/*.json` | `<project>/intermediate/` | Extracted data (reviewable) |
| `sources.json` | `<project>/` | Data source registry |
| `ingestion_plan.json` | `<project>/` | Ingestion order |
