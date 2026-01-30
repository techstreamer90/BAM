# BAM Agent Onboarding Guide

This guide walks an AI agent (or a human+agent team) through the full process
of building a digital twin model with BAM. Follow the four phases in order.

---

## Phase 1: Understand BAM

**Goal:** Learn what BAM does and how the tool is structured.

1. Read `BAM_mission.md` in the repository root for the high-level vision.
2. Skim the directory layout:
   - `src/bam/data/` — tool code shared by all projects (scripts, pipelines, prompts, templates).
   - A **project directory** (created by the seed workflow) holds per-project state:
     `project.json`, `sources.json`, `model/sketch.json`, etc.
3. Understand the three pipeline types:
   - **Standard** (`src/bam/data/pipelines/standard.json`): Full ingestion from scratch using hardcoded parsers.
   - **Incremental** (`src/bam/data/pipelines/incremental.json`): Delta updates to an existing model.
   - **Agent-Driven** (`src/bam/data/pipelines/agent-driven.json`): LLM-driven ingestion where an AI analyses incoming data and produces a transform plan instead of relying on hardcoded parsers. Useful when no parser exists for a data source or the mapping requires judgment.
4. Review `agent_tiers.json` and `process_hints.json` for guidance metadata.

**Checkpoint:** You can explain what a sketch is, what color/colors are, and
how the pipeline stages connect.

---

## Phase 2: Design the Sketch

**Goal:** Define the graph structure (node types, edge types, colors) for the
target project.

1. Pick a sketch template from `src/bam/data/sketch_templates/`:
   | Template | Best for |
   |----------|----------|
   | `hardware_product.json` | ASIC, SoC, FPGA, or mixed-signal products |
   | `software_product.json` | Software libraries, services, applications |
   | `minimal.json` | Quick prototyping or unknown project shape |
2. The seed workflow (`python -m bam seed execute`) creates the project with the
   chosen template. If you are past seed, the project already exists.
3. Answer the **sketch design questions** listed in the template — discuss
   each one with the human.
4. Edit `model/sketch.json` in the project to add the agreed-upon node types,
   edge types, and initial hierarchy.

**Checkpoint:** `sketch.json` has a coherent set of nodes and edges, reviewed
by the human.

---

## Phase 3: Create the Ingestion Plan

**Goal:** Decide which data sources to ingest, in what order, and with what
chunk strategy.

1. Create a plan:
   ```
   python -m bam --project <dir> plan create
   ```
2. For each data source, add steps:
   ```
   python -m bam --project <dir> plan add-step \
     --phase backbone --name "Ingest RTL modules" \
     --source rtl --agent-tier standard \
     --description "Parse Verilog files and create RTL module nodes"
   ```
3. Review the plan:
   ```
   python -m bam --project <dir> plan show
   ```
4. Validate ordering and dependencies:
   ```
   python -m bam --project <dir> plan validate
   ```

### Ordering Rules (from `process_hints.json`)

- **Backbone first:** Ingest top-level documents before detail sources.
- **Sketch before color:** Get the graph structure right, then enrich.
- **Hierarchical order:** Parent nodes before children.
- **Cross-references last:** Link sources (traceability, coverage) come after
  both ends of the link exist.

### Chunk Size Reference

| Data Type | Recommended Max Batch | Notes |
|-----------|-----------------------|-------|
| RTL / Verilog files | 50 files | Group by module hierarchy |
| Documentation pages | 100 pages | Group by section |
| Test cases | 200 cases | Group by test plan |
| Requirements | 100 items | Group by specification |
| Coverage data | 1000 bins | Group by coverage group |

**Checkpoint:** `ingestion_plan.json` exists and `plan validate` passes.

---

## Phase 4: Execute the Plan

**Goal:** Run ingestion step-by-step, verifying after each step.

1. See the next step:
   ```
   python -m bam --project <dir> plan next
   ```
2. Execute the step (run the appropriate pipeline stage or parser).
3. Mark it complete:
   ```
   python -m bam --project <dir> plan complete-step --step <id>
   ```
4. After ingestion, run **reconciliation** to bridge parser nodes with
   the pre-existing sketch hierarchy. Source connectors that call
   `_reconcile_sketch()` do this automatically — creating `REALIZES`
   edges from parser nodes to matching sketch nodes.
5. After each major phase, run verification:
   ```
   python -m bam --project <dir> stats
   python -m bam --project <dir> test run
   ```
   The `test run` command executes the full regression test chain — an
   accumulating suite that grows with each ingestion. It catches
   regressions where a later ingestion breaks earlier data.
6. To see what tests have accumulated:
   ```
   python -m bam --project <dir> test show
   ```
7. Repeat until the plan is fully executed.

### Using the Agent-Driven Pipeline

For data sources without a pre-built parser, use the agent-driven pipeline
instead of standard/incremental. The LLM analyses the data and produces a
transform plan automatically.

