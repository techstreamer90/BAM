# BAM Ingestion Orchestrator

A task orchestration system for building "digital twin" graph models through data ingestion pipelines.

## Overview

BAM uses a **seed-and-grow** approach to build a comprehensive graph model:

1. **Standard Pipeline** - Creates the backbone/sketch from authoritative top-level documents
2. **Incremental Pipeline** - Enriches the model from various sources (JAMA, design docs, code, measurements)
3. **Agent-Driven Pipeline** - LLM-driven ingestion where an AI agent analyses incoming data, proposes how it maps to the graph, and optionally requests human approval for schema changes

```
┌─────────────────────────────────────────────────────────────────────┐
│                        BAM Graph Model                               │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐          │
│  │ Require-│───▶│ Design  │───▶│  Code   │───▶│  Test   │          │
│  │  ments  │    │  Docs   │    │ Modules │    │ Results │          │
│  └─────────┘    └─────────┘    └─────────┘    └─────────┘          │
│       │              │              │              │                 │
│       └──────────────┴──────────────┴──────────────┘                 │
│                    Traceability Links                                │
└─────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
C:\BAM\
├── README.md                   # This file
├── pyproject.toml              # Package config
├── docs/
│   ├── README.md               # Architecture docs
│   ├── agent_guide.md          # Agent onboarding guide
│   └── mission.md              # Project mission
│
├── src/bam/                    # Python package
│   ├── cli.py                  # bam CLI entry point
│   ├── project.py              # Project init/load
│   ├── graph_manager.py        # Graph operations (wraps ModelManager)
│   ├── orchestrator.py         # Pipeline orchestration
│   ├── stage_runner.py         # Stage execution
│   ├── agent_review.py         # LLM agent review (agent-driven pipeline)
│   ├── sketch_review.py        # Sketch change review manager
│   ├── test_chain.py           # Accumulating regression test chain
│   ├── source_connector.py     # Source connectors
│   ├── issue_tracker.py        # Issue management
│   ├── reporter.py             # Report generation
│   ├── ingestion_plan.py       # Ingestion plan management
│   ├── seed_runner.py          # Seed workflow runner
│   │
│   ├── llm/                    # LLM provider abstraction
│   │   ├── provider.py         # Abstract LLMProvider interface
│   │   ├── claude_provider.py  # Claude (Anthropic) implementation
│   │   └── factory.py          # Provider factory + global config
│   │
│   ├── backends/               # Storage backend system
│   │   ├── sketch.py           # SketchManager (graph structure)
│   │   ├── model_manager.py    # ModelManager (orchestrates all)
│   │   ├── color_manager.py    # ColorManager (routes by node type)
│   │   ├── factory.py          # Backend factory functions
│   │   ├── json_color_backend.py
│   │   ├── sqlite_color_backend.py
│   │   ├── neo4j_color_backend.py   # Optional
│   │   └── arango_color_backend.py  # Optional
│   │
│   ├── llm/                    # LLM provider abstraction
│   │   ├── provider.py         # Abstract provider interface
│   │   ├── claude_provider.py  # Claude (Anthropic) provider
│   │   ├── copilot_provider.py # GitHub Copilot provider
│   │   ├── mock_provider.py    # Mock provider for testing
│   │   └── factory.py          # Provider factory + global config
│   │
│   ├── control.py              # Project control.json manager
│   ├── setup_wizard.py         # First-time setup wizard
│   │
│   └── data/                   # Shared tool data
│       ├── pipelines/          # Pipeline definitions
│       ├── prompts/            # AI prompts per source type
│       ├── sketch_templates/   # Sketch templates
│       └── seed/               # Seed playbooks, profiles, checklists
│
├── tests/                      # Test suite
│   ├── test_backends.py
│   ├── test_sketch_color.py
│   ├── test_test_chain.py      # Test chain unit tests
│   └── verification/           # Data verification system
│
└── <project_dir>/              # ★ PER-PROJECT DATA (created by seed) ★
    ├── project.json            # Project config
    ├── control.json            # LLM provider & model configuration
    ├── .env.example            # Template for environment variables
    ├── sources.json            # Data source registry
    ├── tasks.json              # Task queue
    ├── issues.json             # Issue tracker
    ├── history.json            # Run history
    ├── ingestion_plan.json     # Ingestion plan
    ├── test_chain.json         # Accumulating regression test chain
    ├── sketch_review.json      # Pending sketch change review (agent-driven)
    │
    └── model/                  # ★ THE GRAPH MODEL ★
        ├── sketch.json         # Graph structure (nodes, edges, types)
        ├── version.json        # Version tracking
        ├── sketch_snapshots/   # Sketch point-in-time backups
        └── colors/             # Color layer storage
            ├── conceptual.json # Conceptual color (JSON backend)
            ├── design.json     # Design color
            ├── verification.json
            ├── cv.json         # Characterization/validation color
            ├── default.json    # Fallback backend
            └── snapshots/      # Per-backend snapshots
```

