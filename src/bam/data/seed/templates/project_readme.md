# {project_name} — BAM Project

This directory is a **BAM project** — a self-contained graph model (digital
twin) built from project artifacts such as requirements, design documents,
source code, and test data.

**Template:** `{sketch_template}` | **Backend:** `{backend}` | **Created:** {created_at}

---

## For AI Agents

If you are an AI agent asked to work with this project, start here.

### Quick Orientation

1. **Read this file** to understand the project structure and available commands.
2. **Read `status.md`** for project-specific context (data sources, complexity,
   setup decisions).
3. **Check the ingestion plan**: `python -m bam --project . plan show`
4. **Check current model state**: `python -m bam --project . stats`

### What BAM Is

BAM (Build Accurate Models) creates multi-layered graph models from existing
project artifacts. It does NOT create the artifacts — it reads them and builds
a navigable graph that connects requirements to design to verification to
measurements.

The model has two layers:
- **Sketch** — lightweight structural graph (node ID, type, label, edges).
  Always JSON, always fast. Lives in `model/sketch.json`.
- **Colors** — rich properties stored per-domain (conceptual, design,
  verification, CV). Each color has its own backend (JSON, SQLite, etc.).

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Sketch** | The structural backbone: nodes (id, type, label) and edges (type, source, target). |
| **Color** | A property layer that holds rich data for a domain (e.g. conceptual = requirements text, design = RTL details). |
| **Pipeline** | A sequence of stages that ingests data into the model. Three types: `standard`, `incremental`, `agent-driven`. |
| **Stage** | One step in a pipeline: download, validate, parse, transform, integrate, verify, report. |
| **Source** | A data source (requirements DB, design files, test results) defined in `sources.json`. |
| **Ingestion Plan** | An ordered list of steps to populate the model, organized by phase. |
| **Test Chain** | An accumulating regression test suite that grows with each ingestion. |

---

## Project Files

| File | Purpose |
|------|---------|
| `project.json` | Project configuration (storage, colors, backends, halt policies) |
| `profile.json` | Interview answers from project setup (domain, sources, complexity) |
| `sources.json` | Data source definitions (name, type, location, format) |
| `ingestion_plan.json` | Ingestion steps organized by phase |
| `checklist.json` | Setup and readiness checklist |
| `status.md` | Project-specific summary and next steps |
| `tasks.json` | Pipeline task queue |
| `issues.json` | Issue tracker (problems found during ingestion) |
| `human-queue.json` | Items requiring human attention |
| `history.json` | Record of all pipeline runs |
| `model/sketch.json` | The graph sketch (nodes and edges) |
| `model/version.json` | Model version tracking |
| `model/colors/` | Color backend storage (one file per domain) |
| `runs/` | Pipeline run outputs, logs, and reports |
| `data/` | Downloaded source data |

---

## Workflow Phases

### Phase 1: Understand (already done if you're reading this)

The project has been created. Review `status.md` and `project.json` to
understand what template, backend, and data sources were chosen.

### Phase 2: Design the Sketch

Define the graph structure for this project:

1. Check `project.json` for `sketchDesignQuestions` — discuss each with the human.
2. Edit `model/sketch.json` to add agreed-upon node types, edge types, and
   hierarchy.
3. Verify: `python -m bam --project . stats`

### Phase 3: Create the Ingestion Plan

Decide which data sources to ingest and in what order:

```
python -m bam --project . plan show          # View current plan
python -m bam --project . plan create        # Create from template (if empty)
python -m bam --project . plan add-step \
  --phase backbone --name "..." \
  --source <source-id> --agent-tier standard
python -m bam --project . plan validate      # Check ordering and dependencies
```

**Ordering rules:** backbone sources first, sketch before color, parents
before children, cross-references last.

### Phase 4: Execute the Plan

Run ingestion step-by-step:

```
python -m bam --project . plan next                         # See next step
python -m bam orchestrator create <source-id> --pipeline standard
python -m bam orchestrator run <task-id>
python -m bam --project . plan complete-step --step <id>   # Mark done
python -m bam --project . stats                             # Check model
python -m bam --project . test run                          # Run regression tests
```

Repeat until all plan steps are complete.

