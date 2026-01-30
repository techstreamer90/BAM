# Playbook 05: Color the Sketch (Phase 2)

## Purpose

With the sketch structure defined, now spawn AIs to **populate** the sketch
with actual data. Each AI:
1. Understands the complete sketch
2. Analyzes their assigned input folder
3. Adds nodes, edges, and properties (color) to the model
4. Optimizes for future agent consumption

## The Coloring Concept

Phase 1 defined **what types exist**. Phase 2 fills in **what instances exist**.

Each coloring AI:
- Receives the full sketch schema
- Is assigned one input folder
- Must understand the whole system context
- Adds their data in a way that connects to other sources
- Thinks about how future agents will query this data

## Step 1: Create the Coloring Workflow

```json
{
  "name": "sketch-coloring",
  "description": "Each AI populates the sketch with data from their folder",

  "inputs": {
    "project_dir": "string",
    "sketch_schema": "object"
  },

  "steps": {
    "color_jama": {
      "prompt": "You are a coloring agent for the BAM model.\n\n**THE SKETCH (full system model):**\n{{inputs.sketch_schema}}\n\n**YOUR TASK:**\nAnalyze the Jama folder at {{inputs.project_dir}}/project_input/Jama/ and add data to the model.\n\n**CONTEXT:**\nThis sketch represents a complete system with requirements, design, RTL implementation, and tests. Your folder contains Jama requirements. Other agents are simultaneously adding data from Excel, RTL, and Docs folders.\n\n**YOU MUST:**\n1. Create Requirement nodes for each requirement in your data\n2. Extract all properties (id, title, status, priority, etc.)\n3. Create edges where your data references other entities (TRACES_TO if requirements reference modules)\n4. Think about semantic connections - what implicit relationships exist?\n5. Format data so future agents can easily query it\n\n**OUTPUT:**\nReturn JSON with:\n- nodes: [{id, type, properties}]\n- edges: [{from, to, type, properties}]\n- semantic_notes: observations about relationships for future agents",
      "model": "claude-sonnet"
    },

    "color_excel": {
      "prompt": "You are a coloring agent for the BAM model.\n\n**THE SKETCH (full system model):**\n{{inputs.sketch_schema}}\n\n**YOUR TASK:**\nAnalyze the Excel folder at {{inputs.project_dir}}/project_input/Excel/ and add data to the model.\n\n**CONTEXT:**\nThis sketch represents a complete system. Your folder contains Excel spreadsheets with design requirements and traceability data. Other agents handle Jama requirements, RTL code, and documents.\n\n**YOU MUST:**\n1. Create DesignRequirement nodes for each DR\n2. Create edges: DERIVES_FROM (to Jama requirements), IMPLEMENTS (from modules)\n3. Parse traceability matrices to create relationship edges\n4. Capture semantic relationships not explicitly stated\n5. Note any IDs that reference other sources\n\n**OUTPUT:**\nReturn JSON with nodes, edges, semantic_notes.",
      "model": "claude-sonnet"
    },

    "color_rtl": {
      "prompt": "You are a coloring agent for the BAM model.\n\n**THE SKETCH (full system model):**\n{{inputs.sketch_schema}}\n\n**YOUR TASK:**\nAnalyze the RTL folder at {{inputs.project_dir}}/project_input/RTL/ and add data to the model.\n\n**CONTEXT:**\nThis sketch represents requirements, design, implementation, and verification. Your folder contains SystemVerilog code - the actual implementation. Requirements trace TO your modules.\n\n**YOU MUST:**\n1. Create Module nodes for each module (with parameters, ports)\n2. Create Interface nodes for interfaces\n3. Create TestClass nodes for UVM test classes\n4. Create INSTANTIATES edges for module hierarchy\n5. Look for requirement IDs in comments - create edges\n6. Identify which modules are top-level vs leaf\n\n**OUTPUT:**\nReturn JSON with nodes, edges, semantic_notes.",
      "model": "claude-sonnet"
    },

    "color_docs": {
      "prompt": "You are a coloring agent for the BAM model.\n\n**THE SKETCH (full system model):**\n{{inputs.sketch_schema}}\n\n**YOUR TASK:**\nAnalyze the Docs folder at {{inputs.project_dir}}/project_input/Docs/ and add data to the model.\n\n**CONTEXT:**\nDocuments describe the system. They reference requirements, modules, and tests. Your job is to create Document nodes and link them to what they describe.\n\n**YOU MUST:**\n1. Create Document nodes for each document\n2. Extract document type (spec, design doc, test plan)\n3. Find references to requirement IDs, module names\n4. Create DESCRIBES edges to referenced entities\n5. Note which documents are authoritative sources\n\n**OUTPUT:**\nReturn JSON with nodes, edges, semantic_notes.",
      "model": "claude-sonnet"
    }
  },

  "outputs": {
    "jama_color": "{{steps.color_jama.output}}",
    "excel_color": "{{steps.color_excel.output}}",
    "rtl_color": "{{steps.color_rtl.output}}",
    "docs_color": "{{steps.color_docs.output}}"
  }
}
```

