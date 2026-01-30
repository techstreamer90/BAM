# Playbook 01: Choose Project Location

## Purpose

Decide where to create the BAM project directory.

## What to Ask

1. **Where should the project directory live?**
   - This is the directory that will hold all BAM project files (model,
     config, ingestion plans, run history).
   - It should be separate from the source code being modeled.
   - Example: `C:/BAM_projects/my_chip_model`

2. **What should the project be named?**
   - A short, human-readable name (e.g., "Motor Controller", "Auth Service")
   - Used in project.json and reports

3. **Where is the source data?**
   - The root directory of the code/data being modeled
   - Example: `C:/repos/my-project` or `/home/user/projects/my-service`
   - This becomes `source_root` in project.json

## Naming Conventions

- Project directory: lowercase with underscores or hyphens
  (`motor_ctrl_model`, `auth-service-twin`)
- Avoid spaces in paths when possible
- Keep project dirs under a common parent (e.g., `C:/BAM_projects/`)

## Validation

Before proceeding, verify:
- [ ] The parent directory for the project exists (or can be created)
- [ ] The source root path exists and contains the expected data
- [ ] The project name is chosen
- [ ] No existing BAM project at the target location (or user confirms overwrite)

## What to Record

Save these three values — they feed into the project profile:
- `projectDir`: Full path to the project directory
- `projectName`: Human-readable name
- `sourceRoot`: Full path to source data

## Agent Notes

- Suggest a default location based on the current working directory
- If the human is unsure, propose `./bam_projects/<name>_model`
- Validate that the source root actually exists before moving on
- After confirming location, proceed to `02_interview.md`