## Key Files Explained

| File | Purpose | Importance |
|------|---------|------------|
| `model/sketch.json` | Graph structure (IDs, types, connections) | Critical - authoritative structure |
| `model/colors/*.json` | Node/edge properties (JSON backends by color) | Critical - detailed data |
| `model/colors/*.db` | Node/edge properties (SQLite backends by color) | Critical - detailed data |
| `model/version.json` | Tracks model version and snapshots | Important for rollback |
| `model/sketch_snapshots/` | Sketch point-in-time backups | Safety net |
| `model/colors/snapshots/` | Per-backend color backups | Safety net |
| `config.json` | Color definitions, backend routing, policies | Configuration |
| `test_chain.json` | Accumulating regression test chain | Quality tracking |
| `sources.json` | Defines all data sources | Configuration |
| `tasks.json` | Current task queue | Operational |
| `issues.json` | Problems found during ingestion | Quality tracking |
| `history.json` | Record of all pipeline runs | Audit trail |
| `sketch_review.json` | Pending sketch change review (agent-driven pipeline) | Operational |
| `control.json` | Per-project LLM provider and model configuration | Configuration |
| `.env.example` | Template showing required environment variables | Documentation |
| `runs/{id}/transform_plan.json` | LLM-produced transform plan for a run | Operational |

---

## Complete Flow Example

### Phase 1: Create Backbone (Standard Pipeline)

The standard pipeline creates the initial graph sketch from your authoritative source (e.g., JAMA requirements).

```bash
# 1. Create an ingestion task for the backbone
python -m bam orchestrator create jama-requirements --pipeline standard

# Output: Created task: task-ingestion-001

# 2. Run the task
python -m bam orchestrator run task-ingestion-001
```

**What happens internally:**

```
┌──────────────────────────────────────────────────────────────────────┐
│                    STANDARD PIPELINE (7 stages)                       │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐         │
│  │ Download │──▶│ Validate │──▶│  Parse   │──▶│ Transform │         │
│  │          │   │          │   │          │   │           │         │
│  │ Fetch    │   │ Check    │   │ Structure│   │ Create    │         │
│  │ from     │   │ required │   │ into     │   │ nodes &   │         │
│  │ source   │   │ fields,  │   │ items    │   │ edges     │         │
│  │          │   │ refs     │   │          │   │           │         │
│  └──────────┘   └──────────┘   └──────────┘   └───────────┘         │
│                                                      │                │
│                                                      ▼                │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────────┐            │
│  │  Report  │◀──│  Verify  │◀──│      Integrate        │            │
│  │          │   │          │   │                       │            │
│  │ Generate │   │ Check    │   │ 1. Create snapshot    │            │
│  │ summary  │   │ consis-  │   │ 2. Add to sketch    │            │
│  │          │   │ tency    │   │ 3. Update version     │            │
│  └──────────┘   └──────────┘   └───────────────────────┘            │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**After completion:**
- `model/sketch.json` contains requirements as nodes with relationships as edges
- A snapshot exists in `model/snapshots/` for rollback
- Run artifacts in `runs/{run-id}/`

### Phase 2: Enrich Model (Incremental Pipeline)

Now enrich the backbone with additional sources:

```bash
# 3. Add design documents
python -m bam orchestrator create design-data --pipeline incremental
python -m bam orchestrator run task-ingestion-002

# 4. Add codebase
python -m bam orchestrator create codebase --pipeline incremental
python -m bam orchestrator run task-ingestion-003

# 5. Add test measurements
python -m bam orchestrator create measurements --pipeline incremental
python -m bam orchestrator run task-ingestion-004
```

**What happens internally:**

```
┌──────────────────────────────────────────────────────────────────────┐
│                   INCREMENTAL PIPELINE (6 stages)                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐   ┌──────────┐   ┌───────────────────┐             │
│  │ Fetch Delta │──▶│   Diff   │──▶│ Transform Changes │             │
│  │             │   │          │   │                   │             │
│  │ Get changes │   │ Compare  │   │ Convert to graph  │             │
│  │ since last  │   │ with     │   │ operations:       │             │
│  │ sync        │   │ existing │   │ - additions       │             │
│  │             │   │ model    │   │ - modifications   │             │
│  │             │   │          │   │ - deletions       │             │
│  └─────────────┘   └──────────┘   └───────────────────┘             │
│                                            │                          │
│                                            ▼                          │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────────┐            │
│  │  Report  │◀──│  Verify  │◀──│        Merge          │            │
│  │          │   │          │   │                       │            │
│  │ Summary  │   │ Check    │   │ 1. Create snapshot    │            │
│  │ of delta │   │ consis-  │   │ 2. Apply operations   │            │
│  │ changes  │   │ tency    │   │ 3. Link to existing   │            │
│  └──────────┘   └──────────┘   └───────────────────────┘            │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### Alternative: Agent-Driven Pipeline (LLM-Based)

