# install-1.2.1.ps1 - install experiment layer 1.2.1 into .claude\skills and run test_experiment on Windows.
# 1.2.1 = 1.2 with tests\test_experiment.py made Windows-compatible (explicit UTF-8 file I/O, .as_posix() path keys).
# Per file, the table $M below names two hashes:
#   NEW  the hash the file must have in 1.2.1 (the source in skills\ must be NEW; a target at NEW is left untouched)
#   OLD  the only other hash a target may have; a target at OLD is replaced by NEW
#   scripts\experiment.py, CHANGELOG.md, references\experiments.md: NEW = their 1.2 hash, OLD = their 1.1 hash (unchanged)
#   tests\test_experiment.py: NEW = the Windows-compatible 1.2.1 hash, OLD = the 1.2 hash installed on 2026-10-14
# Any other hash, in a source or a target, stops the run before any target is changed.
#
# Phases, in order (each is named in the log):
#   check-project    the project folder is derived from this file's location ($PSScriptRoot\..\..).
#   snapshot-before  SHA-256 of every file under batches\, skills\content-factory\ and .claude\skills\content-factory\,
#                    plus memory\dump.json and %USERPROFILE%\content-factory\runs\factory.db. The trees are walked folder by
#                    folder (Get-ChildItem -Force, never -Recurse). Every item's attributes are checked before entering
#                    or hashing it: a ReparsePoint (junction, symlink, cloud file), Offline, RecallOnOpen or
#                    RecallOnDataAccess item is neither entered nor read; it is recorded as a problem. The folders
#                    between the project folder and each tree root are checked the same way. Fail-closed: a file
#                    counts as MISSING only when its folder can be listed and does not contain it. Any listing, access,
#                    attribute or read problem makes the snapshot INCOMPLETE/UNVERIFIED; then nothing is copied and no
#                    test runs.
#   pre-copy-check   each of the four sources must be exactly NEW; each of the four targets exactly OLD or exactly NEW.
#                    Any other hash (including MISSING or UNREADABLE): NO target is changed and the run stops.
#   staging          the NEW sources of the targets still at OLD are copied to staging-<stamp>\ and SHA-256 verified.
#   replace          for each target still at OLD, immediately before copying: the staged source must still be NEW and the
#                    target must still be OLD, otherwise the run stops before that file. After each copy the target must be
#                    NEW. Targets already at NEW are left untouched, so a re-run completes a partial copy. On any stop the
#                    SHA-256 and state (OLD / NEW / UNKNOWN) of all four targets is logged. No rollback, ever.
#                    The copy is not atomic. A change made by another program between a check and the copy is not
#                    prevented; it can be overwritten and lost, and is detected only if it is still visible afterwards.
#   post-copy-check  all four targets must be NEW.
#   tests            python -m unittest content-factory.tests.test_experiment, in .claude\skills and then in skills. Both
#                    run even if the first fails. Each gets its own result: PASSED (exit 0 and "Ran N tests" with N > 0 and
#                    "OK"), FAILED (non-zero exit), UNKNOWN (no exit code, or exit 0 without that evidence), NOT RUN.
#   snapshot-after   runs whenever snapshot-before was taken, even after a stop or an unexpected error. Every difference
#                    in the CHECKED paths is listed. The only EXPECTED differences are the targets this run replaced
#                    (OLD before, NEW after); any other difference is UNEXPECTED. The four targets are reported before -> after.
# Path chains: before any read outside the walked trees (memory\dump.json, factory.db), before the snapshot (the project
# folder), and before any write (status file, the script folder, the log folder, staging, each target folder), every
# component from the drive root down to the path is checked with Get-Item -Force. A ReparsePoint, Offline, RecallOnOpen or
# RecallOnDataAccess component, a missing component, a non-local path or any access error stops that read or write: a read
# becomes UNREADABLE (snapshot INCOMPLETE/UNVERIFIED), a write is not done (start-up or precondition stop). Hard links carry
# no attribute and cannot be detected this way; their data may live elsewhere on the same volume.
#
# Status file (crash detection, independent of install.log). run-install-1.2.1.cmd creates a new folder
# install-run-<token>\ next to this script, writes status.txt = "LAUNCHED <token>", and passes -StatusFile and -LaunchToken.
# (Run directly, this script creates install-run-<guid>\status.txt itself, with CreateNew.) Transitions, through a temporary
# file and File.Replace:
#   LAUNCHED <token>  ->  STARTED <token> <time>  ->  FINISHED <token> <exit code> <time>
# Exact formats (Get-StatusPattern; the whole file must be exactly one of these, read as strict UTF-8 without BOM, every
# line ending in CR LF, nothing before, between or after the lines):
#   A  LAUNCHED <token>
#   B  STARTED <token> <time>
#   C  STARTED <token> <time>          + line  log: <install.log path of this run>
#   D  FINISHED <token> <code> <time>  [+ line log: <install.log path of this run>]
#   <token> = [0-9A-Za-z]{4,64} (the -LaunchToken of this run); <time> = Get-Date -Format o, local time,
#   yyyy-MM-ddTHH:mm:ss.fffffff+hh:mm (or -hh:mm / Z); <code> = 0 or 1-999 without leading zeros.
# Allowed previous -> new: A -> B (start), B -> C (log recorded), B or C -> D 256 without log (start-up stop; C only when
# this run's log path is known), C -> D with log (final). Any other previous content, or a new text not matching its own
# format, stops the transition and the file is left as it was.
# STARTED is written before anything else is read or written; FINISHED is the very last action before the final exit.
# The result is decided by the .cmd from this file: LAUNCHED = not started (nothing was done), STARTED or a missing file =
# INTERRUPTED/UNKNOWN, FINISHED with the same code as powershell.exe's exit code = that code, anything else = inconsistent.
# Remaining races: another program can change or delete the status file between this script's check and its replacement,
# or between the .cmd's writes and reads; the token makes a foreign or stale file detectable, not impossible. Nothing is
# proven after a power cut, an OS crash or a disk failure: the last write may not have reached the disk.
#
# Exit codes (the same table is in run-install-1.2.1.cmd).
#   This script's exit code, a bit mask; 0 = everything succeeded and was verified:
#     2 precondition stop (no target changed)          4 copy stopped, failed or incomplete
#     8 a test run FAILED or its result is UNKNOWN     16 a test run did NOT RUN
#    32 a snapshot is INCOMPLETE/UNVERIFIED            64 UNEXPECTED change in the checked paths
#   128 unexpected script error
#   256 start-up stop, nothing checked, copied or tested. With status FINISHED 256 when the start was recorded; when the
#       start could not be recorded the status file is left unchanged (LAUNCHED) and the .cmd reports 512.
#   Codes produced only by run-install-1.2.1.cmd (from the status file, never from powershell.exe's exit code alone):
#   512 NOT STARTED: powershell.exe not found, status file not prepared, or status still LAUNCHED after the run
#  1024 INTERRUPTED/UNKNOWN: status STARTED without FINISHED, or the status file disappeared after the launch
#  2048 INCONSISTENT/UNKNOWN: unknown content, wrong token, or FINISHED with a code different from the exit code
#   powershell.exe returns 1 when it cannot run the script or the script crashes; that alone is never trusted.
# Exits: two start-up stops (256: start not recorded / start-up checks failed) and the single final exit; none is inside a
# try block.
# It never runs gate, sync-gate, drive, produce or a rollback, and deletes no file.
# Writes only: up to the four .claude targets; checkpoints\experiment-layer-1.2.1\install-run-<token>\status.txt (+ .tmp);
#              checkpoints\experiment-layer-1.2.1\staging-<stamp>\; checkpoints\experiment-layer-1.2.1\install-<stamp>\.

