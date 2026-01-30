[CmdletBinding()]
param(
  [Parameter(Position=0)]
  [string[]]$Tasks,

  [string]$Model,

  [switch]$ReviewWithClaude,

  # Required for tasks that call external services (e.g., LLM test)
  [switch]$AllowNetwork,

  # Non-interactive: fail if required inputs missing
  [switch]$NoPrompt,

  # Output control for automation. Default is human-friendly console output.
  [ValidateSet('human','object','json')]
  [string]$OutputFormat = 'human'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  # Assume this script lives in <repo>/scripts/
  return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function New-RunDir {
  param([string]$RepoRoot)
  $baseTs = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
  $ts = $baseTs
  $runDir = Join-Path $RepoRoot (Join-Path 'output\cleanup' $ts)

  # Avoid collisions if multiple runs start within the same millisecond.
  if (Test-Path $runDir) {
    $suffix = (Get-Random -Minimum 1000 -Maximum 9999)
    $ts = "$baseTs-$suffix"
    $runDir = Join-Path $RepoRoot (Join-Path 'output\cleanup' $ts)
  }

  $logDir = Join-Path $runDir 'logs'
  New-Item -ItemType Directory -Force $logDir | Out-Null
  return @{ RunDir=$runDir; LogDir=$logDir; Timestamp=$ts }
}

function Invoke-Logged {
  param(
    [Parameter(Mandatory=$true)][string]$LogDir,
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][scriptblock]$Command
  )

  $logPath = Join-Path $LogDir $Name
  $start = Get-Date
  "=== START $($start.ToString('o')) ===" | Out-File -Encoding utf8 $logPath

  $exitCode = 0
  try {
    & $Command 2>&1 | Tee-Object -FilePath $logPath -Append | Out-Null

    $lec = $null
    try {
      $lec = Get-Variable -Name LASTEXITCODE -Scope Global -ValueOnly -ErrorAction Stop
    } catch {
      $lec = $null
    }

    $exitCode = if ($lec -ne $null) { [int]$lec } else { 0 }
  } catch {
    $exitCode = 1
    "EXCEPTION: $($_.Exception.Message)" | Out-File -Encoding utf8 $logPath -Append
    "$($_.ScriptStackTrace)" | Out-File -Encoding utf8 $logPath -Append
  }

  $end = Get-Date
  "=== END $($end.ToString('o')) exit=$exitCode ===" | Out-File -Encoding utf8 $logPath -Append

  return [pscustomobject]@{
    name  = $Name
    exit  = $exitCode
    start = $start.ToString('o')
    end   = $end.ToString('o')
    log   = (Resolve-Path $logPath).Path
  }
}

