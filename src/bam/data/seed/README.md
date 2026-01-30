# BAM_seed — Interactive Project Bootstrapping

BAM_seed guides an AI agent through setting up a new BAM project interactively
with a human. The agent reads playbooks, interviews the human, reasons about
the best setup, explains the plan, and executes it.

## How It Works

The seed contains three layers:

1. **Playbooks** (markdown) — Step-by-step guides the agent reads at each stage
2. **Decision Data** (JSON) — Project profiles, recommendation rules, checklists
3. **Automation** (Python) — `SeedRunner` class that executes the mechanical setup

## Start Here — Playbook Order

Follow these playbooks in sequence:

| Step | Playbook | What Happens |
|------|----------|--------------|
| 0 | `playbooks/00_overview.md` | Explain BAM to the human, set expectations |
| 1 | `playbooks/01_choose_location.md` | Decide where to create the project directory |
| 2 | `playbooks/02_interview.md` | Structured interview to build a project profile |
| 3 | `playbooks/03_recommend.md` | Match the profile to a setup configuration |
| 4 | `playbooks/04_explain_setup.md` | Present the recommended plan to the human |
| 5 | `playbooks/05_execute.md` | Run the setup using `SeedRunner` |
| 6 | `playbooks/06_completion.md` | Summarize what was created, next steps |

## Key Files

| Path | Purpose |
|------|---------|
| `profiles/project_profile_schema.json` | Schema for interview output |
| `profiles/recommendation_rules.json` | IF-THEN rules for setup decisions |
| `profiles/backend_decision_matrix.json` | Backend comparison matrix |
| `checklists/prerequisite_checks.json` | System prerequisite checks |
| `checklists/hardware_checklist.json` | Post-setup checklist for HW projects |
| `checklists/software_checklist.json` | Post-setup checklist for SW projects |
| `checklists/minimal_checklist.json` | Lightweight checklist for quick-start |
| `examples/example_profile_hardware.json` | Reference hardware profile |
| `examples/example_profile_software.json` | Reference software profile |

## CLI Commands

```
python -m bam seed check-prereqs [--backend json|sqlite|neo4j|arango]
python -m bam seed recommend --profile <path>
python -m bam seed execute --profile <path> [--dry-run]
python -m bam seed show-playbook [step_number]

# LLM setup (required for agent-driven pipeline)
python -m bam setup llm --provider claude --api-key sk-ant-...
python -m bam setup llm --provider claude   # uses ANTHROPIC_API_KEY env var
```

## After Setup

Once the seed completes, the project is ready for Phase 2+ of the
`AGENT_GUIDE.md` workflow (sketch design, ingestion planning, execution).