param([string]$StatusFile = "", [string]$LaunchToken = "")

$ErrorActionPreference = "Stop"
$Utf8 = New-Object System.Text.UTF8Encoding($false)          # UTF-8 without BOM for every file this script writes
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"

# ---------------------------------------------------------------- definitions used before the main block (no side effects)
# Attributes that must never be entered or read: ReparsePoint 0x400 (junction, symlink, cloud placeholder), Offline 0x1000,
# RecallOnOpen 0x40000, RecallOnDataAccess 0x400000. The numeric values are used because .NET Framework's FileAttributes enum
# has no names for the last two.
$BadAttr = @(@(0x400, "ReparsePoint"), @(0x1000, "Offline"), @(0x40000, "RecallOnOpen"), @(0x400000, "RecallOnDataAccess"))
function Get-BadAttribute($item) {
  $v = [int]$item.Attributes
  return (@($BadAttr | Where-Object { $v -band $_[0] } | ForEach-Object { $_[1] }) -join "+") }

# Every component from the drive root to $path: "" when all exist (the last one may be missing with -LeafMayBeMissing), are
# accessible and have no bad attribute; otherwise the reason. Fail-closed: any error is a reason.
function Test-PathChain([string]$path, [switch]$LeafMayBeMissing) {
  try { $full = [System.IO.Path]::GetFullPath($path) } catch { return "invalid path '$path': $($_.Exception.Message)" }
  $driveRoot = [System.IO.Path]::GetPathRoot($full)
  if (-not $driveRoot -or $driveRoot.StartsWith("\\")) { return "not on a local drive: $full" }
  $parts = @($full.Substring($driveRoot.Length).Split([char[]]@([char]92), [System.StringSplitOptions]::RemoveEmptyEntries))
  $cur = $driveRoot
  for ($i = -1; $i -lt $parts.Count; $i++) {
    if ($i -ge 0) { $cur = [System.IO.Path]::Combine($cur, $parts[$i]) }
    $last = ($i -eq $parts.Count - 1)
    try { $it = Get-Item -LiteralPath $cur -Force -ErrorAction Stop }
    catch [System.Management.Automation.ItemNotFoundException] {
      if ($last -and $LeafMayBeMissing) { return "" }
      return "missing: $cur" }
    catch { return "not accessible: $cur ($($_.Exception.Message))" }
    $bad = Get-BadAttribute $it
    if ($bad) { return "$bad on $cur" }
    if (-not $last -and -not $it.PSIsContainer) { return "not a folder: $cur" } }
  return "" }

