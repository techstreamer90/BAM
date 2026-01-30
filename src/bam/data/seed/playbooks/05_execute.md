# Playbook 05: Execute Setup

## Purpose

Run the automated setup using `SeedRunner` functions.

## Execution Steps

### Step 1: Check Prerequisites

**Tell the human:** "First, I'll verify your system has everything needed."

**Run:** `SeedRunner.check_prerequisites()` or CLI:
```
python -m bam seed check-prereqs --backend {backend}
```

**If checks fail:** Report what's missing and how to install it. Don't
proceed until prerequisites pass.

**If checks pass:** "All prerequisites verified. Proceeding with setup."

---

### Step 2: Initialize Project

**Tell the human:** "Creating the project directory and initial files."

**What happens:**
1. `init_project()` creates the directory structure with the selected template
2. Profile is written to `profile.json` in the project directory
3. Sources from the profile's `dataSources[]` are written to `sources.json`

---

### Step 3: Configure Backend

**Tell the human:** "Configuring the {backend} storage backend."

**What happens (if non-JSON):**
- Update `project.json` storage config to use the selected backend
- For SQLite: set up database paths
- For Neo4j/Arango: configure connection settings (will need human input)

**If JSON:** No additional configuration needed (it's the default).

---

### Step 4: Create Ingestion Plan Steps

**Tell the human:** "Setting up ingestion plan steps based on your data sources."

**What happens:**
- Creates the ingestion plan from template
- Auto-adds one step per data source from the profile
- Maps each source to the appropriate phase (backbone for primary sources,
  enrichment for detail sources, cross-references for linking sources)

---

### Step 5: Configure LLM Provider (if using agent-driven pipeline)

**Check:** Does the recommended pipeline or user preference include `agent-driven`?

**If yes:**

**Tell the human:** "The agent-driven pipeline requires an LLM provider. Let me check if one is configured."

**Run:** `python -m bam setup show`

**If not configured:**
```
python -m bam setup wizard
```

Or for manual setup:
```bash
# Set API key in environment (recommended)
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Configure provider
python -m bam setup llm --provider claude --test
```

**Then initialize project-level control.json:**
```
python -m bam --project <project-dir> control init
```

This creates:
- `control.json` — per-project LLM settings (models by task, etc.)
- `.env.example` — template showing required environment variables

**If no:** Skip this step.

---

### Step 6: Instantiate Checklist

**Tell the human:** "Creating your project readiness checklist."

**What happens:**
- Copies the appropriate checklist template (hardware/software/minimal)
- Marks automated items as done
- Saves to `checklist.json` in the project directory

---

### Step 7: Write Setup Report

**Tell the human:** "Generating the setup report."

**What happens:**
- Writes `setup_report.json` with:
  - Seed version
  - Execution timestamp
  - Profile reference
  - Recommendations used
  - Steps executed and their status
  - Next actions

---

## Dry Run Mode

If using `--dry-run`, show what would be created without actually creating
anything. Use this to verify before committing.

```
python -m bam seed execute --profile <path> --dry-run
```

## Error Handling

- If any step fails, stop and report the error
- The human can fix the issue and re-run (setup is idempotent for most steps)
- Each step's status is recorded in the setup report

## Agent Notes

- Execute steps one at a time, reporting progress after each
- Use the CLI commands or call `SeedRunner` directly — both work
- After successful execution, proceed to `06_completion.md`