Instead of hardcoded parsers, the agent-driven pipeline uses an LLM to analyse
incoming data and produce a transform plan. This is useful when you don't have
a pre-built parser for a data source, or when the mapping from source data to
graph structure requires judgment.

#### LLM Setup

First-time users should run the interactive wizard:

```bash
python -m bam setup wizard
```

Or configure manually:

```bash
# Option 1: Claude (Anthropic) - recommended
export ANTHROPIC_API_KEY=sk-ant-api03-...
python -m bam setup llm --provider claude --test

# Option 2: GitHub Copilot (requires subscription + CLI)
pip install bam-model[copilot]
python -m bam setup llm --provider copilot --test

# Option 3: Mock provider (for testing without API)
python -m bam setup llm --provider mock --test
```

#### Per-Project LLM Configuration

Each project can have its own LLM settings in `control.json`:

```bash
# Initialize control.json
python -m bam --project ./my-project control init

# Use different models for different tasks (cost optimization)
python -m bam --project ./my-project control set-model --task agent-review --model claude-sonnet-4-20250514
python -m bam --project ./my-project control set-model --task transform-fallback --model claude-haiku-4-20250514

# View configuration
python -m bam --project ./my-project control show
```

The `control.json` file supports:
- **Models by task**: Different models for `agent-review`, `transform-fallback`, `verification`
- **Models by source**: Override models for specific source types (e.g., use a better model for complex data)
- **Security settings**: Enforce environment variables for credentials

#### Running Agent-Driven Ingestion

```bash
python -m bam orchestrator create my-source --pipeline agent-driven
python -m bam orchestrator run task-ingestion-005
```

**What happens internally:**

```
┌──────────────────────────────────────────────────────────────────────┐
│                  AGENT-DRIVEN PIPELINE (6 stages)                     │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────┐   ┌─────────────────┐   ┌───────────┐                  │
│  │ Download │──▶│  Agent Review   │──▶│ Transform │                  │
│  │          │   │                 │   │           │                  │
│  │ Fetch    │   │ LLM analyses    │   │ Execute   │                  │
│  │ from     │   │ data + sketch,  │   │ the plan: │                  │
│  │ source   │   │ produces a      │   │ pattern-  │                  │
│  │          │   │ transform plan  │   │ based +   │                  │
│  │          │   │                 │   │ LLM       │                  │
│  │          │   │ May propose     │   │ fallback  │                  │
│  │          │   │ sketch changes  │   │           │                  │
│  └──────────┘   └────────┬────────┘   └───────────┘                  │
│                          │                   │                        │
│              ┌───────────┴────────┐          │                        │
│              │  Minor changes?    │          │                        │
│              │  → auto-apply      │          │                        │
│              │  Major changes?    │          │                        │
│              │  → PAUSE pipeline  │          │                        │
│              └────────────────────┘          ▼                        │
│                                                                       │
│  ┌──────────┐   ┌──────────┐   ┌───────────────────────┐            │
│  │  Report  │◀──│  Verify  │◀──│      Integrate        │            │
│  └──────────┘   └──────────┘   └───────────────────────┘            │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

**If the pipeline pauses** (major sketch changes proposed):

```bash
python -m bam --project ./p review show              # inspect proposed changes
python -m bam --project ./p review approve           # apply changes, then:
python -m bam --project ./p resume <task-id>         # continue from transform

# Or reject and re-run agent review:
python -m bam --project ./p review reject --feedback "Use existing types instead"
python -m bam --project ./p resume <task-id>         # re-runs agent-review
```

**Key differences from standard pipeline:**
- No separate validate/parse stages — the LLM handles schema inference
- Transform is plan-driven: the agent-review produces a `TransformPlan` that
  the transform stage executes mechanically
- Items that don't match any mapping in the plan trigger a single LLM fallback
  call rather than failing
- The pipeline can pause for human review if the LLM proposes new node/edge
  types that don't exist in the current sketch

### Phase 3: Query the Model

```bash
# View model statistics
python -m bam graph stats

# Find specific nodes
python -m bam graph find --type Requirement
python -m bam graph find --source jama-requirements
python -m bam graph find --label "safety"

