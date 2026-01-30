# BAM - Build Accurate Models

BAM builds multi-colored, multidimensional graph models (digital twins) from
existing project artifacts: requirements, design docs, source code, and test
data.

## For Agents

If you are an AI agent asked to work with BAM, start here:

1. Read [docs/agent_guide.md](docs/agent_guide.md) to understand the
   four-phase workflow (understand, design, plan, ingest).
2. Read [docs/README.md](docs/README.md) for the architecture (sketch/color
   model, pipelines, backends).
3. To set up a new project, follow the seed playbooks in order starting at
   `src/bam/data/seed/playbooks/00_overview.md`. Each playbook tells you
   what to do and which file to read next.

## Getting Started (for humans)

### 1. Install

```bash
pip install -e ".[dev]"

# Optional: install LLM support for agent-driven ingestion
pip install -e ".[llm]"
```

### 2. Start a conversation with your AI agent

Open your agent (e.g. Claude Code) in this repository and say:

> I'd like to set up a new BAM project.

The agent reads the seed playbooks, asks you about your project -- what it
is, what data you have, how complex it is -- and then configures everything:
template, backend, ingestion plan, and checklist.

### 3. Work with the agent through ingestion

Once the project exists the agent follows the
[onboarding guide](docs/agent_guide.md) to design the graph sketch, plan
the ingestion, and populate the model. At any point you can check progress:

```bash
python -m bam --project ./my-project plan show   # ingestion plan
python -m bam --project ./my-project stats       # model statistics
python -m bam --project ./my-project test show   # test chain overview
python -m bam --project ./my-project test run    # run regression tests
python -m bam list-projects C:/models            # all projects
```

### 4. (Optional) Set up LLM-driven ingestion

BAM includes an **agent-driven pipeline** that uses an LLM to analyse
incoming data and decide how it maps to the graph model, instead of relying
on hardcoded parsers.

#### First-time setup

Run the interactive wizard (recommended for first-time users):

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

#### Per-project configuration

Each project can have its own LLM settings in `control.json`:

```bash
# Initialize control.json for a project
python -m bam --project ./my-project control init

# View configuration
python -m bam --project ./my-project control show

# Use different models for different tasks (cost optimization)
python -m bam --project ./my-project control set-model --task agent-review --model claude-sonnet-4-20250514
python -m bam --project ./my-project control set-model --task transform-fallback --model claude-haiku-4-20250514
```

#### Running agent-driven ingestion

```bash
python -m bam --project ./my-project ingest --pipeline agent-driven --source-id my-source
```

If the LLM proposes major changes to the graph structure, the pipeline
pauses for your approval:

```bash
python -m bam --project ./my-project review show      # inspect proposed changes
python -m bam --project ./my-project review approve   # apply and continue
python -m bam --project ./my-project review reject --feedback "..."
python -m bam --project ./my-project resume <task-id> # resume the pipeline
```

See [docs/README.md](docs/README.md) for full details on the agent-driven
pipeline.

## Documentation

| Doc | Contents |
|-----|----------|
| [Architecture](docs/README.md) | Sketch/color model, pipelines, backends |
| [Agent guide](docs/agent_guide.md) | Full four-phase workflow for agents |
| [Mission](docs/mission.md) | Why BAM exists |

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