## Step 2: Execute Coloring Workflow

```bash
# Run the coloring workflow
spawnie workflow workflows/sketch_coloring.json \
  -i project_dir=. \
  --inputs-json '{"sketch_schema": <contents of sketch.json>}'

# Monitor progress
spawnie monitor
```

## Step 3: Merge Coloring Results

After all coloring AIs complete:

1. **Collect all nodes and edges** from each output
2. **Resolve ID conflicts** (same entity found by multiple AIs)
3. **Merge semantic notes** for future reference
4. **Write to sketch.json**

```python
# Pseudo-code for merging
all_nodes = {}
all_edges = []
semantic_notes = []

for source in ["jama", "excel", "rtl", "docs"]:
    color_data = load_color_output(source)

    for node in color_data["nodes"]:
        node_id = f"{source}:{node['id']}"
        all_nodes[node_id] = node

    for edge in color_data["edges"]:
        all_edges.append(edge)

    semantic_notes.extend(color_data.get("semantic_notes", []))

# Write merged data to sketch
sketch["nodes"] = all_nodes
sketch["edges"] = all_edges
sketch["metadata"]["semantic_notes"] = semantic_notes
```

## Step 4: Validate and Report

```
"Coloring complete! Here's what was added:

**Nodes Added:**
| Type | Count | Source |
|------|-------|--------|
| Requirement | 342 | Jama |
| DesignRequirement | 89 | Excel |
| Module | 45 | RTL |
| Interface | 12 | RTL |
| TestClass | 23 | RTL |
| Document | 8 | Docs |
| **Total** | **519** | |

**Edges Added:**
| Type | Count |
|------|-------|
| DERIVES_FROM | 67 |
| TRACES_TO | 198 |
| IMPLEMENTS | 45 |
| INSTANTIATES | 82 |
| VERIFIES | 156 |
| DESCRIBES | 34 |
| **Total** | **582** |

**Semantic Notes from AIs:**
- Jama AI: 'Requirements REQ-100 through REQ-150 all trace to top_module'
- RTL AI: 'Module hierarchy is 3 levels deep, top_module → subsystem → leaf'
- Docs AI: 'architecture_spec.pdf is the authoritative source for requirements'
"
```

## Step 5: Human Review

Let the human review the populated model:

```
"Would you like to:
1. View sample nodes from each type?
2. Check specific relationships (e.g., what traces to top_module)?
3. See the semantic notes from each AI?
4. Proceed to completion?"
```

## Key Principles for Coloring AIs

Each coloring AI should:

1. **Understand the whole sketch** — not just their folder
2. **Think about connections** — how does their data relate to others?
3. **Add semantic value** — not just raw extraction
4. **Optimize for queries** — what will future agents ask?
5. **Note implicit relationships** — things not explicitly stated

## Agent Notes

- Coloring AIs run in parallel (no dependencies)
- Each AI has full context of the sketch schema
- Merging may need conflict resolution (same entity, different sources)
- Semantic notes are valuable for future agents
- After coloring complete, proceed to `06_completion.md`