---

## Agent-Driven Pipeline

For data sources without a pre-built parser, use the agent-driven pipeline.
An LLM analyses the raw data and produces a transform plan automatically.

### Setup (one-time)

```
python -m bam setup llm --provider claude --api-key sk-ant-...
# Or use the ANTHROPIC_API_KEY environment variable:
python -m bam setup llm --provider claude
```

### Running

```
python -m bam orchestrator create <source-id> --pipeline agent-driven
python -m bam orchestrator run <task-id>
```

### If the Pipeline Pauses (major sketch changes proposed)

```
python -m bam --project . review show         # Inspect proposed changes
python -m bam --project . review approve      # Apply and continue
python -m bam --project . resume <task-id>    # Continue pipeline

# Or reject:
python -m bam --project . review reject --feedback "Use existing types"
python -m bam --project . resume <task-id>    # Re-runs agent-review with feedback
```

Minor changes (nodes using existing types, no new edge types) are auto-applied
without pausing.

---

## All CLI Commands

### Project Management
```
python -m bam --project <dir> info             # Show project info
python -m bam --project <dir> stats            # Model statistics
python -m bam list-projects <dir>              # List all projects in a directory
```

### Ingestion Plan
```
python -m bam --project <dir> plan show        # View plan
python -m bam --project <dir> plan create      # Create plan from template
python -m bam --project <dir> plan validate    # Validate ordering
python -m bam --project <dir> plan next        # See next step
python -m bam --project <dir> plan add-step    # Add a step
python -m bam --project <dir> plan complete-step --step <id>
```

### Pipeline Execution
```
python -m bam orchestrator create <source-id> --pipeline standard|incremental|agent-driven
python -m bam orchestrator run <task-id>
python -m bam orchestrator list                # List pending tasks
python -m bam orchestrator status <task-id>    # Task status
```

### Testing
```
python -m bam --project <dir> test show        # Show test chain
python -m bam --project <dir> test run         # Run regression tests
python -m bam --project <dir> test add-check   # Add a test check
```

### Agent-Driven Pipeline
```
python -m bam setup llm --provider claude [--api-key ...] [--model ...]
python -m bam --project <dir> review show      # View sketch review
python -m bam --project <dir> review approve   # Approve proposed changes
python -m bam --project <dir> review reject [--feedback "..."]
python -m bam --project <dir> resume <task-id> # Resume paused pipeline
```

---

## Sketch Format Reference

### Node Format
```json
{
  "node-id": {
    "id": "node-id",
    "type": "Requirement",
    "label": "REQ-001 Safety Shutdown",
    "source_id": "jama-core"
  }
}
```

### Edge Format
```json
{
  "edge-id": {
    "id": "edge-id",
    "type": "TRACES_TO",
    "source_node_id": "req-001",
    "target_node_id": "spec-010",
    "source_id": null
  }
}
```

Edge types are always **UPPERCASE**: `CONTAINS`, `TRACES_TO`, `DEPENDS_ON`,
`VERIFIES`, `DERIVES_FROM`, `REALIZES`, `IMPLEMENTS`, `COVERS`, `MEASURES`,
`DOCUMENTS`, `CONFIGURES`, `HAS_PORT`, `ENRICHES`, `CONNECTS_TO`,
`INSTANTIATES`.

### Node ID Convention

Parser-generated IDs follow `{source_id}-{entity_name}`:
- `jama-core-REQ001`
- `rtl-top_module`
- `dv-smoke_test`

---

## Color Configuration

Colors are defined in `project.json` under `storage.colors`:

| Color | Description | Typical Node Types |
|-------|-------------|-------------------|
| `conceptual` | Requirements, specifications | Requirement, Specification, Feature |
| `design` | Design documents, RTL, code | DesignDocument, RTLModule, CodeModule |
| `verification` | Tests, assertions, coverage | TestCase, Assertion, CoverageGroup |
| `cv` | Characterization & validation | Measurement, TestResult, CVReport |
| `default` | Fallback for unmapped types | (any) |

Each color can use a different storage backend (JSON, SQLite, Neo4j, ArangoDB)
configured in `project.json` under `storage.color_backends`.
