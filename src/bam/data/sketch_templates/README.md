# Sketch Templates

This directory contains starter templates for BAM project sketchs. Each
template provides suggested colors, node types, edge types, and design
questions tailored to a particular project category.

## Available Templates

| Template | File | Best For |
|----------|------|----------|
| Hardware Product | `hardware_product.json` | ASIC, SoC, FPGA, mixed-signal |
| Software Product | `software_product.json` | Libraries, services, applications |
| Minimal | `minimal.json` | Quick prototyping, unknown projects |

## Usage

Pass `--template <id>` when initializing a project:

```bash
python bam_cli.py init --project /path/to/project --name "My Project" --template hardware_product
```

This copies the template's suggested colors and node/edge types into the
project configuration and provides design questions to guide sketch creation.

## Template Structure

Each template JSON file contains:

- **suggestedColors** — Color names and descriptions for the project.
- **suggestedNodeTypes** — Node types appropriate for this project category.
- **suggestedEdgeTypes** — Edge types for relationships between nodes.
- **sketchDesignQuestions** — Questions to discuss with the human before
  building the sketch.
- **exampleSketch** — A minimal example showing the template in action.

## Creating Custom Templates

Copy an existing template and modify it. The `id` field must be unique.
Place the file in this directory with a `.json` extension.