# The exact status formats (see the header), as anchored regexes (\A ... \z, never ^ or $, which accept a trailing LF).
# The token and the log path are inserted with [regex]::Escape, so they match only literally.
function Get-StatusPattern([string]$kind) {
  if ($LaunchToken -cnotmatch '\A[0-9A-Za-z]{4,64}\z') { throw "invalid launch token for the status file" }
  $tok = [regex]::Escape($LaunchToken)
  $t = '[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{7}(Z|[+-][0-9]{2}:[0-9]{2})'
  $codeRx = '(0|[1-9][0-9]{0,2})'
  if ($kind -ceq "launched") { return "\ALAUNCHED $tok\r\n\z" }
  if ($kind -ceq "started") { return "\ASTARTED $tok $t\r\n\z" }
  if ($kind -ceq "finished") { return "\AFINISHED $tok $codeRx $t\r\n\z" }
  if (-not $LogPath) { throw "status format '$kind' needs the log path, which is not known yet" }
  $logRx = "log: " + [regex]::Escape($LogPath) + "\r\n"
  if ($kind -ceq "started-log") { return "\ASTARTED $tok $t\r\n$logRx\z" }
  if ($kind -ceq "finished-log") { return "\AFINISHED $tok $codeRx $t\r\n$logRx\z" }
  throw "unknown status format '$kind'" }

# Replace the status file only when its whole current content matches one of the exact formats in $prev and the new text
# matches the exact format $next, through a temporary file that is read back and must hold exactly the new text. Files are
# read as bytes and decoded as strict UTF-8 (a BOM or an invalid byte makes the content not match).
function Set-Status([string[]]$prev, [string]$next, [string]$text) {
  if ($text -cnotmatch $next) { throw "new status text does not match its own format (not written)" }
  $strict = New-Object System.Text.UTF8Encoding($false, $true)
  $cur = $strict.GetString([System.IO.File]::ReadAllBytes($StatusFile))
  $ok = $false
  foreach ($rx in $prev) { if ($cur -cmatch $rx) { $ok = $true } }
  if (-not $ok) { throw "status file is not in an expected state (found: '$($cur.Trim())')" }
  $tmp = $StatusFile + ".tmp"
  [System.IO.File]::WriteAllText($tmp, $text, $Utf8)
  $written = $strict.GetString([System.IO.File]::ReadAllBytes($tmp))   # the temporary file is checked before it replaces
  if ($written -cne $text -or $written -cnotmatch $next) { throw "temporary status file does not hold the new status (not replaced)" }
  # no backup file. NullString, not $null: PowerShell passes $null to a [string] .NET parameter as "", and File.Replace
  # rejects "" as a backup path (ArgumentException), so every status change would fail.
  [System.IO.File]::Replace($tmp, $StatusFile, [System.Management.Automation.Language.NullString]::Value) }

# ---------------------------------------------------------------- 1) LAUNCHED -> STARTED, before anything else
$StartError = $null
try {
  if (-not $StatusFile) {                                       # run directly: make our own LAUNCHED status file
    $r = Test-PathChain $PSScriptRoot
    if ($r) { throw "script folder: $r" }
    $LaunchToken = [guid]::NewGuid().ToString("N")
    $runDir = Join-Path $PSScriptRoot "install-run-$LaunchToken"
    New-Item -ItemType Directory -Path $runDir | Out-Null
    $StatusFile = Join-Path $runDir "status.txt"
    $fs = [System.IO.File]::Open($StatusFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write)
    try { $bytes = $Utf8.GetBytes("LAUNCHED $LaunchToken`r`n"); $fs.Write($bytes, 0, $bytes.Length) } finally { $fs.Dispose() } }
  if ($LaunchToken -cnotmatch '^[0-9A-Za-z]{4,64}$') { throw "missing or invalid -LaunchToken" }
  $r = Test-PathChain $StatusFile
  if ($r) { throw "status file path: $r" }
  Set-Status @(Get-StatusPattern "launched") (Get-StatusPattern "started") ("STARTED $LaunchToken " + (Get-Date -Format o) + "`r`n")
} catch { $StartError = $_.Exception.Message }
if ($StartError) {                    # the start was not recorded: nothing else is done
  Write-Host "install-1.2.1: the start could not be recorded: $StartError"
  Write-Host "nothing was checked, copied or tested (exit 256); the .cmd decides from the status file (LAUNCHED = not started)"
  exit 256
}

