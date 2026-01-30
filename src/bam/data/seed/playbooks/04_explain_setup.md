# Playbook 04: Explain the Setup Plan

## Purpose

Present the recommended setup to the human for approval before execution.

## Presentation Template

Use this structure to explain the plan:

---

### 1. Project Summary

> **Project:** {projectName}
> **Directory:** {projectDir}
> **Source Root:** {sourceRoot}
> **Domain:** {domain} ({subDomain})

### 2. Template Choice

> Using the **{template}** sketch template.
>
> **Why:** {rationale.template}
>
> This template provides:
> - Pre-defined node types for {domain} projects
> - Suggested colors: {list colors from template}
> - Sketch design questions to discuss in Phase 2

### 3. Storage Backend

> Using **{backend}** backend.
>
> **Why:** {rationale.backend}
>
> What this means:
> - JSON: Simple file-based storage, no setup needed, good for < 10K nodes
> - SQLite: File-based database, fast queries, good for 10K-100K nodes
> - Neo4j: Full graph database, best for complex cross-references at scale
> - Arango: Multi-model database, good for mixed graph + document needs

### 4. Pipeline

> Using **{pipeline}** pipeline.
>
> **Why:** {rationale.pipeline}

### 5. Parsers

> Configured parsers: {parsers[]}
>
> **Why:** {rationale.parsers}

### 6. What Will Be Created

```
{projectDir}/
    project.json          # Project configuration
    profile.json          # Your project profile (interview answers)
    sources.json          # Source definitions (from your data sources)
    checklist.json        # Setup and readiness checklist
    setup_report.json     # Record of what was done
    ingestion_plan.json   # Ingestion plan (empty, ready for Phase 3)
    tasks.json            # Task queue
    issues.json           # Issue tracker
    human-queue.json      # Human intervention queue
    history.json          # Run history
    model/
        sketch.json     # Graph sketch (from template)
        version.json      # Version tracking
        colors/           # Color data storage
            snapshots/    # Point-in-time snapshots
    runs/                 # Pipeline run outputs
    data/                 # Downloaded source data
```

### 7. Next Steps After Setup

1. Review the sketch design questions from the template
2. Design the sketch with the agent (`docs/agent_guide.md` Phase 2)
3. Create the ingestion plan (`docs/agent_guide.md` Phase 3)
4. Execute ingestion (`docs/agent_guide.md` Phase 4)
5. **Post-Ingestion Reconciliation** — After parsers add nodes, run
   reconciliation to create `REALIZES` edges bridging parser nodes to
   the sketch hierarchy. Source connectors do this automatically during
   ingestion, but it can also be triggered manually.

---

## What to Ask

After presenting the plan:

- "Does this look right? Any changes you'd like to make?"
- "Should I proceed with this setup?"

If the human wants changes:
- Adjust the profile or recommendations as needed
- Re-present the updated plan

## Agent Notes

- Be clear about what is automated vs. what requires human decisions later
- Emphasize that this is just the infrastructure — the real modeling work
  comes in Phases 2-4
- If the human approves, proceed to `05_execute.md`
