# Playbook 00: Overview

## Purpose

Introduce BAM to the human and set expectations for the setup process.

## What to Tell the Human

BAM (Build Accurate Models) creates multi-colored digital twin models from
existing project data. It ingests source code, documentation, requirements,
test plans, and other artifacts into a structured graph model that AI agents
can query with high speed and precision.

### Key Concepts

- **Sketch**: The graph structure — nodes (components, documents, tests) and
  edges (relationships between them). Think of it as the blueprint.
- **Color/Colors**: Detailed data attached to sketch nodes, organized by
  domain (conceptual, design, verification, etc.). Different backends can
  store different colors.
- **Ingestion**: The process of parsing source data and populating the model.
- **Pipeline**: A defined sequence of stages (extract, transform, validate,
  integrate) that processes data into the model. Three types exist:
  standard (hardcoded parsers), incremental (delta updates), and
  agent-driven (LLM analyses data and produces a transform plan).

### What BAM_seed Does

BAM_seed is the bootstrapping layer. It will:

1. Interview you about your project (what it is, what data you have, how
   complex it is, what you want to do with the model)
2. Recommend a setup configuration (template, backend, parsers, pipeline)
3. Explain the recommended plan so you understand what will be created
4. Execute the setup to create your project infrastructure
5. Hand off to `docs/agent_guide.md` for sketch design and ingestion

### The Human's Role

- Answer interview questions honestly — the recommendations depend on it
- Approve or adjust the recommended setup before execution
- Provide access to source data locations
- Participate in sketch design decisions after setup

### Time Commitment

The interview and setup process is interactive. The agent handles all file
creation and configuration; the human provides domain knowledge and decisions.

## Agent Notes

- Read this playbook first, then present the overview conversationally
- Don't dump all information at once — gauge the human's familiarity with
  modeling concepts
- If the human is experienced, abbreviate; if new, explain more
- After the overview, proceed to `01_choose_location.md`