# ---------------------------------------------------------------- 2) start-up checks, all inside a try
$BootError = $null
try {
  $Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
  if (-not $env:USERPROFILE) { throw "USERPROFILE is not set" }
  $RuntimeFiles = @((Join-Path $Root "memory\dump.json"), (Join-Path $env:USERPROFILE "content-factory\runs\factory.db"))
  $r = Test-PathChain $PSScriptRoot
  if ($r) { throw "script folder: $r" }
  $Out = Join-Path $PSScriptRoot "install-$Stamp"
  New-Item -ItemType Directory -Path $Out | Out-Null
  $r = Test-PathChain $Out
  if ($r) { throw "log folder: $r" }
  $LogPath = Join-Path $Out "install.log"
  Set-Status @(Get-StatusPattern "started") (Get-StatusPattern "started-log") ("STARTED $LaunchToken " + (Get-Date -Format o) + "`r`nlog: $LogPath`r`n")
} catch { $BootError = $_.Exception.Message }
if ($BootError) {                     # no usable log: report on screen and stop before reading or writing anything else
  Write-Host "install-1.2.1: start-up stop: $BootError"
  Write-Host "nothing was checked, copied or tested (exit 256)"
  try {                               # previous: STARTED without log, or with this run's log line when its path is known
    $prev = @(Get-StatusPattern "started")
    if ($LogPath) { $prev += Get-StatusPattern "started-log" }
    Set-Status $prev (Get-StatusPattern "finished") ("FINISHED $LaunchToken 256 " + (Get-Date -Format o) + "`r`n") }
  catch { Write-Host "status file not updated ($($_.Exception.Message)); it stays STARTED and the result is INTERRUPTED/UNKNOWN" }
  exit 256
}

$script:Phase = "check-project"
$script:Code = 0
$script:Halt = $false
$script:SnapOk = $false
$script:CopyStatus = "NOT STARTED"
$script:Replaced = @()
$script:SnapStatus = [ordered]@{ "before" = "NOT TAKEN"; "after" = "NOT TAKEN" }
$script:TestStatus = [ordered]@{ ".claude\skills" = "NOT RUN"; "skills" = "NOT RUN" }

function Log([string]$t) { Write-Host $t; [System.IO.File]::AppendAllText($LogPath, $t + "`r`n", $Utf8) }
function Set-Phase([string]$p) { $script:Phase = $p; Log "== phase: $p" }
function Add-Bit([int]$b) { $script:Code = $script:Code -bor $b }
function Stop-Run([int]$b, [string]$msg) { Log "STOP in phase '$($script:Phase)' (bit $b): $msg"; Add-Bit $b; $script:Halt = $true }
function Write-Utf8Text([string]$path, $lines) { [System.IO.File]::WriteAllLines($path, [string[]]@($lines), $Utf8) }

# Fail-closed file state: a SHA-256, "MISSING" (only when the parent folder can be listed, has no bad attribute, and does
# not contain the name), or "UNREADABLE: <reason>" for every other case. Test-Path is not used: it returns $false on access
# errors too.
function Hash([string]$p) {
  try { $it = Get-Item -LiteralPath $p -Force -ErrorAction Stop }
  catch [System.Management.Automation.ItemNotFoundException] {
    $parent = Split-Path -Parent $p
    try { $pi = Get-Item -LiteralPath $parent -Force -ErrorAction Stop } catch { return "UNREADABLE: absence not confirmed (folder: $($_.Exception.Message))" }
    $pb = Get-BadAttribute $pi
    if ($pb) { return "UNREADABLE: absence not confirmed (folder has $pb)" }
    try { $names = @(Get-ChildItem -LiteralPath $parent -Force -ErrorAction Stop | ForEach-Object { $_.Name }) }
    catch { return "UNREADABLE: absence not confirmed (folder not listable: $($_.Exception.Message))" }
    if ($names -contains (Split-Path -Leaf $p)) { return "UNREADABLE: listed by its folder but not accessible" }
    return "MISSING" }
  catch { return "UNREADABLE: $($_.Exception.Message)" }
  if ($it.PSIsContainer) { return "UNREADABLE: a folder, not a file" }
  $bad = Get-BadAttribute $it
  if ($bad) { return "UNREADABLE: $bad (not read)" }
  try { return (Get-FileHash -LiteralPath $p -Algorithm SHA256 -ErrorAction Stop).Hash }
  catch { return "UNREADABLE: $($_.Exception.Message)" } }

# A file outside the walked trees: its whole path chain is checked first.
function Get-ChainHash([string]$p) {
  $r = Test-PathChain $p -LeafMayBeMissing
  if ($r) { return "UNREADABLE: path chain: $r" }
  return Hash $p }

