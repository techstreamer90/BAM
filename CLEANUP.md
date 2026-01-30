
# BAM cleanup playbook

This file is a menu of safe, repeatable “cleanup” tasks for BAM itself (the
framework repo). It is written so you can tell an agent:

> “Run cleanup task T03”

…and it will execute the steps, capture outputs, and write a small summary that
another model can review later.

## Rules for the agent

1. Only do the task(s) requested by ID (e.g. `T03`).
2. Never delete user data or project models unless the task explicitly says so.
3. Always capture outputs using the **Output protocol** below.
4. If a command requires external credentials/network (e.g. LLM test), ask before running it.

## Output protocol (required)

## Quickstart (PowerShell runner)

If you prefer an automated runner (recommended on Windows), use:

```powershell
./scripts/cleanup.ps1
```

It will prompt you for task IDs, and (optionally) whether to generate an AI review; if you choose yes, it will ask you to select a model.

Common examples:

```powershell
# Run repo snapshot + tests
./scripts/cleanup.ps1 -Tasks T01,T03

# Run cache cleanup
./scripts/cleanup.ps1 -Tasks T02

# Run a cleanup task and then have Claude summarize the results (model selectable)
./scripts/cleanup.ps1 -Tasks T01,T04 -ReviewWithClaude -Model sonnet

# Allow network calls for the LLM connectivity test task
./scripts/cleanup.ps1 -Tasks T07 -AllowNetwork
```

This script always writes artifacts to `output/cleanup/...` and appends an index entry to `output/cleanup/runs.jsonl`.

## Batch mode (control file)

If you want to toggle tasks on/off and assign an agent per task, edit:

- `cleanup.control.json`

Then run:

```powershell
./scripts/cleanup_batch.ps1
```

This creates a batch folder under `output/cleanup/batch-YYYYMMDD-HHMMSS/` with `batch.json` and `batch_summary.md`, and each enabled task still produces its own standard run folder.

For every cleanup run, create a timestamped folder under:

- `output/cleanup/YYYYMMDD-HHMMSS/`

Write these files:

- `run.json` — machine-readable metadata (task id(s), commands, exit codes, start/end time)
- `summary.md` — short human summary + next actions
- `logs/` — one log file per command (`01_*.log`, `02_*.log`, …)

Also append one JSON line to:

- `output/cleanup/runs.jsonl`

Each line should minimally include: `timestamp`, `tasks`, `run_dir`, `status`.

### PowerShell starter (preferred on Windows)

```powershell
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path 'output/cleanup' $ts
$logDir = Join-Path $runDir 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null

function Invoke-Logged {
	param(
		[Parameter(Mandatory=$true)][string]$Name,
		[Parameter(Mandatory=$true)][scriptblock]$Command
	)
	$logPath = Join-Path $logDir $Name
	$start = Get-Date
	"=== START $($start.ToString('o')) ===" | Out-File -Encoding utf8 $logPath
	& $Command 2>&1 | Tee-Object -FilePath $logPath -Append
	$exit = $LASTEXITCODE
	$end = Get-Date
	"=== END $($end.ToString('o')) exit=$exit ===" | Out-File -Encoding utf8 $logPath -Append
	return @{ name=$Name; exit=$exit; start=$start.ToString('o'); end=$end.ToString('o'); log=$logPath }
}
```

### Bash starter (if running in WSL)

```bash
ts=$(date +%Y%m%d-%H%M%S)
run_dir="output/cleanup/$ts"
log_dir="$run_dir/logs"
mkdir -p "$log_dir"

invoke_logged () {
	name="$1"; shift
	log="$log_dir/$name"
	start=$(date -Iseconds)
	printf "=== START %s ===\n" "$start" > "$log"
	"$@" 2>&1 | tee -a "$log"
	exit_code=${PIPESTATUS[0]}
	end=$(date -Iseconds)
	printf "=== END %s exit=%s ===\n" "$end" "$exit_code" >> "$log"
	return $exit_code
}
```

## Tasks

### T01 — Repo health snapshot (read-only)

