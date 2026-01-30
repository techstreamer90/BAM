# BAM Architecture

A framework for building "digital twin" graph models through AI-driven data extraction and ingestion.

## Overview

BAM uses a **two-stage, AI-driven approach** to build graph models from diverse data sources:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 1: EXTRACTION (AI-Driven)                     │
│                                                                             │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐               │
│  │SystemVeri-│  │    PDF    │  │   Word    │  │   Jama    │  ...          │
│  │   log     │  │ Extractor │  │ Extractor │  │ Extractor │               │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               │
│        │              │              │              │                      │
│        └──────────────┴──────────────┴──────────────┘                      │
│                              │                                              │
│                              ▼                                              │
│                 ┌─────────────────────────┐                                │
│                 │   Intermediate Format   │  ← Canonical JSON              │
│                 │   (nodes + edges)       │    Reviewable by AI/human      │
│                 └─────────────────────────┘                                │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         STAGE 2: INGESTION (AI-Driven)                      │
│                                                                             │
│                 ┌─────────────────────────┐                                │
│                 │  IntermediateIngester   │                                │
│                 │  (validates, proposes   │                                │
│                 │   sketch changes)       │                                │
│                 └───────────┬─────────────┘                                │
│                             │                                               │
│               ┌─────────────┴─────────────┐                                │
│               ▼                           ▼                                 │
│      ┌──────────────┐            ┌──────────────┐                          │
│      │    Sketch    │            │    Color     │                          │
│      │ (structure)  │            │ (properties) │                          │
│      └──────────────┘            └──────────────┘                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Concepts

- **Sketch**: The graph structure — nodes (components, documents, tests) and edges (relationships). Lightweight, contains only IDs, types, labels, and connections.
- **Color**: Detailed properties attached to sketch nodes, organized by source. Rich data like descriptions, parameters, metadata.
- **Intermediate Format**: The canonical JSON format that all extractors produce. Human/AI reviewable before ingestion.
- **Source Mapping**: Configuration (created during sketch design) that tells extractors how to map source data to the intermediate format.

### Why Two Stages?

1. **Source diversity**: Different sources (SystemVerilog, PDFs, Jama, Word docs) need specialized extractors
2. **Single ingestion logic**: Stage 2 is written once and works with any intermediate data
3. **Review point**: Intermediate format can be inspected/modified before ingestion
4. **AI flexibility**: AI can propose sketch changes during ingestion if data doesn't fit current schema

---

## Directory Structure

```
C:\BAM\
├── README.md                   # Project overview
├── pyproject.toml              # Package config
├── docs/
│   ├── README.md               # This architecture doc
│   ├── agent_guide.md          # Agent onboarding guide
│   └── mission.md              # Project mission
│
├── src/bam/                    # Python package
│   ├── cli.py                  # bam CLI entry point
│   ├── project.py              # Project init/load
│   ├── graph_manager.py        # Graph operations
│   ├── orchestrator.py         # Pipeline orchestration
│   ├── stage_runner.py         # Stage execution
│   │
│   ├── extractors/             # ★ TWO-STAGE EXTRACTION SYSTEM ★
│   │   ├── base.py             # BaseExtractor class
│   │   ├── intermediate.py     # IntermediateData, SourceMapping
│   │   ├── ingest.py           # IntermediateIngester (Stage 2)
│   │   └── systemverilog.py    # SystemVerilog extractor
│   │
│   ├── llm/                    # LLM provider abstraction
│   │   ├── provider.py         # Abstract LLMProvider interface
│   │   ├── claude_provider.py  # Claude implementation
│   │   └── factory.py          # Provider factory
│   │
│   ├── backends/               # Storage backend system
│   │   ├── sketch.py           # SketchManager (graph structure)
│   │   ├── model_manager.py    # ModelManager (orchestrates all)
│   │   ├── color_manager.py    # ColorManager (routes by node type)
│   │   └── *_color_backend.py  # JSON, SQLite, Neo4j, Arango
│   │
│   └── data/                   # Shared tool data
│       ├── pipelines/          # Pipeline definitions
│       ├── prompts/            # AI prompts per source type
│       ├── sketch_templates/   # Sketch templates
│       └── seed/               # Seed playbooks, profiles, checklists
│
├── tests/                      # Test suite
│
└── <project_dir>/              # ★ PER-PROJECT DATA ★
    ├── project.json            # Project config
    ├── sources.json            # Data source registry
    ├── source_mappings/        # Source mapping configs (per source)
    ├── intermediate/           # Intermediate format files (reviewable)
    ├── ingestion_plan.json     # Ingestion plan
    │
    └── model/                  # ★ THE GRAPH MODEL ★
        ├── sketch.json         # Graph structure (nodes, edges, types)
        └── colors/             # Color layer storage (properties)
```