$SnapDirs = @("batches", "skills\content-factory", ".claude\skills\content-factory")
# returns @{ map = relative path -> state; problems = every listing, access or read failure }
# Controlled walk: one folder at a time with Get-ChildItem -Force (no -Recurse). An item with a bad attribute is recorded and
# neither entered nor hashed; a folder that cannot be read is recorded and not entered. Nothing outside $Root is entered.
function Snap {
  $h = @{}; $problems = @()
  $r = Test-PathChain $Root                                       # the project folder and every folder above it
  if ($r) { return @{ map = $h; problems = @("PROJECT PATH NOT SAFE: $r (no tree was walked)") } }
  foreach ($d in $SnapDirs) {
    # the folders from the project folder down to the tree root (e.g. .claude, .claude\skills, ...) and the root itself
    $parts = $d -split '\\'; $rel = ""; $rootOk = $true
    foreach ($part in $parts) {
      $rel = if ($rel) { "$rel\$part" } else { $part }
      try { $di = Get-Item -LiteralPath (Join-Path $Root $rel) -Force -ErrorAction Stop }
      catch { $problems += "FOLDER NOT ACCESSIBLE $rel : $($_.Exception.Message)"; $rootOk = $false; break }
      if (-not $di.PSIsContainer) { $problems += "NOT A FOLDER $rel"; $rootOk = $false; break }
      $bad = Get-BadAttribute $di
      if ($bad) { $problems += "NOT ENTERED $rel : $bad"; $rootOk = $false; break } }
    if (-not $rootOk) { continue }
    $stack = New-Object System.Collections.Stack
    $stack.Push((Join-Path $Root $d))
    while ($stack.Count -gt 0) {
      $dir = [string]$stack.Pop()
      try { $items = @(Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop) }
      catch { $problems += "LISTING-ERROR $($dir.Substring($Root.Length + 1)): $($_.Exception.Message)"; continue }
      foreach ($it in $items) {
        if (-not $it.FullName.StartsWith($Root + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
          $problems += "OUTSIDE PROJECT $($it.FullName)"; continue }
        $relp = $it.FullName.Substring($Root.Length + 1)
        $bad = Get-BadAttribute $it
        if ($bad) { $problems += "NOT ENTERED/READ $relp : $bad"; continue }
        if ($it.PSIsContainer) { $stack.Push($it.FullName) }
        else { $h[$relp] = Hash $it.FullName } } } }
  foreach ($p in $RuntimeFiles) { $h["RUNTIME " + $p] = Get-ChainHash $p }
  foreach ($k in $h.Keys) { if ($h[$k] -like "UNREADABLE*") { $problems += "UNREADABLE $k ($($h[$k]))" } }
  return @{ map = $h; problems = $problems } }
function Save-Snap($s, [string]$path) {
  $lines = @($s.map.Keys | Sort-Object | ForEach-Object { "{0}  {1}" -f $s.map[$_], $_ }) + @($s.problems | ForEach-Object { "PROBLEM  $_" })
  Write-Utf8Text $path $lines }
function Write-SnapshotStatus([string]$which, $s) {
  if (@($s.problems).Count -gt 0) {
    $script:SnapStatus[$which] = "INCOMPLETE/UNVERIFIED ($(@($s.problems).Count) problems)"
    foreach ($p in $s.problems) { Log "  PROBLEM $p" }
    Add-Bit 32 }
  else { $script:SnapStatus[$which] = "complete" }
  Log ("snapshot {0}: {1} entries, {2}" -f $which, $s.map.Count, $script:SnapStatus[$which]) }

$KeyFiles = @("batches\EXP-2026W42-beat3to9-c\experiment\slots\02.json",
              "batches\EXP-2026W42-beat3to9-c\runs\2026-10-13-why-do-you-see-a-ghost-color-aft\state.json")
# relative path under content-factory, SHA-256 NEW (1.2.1), SHA-256 OLD (replaceable)
$M = @(
 @("scripts\experiment.py","3cc21864d348e88e8b3e30cb3cb97f6b3906b2e8e661b797c68db0cec313ca05","d9a52eb7d152c26d71f17fbdb55757c6ef89484840c0a23b54222acbe3100132"),
 @("tests\test_experiment.py","393000b42e651d7d8620f2d6c58cf9b84b1f7ee5efe4132137e962910495d4ba","1e8e737caede03695f13813f213c069c96ef278bca892f588c0bcb60f5e91464"),
 @("CHANGELOG.md","199ecb49230fe92923d180cf5b27f6e93f62fe6779a29fdb1bbc79732cfaa06a","b59efb41055b5cb808179117b834572a777d8e5886c6d513e5ae7b1b5cebf5bf"),
 @("references\experiments.md","ff243bfd347099ef36a85df7e16a451aa18de46783f20fa6655582392146c019","98c8f2840f8820d40652053a4596e100ecbdfba47dc80da807f5a70bdc7dd7fa"))
function Src([string]$r) { Join-Path $Root "skills\content-factory\$r" }
function Dst([string]$r) { Join-Path $Root ".claude\skills\content-factory\$r" }
function Get-Version($x, [string]$h) { if ($h -eq $x[1].ToUpper()) { "NEW" } elseif ($h -eq $x[2].ToUpper()) { "OLD" } else { "UNKNOWN" } }
function Write-TargetHash {
  foreach ($x in $M) { $h = Hash (Dst $x[0]); Log ("  {0,-7} {1}  {2}" -f (Get-Version $x $h), $h, $x[0]) } }

try {
  # ------------------------------------------------------------------ check-project
  Set-Phase "check-project"
  Log "install-1.2.1 started $(Get-Date -Format o)"
  Log "project folder: $Root"
  Set-Location -LiteralPath $Root
  if ((Hash (Join-Path $Root "skills\content-factory\scripts\experiment.py")) -notmatch '^[0-9A-F]{64}$') {
    Stop-Run 2 "$Root is not the project folder (skills\content-factory\scripts\experiment.py not readable); nothing was changed" }

  # ------------------------------------------------------------------ snapshot-before
  if (-not $script:Halt) {
    Set-Phase "snapshot-before"
    $before = Snap
    Save-Snap $before (Join-Path $Out "snapshot-before.sha256")
    $script:SnapOk = $true
    Write-SnapshotStatus "before" $before
    foreach ($k in $KeyFiles) { Log ("  {0}  {1}" -f (Hash (Join-Path $Root $k)), $k) }
    if (@($before.problems).Count -gt 0) { Stop-Run 2 "snapshot-before is INCOMPLETE/UNVERIFIED; nothing will be copied or tested" } }

  # ------------------------------------------------------------------ pre-copy-check
  $toReplace = @()
  if (-not $script:Halt) {
    Set-Phase "pre-copy-check"
    $srcBad = @(); $unknown = @()
    foreach ($x in $M) {
      $s = Hash (Src $x[0]); $t = Hash (Dst $x[0]); $v = Get-Version $x $t
      if ($s -ne $x[1].ToUpper()) { $srcBad += $x[0] }
      if ($v -eq "OLD")     { $state = "OLD -> to be replaced"; $toReplace += ,$x }
      elseif ($v -eq "NEW") { $state = "NEW -> left untouched" }
      else                  { $state = "UNKNOWN"; $unknown += $x[0] }
      Log ("{0}`r`n  source {1}`r`n  target {2}  {3}" -f $x[0], $s, $t, $state) }
    if ($srcBad) { Stop-Run 2 "source is not NEW: $($srcBad -join ', '); no target was changed" }
    elseif ($unknown) { Stop-Run 2 "target is neither OLD nor NEW: $($unknown -join ', '); no target was changed" }
    elseif ($toReplace.Count -eq 0) { $script:CopyStatus = "NOT NEEDED (all four targets already NEW)"; Log $script:CopyStatus } }

  # ------------------------------------------------------------------ staging
  if (-not $script:Halt -and $toReplace.Count -gt 0) {
    Set-Phase "staging"
    $stage = Join-Path $PSScriptRoot "staging-$Stamp"
    foreach ($x in $toReplace) {
      $sp = Join-Path $stage $x[0]
      New-Item -ItemType Directory -Force -Path (Split-Path $sp) | Out-Null
      $r = Test-PathChain (Split-Path $sp)
      if ($r) { Stop-Run 2 "staging folder not safe: $r; no target was changed"; break }
      Copy-Item -LiteralPath (Src $x[0]) -Destination $sp
      $h = Hash $sp
      Log ("  {0}  {1}  staged {2}" -f ($h -eq $x[1].ToUpper()), $h, $x[0])
      if ($h -ne $x[1].ToUpper()) { Stop-Run 2 "staged copy of $($x[0]) is not NEW; no target was changed"; break } } }

  # ------------------------------------------------------------------ replace (re-checked file by file)
  if (-not $script:Halt -and $toReplace.Count -gt 0) {
    Set-Phase "replace"
    try {
      foreach ($x in $toReplace) {
        $sp = Join-Path $stage $x[0]; $dp = Dst $x[0]
        $hs = Hash $sp; $ht = Hash $dp                                  # re-check immediately before this copy
        if ($hs -ne $x[1].ToUpper()) { throw "staged source of $($x[0]) is no longer NEW ($hs)" }
        if ($ht -ne $x[2].ToUpper()) { throw "target $($x[0]) is no longer the expected OLD ($ht)" }
        $r = Test-PathChain $dp                                         # the target and every folder above it
        if ($r) { throw "target path not safe: $r" }
        $r = Test-PathChain $sp
        if ($r) { throw "staged source path not safe: $r" }
        Copy-Item -LiteralPath $sp -Destination $dp -Force
        $script:Replaced += $x[0]                                       # attempted: counted even if the check below fails
        $ha = Hash $dp
        if ($ha -ne $x[1].ToUpper()) { throw "target $($x[0]) is not NEW right after the copy ($ha)" }
        Log "  replaced and verified: $($x[0])" }
      $script:CopyStatus = "DONE ($($script:Replaced.Count) replaced, $(4 - $toReplace.Count) already NEW)"
    } catch {
      $script:CopyStatus = "STOPPED (copied: $($script:Replaced.Count) of $($toReplace.Count))"
      Log "COPY STOPPED: $($_.Exception.Message)"
      Log "copied before the stop: [$($script:Replaced -join ', ')]; NOT rolled back. All four targets now:"
      Write-TargetHash
      Log "a re-run leaves NEW targets untouched, replaces OLD targets, and stops without changes if any target is UNKNOWN"
      Stop-Run 4 "replacement stopped or incomplete" } }

  # ------------------------------------------------------------------ post-copy-check
  if (-not $script:Halt) {
    Set-Phase "post-copy-check"
    Write-TargetHash
    $bad = @($M | Where-Object { (Hash (Dst $_[0])) -ne $_[1].ToUpper() } | ForEach-Object { $_[0] })
    if ($bad) { $script:CopyStatus = "FAILED post-copy check"; Stop-Run 4 "targets not at NEW: $($bad -join ', ') (NOT rolled back)" } }

  # ------------------------------------------------------------------ tests
  if (-not $script:Halt) {
    Set-Phase "tests"
    foreach ($v in "CF_EXPERIMENT_CLAUDE","CF_DB","CF_RUNS_DIR","CF_OUTPUT_DIR","CF_BATCHES_DIR","CF_SKILLS_ROOT") {
      Remove-Item -Path "Env:$v" -ErrorAction SilentlyContinue }      # this process only; the tests make their own temp data
    $env:PYTHONDONTWRITEBYTECODE = "1"                                # no __pycache__ written into the project
    $env:PYTHONIOENCODING = "utf-8"                                   # test output is UTF-8
    $ErrorActionPreference = "Continue"                               # PS 5.1: native stderr must not abort the script
    try {
      $global:LASTEXITCODE = $null
      $pyv = (& cmd.exe /c "python --version 2>&1" | Out-String).Trim()
      Log "python: $pyv (exit $LASTEXITCODE)"
      foreach ($tree in @($script:TestStatus.Keys)) {
        $tlog = Join-Path $Out ("test-" + ($tree -replace '[\\.]', '_') + ".log")
        Log "-- test_experiment in $tree"
        $script:TestStatus[$tree] = "UNKNOWN (started; interrupted before an exit code was recorded)"
        $global:LASTEXITCODE = $null                                  # a stale code from an earlier command cannot be reused
        & cmd.exe /c "cd /d `"$(Join-Path $Root $tree)`" && python -m unittest content-factory.tests.test_experiment > `"$tlog`" 2>&1"
        $testRc = $LASTEXITCODE                                       # not $code: names are case-insensitive, $code IS $script:Code here
        $lines = @()
        if (Test-Path -LiteralPath $tlog) { $lines = @([System.IO.File]::ReadAllLines($tlog, $Utf8)) }
        else { Log "  no test output file was written" }
        foreach ($l in @($lines | Where-Object { $_ -match '^(Ran |OK|FAILED|ERROR:|FAIL:|Traceback)' })) { Log "  $l" }
        $ran = @($lines | Where-Object { $_ -match '^Ran (\d+) tests? in ' -and [int]$Matches[1] -gt 0 }).Count -gt 0
        $ok  = @($lines | Where-Object { $_ -match '^OK( |$)' }).Count -gt 0
        if ($null -eq $testRc)             { $script:TestStatus[$tree] = "UNKNOWN (no exit code received)" }
        elseif ($testRc -ne 0)             { $script:TestStatus[$tree] = "FAILED (exit $testRc)" }
        elseif ($ran -and $ok)             { $script:TestStatus[$tree] = "PASSED (exit 0, 'Ran N tests' and 'OK' found)" }
        else                               { $script:TestStatus[$tree] = "UNKNOWN (exit 0 but no 'Ran N tests' with N > 0 and 'OK' in the output)" }
        Log "  $($script:TestStatus[$tree]); full output: $tlog" }
    } finally { $ErrorActionPreference = "Stop" } }
} catch {
  $ErrorActionPreference = "Stop"
  Log "UNEXPECTED ERROR in phase '$($script:Phase)': $($_.Exception.Message) (script line $($_.InvocationInfo.ScriptLineNumber))"
  Add-Bit 128
}
foreach ($tree in @($script:TestStatus.Keys)) {
  $st = $script:TestStatus[$tree]
  if ($st -like "NOT RUN*") { Add-Bit 16 } elseif ($st -notlike "PASSED*") { Add-Bit 8 } }

# ------------------------------------------------------------------ snapshot-after (whenever snapshot-before was taken)
$lastWork = $script:Phase
if ($script:SnapOk) {
  try {
    Set-Phase "snapshot-after"
    $after = Snap
    Save-Snap $after (Join-Path $Out "snapshot-after.sha256")
    Write-SnapshotStatus "after" $after
    $b = $before.map; $a = $after.map
    $expected = @{}                                                     # key -> @(hash before, hash after) for replaced targets
    foreach ($x in $M) { if ($script:Replaced -contains $x[0]) { $expected[".claude\skills\content-factory\" + $x[0]] = @($x[2].ToUpper(), $x[1].ToUpper()) } }
    $diff = @()
    foreach ($k in @(@($a.Keys) + @($b.Keys) | Sort-Object -Unique)) {      # @() first: a KeyCollection has no "+"
      $hb = if ($b.ContainsKey($k)) { $b[$k] } else { "ABSENT" }
      $ha = if ($a.ContainsKey($k)) { $a[$k] } else { "ABSENT" }
      if ($hb -ne $ha) {
        $kind = if ($expected.ContainsKey($k) -and $hb -eq $expected[$k][0] -and $ha -eq $expected[$k][1]) { "EXPECTED  " } else { "UNEXPECTED" }
        $diff += "$kind $k  $hb -> $ha" } }
    Log "CHECKED (content SHA-256, before vs after):"
    foreach ($d in $SnapDirs) { Log ("  {0}\  every file, recursive, including hidden and system files ({1} files now)" -f (Join-Path $Root $d), @($a.Keys | Where-Object { $_ -like "$d\*" }).Count) }
    foreach ($p in $RuntimeFiles) { Log "  $p (with its whole path chain)" }
    Log "NOT CHECKED (this script makes no claim about them):"
    Log "  everything else under $Root (other skills\ and .claude\ folders, tools\, input\, data\, checkpoints\, memory\ except dump.json)"
    Log "  everything else under $env:USERPROFILE (including content-factory\runs\ except factory.db and .brain-academy\), %TEMP%, the registry and the environment"
    Log "the four targets, before -> after:"
    foreach ($x in $M) {
      $k = ".claude\skills\content-factory\" + $x[0]
      $hb = if ($b.ContainsKey($k)) { $b[$k] } else { "ABSENT" }; $ha = if ($a.ContainsKey($k)) { $a[$k] } else { "ABSENT" }
      Log ("  {0} -> {1}  {2}" -f (Get-Version $x $hb), (Get-Version $x $ha), $x[0]) }
    foreach ($l in $diff) { Log $l }
    $unexpected = @($diff | Where-Object { $_ -like "UNEXPECTED*" }).Count
    if ($unexpected -gt 0) { Add-Bit 64; Log "SNAPSHOT RESULT: $unexpected UNEXPECTED change(s) in the CHECKED paths (see above)" }
    if ($script:SnapStatus["before"] -ne "complete" -or $script:SnapStatus["after"] -ne "complete") {
      Log "SNAPSHOT RESULT: INCOMPLETE/UNVERIFIED - entries that could not be listed or read are not compared; no claim is made about them" }
    elseif ($unexpected -eq 0) { Log ("SNAPSHOT RESULT: no unexpected change in the CHECKED paths ({0} entries; {1} expected changes)" -f $a.Count, $diff.Count) }
    foreach ($k in $KeyFiles) { Log ("  {0}  {1}" -f (Hash (Join-Path $Root $k)), $k) }
  } catch {
    $script:SnapStatus["after"] = "INCOMPLETE/UNVERIFIED (error: $($_.Exception.Message))"
    Log "UNEXPECTED ERROR in phase 'snapshot-after': $($_.Exception.Message) - the comparison is INCOMPLETE/UNVERIFIED"
    Add-Bit 32; Add-Bit 128 }
} else {
  Log "== phase: snapshot-after skipped: snapshot-before was not taken, so no before/after comparison exists" }

# ------------------------------------------------------------------ final report and the single exit
Log "== final report"
Log "last work phase : $lastWork"
Log "copy            : $($script:CopyStatus)"
foreach ($k in $script:SnapStatus.Keys) { Log ("snapshot {0,-7}: {1}" -f $k, $script:SnapStatus[$k]) }
foreach ($k in $script:TestStatus.Keys) { Log ("tests {0,-15}: {1}" -f $k, $script:TestStatus[$k]) }
# (bit, meaning) pairs; a plain array, because an [ordered] dictionary indexed with an int returns by position, not by key
$names = @(@(2, "precondition stop"), @(4, "copy stopped/failed"), @(8, "test FAILED or UNKNOWN"), @(16, "test NOT RUN"),
           @(32, "snapshot INCOMPLETE/UNVERIFIED"), @(64, "UNEXPECTED change in checked paths"), @(128, "unexpected script error"))
$hit = @($names | Where-Object { $script:Code -band $_[0] } | ForEach-Object { "$($_[0]) $($_[1])" })
if ($script:Code -eq 0) { Log "OVERALL: OK - copy verified, both test runs PASSED, both snapshots complete, no unexpected change" }
else { Log ("OVERALL: NOT OK - exit code {0} = {1}" -f $script:Code, ($hit -join " + ")) }
Log "finished $(Get-Date -Format o)"
# the very last action: FINISHED with the exit code. If this write fails the status stays STARTED and the .cmd reports
# INTERRUPTED/UNKNOWN (1024): conservative, never a false success.
try { Set-Status @(Get-StatusPattern "started-log") (Get-StatusPattern "finished-log") ("FINISHED $LaunchToken $($script:Code) " + (Get-Date -Format o) + "`r`nlog: $LogPath`r`n") }
catch { Log "status file NOT updated to FINISHED: $($_.Exception.Message) - the .cmd will report INTERRUPTED/UNKNOWN" }
exit $script:Code