**One-time setup** (if not already configured):
```
python -m bam setup llm --provider claude --api-key sk-ant-...
# Or rely on the ANTHROPIC_API_KEY environment variable:
python -m bam setup llm --provider claude
```

**Running agent-driven ingestion:**
```
python -m bam orchestrator create <source-id> --pipeline agent-driven
python -m bam orchestrator run <task-id>
```

The agent-review stage sends a sample of the raw data plus the current sketch
summary to the LLM. The LLM returns a `TransformPlan` (node/edge mappings)
and optionally a `SketchChangeProposal` (new types needed).

**If the pipeline pauses** (major sketch changes proposed):
```
python -m bam --project <dir> review show       # inspect proposed changes
python -m bam --project <dir> review approve    # apply to sketch
python -m bam --project <dir> resume <task-id>  # continue from transform

# Or reject:
python -m bam --project <dir> review reject --feedback "..."
python -m bam --project <dir> resume <task-id>  # re-runs agent-review
```

Minor sketch changes (nodes using existing types) are auto-applied without
pausing. The transform stage then executes the plan mechanically using
pattern-based ID generation, with an LLM fallback for items that don't match
any mapping.

**Checkpoint:** All plan steps are complete, model stats look correct,
`test run` passes, and verification passes.

---

## Sketch Format Reference

The sketch (`model/sketch.json`) uses a canonical format for nodes and edges.

### Canonical Node Format

```json
{
  "node-id": {
    "id": "node-id",
    "type": "RTLModule",
    "label": "top_module",
    "source_id": "project-rtl"
  }
}
```

Fields:
- `id` (required): Unique node identifier.
- `type` (required): Node type (e.g., `Product`, `Subsystem`, `RTLModule`, `TestCase`).
- `label` (required): Human-readable display name.
- `source_id` (optional): Which source/parser created this node.

### Canonical Edge Format

```json
{
  "edge-id": {
    "id": "edge-id",
    "type": "CONTAINS",
    "source_node_id": "product-top",
    "target_node_id": "subsys-cpu",
    "source_id": null
  }
}
```

Fields:
- `id` (required): Unique edge identifier.
- `type` (required): Edge type in **UPPERCASE** (e.g., `CONTAINS`, `INSTANTIATES`, `VERIFIES`, `REALIZES`).
- `source_node_id` (required): ID of the source node.
- `target_node_id` (required): ID of the target node.
- `source_id` (optional): Which source/parser created this edge.

### Edge Type Convention

All edge types must be UPPERCASE. Standard edge types:
`CONTAINS`, `INSTANTIATES`, `IMPLEMENTS`, `VERIFIES`, `TRACES_TO`, `DEPENDS_ON`,
`CONNECTS_TO`, `COVERS`, `MEASURES`, `DOCUMENTS`, `DERIVES_FROM`, `CONFIGURES`,
`REALIZES`, `HAS_PORT`, `ENRICHES`.

Old lowercase edge types are automatically normalized to UPPERCASE on load.

---

## Parser Node ID Convention

All parser-generated node IDs follow the pattern:

```
{source_id}-{entity_name}
```

Examples:
- RTL module: `myproject-rtl-top_module`
- Test case: `myproject-dv-smoke_test`
- Doc section: `myproject-docs-overview`
- Config: `myproject-cfg-default`
- Port: `myproject-rtl-top_module-port-clk_i`
- Parameter: `myproject-rtl-top_module-param-DataWidth`

Edge IDs follow: `edge-{source_node_id}-{EDGE_TYPE}-{target_entity}`

This convention ensures IDs are deterministic and re-runnable (same input
always produces the same IDs).

---

## Agent Tier Reference

| Tier | Description | Typical Tasks |
|------|-------------|---------------|
| **low** | Simple, repetitive, low-risk | Download, file copying, format conversion |
| **standard** | Moderate judgment needed | Parsing, basic transforms, report generation |
| **high** | Complex reasoning required | Schema design, cross-reference mapping, verification, conflict resolution |

See `agent_tiers.json` for full definitions including model recommendations.

---

## Quick Reference: Key Files

| File | Location | Purpose |
|------|----------|---------|
| `AGENT_GUIDE.md` | `src/bam/data/` | This file |
| `agent_tiers.json` | `src/bam/data/` | Tier definitions |
| `process_hints.json` | `src/bam/data/` | Ordering advice and common mistakes |
| `ingestion_plan_template.json` | `src/bam/data/` | Template for new ingestion plans |
| Sketch templates | `src/bam/data/sketch_templates/` | Starting points for sketch design |
| Pipeline definitions | `src/bam/data/pipelines/` | Stage definitions with agent guidance |
| `project.json` | `<project>/` | Per-project configuration |
| `ingestion_plan.json` | `<project>/` | Per-project ingestion plan |
| `test_chain.json` | `<project>/` | Accumulating regression test chain |
| `model/sketch.json` | `<project>/model/` | The graph sketch |
