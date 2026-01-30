# {project_name} — BAM Project

This directory is a **BAM project** — a self-contained graph model (digital
twin) built from project artifacts such as requirements, design documents,
source code, and test data.

**Backend:** `{backend}` | **Created:** {created_at}

---

## For AI Agents

If you are an AI agent asked to work with this project, start here.

### Quick Orientation

1. **Read this file** to understand the project structure and available commands.
2. **Read `sources.json`** for configured data sources.
3. **Check intermediate files**: `intermediate/*.json` for extracted data.
4. **Check current model state**: `python -m bam --project . stats`

### What BAM Is

BAM (Build Accurate Models) creates multi-layered graph models from existing
project artifacts. It does NOT create the artifacts — it reads them and builds
a navigable graph that connects requirements to design to verification to
measurements.

### The Two-Stage Architecture

BAM uses a two-stage, AI-driven approach:

```
Stage 1: EXTRACTION
Source Files → [Extractor] → Intermediate Format (reviewable JSON)

Stage 2: INGESTION
Intermediate Format → [Ingester] → Sketch (structure) + Color (properties)
```

The model has two layers:
- **Sketch** — lightweight structural graph (node ID, type, label, edges).
  Always JSON. Lives in `model/sketch.json`.
- **Color** — rich properties stored per source. Each source's color data
  lives in `model/colors/{source_id}.json`.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Sketch** | The structural backbone: nodes (id, type, label) and edges (type, source, target). |
| **Color** | A property layer that holds rich data for each node (parameters, metadata, content). |
| **Intermediate Format** | Canonical JSON that extractors produce. Reviewable before ingestion. |
| **Source Mapping** | Configuration that tells extractors how to map source data to the sketch. |
| **Extractor** | Stage 1 component that parses source files into intermediate format. |
| **Ingester** | Stage 2 component that loads intermediate data into sketch + color. |

---

## Project Files

| File | Purpose |
|------|---------|
| `project.json` | Project configuration |
| `sources.json` | Data source definitions (name, type, location, format) |
| `source_mappings/` | Source mapping configs (one per source) |
| `intermediate/` | Extracted data (reviewable before ingestion) |
| `model/sketch.json` | The graph sketch (nodes, edges, types) |
| `model/colors/` | Color (property) data per source |

---

## Workflow Phases

### Phase 1: Setup (already done if you're reading this)

The project has been created. Review `sources.json` and `model/sketch.json`
to understand what sources and node/edge types are configured.

### Phase 2: Extraction (Stage 1)

Run extractors for each data source:

```python
from bam.extractors import SystemVerilogExtractor
from pathlib import Path

extractor = SystemVerilogExtractor('{source_id}')
result = extractor.extract_directory(Path('{source_path}'))
intermediate = extractor.to_intermediate(result)
intermediate.save(Path('intermediate/{source_id}.json'))
```

Or via CLI:
```bash
python -m bam extract systemverilog \
  --source-id {source_id} \
  --path {source_path} \
  --output intermediate/{source_id}.json
```

### Phase 3: Review (Optional)

Review the intermediate files before ingestion:
- Check `intermediate/{source_id}.json`
- Verify nodes and edges look correct
- Edit if needed

### Phase 4: Ingestion (Stage 2)

Ingest intermediate data into the model:

```python
from bam.extractors import IntermediateIngester, IntermediateData
from pathlib import Path

intermediate = IntermediateData.load(Path('intermediate/{source_id}.json'))
ingester = IntermediateIngester(Path('.'))

# Dry run first
result = ingester.ingest(intermediate, dry_run=True)
print(f"Would add: {result.nodes_added} nodes, {result.edges_added} edges")

# Real ingestion
result = ingester.ingest(intermediate)
```

Or via CLI:
```bash
# Dry run
python -m bam ingest \
  --project . \
  --intermediate intermediate/{source_id}.json \
  --dry-run

# Real ingestion
python -m bam ingest \
  --project . \
  --intermediate intermediate/{source_id}.json
```

### Phase 5: Verify

Check the model:

```bash
python -m bam --project . stats           # Model statistics
python -m bam --project . graph check     # Verify structure
python -m bam --project . graph find --type RTLModule  # Query nodes
```

---

## Available Extractors

| Extractor | File Types | Node Types Produced |
|-----------|------------|---------------------|
| `SystemVerilogExtractor` | `.sv`, `.v` | RTLModule, RTLInterface, RTLPackage, VerificationClass |
| *(planned)* `PDFExtractor` | `.pdf` | Document sections, requirements |
| *(planned)* `WordExtractor` | `.docx` | Document sections, requirements |
| *(planned)* `JamaExtractor` | Jama API | Requirements, specifications |

---

## Handling Sketch Changes

During ingestion, if the intermediate data has types not in the sketch:

1. **Ingester reports the missing types**
2. **Options:**
   - Add the new type to sketch
   - Map to an existing type
   - Skip those items

Example:
```
AI: "The intermediate data has node type 'RTLInterface' which isn't in
     the sketch. Should I add it?"
Human: "Yes, add it"
AI: "Added RTLInterface to sketch. Continuing..."
```

---

## Sketch Format Reference

### Node Format
```json
{
  "node-id": {
    "id": "node-id",
    "type": "RTLModule",
    "label": "ibex_core",
    "source_id": "my-rtl"
  }
}
```

### Edge Format
```json
{
  "edge-id": {
    "id": "edge-id",
    "type": "INSTANTIATES",
    "source_node_id": "module-ibex_core",
    "target_node_id": "module-ibex_if_stage",
    "source_id": "my-rtl"
  }
}
```

### Node ID Convention

Ingested node IDs follow: `{source_id}-{external_id}`

Example: `my-rtl-module-ibex_core`

### Edge ID Convention

Edge IDs follow: `{source_id}-{edge_type}-{source_external_id}-{target_external_id}`

---

## CLI Reference

```bash
# Project info
python -m bam --project . info
python -m bam --project . stats

# Extraction
python -m bam extract systemverilog --source-id <id> --path <path> --output <file>

# Ingestion
python -m bam ingest --project . --intermediate <file>
python -m bam ingest --project . --intermediate <file> --dry-run

# Graph queries
python -m bam --project . graph find --type <NodeType>
python -m bam --project . graph check
```
