# Playbook 04: Consolidate Sketch

## Purpose

Take all the structure proposals from the AI spawns and consolidate them into
a unified sketch. Resolve overlaps, discuss with human, finalize the schema.

## Step 1: Gather All Proposals

Collect outputs from the structure analysis workflow:

```
Proposals received:
├── Jama AI: Requirement, Specification + TRACES_TO, PARENT_OF
├── Excel AI: DesignRequirement, TraceLink + IMPLEMENTS, SATISFIES
├── RTL AI: Module, Interface, Package, TestClass + INSTANTIATES, IMPORTS
└── Docs AI: Document, Section + REFERENCES, DESCRIBES
```

## Step 2: Identify Overlaps and Conflicts

Look for:
- **Same concept, different names**: Requirement vs DesignRequirement
- **Duplicate edge types**: IMPLEMENTS proposed by multiple AIs
- **Missing connections**: How does Jama connect to RTL?

```
"Looking at all proposals, I see:

**Overlaps:**
- 'Requirement' (Jama) and 'DesignRequirement' (Excel) seem related
  → Should these be one type or two?

- 'IMPLEMENTS' proposed by both Excel and RTL AIs
  → Same meaning or different?

**Gaps:**
- No direct edge between Jama requirements and RTL modules
  → The Jama AI mentioned TRACES_TO but didn't specify target type

**Questions for you:**
1. Are Jama requirements and Excel design requirements the same thing?
2. Should documents be nodes, or just metadata on other nodes?
"
```

## Step 3: Resolve with Human

Have a back-and-forth conversation to resolve:

```
Human: "Jama has high-level requirements, Excel has derived design requirements.
        Keep them separate but link them."

Agent: "OK, I'll create:
        - Requirement (from Jama) - high level
        - DesignRequirement (from Excel) - derived
        - DERIVES_FROM edge: DesignRequirement → Requirement

        Does that capture the relationship?"
```

## Step 4: Build Unified Sketch

Create the consolidated schema:

```json
{
  "node_types": {
    "Requirement": {"source": "Jama", "properties": ["id", "title", "status"]},
    "DesignRequirement": {"source": "Excel", "properties": ["dr_id", "description"]},
    "Module": {"source": "RTL", "properties": ["name", "file_path", "parameters"]},
    "Interface": {"source": "RTL", "properties": ["name", "file_path"]},
    "TestClass": {"source": "RTL", "properties": ["name", "uvm_type"]},
    "Document": {"source": "Docs", "properties": ["title", "path", "type"]}
  },
  "edge_types": {
    "DERIVES_FROM": {"from": "DesignRequirement", "to": "Requirement"},
    "TRACES_TO": {"from": "Requirement", "to": "Module"},
    "IMPLEMENTS": {"from": "Module", "to": "DesignRequirement"},
    "INSTANTIATES": {"from": "Module", "to": "Module"},
    "VERIFIES": {"from": "TestClass", "to": "Requirement"},
    "DESCRIBES": {"from": "Document", "to": ["Requirement", "Module"]}
  }
}
```

## Step 5: Present Final Sketch for Approval

```
"Here's the consolidated sketch:

**Node Types (6):**
| Type | Source | Description |
|------|--------|-------------|
| Requirement | Jama | High-level requirements |
| DesignRequirement | Excel | Derived design requirements |
| Module | RTL | Hardware modules |
| Interface | RTL | SystemVerilog interfaces |
| TestClass | RTL | UVM test classes |
| Document | Docs | Specification documents |

**Edge Types (6):**
| Edge | From → To | Meaning |
|------|-----------|---------|
| DERIVES_FROM | DesignReq → Requirement | DR derived from high-level req |
| TRACES_TO | Requirement → Module | Requirement traces to implementation |
| IMPLEMENTS | Module → DesignReq | Module implements design requirement |
| INSTANTIATES | Module → Module | Module hierarchy |
| VERIFIES | TestClass → Requirement | Test verifies requirement |
| DESCRIBES | Document → any | Document describes entity |

Does this sketch capture your system correctly?"
```

## Step 6: Save the Sketch

Once approved, save to `model/sketch.json`:

```bash
# Create model directory
mkdir -p {projectDir}/model

# Save sketch schema (nodes and edges empty, ready for Phase 2)
```

## Phase 1 Complete

At this point:
- Sketch structure is defined (node types, edge types)
- Sketch is empty (no actual nodes or edges yet)
- Ready for Phase 2: Coloring

**Next:** Proceed to `05_color_sketch.md` (Phase 2)

## Agent Notes

- This is collaborative — don't just merge blindly
- Human domain knowledge resolves semantic questions
- Keep sketch minimal — only types that will be used
- The sketch can evolve in Phase 2 if needed
- Document decisions for future reference