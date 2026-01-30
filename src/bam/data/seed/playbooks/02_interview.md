# Playbook 02: Project Interview

## Purpose

Gather structured information about the project to build a profile that
drives setup recommendations.

## Interview Structure

Ask questions in groups. After each group, summarize what you heard and
confirm before moving on.

---

### Group 1: Project Identity

| Question | Why It Matters | What to Probe |
|----------|---------------|---------------|
| What does this project do? | Sets domain context | Get a 1-2 sentence description |
| Is this hardware, software, or mixed? | Determines template choice | If mixed, ask which is primary |
| What sub-domain? (e.g., ASIC, FPGA, web service, embedded) | Refines template and parser selection | Affects sketch node types |

---

### Group 2: Data Sources

| Question | Why It Matters | What to Probe |
|----------|---------------|---------------|
| What types of source data exist? | Determines which parsers to configure | RTL, docs, requirements, tests, configs, etc. |
| For each source type: where is it located? | Needed for source definitions | Relative or absolute paths |
| For each source type: what format? | Parser selection | Verilog, SystemVerilog, Markdown, XML, JSON, CSV, etc. |
| For each source type: roughly how large? | Affects backend choice and batch sizing | Number of files, total size, or item count |

Build a `dataSources[]` array from this group.

---

### Group 3: Complexity Assessment

| Question | Why It Matters | What to Probe |
|----------|---------------|---------------|
| How many distinct source types are there? | Affects ingestion plan complexity | Count from Group 2 |
| How many nodes do you estimate in the final model? | Backend selection threshold | <1K, 1K-10K, 10K-100K, >100K |
| How many major subsystems or components? | Sketch hierarchy depth | Top-level breakdown |
| Are there cross-references between source types? | Determines cross-reference phase needs | Requirements-to-tests, coverage-to-design, etc. |
| Is traceability required? | Adds traceability edges and validation | Regulatory, quality, or just nice-to-have |

---

### Group 4: Use Cases

| Question | Why It Matters | What to Probe |
|----------|---------------|---------------|
| What questions should the model answer? | Validates scope and completeness | "Which tests cover requirement X?" etc. |
| Who will use the model? | Affects what colors to prioritize | Engineers, managers, AI agents, auditors |
| What's the primary use case? | Guides template and color weighting | Impact analysis, traceability, documentation, exploration |

---

### Group 5: Constraints

| Question | Why It Matters | What to Probe |
|----------|---------------|---------------|
| Are there existing tools in the workflow? | Integration considerations | Jama, DOORS, Jira, custom tools |
| Team size working with BAM? | Affects complexity of setup | Solo, small team, large team |
| Any timeline pressure? | Affects whether to use minimal template | Quick prototype vs. production model |
| Backend preference? | May override recommendation | JSON (simple), SQLite (medium), Neo4j/Arango (large) |

---

## Building the Profile

As you interview, populate the profile structure:

```json
{
  "projectName": "",
  "projectDir": "",
  "description": "",
  "domain": "hardware|software|mixed|other",
  "subDomain": "",
  "sourceRoot": "",
  "dataSources": [
    {
      "name": "",
      "type": "",
      "location": "",
      "format": "",
      "estimatedSize": ""
    }
  ],
  "complexity": {
    "sourceTypeCount": 0,
    "estimatedNodeCount": 0,
    "subsystemCount": 0,
    "hasCrossReferences": false,
    "hasTraceability": false
  },
  "useCases": [],
  "constraints": {
    "existingTools": [],
    "teamSize": "",
    "timeline": "",
    "preferredBackend": ""
  }
}
```

## Agent Notes

- Don't ask all questions robotically — have a conversation
- Skip questions that are obviously not applicable (e.g., don't ask about
  RTL for a pure software project)
- If the human doesn't know an answer, provide reasonable defaults and note
  the uncertainty
- After completing the interview, save the profile and proceed to
  `03_recommend.md`
- Reference `profiles/project_profile_schema.json` for the full schema
