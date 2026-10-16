# Content Factory — unattended run on Windows (Task Scheduler friendly). Never publishes.
param(
  [Parameter(Mandatory = $true)][string]$Topic,
  [string]$Count = "2",            # videos per run; default 2; a positive whole number, 1-50
  [string]$Languages = "en",
  [string]$Project = "D:\shorts-ai\factory"
)
$ErrorActionPreference = "Stop"
if ($Count -notmatch '^[0-9]{1,3}$' -or [int]$Count -lt 1 -or [int]$Count -gt 50) {
  [Console]::Error.WriteLine("run_factory: invalid -Count '$Count': must be a positive whole number from 1 to 50, e.g. -Count 4 (default 2)")
  exit 2 }
$Count = [int]$Count
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
