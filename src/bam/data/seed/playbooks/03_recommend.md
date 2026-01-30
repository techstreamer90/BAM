# Playbook 03: Generate Recommendations

## Purpose

Match the project profile to a setup configuration using decision rules.

## Decision Process

Use the rules in `profiles/recommendation_rules.json` and
`profiles/backend_decision_matrix.json` to determine:

1. **Template** — which sketch template to use
2. **Backend** — which storage backend
3. **Pipeline** — standard or incremental
4. **Parsers** — which parsers to configure
5. **Color overrides** — any non-default color configuration

## Decision Flowcharts

### Template Selection

| Domain | Sub-domain | Timeline | Template |
|--------|-----------|----------|----------|
| hardware | any | any | `hardware_product` |
| software | any | any | `software_product` |
| mixed | HW-primary | any | `hardware_product` |
| mixed | SW-primary | any | `software_product` |
| other | any | quick | `minimal` |
| other | any | normal | `software_product` |

### Backend Selection

| Estimated Nodes | Cross-refs | Traceability | Backend |
|----------------|------------|--------------|---------|
| < 1,000 | any | any | `json` |
| 1,000 - 10,000 | no | no | `json` |
| 1,000 - 10,000 | yes | any | `sqlite` |
| 10,000 - 100,000 | any | any | `sqlite` |
| > 100,000 | no | no | `sqlite` |
| > 100,000 | yes | yes | `neo4j` |

Override: If the human specified a preferred backend, use it (with a note
about whether it matches the recommendation).

### Pipeline Selection

| Scenario | Pipeline |
|----------|----------|
| First-time setup with known parsers | `standard` |
| Updating existing model | `incremental` |
| No parser exists for the data source | `agent-driven` |
| Mapping requires judgment / unfamiliar format | `agent-driven` |
| Default for new project | `standard` |

**Note:** The `agent-driven` pipeline requires LLM configuration
(`python -m bam setup llm --provider claude`). It replaces the validate/parse stages
with an LLM agent-review stage that produces a transform plan. The pipeline
may pause for human approval if the LLM proposes new node/edge types.

### Parser Selection

Map data source types to parsers:

| Source Type | Parser |
|-------------|--------|
| rtl, verilog, systemverilog | `rtl_parser` |
| documentation, markdown, docx | `docs_parser` |
| configuration, json, yaml, xml | `config_parser` |
| testbench, testplan, verification | `dv_parser` |

## Recommendation Output

```json
{
  "template": "hardware_product",
  "backend": "json",
  "pipeline": "standard",
  "parsers": ["rtl_parser", "docs_parser"],
  "colorOverrides": {},
  "rationale": {
    "template": "Hardware domain maps to hardware_product template",
    "backend": "< 10K nodes without cross-refs, JSON is sufficient",
    "pipeline": "New project, using standard pipeline",
    "parsers": "RTL and documentation sources detected"
  }
}
```

## Agent Notes

- Run `seed recommend --profile <path>` to get automated recommendations,
  or apply the rules manually
- Always explain the rationale for each choice
- If a recommendation conflicts with the human's preference, explain the
  trade-off and let them decide
- After generating recommendations, proceed to `04_explain_setup.md`
