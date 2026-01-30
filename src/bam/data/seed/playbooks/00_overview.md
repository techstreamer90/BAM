# Playbook 00: Overview

## Purpose

Introduce BAM and the AI-driven sketch creation process.

## What to Tell the Human

BAM (Build Accurate Models) creates digital twin graph models from project data.

### The Core Concept

Your project data lives in different sources — requirements in Jama, designs in
Excel, code in SystemVerilog files. BAM brings these together into a unified
**sketch** (graph model) that captures the relationships between everything.

### How It Works

```
project_input/           Your prepared input folders
├── Jama/               (requirements exports)
├── Excel/              (design spreadsheets)
├── RTL/                (SystemVerilog files)
└── Docs/               (PDFs, Word docs)
        ↓
   [AI Agent]           Scans, plans, orchestrates via Spawnie
        ↓
   model/sketch.json    Unified graph model
```

### The Agent's Approach

1. **Scan** — Look at all your `project_input/` folders, understand what's there
2. **Assess** — Check if anything is missing, ask clarifying questions
3. **Plan** — Create a Spawnie workflow to extract and analyze each source
4. **Execute** — Run the workflow, monitor progress in real-time
5. **Synthesize** — Collect results and design the final sketch structure

### Key Terms

- **Sketch**: Graph structure — nodes (components, requirements, tests) and
  edges (relationships like traces-to, verifies, implements)
- **Color**: Detailed properties attached to nodes (metadata, status, etc.)
- **Spawnie**: Workflow orchestrator that runs extraction tasks in parallel
- **Intermediate Format**: Canonical JSON that all extractors produce

### Your Role

- Prepare your input data in `project_input/` subfolders
- Answer questions when the agent needs clarification
- Review and approve the proposed sketch design
- Monitor progress (optional) via `spawnie monitor`

### The Agent's Role

- Analyze what data you have
- Identify gaps or unclear areas
- Create an extraction workflow
- Run and monitor the workflow
- Synthesize results into a coherent sketch

## Agent Notes

- Present this conversationally, gauge the human's familiarity
- Emphasize that they should prepare `project_input/` folders first
- The agent drives the process but the human approves structural decisions
- After overview, proceed to `01_prepare_inputs.md`