function Write-JsonUtf8 {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)]$Object
  )
  $json = $Object | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Add-JsonlUtf8 {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)]$Object
  )
  $line = ($Object | ConvertTo-Json -Depth 20 -Compress)
  [System.IO.File]::AppendAllText($Path, $line + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Resolve-Tasks {
  param([string[]]$Tasks,[switch]$NoPrompt)

  $known = @('T01','T02','T03','T04','T05','T06','T07','T08')

  if (-not $Tasks -or $Tasks.Count -eq 0) {
    if ($NoPrompt) { throw "No tasks specified. Pass -Tasks T01,T03 (or run interactively)." }

    Write-Host "Select cleanup task(s):" -ForegroundColor Cyan
    $known | ForEach-Object { Write-Host "  $_" }
    $inputTasks = Read-Host "Enter one or more task IDs (comma-separated), e.g. T01,T03"
    $Tasks = $inputTasks -split ',' | ForEach-Object { $_.Trim().ToUpperInvariant() } | Where-Object { $_ }
  }

  $Tasks = $Tasks | ForEach-Object { $_.Trim().ToUpperInvariant() } | Where-Object { $_ }
  $invalid = $Tasks | Where-Object { $_ -notin $known }
  if ($invalid) {
    throw "Unknown task id(s): $($invalid -join ', '). Known: $($known -join ', ')"
  }

  return $Tasks
}

function Resolve-Model {
  param([string]$Model,[switch]$ReviewWithClaude,[switch]$NoPrompt)

  if (-not $ReviewWithClaude) { return $Model }

  if ($Model -ne $null) {
    $Model = $Model.Trim()
    if ($Model.Length -eq 0) { $Model = $null }
  }

  if (-not $Model) {
    if ($NoPrompt) { throw "-ReviewWithClaude requires -Model (opus|sonnet|haiku) in -NoPrompt mode." }

    Write-Host "Select Claude model for review:" -ForegroundColor Cyan
    Write-Host "  1) opus"
    Write-Host "  2) sonnet"
    Write-Host "  3) haiku"
    $choice = Read-Host "Choose 1-3"
    switch ($choice) {
      '1' { $Model = 'opus' }
      '2' { $Model = 'sonnet' }
      '3' { $Model = 'haiku' }
      default { throw "Invalid selection." }
    }
  }

  $Model = $Model.ToLowerInvariant()
  $allowed = @('opus','sonnet','haiku')
  if ($Model -notin $allowed) {
    throw "Invalid model '$Model'. Use one of: $($allowed -join ', ')"
  }

  return $Model
}

function Get-TaskSteps {
  param(
    [string]$TaskId,
    [switch]$AllowNetwork
  )

  switch ($TaskId) {
    'T01' {
      return @(
        @{ name='01_git_status.log'; command={ git status } },
        @{ name='02_python_version.log'; command={ python --version } },
        @{ name='03_pip_freeze.log'; command={ python -m pip freeze } },
        @{ name='04_pytest_collect.log'; command={ pytest -q --collect-only } }
      )
    }
    'T02' {
      return @(
        @{ name='01_remove_pycache.log'; command={ Get-ChildItem -Recurse -Force -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue } },
        @{ name='02_remove_pyc.log'; command={ Get-ChildItem -Recurse -Force -File -Include '*.pyc','*.pyo' | Remove-Item -Force -ErrorAction SilentlyContinue } },
        @{ name='03_remove_pytest_cache.log'; command={ Remove-Item -Recurse -Force '.pytest_cache' -ErrorAction SilentlyContinue } }
      )
    }
    'T03' {
      return @(
        @{ name='01_pytest.log'; command={ pytest -v } }
      )
    }
    'T04' {
      return @(
        @{ name='01_compileall.log'; command={ python -m compileall -q src/bam } },
        @{ name='02_import_bam.log'; command={ python -c "import bam; print('bam import: ok')" } },
        @{ name='03_bam_help.log'; command={ python -m bam --help } }
      )
    }
    'T05' {
      return @(
        @{ name='01_seed_list_playbooks.log'; command={ python -m bam seed show-playbook } },
        @{ name='02_seed_playbook_00.log'; command={ python -m bam seed show-playbook 0 } }
      )
    }
    'T06' {
      return @(
        @{ name='01_prereqs_json.log'; command={ python -m bam seed check-prereqs --backend json } }
      )
    }
    'T07' {
      if (-not $AllowNetwork) {
        return @(
          @{ name='01_llm_test_SKIPPED.log'; command={ Write-Output 'SKIPPED: requires -AllowNetwork to make a real API call (python -m bam setup llm --provider claude --test)'; $global:LASTEXITCODE = 2 } }
        )
      }
      return @(
        @{ name='01_setup_llm_test.log'; command={ python -m bam setup llm --provider claude --test } }
      )
    }
    'T08' {
      return @(
        @{ name='01_output_inventory.log'; command={
          Get-ChildItem -Recurse -Force 'output' -File |
            Select-Object FullName, Length, LastWriteTime |
            Sort-Object Length -Descending |
            Select-Object -First 200 |
            Format-Table -AutoSize
        } }
      )
    }
    default {
      throw "Unhandled task id: $TaskId"
    }
  }
}

function Write-Summary {
  param(
    [string]$SummaryPath,
    [string[]]$Tasks,
    [object[]]$StepResults,
    [string]$RunDir
  )

  $failed = $StepResults | Where-Object { $_.exit -ne 0 }
  $status = if ($failed) { 'FAILED' } else { 'OK' }

  $lines = @()
  $lines += "# BAM cleanup summary"
  $lines += ""
  $lines += "Status: **$status**"
  $lines += ""
  $lines += "Tasks: $($Tasks -join ', ')"
  $lines += "Run dir: $RunDir"
  $lines += ""
  $lines += "## Steps"
  foreach ($r in $StepResults) {
    $lines += "- $($r.name) exit=$($r.exit) log=$($r.log)"
  }
  if ($failed) {
    $lines += ""
    $lines += "## Failures"
    foreach ($r in $failed) {
      $lines += "- $($r.name) (exit=$($r.exit))"
    }
  }
  $lines += ""
  $lines += "Next: review logs; optionally run -ReviewWithClaude to generate ai_review.md"

  [System.IO.File]::WriteAllLines($SummaryPath, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Invoke-ClaudeReview {
  param(
    [string]$Model,
    [string]$RunDir,
    [string[]]$Tasks,
    [string]$OutPath
  )

  $prompt = @(
    "You are reviewing a BAM cleanup run.",
    "Repository: BAM (framework)",
    "Run directory: $RunDir",
    "Tasks executed: $($Tasks -join ', ')",
    "",
    "Read the files under the run directory (especially summary.md and logs/) and produce:",
    "1) A concise diagnosis of what happened",
    "2) Any actionable follow-up cleanup suggestions (safe)",
    "3) A short list of anomalies/warnings to investigate",
    "",
    "Keep it brief and structured."
  ) -join "`n"

  # Capture stdout to file; if claude fails, still write stderr to the same file.
  $output = & claude -p --model $Model $prompt 2>&1
  [System.IO.File]::WriteAllText($OutPath, ($output | Out-String), (New-Object System.Text.UTF8Encoding($false)))
}

# --- main ---
$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$Tasks = Resolve-Tasks -Tasks $Tasks -NoPrompt:$NoPrompt

if (-not $NoPrompt -and -not $ReviewWithClaude) {
  $ans = Read-Host "Generate an AI review with Claude after the run? (y/N)"
  if ($ans -match '^(y|yes)$') { $ReviewWithClaude = $true }
}

$Model = Resolve-Model -Model $Model -ReviewWithClaude:$ReviewWithClaude -NoPrompt:$NoPrompt

$run = New-RunDir -RepoRoot $repoRoot
$runDir = $run.RunDir
$logDir = $run.LogDir
$ts = $run.Timestamp

$runStart = Get-Date

$stepResults = New-Object System.Collections.Generic.List[object]

$taskToSteps = @{}
foreach ($t in $Tasks) {
  $steps = Get-TaskSteps -TaskId $t -AllowNetwork:$AllowNetwork
  $taskToSteps[$t] = @($steps)
}

# Execute
$stepIndex = 0
foreach ($t in $Tasks) {
  foreach ($s in $taskToSteps[$t]) {
    $stepIndex++
    $res = Invoke-Logged -LogDir $logDir -Name $s.name -Command $s.command
    $res | Add-Member -NotePropertyName 'task' -NotePropertyValue $t -Force
    $stepResults.Add($res) | Out-Null
  }
}

$runEnd = Get-Date
$failed = $stepResults | Where-Object { $_.exit -ne 0 }
$status = if ($failed) { 'failed' } else { 'ok' }

# Write artifacts
$runJsonPath = Join-Path $runDir 'run.json'
$summaryPath = Join-Path $runDir 'summary.md'
$aiReviewPath = Join-Path $runDir 'ai_review.md'

$runJson = [ordered]@{
  timestamp = $ts
  repo_root = $repoRoot
  tasks = $Tasks
  allow_network = [bool]$AllowNetwork
  start = $runStart.ToString('o')
  end = $runEnd.ToString('o')
  status = $status
  steps = $stepResults.ToArray()
}

Write-JsonUtf8 -Path $runJsonPath -Object $runJson
Write-Summary -SummaryPath $summaryPath -Tasks $Tasks -StepResults $stepResults.ToArray() -RunDir $runDir

$runsIndex = Join-Path $repoRoot 'output\cleanup\runs.jsonl'
$indexEntry = [ordered]@{
  timestamp = $ts
  tasks = $Tasks
  run_dir = $runDir
  status = $status
}
Add-JsonlUtf8 -Path $runsIndex -Object $indexEntry

if ($ReviewWithClaude) {
  Invoke-ClaudeReview -Model $Model -RunDir $runDir -Tasks $Tasks -OutPath $aiReviewPath
}

$result = [pscustomobject]@{
  timestamp = $ts
  repo_root = $repoRoot
  tasks = @($Tasks)
  allow_network = [bool]$AllowNetwork
  status = $status
  run_dir = $runDir
  run_json = $runJsonPath
  summary = $summaryPath
  ai_review = if ($ReviewWithClaude) { $aiReviewPath } else { $null }
}

switch ($OutputFormat) {
  'human' {
    Write-Host "Cleanup complete: $status" -ForegroundColor Cyan
    Write-Host "Run directory: $runDir" -ForegroundColor Cyan
    if ($ReviewWithClaude) {
      Write-Host "AI review: $aiReviewPath" -ForegroundColor Cyan
    }
  }
  'object' {
    Write-Output $result
  }
  'json' {
    Write-Output ($result | ConvertTo-Json -Depth 10 -Compress)
  }
}

if ($status -ne 'ok') {
  exit 1
}

exit 0