---

## The AI-Driven Workflow

### Phase 1: Sketch Design (AI + Human)

The AI helps design the project's graph schema:

```
AI: "What kinds of things do you track in this project?"
Human: "Design requirements, RTL modules, verification tests, coverage"

AI: "What relationships matter between them?"
Human: "Requirements trace to RTL, tests verify requirements, coverage measures tests"

AI: "I'll create a sketch with these node types:
     - DesignRequirement (properties: status, priority, owner)
     - RTLModule (properties: parameters, ports)
     - VerificationTest (properties: status, pass_rate)
     - CoverageItem (properties: hits, goal)

     And these edge types:
     - TRACES_TO, IMPLEMENTS, VERIFIES, MEASURES"
```

**Output**: `model/sketch.json` with node types, edge types, and initial structure.

### Phase 2: Source Mapping (AI + Human)

For each data source, the AI analyzes the data and proposes how to map it:

```
AI: "I see you have SystemVerilog files. Let me analyze them..."
AI: "I found modules, interfaces, packages, and classes."
AI: "I propose this mapping:
     - module → RTLModule
     - interface → RTLInterface
     - class (extends uvm_*) → VerificationTest
     - INSTANTIATES edges for module hierarchy"
```

**Output**: `source_mappings/{source_id}.json` with mapping configuration.

### Phase 3: Extraction (AI-Driven)

The AI runs extractors to produce intermediate format:

```
AI: "Running SystemVerilog extractor on /path/to/rtl..."
AI: "Extracted 30 modules, 2 packages, 129 relationships"
AI: "Intermediate file saved to intermediate/rtl_extract.json"
AI: "Would you like to review before ingestion?"
```

**Output**: `intermediate/{source_id}.json` — reviewable canonical format.

### Phase 4: Ingestion (AI-Driven)

The AI ingests intermediate data, proposing sketch changes if needed:

```
AI: "Ingesting intermediate/rtl_extract.json..."
AI: "Found node type 'RTLInterface' not in sketch."
AI: "Proposal: Add RTLInterface as a new node type?"
Human: "Yes, add it"
AI: "Updated sketch. Continuing ingestion..."
AI: "Ingested 30 nodes, 74 edges into sketch + color layers."
```

**Output**: Updated `model/sketch.json` and `model/colors/{source_id}.json`.

---

## Intermediate Format

The canonical format that all extractors produce:

```json
{
  "format_version": "1.0",
  "source_id": "my-rtl",
  "source_type": "systemverilog",
  "extracted_at": "2026-01-30T...",

  "nodes": [
    {
      "type": "RTLModule",
      "external_id": "module-ibex_core",
      "label": "ibex_core",
      "properties": {"parameters": [...], "ports": [...]},
      "content": "Top level module of the ibex RISC-V core",
      "source_location": "rtl/ibex_core.sv:16"
    }
  ],

  "edges": [
    {
      "type": "INSTANTIATES",
      "source_external_id": "module-ibex_core",
      "target_external_id": "module-ibex_if_stage",
      "properties": {"instance_name": "if_stage_i"}
    }
  ],

  "summary": {
    "node_count": 30,
    "edge_count": 74,
    "node_types": {"RTLModule": 28, "RTLPackage": 2},
    "edge_types": {"INSTANTIATES": 63, "IMPORTS": 11}
  }
}
```

### Why This Format?

- **Type-aware**: Node/edge types must match sketch schema
- **External IDs**: Source system IDs preserved for traceability
- **Properties**: Arbitrary data — sketch defines what's expected
- **Reviewable**: Human or AI can inspect/edit before ingestion
- **Summary**: Quick stats for validation

---

## Sketch vs Color Separation

The model uses a two-layer architecture:

| Layer | Contains | Storage | Purpose |
|-------|----------|---------|---------|
| **Sketch** | IDs, types, labels, edges | `model/sketch.json` | Fast graph traversal |
| **Color** | Properties, content, metadata | `model/colors/*.json` | Rich queryable data |

**Example Sketch Node:**
```json
{
  "id": "my-rtl-module-ibex_core",
  "type": "RTLModule",
  "label": "ibex_core",
  "source_id": "my-rtl"
}
```

