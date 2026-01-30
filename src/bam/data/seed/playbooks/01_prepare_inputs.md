# Playbook 01: Prepare Input Sources

## Purpose

Guide the human to organize their project data into the `project_input/` structure
that the agent will scan.

## Expected Input Structure

```
{projectDir}/
└── project_input/
    ├── Jama/              # Requirements exports
    │   └── *.csv, *.json
    ├── Excel/             # Design spreadsheets, matrices
    │   └── *.xlsx, *.csv
    ├── RTL/               # SystemVerilog/Verilog source
    │   └── **/*.sv, **/*.v
    ├── Docs/              # Specifications, design docs
    │   └── *.pdf, *.docx
    └── Tests/             # Test specifications, results
        └── *.csv, *.json
```

## What to Ask the Human

### Step 1: Project Location

"Where should we create the BAM project? This will be the root directory."

- Suggest: `./bam_project` or `~/projects/{project_name}_bam`
- Create the directory if it doesn't exist

### Step 2: Input Folder Setup

"I need you to organize your source data into `project_input/` subfolders.
Each subfolder represents one data source type."

**Common source types:**

| Folder | What Goes Here | Common Formats |
|--------|----------------|----------------|
| `Jama/` | Requirements exports from Jama | CSV, JSON |
| `Excel/` | Design spreadsheets, traceability matrices | XLSX, CSV |
| `RTL/` | Hardware design source code | .sv, .v files |
| `Docs/` | Specifications, design documents | PDF, DOCX |
| `Tests/` | Test plans, test results | CSV, JSON |
| `Coverage/` | Coverage reports | CSV, HTML, XML |

"Which of these do you have? Create a subfolder for each and copy your files there."

### Step 3: Confirm Readiness

Once the human has prepared the folders:

"Let me know when you've placed your files in `project_input/`. I'll scan
each folder to understand what we're working with."

## Folder Naming Convention

- Use clear, descriptive names
- One source type per folder
- Can have subdirectories within each folder
- Agent will recursively scan each folder

## Example Prepared Structure

```
~/my_chip_project/
└── project_input/
    ├── Jama/
    │   └── requirements_export_2024-01-15.csv
    ├── Excel/
    │   ├── design_requirements.xlsx
    │   └── traceability_matrix.xlsx
    ├── RTL/
    │   ├── src/
    │   │   ├── top_module.sv
    │   │   └── subsystem/
    │   │       └── *.sv
    │   └── tb/
    │       └── test_*.sv
    └── Docs/
        ├── architecture_spec.pdf
        └── design_spec.docx
```

## Agent Notes

- Don't proceed until the human confirms files are in place
- The folder structure doesn't need to be perfect — agent will adapt
- If the human doesn't have a source type, that's fine (skip that folder)
- Create the project directory if needed: `mkdir -p {projectDir}/project_input`
- After inputs are prepared, proceed to `02_scan_inputs.md`
