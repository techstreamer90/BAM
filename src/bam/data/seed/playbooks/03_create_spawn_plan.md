# Playbook 03: Create Sketch Structure Spawn Plan

## Purpose

Create a Spawnie workflow where **each input folder gets its own AI** to analyze
the data and propose what should be in the sketch. This is about understanding
structure, not extracting data yet.

## The Concept

Each AI spawn:
1. Looks at one input folder
2. Understands what's in there (files, formats, content)
3. Proposes: "Based on this data, the sketch should have these node types, edge types, and properties"

Then we consolidate all proposals into a unified sketch.

## Step 1: Design the Structure Analysis Workflow

For each folder in `project_input/`, create an analysis step:

```json
{
  "name": "sketch-structure-analysis",
  "description": "Each AI analyzes one input folder to propose sketch structure",

  "inputs": {
    "project_dir": "string"
  },

  "steps": {
    "analyze_jama": {
      "prompt": "You are analyzing the Jama folder at {{inputs.project_dir}}/project_input/Jama/ to help design a graph model (sketch).\n\nYour task:\n1. Examine all files in this folder\n2. Understand what entities exist (requirements, specs, etc.)\n3. Identify relationships between entities\n4. Note what properties/attributes each entity has\n\nPropose:\n- What NODE TYPES should exist in the sketch for this data?\n- What EDGE TYPES (relationships) should exist?\n- What PROPERTIES should each node type have?\n\nThink about how this data would connect to other sources (RTL code, tests, etc.)\n\nReturn a structured JSON proposal.",
      "model": "claude-sonnet"
    },

    "analyze_excel": {
      "prompt": "You are analyzing the Excel folder at {{inputs.project_dir}}/project_input/Excel/ to help design a graph model (sketch).\n\nYour task:\n1. Open and examine each spreadsheet\n2. Understand what entities are tracked (design requirements, traces, etc.)\n3. Identify relationships (especially cross-references to other systems)\n4. Note columns that represent properties\n\nPropose:\n- What NODE TYPES should exist for this data?\n- What EDGE TYPES connect these to other data?\n- What PROPERTIES are important?\n\nConsider how this connects to requirements in Jama, modules in RTL, etc.\n\nReturn a structured JSON proposal.",
      "model": "claude-sonnet"
    },

    "analyze_rtl": {
      "prompt": "You are analyzing the RTL folder at {{inputs.project_dir}}/project_input/RTL/ to help design a graph model (sketch).\n\nYour task:\n1. Scan the SystemVerilog/Verilog files\n2. Identify what design entities exist (modules, interfaces, packages)\n3. Understand the hierarchy and relationships\n4. Note important properties (parameters, ports, etc.)\n\nPropose:\n- What NODE TYPES for RTL entities?\n- What EDGE TYPES capture hierarchy and relationships?\n- What PROPERTIES matter for each type?\n\nThink about how RTL connects to requirements and tests.\n\nReturn a structured JSON proposal.",
      "model": "claude-sonnet"
    },

    "analyze_docs": {
      "prompt": "You are analyzing the Docs folder at {{inputs.project_dir}}/project_input/Docs/ to help design a graph model (sketch).\n\nYour task:\n1. Examine each document (PDFs, Word docs)\n2. Identify what entities are described (specs, designs, requirements)\n3. Note any cross-references to other systems (requirement IDs, module names)\n4. Understand document types and their roles\n\nPropose:\n- Should documents be NODE TYPES themselves?\n- What EDGE TYPES link documents to other entities?\n- What PROPERTIES describe documents?\n\nReturn a structured JSON proposal.",
      "model": "claude-sonnet"
    }
  },

  "outputs": {
    "jama_proposal": "{{steps.analyze_jama.output}}",
    "excel_proposal": "{{steps.analyze_excel.output}}",
    "rtl_proposal": "{{steps.analyze_rtl.output}}",
    "docs_proposal": "{{steps.analyze_docs.output}}"
  }
}
```

## Step 2: Customize for Available Sources

Only include steps for folders that exist:

```python
# Check which folders exist
folders = list(Path(project_dir, "project_input").iterdir())

# Build workflow with only existing sources
steps = {}
for folder in folders:
    step_name = f"analyze_{folder.name.lower()}"
    steps[step_name] = {
        "prompt": f"Analyze {folder.name} folder...",
        "model": "claude-sonnet"
    }
```

## Step 3: Present Plan to Human

```
"I'll create a workflow where each input folder gets its own AI to analyze
the contents and propose sketch structure.

**Spawn Plan:**

| AI Spawn | Folder | Task |
|----------|--------|------|
| analyze_jama | project_input/Jama/ | Propose structure for requirements data |
| analyze_excel | project_input/Excel/ | Propose structure for spreadsheet data |
| analyze_rtl | project_input/RTL/ | Propose structure for RTL code |
| analyze_docs | project_input/Docs/ | Propose structure for documents |

Each AI will independently analyze their folder and propose:
- Node types (what entities exist)
- Edge types (what relationships matter)
- Properties (what attributes to track)

After all complete, I'll consolidate their proposals into a unified sketch.

Execute this plan?"
```

## Step 4: Execute and Monitor

```bash
# Run the workflow
spawnie workflow workflows/sketch_structure.json -i project_dir=.

# Monitor in another terminal
spawnie monitor
```

The monitor will show each AI spawn progressing independently.

## Step 5: Consolidate Proposals

After all spawns complete, collect and consolidate:

```
"All analysis spawns complete. Here's what each AI proposed:

**Jama AI proposed:**
- Nodes: Requirement, Specification
- Edges: TRACES_TO, PARENT_OF
- Properties: id, title, status, priority

**Excel AI proposed:**
- Nodes: DesignRequirement, TraceLink
- Edges: IMPLEMENTS, SATISFIES
- Properties: dr_id, description, owner

**RTL AI proposed:**
- Nodes: Module, Interface, Package, TestClass
- Edges: INSTANTIATES, IMPORTS, IMPLEMENTS
- Properties: name, file_path, parameters

**Docs AI proposed:**
- Nodes: Document, Section
- Edges: REFERENCES, DESCRIBES
- Properties: title, type, path

Now let's consolidate these into a unified sketch..."
```

## Key Points

- **Each AI works independently** on its folder
- **No extraction yet** — just understanding structure
- **Proposals may overlap** — consolidation resolves this
- **Human approves** the final unified sketch

## Agent Notes

- The prompts should emphasize thinking about cross-source connections
- Each AI should consider how their data relates to other sources
- Run all spawns in parallel (no dependencies between them)
- After consolidation, proceed to `04_consolidate_sketch.md`