# Generate reports
python -m bam report model
python -m bam report issues
```

---

## Adding a New Data Source

### Step 1: Define the Source in `sources.json`

```json
{
  "sources": {
    "my-new-source": {
      "id": "my-new-source",
      "name": "My New Data Source",
      "type": "custom",
      "enabled": true,

      "connection": {
        "type": "api",           // or: "filesystem", "git", "database"
        "baseUrl": "https://api.example.com",
        "authType": "bearer",
        "credentials": "env:MY_SOURCE_TOKEN"
      },

      "extraction": {
        "endpoint": "/items",
        "filters": {"status": "active"},
        "depth": "full"
      },

      "validation": {
        "promptPath": "prompts/my-source/validate.md",
        "rules": ["required-fields", "valid-references"]
      },

      "transform": {
        "promptPath": "prompts/my-source/transform.md",
        "nodeMapping": {
          "item": "MyItemNode",
          "category": "CategoryNode"
        },
        "edgeMapping": {
          "belongs-to": "BELONGS_TO",
          "references": "REFERENCES"
        }
      },

      "consistency": {
        "promptPath": "prompts/my-source/consistency.md",
        "checks": ["id-uniqueness", "relationship-integrity"]
      }
    }
  }
}
```

### Step 2: Create Prompts

Create prompts in `src/bam/data/prompts/my-source/`:

**validate.md** - Rules for validating raw data
```markdown
# Validation Prompt for My Source

## Required Fields
- id: unique identifier
- name: display name
- ...

## Validation Rules
1. Check required fields exist
2. Validate references point to real items
3. ...
```

**transform.md** - Rules for converting to graph nodes/edges
```markdown
# Transformation Prompt for My Source

## Node Mapping
| Source Field | Node Property |
|--------------|---------------|
| id           | source_ref    |
| name         | label         |
| ...          | ...           |

## Edge Creation
- For each "belongs-to" relationship, create BELONGS_TO edge
- ...
```

### Step 3: (Optional) Add Custom Connector

If your source needs special connection logic, add to `source_connector.py`:

```python
class MySourceConnector(BaseConnector):
    def test_connection(self) -> bool:
        # Test API connectivity
        ...

    def fetch_full(self) -> FetchResult:
        # Fetch all data
        ...

    def fetch_delta(self, since: str) -> FetchResult:
        # Fetch changes since timestamp
        ...

# Register in ConnectorFactory._connector_types
```

### Step 4: Run Ingestion

```bash
# Create and run task
python -m bam orchestrator create my-new-source --pipeline standard
python -m bam orchestrator run task-ingestion-XXX
```

### Alternative: Agent-Driven Ingestion (No Parser Needed)

If you don't have a custom parser for your data source, use the agent-driven
pipeline instead. The LLM analyses the raw data and produces a transform plan
automatically — no prompts or connector code required.

```bash
# Configure LLM (once)
python -m bam setup llm --provider claude

# Run with agent-driven pipeline
python -m bam orchestrator create my-new-source --pipeline agent-driven
python -m bam orchestrator run task-ingestion-XXX
```

The LLM examines a sample of the data alongside the current sketch and decides
how items map to node types, what ID patterns to use, and which edges to
create. If it needs new node or edge types, the pipeline pauses for your
approval (see [Error Handling](#when-agent-driven-pipeline-pauses)).

---

## Artifacts Reference

### Where Data Ends Up

```
Source Data Flow:

  External     ┌─────────┐     ┌─────────┐     ┌──────────────────┐
  Source  ────▶│  data/  │────▶│ Pipeline│────▶│ model/sketch   │
               │         │     │ Process │     │                  │
               │ Raw     │     │         │     │ Nodes & Edges    │
               │ download│     │         │     │ (FINAL OUTPUT)   │
               └─────────┘     └─────────┘     └──────────────────┘
                    │               │                    │
                    │               │                    │
                    ▼               ▼                    ▼
               (transient)    runs/{id}/         model/snapshots/
                              (audit trail)      (backup/rollback)
