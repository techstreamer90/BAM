# BAM Seed — AI-Driven Project Bootstrapping

BAM Seed guides an AI agent through setting up a new BAM project interactively
with a human. The agent interviews the human, designs the sketch (graph schema),
configures source mappings, and executes the two-stage extraction and ingestion.

## The Two-Stage Architecture

BAM uses a two-stage, AI-driven approach:

```
Stage 1: EXTRACTION
Source Files → [Extractor] → Intermediate Format (reviewable JSON)

Stage 2: INGESTION
Intermediate Format → [Ingester] → Sketch (structure) + Color (properties)
```

The AI drives both stages, with human approval at key decision points:
- Sketch design (what node/edge types to use)
- Source mappings (how source data maps to sketch)
- Sketch changes (when data doesn't fit current schema)

## How It Works

The seed contains three layers:

1. **Playbooks** (markdown) — Step-by-step guides the agent reads at each stage
2. **Decision Data** (JSON) — Project profiles, recommendation rules
3. **Automation** (Python) — Extractor and ingester classes that do the work

## Playbook Order

Follow these playbooks in sequence:

| Step | Playbook | What Happens |
|------|----------|--------------|
| 0 | `playbooks/00_overview.md` | Explain BAM and two-stage architecture to human |
| 1 | `playbooks/01_choose_location.md` | Decide project directory location |
| 2 | `playbooks/02_interview.md` | Interview to understand project and data sources |
| 3 | `playbooks/03_recommend.md` | Design sketch and plan source mappings |
| 4 | `playbooks/04_explain_setup.md` | Present complete plan for approval |
| 5 | `playbooks/05_execute.md` | Run extraction and ingestion |
| 6 | `playbooks/06_completion.md` | Summarize results and next steps |

## Key Concepts

### Sketch
The graph structure — nodes (components, documents, tests) and edges
(relationships). Lightweight, contains only IDs, types, labels, and connections.

### Color
Detailed properties attached to sketch nodes, organized by source.
Rich data like descriptions, parameters, metadata.

### Intermediate Format
The canonical JSON format that all extractors produce. Human/AI reviewable
before ingestion. Located in `intermediate/{source_id}.json`.

### Source Mapping
Configuration that tells extractors how to map source data to the sketch.
Created during sketch design, stored in `source_mappings/{source_id}.json`.

## Available Extractors

| Extractor | File Types | Produces |
|-----------|------------|----------|
| `SystemVerilogExtractor` | `.sv`, `.v` | RTLModule, RTLInterface, VerificationClass |
| `RequirementsExtractor` | `.xlsx`, `.csv` | Requirement (configurable node type) |
| *(planned)* `PDFExtractor` | `.pdf` | Document sections, requirements |
| *(planned)* `WordExtractor` | `.docx` | Document sections, requirements |
| *(planned)* `JamaExtractor` | Jama API | Requirements, specifications |

## CLI Commands

```bash
# Initialize a project
python -m bam init --project ./my-project --name "My Project"

# Extract SystemVerilog to intermediate format
python -m bam extract systemverilog \
  --source-id my-rtl \
  --path /path/to/rtl \
  --output intermediate/my-rtl.json

# Ingest intermediate into model
python -m bam ingest \
  --project ./my-project \
  --intermediate intermediate/my-rtl.json

# Dry run ingestion (validate only)
python -m bam ingest \
  --project ./my-project \
  --intermediate intermediate/my-rtl.json \
  --dry-run

# View model statistics
python -m bam --project ./my-project stats
```

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
```

## Project Structure After Setup

```
my-project/
    project.json              # Project configuration
    sources.json              # Data source registry
    source_mappings/          # Source mapping configs
        my-rtl.json
    intermediate/             # Extracted data (reviewable)
        my-rtl.json
    model/
        sketch.json           # Graph structure (nodes, edges, types)
        colors/               # Property data storage
            my-rtl.json
```

## After Setup

Once the seed completes, the project has a populated model. The human can:
- Query the model for insights
- Add more data sources
- Re-extract/re-ingest when source data changes
- Extend the sketch with new types

See `docs/agent_guide.md` for the full reference.
