# Content Factory — unattended run on Windows (Task Scheduler friendly). Never publishes.
param(
  [Parameter(Mandatory = $true)][string]$Topic,
  [int]$Count = 5,
  [string]$Languages = "en",
  [string]$Project = "D:\shorts-ai\factory"
)
$ErrorActionPreference = "Stop"
Set-Location $Project
if (Test-Path "$Project\.env") {  # load KEY=VALUE lines into this process only
  Get-Content "$Project\.env" | Where-Object { $_ -match '^\s*[^#].*=' } | ForEach-Object {
    $k, $v = $_ -split '=', 2; [Environment]::SetEnvironmentVariable($k.Trim(), $v.Trim(), 'Process') }
}
New-Item -ItemType Directory -Force -Path "$Project\logs", "$Project\memory" | Out-Null
$Runs = if ($env:CF_RUNS_DIR) { $env:CF_RUNS_DIR } else { "$Project\runs" }; $env:CF_RUNS_DIR = $Runs
New-Item -ItemType Directory -Force -Path $Runs | Out-Null
$Cfdb = "$Project\.claude\skills\content-database\scripts\cfdb.py"
# content memory: the factory refuses repeated topics/hooks only if it remembers them (Phase 5)
if (-not (Test-Path "$Runs\factory.db") -and (Test-Path "$Project\memory\dump.json")) {
  python $Cfdb import --db "$Runs\factory.db" --in "$Project\memory\dump.json" }
$stamp = Get-Date -Format "yyyyMMdd-HHmm"
$prompt = "/content-factory Create $Count high-quality short videos on $Topic. Languages: $Languages. " +
          "Unattended run: never publish or upload anything; stop after FINAL PACKAGE and report escalations."
claude -p $prompt --permission-mode acceptEdits --permission-prompts none `
  --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch" --output-format json |
  Out-File -Encoding utf8 "$Project\logs\run-$stamp.json"
$rc = $LASTEXITCODE
python $Cfdb export --db "$Runs\factory.db" --out "$Project\memory\dump.json"   # persist what was made
exit $rc