Goal: capture quick “what state is this repo in?” info.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_git_status.log' -Command { git status }
$results += Invoke-Logged -Name '02_python_version.log' -Command { python --version }
$results += Invoke-Logged -Name '03_pip_freeze.log' -Command { python -m pip freeze }
$results += Invoke-Logged -Name '04_pytest_collect.log' -Command { pytest -q --collect-only }
```

Notes:
- If `git` or `pytest` isn’t available, record that in `summary.md`.

### T02 — Clean Python caches + test artifacts (safe)

Goal: remove generated caches without touching source.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_remove_pycache.log' -Command {
	Get-ChildItem -Recurse -Force -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
$results += Invoke-Logged -Name '02_remove_pyc.log' -Command {
	Get-ChildItem -Recurse -Force -File -Include '*.pyc','*.pyo' | Remove-Item -Force -ErrorAction SilentlyContinue
}
$results += Invoke-Logged -Name '03_remove_pytest_cache.log' -Command {
	Remove-Item -Recurse -Force '.pytest_cache' -ErrorAction SilentlyContinue
}
```

Optional (more aggressive; ask before running):
- Remove `src/bam_model.egg-info/` (recreated by packaging tools)
- Remove coverage outputs (`.coverage`, `htmlcov/`) if present

### T03 — Run BAM unit tests (verification)

Goal: ensure the framework’s tests still pass.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_pytest.log' -Command { pytest -v }
```

If failures occur:
- Do not attempt large refactors.
- Summarize failures (first error per failing test) in `summary.md` and point to the log.

### T04 — Bytecode + import sanity check (fast)

Goal: catch syntax/import errors early.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_compileall.log' -Command { python -m compileall -q src/bam }
$results += Invoke-Logged -Name '02_import_bam.log' -Command { python -c "import bam; print('bam import: ok')" }
$results += Invoke-Logged -Name '03_bam_help.log' -Command { python -m bam --help }
```

### T05 — Seed playbooks sanity (read-only)

Goal: ensure seed assets are present and the CLI can render them.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_seed_readme.log' -Command { python -m bam seed show-playbook }
$results += Invoke-Logged -Name '02_seed_playbook_00.log' -Command { python -m bam seed show-playbook 0 }
```

### T06 — Prerequisite checks (backend smoke)

Goal: run the built-in prereq checks for at least the JSON backend.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_prereqs_json.log' -Command { python -m bam seed check-prereqs --backend json }
```

Optional (only if dependencies are installed):
- `python -m bam seed check-prereqs --backend neo4j`
- `python -m bam seed check-prereqs --backend arango`

### T07 — LLM provider connectivity check (network; ask first)

Goal: verify BAM’s LLM provider wiring without changing code.

Preconditions:
- Provider credentials already configured (e.g. `ANTHROPIC_API_KEY` for Claude)
- You explicitly approve making a real API call

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_setup_llm_test.log' -Command { python -m bam setup llm --provider claude --test }
```

If credentials are missing, record “SKIPPED” in `summary.md`.

### T08 — Cleanup of BAM-maintained output folders (conservative)

Goal: keep `output/` tidy while preserving historical runs.

Default behavior (safe):
- Do not delete anything automatically.
- Produce a report of large/old files and suggested deletions.

Commands (PowerShell):

```powershell
$results = @()
$results += Invoke-Logged -Name '01_output_inventory.log' -Command {
	Get-ChildItem -Recurse -Force 'output' -File |
		Select-Object FullName, Length, LastWriteTime |
		Sort-Object Length -Descending |
		Select-Object -First 200 |
		Format-Table -AutoSize
}
```

If the user asks to actually delete old runs, require explicit criteria (age threshold, keep-last-N, etc.).

## Run finalization (required)

After executing a task:

1. Write `run.json` containing: start/end timestamps, task IDs, command list, per-command exit codes, and log paths.
2. Write `summary.md` with:
	 - what ran
	 - what failed
	 - what was cleaned
	 - follow-ups (if any)
3. Append an entry to `output/cleanup/runs.jsonl`.

