[CmdletBinding()]
param(
  [Parameter(Position=0)]
  [string]$ControlFile = "./cleanup.control.json",

  # Override: force a specific Claude model for all claude-review agents (opus|sonnet|haiku)
  [string]$Model,

  # Override: allow network calls (needed for task T07 when enabled)
  [switch]$AllowNetwork,

  # If set, run tasks sequentially regardless of control file defaults
  [switch]$Sequential,

  # Notify on completion (toast if possible, else messagebox/beep).
  [switch]$Notify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Read-Control {
  param([string]$Path)
  if (-not (Test-Path $Path)) {
    throw "Control file not found: $Path"
  }
  $raw = Get-Content -Raw -Encoding UTF8 $Path
  return ($raw | ConvertFrom-Json)
}

function New-BatchDir {
  param([string]$RepoRoot)
  $ts = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
  $batchDir = Join-Path $RepoRoot (Join-Path 'output\\cleanup' ("batch-" + $ts))
  New-Item -ItemType Directory -Force $batchDir | Out-Null
  return @{ Timestamp=$ts; BatchDir=$batchDir }
}

function Write-JsonUtf8 {
  param([string]$Path, $Object)
  $json = $Object | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText($Path, $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Write-TextUtf8 {
  param([string]$Path, [string[]]$Lines)
  [System.IO.File]::WriteAllLines($Path, $Lines, (New-Object System.Text.UTF8Encoding($false)))
}

function Try-Notify {
  param(
    [Parameter(Mandatory=$true)][string]$Title,
    [Parameter(Mandatory=$true)][string]$Message
  )

  # Prefer BurntToast if installed.
  try {
    if (Get-Module -ListAvailable -Name BurntToast) {
      Import-Module BurntToast -ErrorAction Stop
      New-BurntToastNotification -Text $Title, $Message | Out-Null
      return
    }
  } catch { }

  # Fallback to MessageBox (may fail in some hosts).
  try {
    Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
    [System.Windows.Forms.MessageBox]::Show($Message, $Title) | Out-Null
    return
  } catch { }

  # Last resort: console beep.
  try {
    [console]::beep(1000, 300)
    Start-Sleep -Milliseconds 150
    [console]::beep(1300, 300)
  } catch { }
}

function Resolve-Model {
  param([string]$Model, [string]$Fallback)
  $m = $Model
  if ($null -eq $m -or $m.Trim().Length -eq 0) {
    $m = $Fallback
  }
  $m = $m.Trim().ToLowerInvariant()
  $allowed = @('opus','sonnet','haiku')
  if ($m -notin $allowed) {
    throw "Invalid model '$m'. Use one of: $($allowed -join ', ')"
  }
  return $m
}

function Clean-CleanupOutput {
  param(
    [Parameter(Mandatory=$true)][string]$RepoRoot,
    [Parameter(Mandatory=$true)][string]$Mode
  )

  $cleanupRoot = Join-Path $RepoRoot 'output\cleanup'
  if (-not (Test-Path $cleanupRoot)) {
    New-Item -ItemType Directory -Force $cleanupRoot | Out-Null
    return $null
  }

  $ts = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
  $archiveDir = Join-Path $cleanupRoot (Join-Path '_archive' $ts)
  if ($Mode -eq 'archive') {
    New-Item -ItemType Directory -Force $archiveDir | Out-Null
  }

  $items = Get-ChildItem -LiteralPath $cleanupRoot -Force
  foreach ($it in $items) {
    if ($it.Name -eq '.gitkeep') { continue }
    if ($it.Name -eq '_archive') { continue }
    if ($it.Name -eq 'runs.jsonl') {
      if ($Mode -eq 'archive') {
        Move-Item -LiteralPath $it.FullName -Destination (Join-Path $archiveDir $it.Name) -Force
      } elseif ($Mode -eq 'delete') {
        Remove-Item -LiteralPath $it.FullName -Force -ErrorAction SilentlyContinue
      }
      continue
    }

    if ($Mode -eq 'archive') {
      Move-Item -LiteralPath $it.FullName -Destination (Join-Path $archiveDir $it.Name) -Force
    } elseif ($Mode -eq 'delete') {
      Remove-Item -LiteralPath $it.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
  }

  # Recreate an empty runs.jsonl for the new run set.
  $runsIndex = Join-Path $cleanupRoot 'runs.jsonl'
  if (-not (Test-Path $runsIndex)) {
    [System.IO.File]::WriteAllText($runsIndex, '', (New-Object System.Text.UTF8Encoding($false)))
  }

  return $archiveDir
}

$repoRoot = Get-RepoRoot
Set-Location $repoRoot

$control = Read-Control -Path $ControlFile
$defaults = $control.defaults

$maxParallel = if ($Sequential) { 1 } else { [int]($defaults.maxParallel) }
if ($maxParallel -lt 1) { $maxParallel = 1 }

$allowNetworkEffective = [bool]$AllowNetwork -or [bool]($defaults.allowNetwork)

$cleanBefore = $false
if ($defaults -and ($defaults.PSObject.Properties.Name -contains 'cleanOutputBeforeRun')) {
  $cleanBefore = [bool]$defaults.cleanOutputBeforeRun
}
$cleanupMode = 'archive'
if ($defaults -and ($defaults.PSObject.Properties.Name -contains 'cleanupOutputMode')) {
  $cleanupMode = [string]$defaults.cleanupOutputMode
}
if (-not $cleanupMode -or $cleanupMode.Trim().Length -eq 0) { $cleanupMode = 'archive' }
$cleanupMode = $cleanupMode.Trim().ToLowerInvariant()
if ($cleanupMode -notin @('archive','delete')) { throw "Invalid defaults.cleanupOutputMode '$cleanupMode' (use 'archive' or 'delete')." }

$archiveDir = $null
if ($cleanBefore) {
  $archiveDir = Clean-CleanupOutput -RepoRoot $repoRoot -Mode $cleanupMode
}

$batch = New-BatchDir -RepoRoot $repoRoot
$batchDir = $batch.BatchDir
$ts = $batch.Timestamp

$enabledTasks = @($control.tasks | Where-Object { $_.enabled -eq $true })
if (-not $enabledTasks -or $enabledTasks.Count -eq 0) {
  throw "No enabled tasks in control file. Edit cleanup.control.json and set enabled=true."
}

$jobs = @()
$results = New-Object System.Collections.Generic.List[object]

function Start-TaskJob {
  param($task)

  $agentName = [string]$task.agent
  if (-not $control.agents.$agentName) {
    throw "Task $($task.id) references unknown agent '$agentName'."
  }

  $agent = $control.agents.$agentName
  $taskAllowNetwork = if ($task.PSObject.Properties.Name -contains 'allowNetwork') { [bool]$task.allowNetwork } else { $false }
  $network = $allowNetworkEffective -or $taskAllowNetwork

  $type = [string]$agent.type

  $reviewMode = 'none'  # none | claude | copilot
  $reviewWithClaude = $false
  $reviewModel = $null
  $copilotModel = $null

  if ($type -eq 'local') {
    $reviewMode = 'none'
    $reviewWithClaude = $false
  } elseif ($type -eq 'local+claude-review') {
    $reviewMode = 'claude'
    $reviewWithClaude = $true
    $fallback = $null
    if ($agent.PSObject.Properties.Name -contains 'model') {
      $fallback = [string]$agent.model
    }
    if (-not $fallback -or $fallback.Trim().Length -eq 0) {
      $fallback = [string]$defaults.model
    }
    $reviewModel = Resolve-Model -Model $Model -Fallback $fallback
  } elseif ($type -eq 'local+copilot-review') {
    $reviewMode = 'copilot'
    $reviewWithClaude = $false
    if ($agent.PSObject.Properties.Name -contains 'model') {
      $copilotModel = [string]$agent.model
    }
    if (-not $copilotModel -or $copilotModel.Trim().Length -eq 0) {
      $copilotModel = 'gpt-5.2'
    }
  } else {
    throw "Unsupported agent type '$type' for agent '$agentName'."
  }

  return Start-Job -Name ("cleanup_" + $task.id) -ScriptBlock {
    param($repoRoot,$taskId,$reviewMode,$reviewWithClaude,$reviewModel,$copilotModel,$network)

    Set-Location $repoRoot

    $splat = @{
      Tasks   = @($taskId)
      NoPrompt = $true
      OutputFormat = 'object'
    }
    if ($network) { $splat.AllowNetwork = $true }
    if ($reviewWithClaude) {
      $splat.ReviewWithClaude = $true
      $splat.Model = $reviewModel
    }

    # Run the single-task runner; it creates its own timestamped output folder.
    $runResult = & .\scripts\cleanup.ps1 @splat

    if ($reviewMode -eq 'copilot' -and $runResult -and $runResult.run_dir) {
      $promptPath = Join-Path $runResult.run_dir 'copilot_review_prompt.md'
      $reviewPath = Join-Path $runResult.run_dir 'copilot_review.md'
      $lines = @()
      $lines += "# Copilot (GPT-5.2) review request"
      $lines += ""
      $lines += "Model (requested): $copilotModel"
      $lines += "Run dir: $($runResult.run_dir)"
      $lines += "Tasks: $($runResult.tasks -join ', ')"
      $lines += "Status: $($runResult.status)"
      $lines += ""
      $lines += "Please review this cleanup run by reading:"
      $lines += "- summary.md"
      $lines += "- run.json"
      $lines += "- logs/*"
      $lines += ""
      $lines += "Output:" 
      $lines += "- 3-8 bullet summary of findings"
      $lines += "- Any failures/anomalies with likely root cause"
      $lines += "- Safe follow-ups (commands/edits)"
      [System.IO.File]::WriteAllLines($promptPath, $lines, (New-Object System.Text.UTF8Encoding($false)))

      if (-not $network) {
        $msg = @(
          "Copilot review skipped because network access is disabled for this task.",
          "Enable allowNetwork in cleanup.control.json (defaults.allowNetwork or task.allowNetwork).",
          "",
          "You can still open copilot_review_prompt.md in VS Code and run it manually."
        ) -join "`n"
        [System.IO.File]::WriteAllText($reviewPath, $msg, (New-Object System.Text.UTF8Encoding($false)))
      } else {
        # Try to generate the review automatically using Copilot CLI.
      $prompt = @(
        "You are GitHub Copilot Chat running in CLI mode.",
        "Model requested: $copilotModel",
        "Repository root: $repoRoot",
        "Run directory: $($runResult.run_dir)",
        "Tasks executed: $($runResult.tasks -join ', ')",
        "Status: $($runResult.status)",
        "",
        "Read and use these files from the run directory:",
        "- summary.md",
        "- run.json",
        "- logs/*",
        "",
        "Produce a concise report with:",
        "1) What happened (bullets)",
        "2) Issues/anomalies (if any) and likely root cause",
        "3) Safe follow-ups (commands/edits)",
        "",
        "Keep it brief and actionable."
      ) -join "`n"

      try {
        $copilotOut = & copilot -p $prompt --model $copilotModel --allow-all-tools --add-dir $runResult.run_dir --add-dir $repoRoot --no-color --silent 2>&1
        if ($LASTEXITCODE -eq 0 -and $copilotOut) {
          [System.IO.File]::WriteAllText($reviewPath, ($copilotOut | Out-String), (New-Object System.Text.UTF8Encoding($false)))
        } else {
          $fallback = @(
            "Copilot CLI invocation failed (exit=$LASTEXITCODE).",
            "Open copilot_review_prompt.md in VS Code and run it via Copilot Chat.",
            "",
            "Raw output:",
            ($copilotOut | Out-String)
          ) -join "`n"
          [System.IO.File]::WriteAllText($reviewPath, $fallback, (New-Object System.Text.UTF8Encoding($false)))
        }
      } catch {
        $fallback = @(
          "Copilot CLI invocation threw an exception.",
          "Open copilot_review_prompt.md in VS Code and run it via Copilot Chat.",
          "",
          "Exception:",
          $_.Exception.Message
        ) -join "`n"
        [System.IO.File]::WriteAllText($reviewPath, $fallback, (New-Object System.Text.UTF8Encoding($false)))
      }
      }
    }

    # Emit the run result so the parent process can capture run_dir/status.
    if ($runResult) { Write-Output $runResult }

    if ($LASTEXITCODE -ne $null -and $LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  } -ArgumentList $repoRoot, $task.id, $reviewMode, $reviewWithClaude, $reviewModel, $copilotModel, $network
}

function Get-RunnerResultFromJobOutput {
  param($JobOutput)
  foreach ($o in @($JobOutput)) {
    if ($o -is [psobject]) {
      $names = @($o.PSObject.Properties.Name)
      if ($names -contains 'run_dir' -and $names -contains 'status' -and $names -contains 'tasks') {
        return $o
      }
    }
  }
  return $null
}

function JobOutputToText {
  param($JobOutput)
  if (-not $JobOutput) { return '' }
  return ($JobOutput | Out-String)
}

foreach ($t in $enabledTasks) {
  while (@($jobs).Count -ge $maxParallel) {
    $done = Wait-Job -Job $jobs -Any -Timeout 2
    if ($done) {
      $jobOutput = Receive-Job -Job $done -Keep 2>&1
      $runner = Get-RunnerResultFromJobOutput -JobOutput $jobOutput
      $outText = JobOutputToText -JobOutput $jobOutput
      $state = $done.State
      $results.Add([pscustomobject]@{
        task = $done.Name
        state = $state
        cleanup_status = if ($runner) { [string]$runner.status } else { $null }
        run_dir = if ($runner) { [string]$runner.run_dir } else { $null }
        output = $outText
      }) | Out-Null
      Remove-Job -Job $done
      $jobs = @($jobs | Where-Object { $_.Id -ne $done.Id })
    }
  }

  $jobs = @($jobs + (Start-TaskJob -task $t))
}

# Wait remaining
foreach ($j in @($jobs)) {
  Wait-Job -Job $j | Out-Null
  $jobOutput = Receive-Job -Job $j -Keep 2>&1
  $runner = Get-RunnerResultFromJobOutput -JobOutput $jobOutput
  $outText = JobOutputToText -JobOutput $jobOutput
  $results.Add([pscustomobject]@{
    task = $j.Name
    state = $j.State
    cleanup_status = if ($runner) { [string]$runner.status } else { $null }
    run_dir = if ($runner) { [string]$runner.run_dir } else { $null }
    output = $outText
  }) | Out-Null
  Remove-Job -Job $j
}

$batchJson = [pscustomobject]@{
  timestamp = $ts
  control_file = (Resolve-Path $ControlFile).Path
  batch_dir = $batchDir
  max_parallel = $maxParallel
  allow_network = $allowNetworkEffective
  enabled_tasks = @($enabledTasks | ForEach-Object { $_.id })
  job_results = $results.ToArray()
}

Write-JsonUtf8 -Path (Join-Path $batchDir 'batch.json') -Object $batchJson

$lines = @()
$lines += "# BAM cleanup batch summary"
$lines += ""
$lines += "Timestamp: $ts"
$lines += "Control: $($batchJson.control_file)"
$lines += "Enabled tasks: $($batchJson.enabled_tasks -join ', ')"
$lines += "Max parallel: $maxParallel"
$lines += "Allow network: $allowNetworkEffective"
$lines += ""
$lines += "## Job results"
foreach ($r in $batchJson.job_results) {
  $statusText = if ($r.cleanup_status) { $r.cleanup_status } else { $r.state }
  if ($r.run_dir) {
    $lines += "- $($r.task): $statusText ($($r.run_dir))"
  } else {
    $lines += "- $($r.task): $statusText"
  }
}
$lines += ""
$lines += "Tip: open the per-task run_dir and check summary.md + logs/."

Write-TextUtf8 -Path (Join-Path $batchDir 'batch_summary.md') -Lines $lines

$marker = Join-Path $repoRoot 'output\cleanup\last_batch_complete.txt'
$markerLines = @(
  "timestamp=$ts",
  "batch_dir=$batchDir",
  "control=$($batchJson.control_file)",
  "allow_network=$allowNetworkEffective"
)
Write-TextUtf8 -Path $marker -Lines $markerLines

if ($Notify) {
  $failedAny = $false
  foreach ($r in $batchJson.job_results) {
    if ($r.cleanup_status -and $r.cleanup_status -ne 'ok') { $failedAny = $true }
  }
  $title = if ($failedAny) { 'BAM cleanup batch FAILED' } else { 'BAM cleanup batch complete' }
  $msg = "Batch dir: $batchDir"
  Try-Notify -Title $title -Message $msg
}

Write-Host "Batch complete." -ForegroundColor Cyan
Write-Host "Batch dir: $batchDir" -ForegroundColor Cyan
