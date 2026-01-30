# Playbook 06: Completion

## Purpose

Summarize what was created and guide the human to next steps.

## Completion Message Template

---

**Setup Complete!**

Project **{projectName}** has been created at `{projectDir}`.

### What Was Created

| File | Purpose |
|------|---------|
| `project.json` | Project configuration with {template} template |
| `profile.json` | Your project profile (interview answers) |
| `sources.json` | {sourceCount} data source(s) configured |
| `checklist.json` | Project readiness checklist |
| `setup_report.json` | Record of this setup |
| `ingestion_plan.json` | Ingestion plan with {stepCount} initial steps |
| `model/sketch.json` | Graph sketch from {template} template |

### Configuration

- **Backend:** {backend}
- **Pipeline:** {pipeline}
- **Parsers:** {parsers}

### Next Steps

1. **Review the checklist** — Open `checklist.json` and work through any
   unchecked items
2. **Design the sketch** — Follow AGENT_GUIDE Phase 2 to refine the graph
   structure with sketch design questions from the template
3. **Refine the ingestion plan** — Follow AGENT_GUIDE Phase 3 to add detail
   to the auto-generated steps
4. **Execute ingestion** — Follow AGENT_GUIDE Phase 4 to populate the model

### Useful Commands

```
python -m bam --project {projectDir} info          # Show project info
python -m bam --project {projectDir} plan show     # View ingestion plan
python -m bam --project {projectDir} plan validate # Validate the plan
python -m bam --project {projectDir} stats         # Model statistics
python -m bam --project {projectDir} test show     # Test chain overview
python -m bam --project {projectDir} test run      # Run regression tests
python -m bam --project {projectDir} review show   # Inspect sketch review (agent-driven)
python -m bam --project {projectDir} resume <id>   # Resume paused pipeline
python -m bam setup llm --provider claude          # Configure LLM (for agent-driven)
```

---

## Agent Notes

- Present this summary clearly
- Offer to start Phase 2 (sketch design) immediately if the human wants
- The setup report at `setup_report.json` has detailed records if needed
- The AGENT_GUIDE at `docs/agent_guide.md` has the full Phase 2-4 workflow