```

### Important Artifacts by Purpose

**For Using the Model:**
```
model/sketch.json     ← Graph structure (nodes + edges)
model/colors/           ← Node/edge properties by color
```

**For Recovery/Rollback:**
```
model/sketch_snapshots/   ← Sketch point-in-time backups
model/colors/snapshots/     ← Per-backend color backups
model/version.json          ← Version history
```

**For Debugging/Audit:**
```
runs/{run-id}/          ← Full run history
  ├── manifest.json          ← What was run
  ├── stages/*.json          ← Per-stage results
  └── report.md              ← Human-readable summary
```

**For Quality Tracking:**
```
issues.json             ← Problems found
human-queue.json        ← Items needing attention
test_chain.json         ← Accumulating regression tests
```

**For Operations:**
```
tasks.json              ← Current task queue
history.json            ← All runs ever executed
sketch_review.json      ← Pending sketch review (agent-driven pipeline)
```

**For Agent-Driven Pipeline:**
```
control.json                       ← Per-project LLM config, models by task/source
.env.example                       ← Template for required environment variables
runs/{run-id}/transform_plan.json  ← LLM-produced mapping plan
runs/{run-id}/stage_outputs.json   ← Saved outputs when pipeline pauses
~/.bam/config.json                 ← Global LLM provider configuration (fallback)
```

---

## Architecture: Sketch + Color Layer

The graph model uses a **sketch/color** split with **color-layered routing** for performance and flexibility:

```
┌─────────────────────────────────────────────────────────────────┐
│                        ModelManager                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐     │
│  │                      SKETCH                           │     │
│  │           (Single JSON file - graph structure)          │     │
│  │                                                         │     │
│  │  • Node IDs, types, labels, source_id                  │     │
│  │  • Edge IDs, types, connections                        │     │
│  │  • Fast navigation via adjacency index                 │     │
│  └────────────────────────────────────────────────────────┘     │
│                            │                                     │
│                            │ node_type → colors                  │
│                            ▼                                     │
│  ┌────────────────────────────────────────────────────────┐     │
│  │                    COLOR MANAGER                        │     │
│  │          (Routes by node type to colors)                │     │
│  │                                                         │     │
│  │  ┌──────────┐ ┌────────┐ ┌────────────┐ ┌────┐        │     │
│  │  │conceptual│ │ design │ │verification│ │ cv │        │     │
│  │  └────┬─────┘ └───┬────┘ └─────┬──────┘ └─┬──┘        │     │
│  │       │           │            │          │            │     │
│  │       ▼           ▼            ▼          ▼            │     │
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐       │     │
│  │  │jama.json│  │design.db│ │verif.json│ │ cv.db │       │     │
│  │  └────────┘  └────────┘  └────────┘  └────────┘       │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Concepts

- **Sketch**: Single authoritative source for graph structure (always JSON, always fast)
- **Colors**: Logical groupings of node types by perspective:
  - `conceptual`: Requirements, Specifications, Features
  - `design`: DesignDocuments, RTLModules, CodeModules
  - `verification`: Testbenches, Assertions, CoverageGroups
  - `cv`: Measurements, TestResults, CVReports
- **Color backends**: Store properties/content, each color maps to a backend (JSON or SQLite)
- **Benefits**:
  - Fast traversal via sketch with adjacency index
  - Color-specific queries (e.g., get design data without loading requirements)
  - Mix storage backends per use case (JSON for simplicity, SQLite for scale)

---

## The Graph Model

**sketch.json** - Graph structure (lightweight):

```json
{
  "version": "1.0.0",
  "metadata": { "nodeCount": 1547, "edgeCount": 3892 },
  "nodes": {
    "jama-req-REQ001": {
      "id": "jama-req-REQ001",
      "type": "Requirement",
      "label": "System shall provide user authentication",
      "source_id": "jama-requirements"
    }
  },
  "edges": {
    "impl-REQ001-auth": {
      "id": "impl-REQ001-auth",
      "type": "IMPLEMENTS",
      "source_node_id": "code-auth-service",
      "target_node_id": "jama-req-REQ001"
    }
  }
}
```

**color (per-color backend)** - Properties and content:

```json
{
  "nodes": {
    "jama-req-REQ001": {
      "id": "jama-req-REQ001",
      "properties": { "status": "approved", "priority": "high" },
      "source_ref": "REQ001",
      "content": "Full requirement text...",
      "created_at": "2026-01-26T10:00:00Z",
      "updated_at": "2026-01-26T12:30:00Z"
    }
  },
  "edges": {
    "impl-REQ001-auth": {
      "id": "impl-REQ001-auth",
      "properties": { "confidence": 0.95 },
      "created_at": "2026-01-26T11:00:00Z"
    }
  }
}
```

### Node Types

| Type | Color | Description |
|------|-------|-------------|
| `Requirement` | conceptual | System requirements |
| `Specification` | conceptual, design | Detailed specifications |
| `Feature` | conceptual | Feature definitions |
| `UserStory` | conceptual | User stories |
| `DesignDocument` | design | Design documents |
| `DesignSection` | design | Document sections |
| `RTLModule` | design | RTL/HDL modules |
| `AnalogBlock` | design | Analog circuit blocks |
| `CodeModule` | design | Source files |
| `CodeClass` | design | Classes |
| `CodeFunction` | design | Functions |
| `Testbench` | verification | Testbench files |
| `Assertion` | verification | SVA/PSL assertions |
| `CoverageGroup` | verification | Coverage definitions |
| `TestPlan` | verification | Test plans |
| `TestCase` | verification | Individual test cases |
| `TestResult` | cv | Test outcomes |
| `Measurement` | cv | Measured values |
| `CVReport` | cv | Characterization reports |

### Edge Types

| Type | Meaning |
|------|---------|
| `DERIVES_FROM` | Requirement derives from parent |
| `SATISFIES` | Design satisfies requirement |
| `IMPLEMENTS` | Code implements requirement |
| `TESTS` | Test verifies requirement |
| `CONTAINS` | Parent contains child |
| `REFERENCES` | Cross-reference |
| `CALLS` | Code calls code |
| `DEPENDS_ON` | Dependency relationship |

---

## CLI Reference

### Orchestrator Commands

```bash
# Task Management
orchestrator.py create <source-id> [--pipeline standard|incremental|agent-driven]
orchestrator.py run <task-id>
orchestrator.py list
orchestrator.py status <task-id>

# Examples
python -m bam orchestrator create jama-requirements
python -m bam orchestrator create my-source --pipeline agent-driven
python -m bam orchestrator run task-ingestion-001
python -m bam orchestrator list
python -m bam orchestrator status task-ingestion-001
```

### Graph Manager Commands

```bash
# Model Operations
graph_manager.py stats                    # Show model statistics
graph_manager.py find [--type T] [--source S] [--label L] [--color F]
graph_manager.py snapshot [--label L]     # Create backup
graph_manager.py snapshots                # List backups
graph_manager.py restore <snapshot-id>    # Rollback
graph_manager.py check                    # Check consistency across backends
graph_manager.py repair                   # Repair inconsistencies

# Color Operations
graph_manager.py list-colors              # List configured colors
graph_manager.py list-backends            # List active color backends

# Examples
python -m bam graph stats
python -m bam graph find --type Requirement
python -m bam graph find --type RTLModule --color design
python -m bam graph snapshot --label "before-code-ingestion"
python -m bam graph check
python -m bam graph list-colors
```

### Issue Tracker Commands

```bash
# Issue Management
issue_tracker.py list [--blocking]
issue_tracker.py show <issue-id>
issue_tracker.py resolve <issue-id> <resolution>
issue_tracker.py stats
issue_tracker.py queue                    # Human intervention queue
issue_tracker.py claim <item-id> <assignee>

# Examples
python -m bam issues list --blocking
python -m bam issues resolve issue-0001 "Fixed duplicate ID"
```

### Test Chain Commands

```bash
# Run the full regression test chain
python -m bam --project <dir> test run

# Show test chain overview (sets, counts, gates)
python -m bam --project <dir> test show

# Add a manual check
python -m bam --project <dir> test add-check \
  --description "Product node must exist" \
  --type node_exists --node-id product-top --gate blocking

python -m bam --project <dir> test add-check \
  --description "At least 10 requirements" \
  --type node_count --node-type Requirement --min-count 10 --gate blocking
```

### Reporter Commands

```bash
# Report Generation
reporter.py model                         # Model state report
reporter.py issues                        # Issues report
reporter.py source <source-id>            # Source-specific report
reporter.py run <run-id>                  # Run report

# Examples
python -m bam report model
python -m bam report source jama-requirements
```

---

## Error Handling

### Severity Levels

| Level | Action | Human Required |
|-------|--------|----------------|
| Critical | Halt immediately, rollback | Yes |
| Error | Halt current stage | Yes |
| Warning | Log and continue | No |
| Info | Log only | No |

### When Pipeline Halts

1. Issue is created in `issues.json`
2. Item added to `human-queue.json`
3. Task marked as `failed` or `blocked`

### When Agent-Driven Pipeline Pauses

The agent-driven pipeline pauses (rather than halts) when the LLM proposes
major sketch changes — new node types, new edge types, or type renames that
don't exist in the current sketch. The flow is:

1. `sketch_review.json` is created with the proposed changes
2. Task is marked as `PAUSED` (not failed)
3. Stage outputs saved to `runs/{run-id}/stage_outputs.json` for continuation

```bash
# Inspect proposed changes
python -m bam --project ./p review show

# Approve and apply to sketch, then continue
python -m bam --project ./p review approve
python -m bam --project ./p resume <task-id>

# Or reject with feedback, then re-run agent-review
python -m bam --project ./p review reject --feedback "Use existing types"
python -m bam --project ./p resume <task-id>
```

Minor changes (new nodes using existing types, no new edge types) are
auto-applied without pausing.

### To Resume After Fix

```bash
# Check blocking issues
python -m bam issues list --blocking

# Resolve the issue
python -m bam issues resolve issue-0001 "Fixed the problem"

# Re-run the task
python -m bam orchestrator run task-ingestion-001
```

### To Rollback

```bash
# List available snapshots
python -m bam graph snapshots

# Restore to previous state
python -m bam graph restore snapshot-20260126-100000-pre-integrate
```

---

## Typical Workflow

```
Week 1: Initial Setup
├── Configure JAMA source connection
├── Run standard pipeline → backbone created
└── Review issues, fix data problems

Week 2: Enrich with Design Docs
├── Configure design-data source
├── Run incremental pipeline → design nodes added
└── Verify traceability links

Week 3: Add Codebase
├── Configure codebase source
├── Run incremental pipeline → code nodes added
└── Establish implements relationships

Week 4+: Continuous Updates
├── Run incremental pipelines as sources update
├── Monitor issues dashboard
└── Generate traceability reports
```

---

## Programmatic Access

### Using GraphManager (recommended for most use cases)

```python
from bam.graph_manager import GraphManager

# Use context manager for proper cleanup
with GraphManager(project_dir="./my-project") as gm:
    # Find nodes
    reqs = gm.find_nodes(node_type="Requirement")
    code = gm.find_nodes(source_id="codebase")

    # Get node with color-specific color
    node = gm.get_node("jama-req-001", color="conceptual")

    # Get connections
    connected = gm.get_connected_nodes("jama-req-001", direction="incoming")

    # Extract subgraph
    subgraph = gm.get_subgraph("jama-req-001", max_depth=3)

    # Color and backend info
    colors = gm.list_colors()       # {'conceptual': {...}, 'design': {...}, ...}
    backends = gm.list_backends()   # ['jama', 'design', 'verification', 'cv']

    # Check backend consistency
    report = gm.check_consistency()
```

### Using ModelManager (for more control)

```python
from bam.backends import get_model_manager

mm = get_model_manager(project_dir="./my-project")
mm.load()

try:
    # Bulk fetch all nodes efficiently
    all_nodes = mm.get_all_nodes(include_color=True)

    # Get specific nodes by ID
    nodes = mm.get_nodes_by_ids(["id1", "id2"], include_color=True)

    # Get node from specific color
    node = mm.get_node("jama-req-001", color="conceptual")

    # Fast navigation (sketch only, no color)
    connected_ids = mm.get_connected_node_ids("jama-req-001")

    # Statistics
    stats = mm.get_statistics()
    print(f"Sketch: {stats.sketch.total_nodes} nodes")
    for name, color_stats in stats.color_by_backend.items():
        print(f"  {name}: {color_stats.total_nodes} nodes")

finally:
    mm.save()
    mm.close()
```

### Direct sketch access (read-only, fastest)

```python
import json

with open('model/sketch.json') as f:
    sketch = json.load(f)

# Query structure (IDs, types, connections)
requirements = [n for nid, n in sketch['nodes'].items()
                if n['type'] == 'Requirement']

# Find edges by type
impl_edges = [e for eid, e in sketch['edges'].items()
              if e['type'] == 'IMPLEMENTS']
```

---

## Configuration Reference

The `config.json` file controls color definitions, backend routing, and system behavior.

### Color Definitions

```json
{
  "storage": {
    "colors": {
      "conceptual": {
        "description": "Requirements, specifications, conceptual artifacts",
        "node_types": ["Requirement", "Specification", "Feature", "UserStory"]
      },
      "design": {
        "description": "Design artifacts, RTL, schematics",
        "node_types": ["DesignDocument", "RTLModule", "CodeModule", "CodeClass"]
      },
      "verification": {
        "description": "Testbenches, assertions, coverage",
        "node_types": ["Testbench", "Assertion", "CoverageGroup", "TestCase"]
      },
      "cv": {
        "description": "Characterization and validation measurements",
        "node_types": ["Measurement", "TestResult", "CVReport"]
      }
    }
  }
}
```

### Backend Configuration

```json
{
  "storage": {
    "color_backends": {
      "jama": {
        "type": "json",              // Backend type: "json" or "sqlite"
        "colors": ["conceptual"],    // Which colors this backend serves
        "path": "model/colors/jama.json",
        "snapshotsDir": "model/colors/snapshots/jama"
      },
      "design": {
        "type": "sqlite",
        "colors": ["design"],
        "path": "model/colors/design.db"
      },
      "default": {
        "type": "json",
        "colors": ["conceptual", "design", "verification", "cv"],
        "path": "model/colors/default.json",
        "description": "Fallback backend for backward compatibility"
      }
    }
  }
}
```

### Adding a New Color

1. Define the color with its node types in `config.json`
2. Create a backend that serves the color
3. Node types automatically route to the appropriate backend

---

## Performance Notes

### Optimizations Built-In

- **Adjacency index**: Navigation queries (`get_connected_node_ids`, `get_subgraph_ids`) use a lazy-built adjacency index for O(1) lookups instead of scanning all edges
- **Batch saves**: JSON backend uses deferred writes - changes are buffered and only written on `save()` or `close()`
- **Bulk operations**: Use `get_all_nodes()`, `get_nodes_by_ids()`, `bulk_add_nodes()` for efficient batch processing
- **Sketch-only queries**: Use `include_color=False` for fast structure-only queries

### Best Practices

```python
# GOOD: Bulk fetch
nodes = mm.get_all_nodes(include_color=True)

# BAD: N+1 query pattern
for node_id in node_ids:
    node = mm.get_node(node_id)  # Separate query each time

# GOOD: Use sketch for navigation
connected_ids = mm.get_connected_node_ids("node-1")  # Fast, indexed

# GOOD: Explicit save for batch operations
mm.load()
for item in large_batch:
    mm.add_node(...)
mm.save()  # Single write at end
mm.close()
```

### When to Use Each Backend

| Backend | Best For | Trade-offs |
|---------|----------|------------|
| JSON | Development, small models (<10K nodes) | Simple, human-readable, loads entire file |
| SQLite | Production, larger models | Indexed queries, concurrent access |
| Neo4j | Complex graph queries | Requires server, best for traversals |

---

## Testing & Verification

BAM includes two complementary verification systems:

1. **Test Chain** — an accumulating regression test suite built into every project
2. **Verification Framework** — a declarative fixture-based testing system

### Test Chain (Regression Testing)

The test chain (`test_chain.json`) grows automatically as a project evolves.
Tests are generated at two points:

- **Project init** — structural checks from the sketch template (node/edge existence, type counts)
- **Each pipeline ingestion** — download, transform, and integrate stages each append tests

All accumulated tests run during every subsequent `verify` stage, catching
regressions where a later ingestion breaks earlier data.

```bash
# Show what tests exist
python -m bam --project ./my-project test show

# Run the full chain (exit 1 on failure)
python -m bam --project ./my-project test run

# Add a manual check
python -m bam --project ./my-project test add-check \
  --description "Product node must exist" \
  --type node_exists --node-id product-top
```

#### Gate Levels

| Test Type | Default Gate | Rationale |
|-----------|-------------|-----------|
| Sketch structural | blocking | Template structure must hold |
| Download completeness | blocking | Missing data = bad model |
| Transform node/edge existence | blocking | Nodes/edges must be created correctly |
| Integration count baselines | warning | Counts may shift during incremental updates |
| Manual checks | user's choice | Configurable via `--gate` |

- **blocking** tests must pass or the pipeline halts
- **warning** tests are reported but do not halt the pipeline

#### How It Works End-to-End

1. `python -m bam seed execute` → creates `test_chain.json` with sketch structural tests
2. First ingestion pipeline runs → download/transform/integrate each append test sets
3. Verify stage runs ALL accumulated tests. If blocking tests fail, pipeline halts.
4. Second ingestion → appends its own tests. Verify runs ALL tests (sketch + first + second ingestion). If the second ingestion broke first-ingestion data, those tests catch it.

### Verification Framework (Fixture-Based Testing)

```bash
# Run all verification tests
python -m tests.verification.cli run

# Run with questions database
python -m tests.verification.cli run --questions

# Filter by tags
python -m tests.verification.cli run --tags critical

# Run via pytest
pytest tests/verification/test_model_verification.py -v
```

### Verification Types

| Type | Description |
|------|-------------|
| `node_exists` | Check if node exists with expected type/label |
| `node_count` | Count nodes matching criteria |
| `edge_exists` | Check if edge exists between nodes |
| `relationship_count` | Count edges for a node |
| `node_properties` | Verify node color properties |
| `node_content` | Check node content contains terms |

### Writing Fixture Tests

Create YAML files in `scripts/tests/verification/fixtures/`:

```yaml
# my-source.fixtures.yaml
version: "1.0"
source_id: "my-source"

data_points:
  - id: "dp-001"
    type: "node_exists"
    description: "Main requirement exists"
    tags: ["critical"]
    query:
      node_id: "my-source-REQ-001"
    expected:
      exists: true
      type: "Requirement"
```

For complete documentation, see [`scripts/tests/verification/README.md`](scripts/tests/verification/README.md).
