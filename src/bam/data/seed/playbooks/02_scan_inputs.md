# Playbook 02: Scan Input Sources

## Purpose

Perform a comprehensive scan of all `project_input/` folders to understand what
data is available, assess completeness, and identify gaps or unclear areas.

## The Scan Process

### Step 1: Enumerate Sources

List all subfolders in `project_input/`:

```bash
ls -la {projectDir}/project_input/
```

For each folder, identify:
- Folder name (source type)
- Number of files
- File types present
- Total size

**Report to human:**
```
"I found these input sources:

| Source | Files | Types | Size |
|--------|-------|-------|------|
| Jama/ | 3 | .csv | 2.4 MB |
| Excel/ | 5 | .xlsx, .csv | 1.8 MB |
| RTL/ | 127 | .sv, .v | 4.2 MB |
| Docs/ | 8 | .pdf, .docx | 12 MB |
"
```

### Step 2: Quick Content Scan

For each source folder, do a quick analysis:

**For CSV/Excel files:**
- Read headers/column names
- Count rows
- Identify key columns (ID, name, status, traces_to, etc.)

**For RTL files:**
- Count modules, interfaces, classes
- Identify top-level modules
- Note testbench vs design files

**For Documents:**
- Extract titles if possible
- Note page counts
- Identify document types (spec, design, test plan)

### Step 3: Build Source Inventory

Create a mental model of what's available:

```
Source Inventory:
├── Jama/ (requirements)
│   └── 342 requirements with ID, title, status, traces_to columns
├── Excel/ (design data)
│   ├── design_reqs.xlsx: 89 design requirements
│   └── trace_matrix.xlsx: requirement-to-module mapping
├── RTL/ (implementation)
│   ├── 45 design modules
│   ├── 12 interfaces
│   └── 23 testbench classes
└── Docs/ (specifications)
    ├── 3 architecture PDFs
    └── 5 design specs
```

### Step 4: Assess Completeness

Check for common gaps:

| Check | Question to Consider |
|-------|---------------------|
| Traceability | Can requirements trace to implementations? |
| Coverage | Is there coverage data? |
| Test results | Are test pass/fail results available? |
| Hierarchy | Is module hierarchy clear from RTL? |
| Cross-references | Do documents reference requirement IDs? |

### Step 5: Identify Unclear Areas

Flag anything that needs clarification:

- Columns with unclear meaning
- Files that don't fit expected patterns
- Missing expected data (e.g., requirements but no traces)
- Duplicate or conflicting data

### Step 6: Ask Clarifying Questions

**Report findings and ask questions:**

```
"Based on my scan, here's what I found:

**Requirements (Jama/):**
- 342 requirements in requirements_export.csv
- Columns: ID, Title, Status, Priority, Traces_To
- The Traces_To column references module names

**Design Data (Excel/):**
- design_reqs.xlsx has 89 items but no ID column — how should I identify these?
- trace_matrix.xlsx maps Req_ID to Module — this looks useful for edges

**RTL (RTL/):**
- 45 modules, 12 interfaces in src/
- 23 UVM test classes in tb/
- Top module appears to be 'chip_top'

**Questions:**
1. In design_reqs.xlsx, what column should I use as the unique identifier?
2. Should UVM testbench classes become nodes, or just the test cases they run?
3. I don't see coverage data — is that available, or should we skip coverage?
"
```

### Step 7: Resolve All Questions

Do not proceed until:
- All unclear columns/fields are explained
- Missing data is either provided or explicitly skipped
- The human confirms the inventory is complete

**Track resolutions:**
```
Resolutions:
- design_reqs.xlsx: Use "DR_Number" column as ID
- UVM classes: Create VerificationClass nodes, extract test methods later
- Coverage: Not available for initial sketch, will add later
```

## Output: Source Assessment

After scanning and resolving questions, you should have:

```json
{
  "sources": [
    {
      "folder": "Jama",
      "type": "requirements",
      "files": ["requirements_export.csv"],
      "record_count": 342,
      "key_columns": ["ID", "Title", "Status", "Traces_To"],
      "produces": ["Requirement"],
      "edges_to": ["RTLModule via Traces_To"]
    },
    {
      "folder": "Excel",
      "type": "design_requirements",
      "files": ["design_reqs.xlsx"],
      "record_count": 89,
      "key_columns": ["DR_Number", "Description", "Owner"],
      "produces": ["DesignRequirement"],
      "notes": "Use DR_Number as ID"
    },
    {
      "folder": "RTL",
      "type": "systemverilog",
      "files": "127 .sv files",
      "produces": ["RTLModule", "RTLInterface", "VerificationClass"],
      "hierarchy": "chip_top is top module"
    }
  ],
  "gaps": [
    "No coverage data available"
  ],
  "resolutions": {
    "design_reqs_id": "DR_Number column",
    "uvm_handling": "Create VerificationClass nodes"
  }
}
```

## Agent Notes

- Be thorough but not overwhelming — summarize, don't dump raw data
- Ask questions in batches, not one at a time
- The human may not know all answers — offer reasonable defaults
- Keep track of what was resolved vs. what was skipped
- After all questions resolved, proceed to `03_create_spawn_plan.md`