**Example Color Data (same node):**
```json
{
  "id": "my-rtl-module-ibex_core",
  "properties": {
    "parameters": [{"name": "PMPEnable", "default": "1'b0"}],
    "ports": [{"name": "clk_i", "direction": "input"}],
    "category": "rtl"
  },
  "content": "Top level module of the ibex RISC-V core",
  "source_location": "rtl/ibex_core.sv:16"
}
```

---

## Available Extractors

| Extractor | Source Type | Node Types Produced |
|-----------|-------------|---------------------|
| `SystemVerilogExtractor` | `.sv`, `.v` files | RTLModule, RTLInterface, RTLPackage, VerificationClass |
| `RequirementsExtractor` | `.xlsx`, `.csv` files | Requirement (configurable) |
| *(planned)* `PDFExtractor` | PDF documents | Document sections, requirements |
| *(planned)* `WordExtractor` | Word documents | Document sections, requirements |
| *(planned)* `JamaExtractor` | Jama API | Requirements, specifications |

---

## CLI Reference

### Extraction (Stage 1)

```bash
# Extract SystemVerilog files to intermediate format
python -m bam extract systemverilog \
  --source-id my-rtl \
  --path /path/to/rtl \
  --output intermediate/my-rtl.json

# Extract with source mapping
python -m bam extract \
  --source-id my-rtl \
  --mapping source_mappings/my-rtl.json
```

### Ingestion (Stage 2)

```bash
# Ingest intermediate file into sketch
python -m bam ingest \
  --project ./my-project \
  --intermediate intermediate/my-rtl.json

# Dry run (validate without modifying)
python -m bam ingest \
  --project ./my-project \
  --intermediate intermediate/my-rtl.json \
  --dry-run

# With sketch change approval
python -m bam ingest \
  --project ./my-project \
  --intermediate intermediate/my-rtl.json \
  --auto-approve  # or --interactive for prompts
```

### Model Operations

```bash
# View model statistics
python -m bam --project ./my-project stats

# Query nodes
python -m bam --project ./my-project graph find --type RTLModule

# Create snapshot before changes
python -m bam --project ./my-project graph snapshot --label "before-dv-ingestion"
```

---

## Programmatic Usage

### Stage 1: Extraction

```python
from bam.extractors import SystemVerilogExtractor
from pathlib import Path

# Create extractor
extractor = SystemVerilogExtractor('my-rtl')

# Extract from directory
result = extractor.extract_directory(Path('/path/to/rtl'))

# Convert to intermediate format
intermediate = extractor.to_intermediate(result)

# Save for review
intermediate.save(Path('intermediate/my-rtl.json'))

# Check summary
print(f"Nodes: {len(intermediate.nodes)}")
print(f"Edges: {len(intermediate.edges)}")
```

### Stage 2: Ingestion

```python
from bam.extractors import IntermediateIngester, IntermediateData
from pathlib import Path

# Load intermediate data
intermediate = IntermediateData.load(Path('intermediate/my-rtl.json'))

# Create ingester for project
ingester = IntermediateIngester(Path('./my-project'))

# Dry run first
result = ingester.ingest(intermediate, dry_run=True)
print(f"Would add: {result.nodes_added} nodes, {result.edges_added} edges")

# Real ingestion
result = ingester.ingest(intermediate)
print(f"Added: {result.nodes_added} nodes, {result.edges_added} edges")
```

---

## Adding a New Extractor

1. Create extractor in `src/bam/extractors/`:

```python
from bam.extractors import BaseExtractor, IntermediateData, IntermediateNode

class MyExtractor(BaseExtractor):
    EXTRACTOR_TYPE = "my-format"
    FILE_EXTENSIONS = ["xyz"]

    def extract_file(self, file_path):
        # Parse file, return items and relationships
        ...

    def to_intermediate(self, result):
        # Convert to IntermediateData
        intermediate = IntermediateData(
            source_id=result.source_id,
            source_type=self.EXTRACTOR_TYPE
        )
        for item in result.items:
            intermediate.add_node(IntermediateNode(...))
        return intermediate
```

2. Register in `__init__.py`
3. Add prompts in `src/bam/data/prompts/{extractor}/`

---

## Testing

```bash
# Run extractor tests
python -m pytest tests/test_extractors.py -v

# Test full pipeline
python -m pytest tests/test_agent_pipeline.py -v
```