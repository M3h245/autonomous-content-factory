@echo off
setlocal
rem run-install-1.2.1.cmd - starts install-1.2.1.ps1 (hash-guarded install of experiment layer 1.2.1 into .claude\skills, then
rem test_experiment) and decides the result from the script's status file, never from powershell.exe's exit code alone.
rem It never runs gate, sync-gate, drive, produce or a rollback.
rem
rem Status file: install-run-<token>\status.txt next to this file. This .cmd creates the folder (mkdir fails if it exists,
rem so it is new) and writes "LAUNCHED <token>". The script replaces it with "STARTED <token> <time>" before doing anything
rem else and with "FINISHED <token> <code> <time>" as its very last action. A status file proves nothing after a power cut,
rem an OS crash or a disk failure, and another program could still change or delete it between writes and reads.
rem
rem Exit codes (same table as in install-1.2.1.ps1):
rem   from the script (only accepted when the status says FINISHED with the same token and code), a bit mask;
rem   0 = everything succeeded and was verified:
rem     2 precondition stop (no target changed)      4 copy stopped, failed or incomplete
rem     8 a test run FAILED or UNKNOWN              16 a test run did NOT RUN
rem    32 a snapshot is INCOMPLETE/UNVERIFIED       64 UNEXPECTED change in the checked paths
rem   128 unexpected script error                  256 start-up stop, nothing checked, copied or tested
rem   only from this .cmd:
rem   512 NOT STARTED: powershell.exe not found, status file not prepared, or the status still says LAUNCHED after the
rem       run (the script never recorded a start, so it did nothing)
rem  1024 INTERRUPTED/UNKNOWN: the status says STARTED, or the status file disappeared after the launch
rem  2048 INCONSISTENT/UNKNOWN: unknown content, wrong token, or FINISHED with a code different from the exit code

rem powershell.exe by its full Windows path, so a file with the same name earlier in PATH is never run
set "PSEXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "FINAL="
set "STATUS="
set /a TRIES=0

:newrun
set /a TRIES+=1
if %TRIES% gtr 20 goto prepfail
set "TOKEN=%RANDOM%%RANDOM%%RANDOM%%RANDOM%"
set "RUNDIR=%~dp0install-run-%TOKEN%"
mkdir "%RUNDIR%" 2>nul || goto newrun
set "STATUS=%RUNDIR%\status.txt"
(echo LAUNCHED %TOKEN%)>"%STATUS%" 2>nul
if not exist "%STATUS%" goto prepfail
set "LINE="
set /p LINE=<"%STATUS%"
if not "%LINE%"=="LAUNCHED %TOKEN%" goto prepfail
if not defined SystemRoot goto nops
if not exist "%PSEXE%" goto nops

"%PSEXE%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-1.2.1.ps1" -StatusFile "%STATUS%" -LaunchToken "%TOKEN%"
set "RC=%ERRORLEVEL%"
echo.

if not exist "%STATUS%" goto vanished
set "LINE="
set /p LINE=<"%STATUS%"
if "%LINE%"=="LAUNCHED %TOKEN%" goto notstarted
set "S1="
set "S2="
set "S3="
for /f "tokens=1-3" %%a in ("%LINE%") do (
  set "S1=%%a"
  set "S2=%%b"
  set "S3=%%c"
)
if not "%S2%"=="%TOKEN%" goto inconsistent
if "%S1%"=="STARTED" goto interrupted
if not "%S1%"=="FINISHED" goto inconsistent
if not "%S3%"=="%RC%" goto inconsistent
set "FINAL=%RC%"
if "%RC%"=="0" (
  echo install-1.2.1: OVERALL OK, exit code 0
) else (
  echo install-1.2.1: NOT OK, exit code %RC% = sum of the bits listed at the top of this file and in the log
)
goto report

:prepfail
echo install-1.2.1: NOT STARTED - the status file could not be prepared. PowerShell was not run; nothing was done.
set "FINAL=512"
goto report

:nops
echo install-1.2.1: NOT STARTED - powershell.exe not found at "%PSEXE%". Nothing was done.
set "FINAL=512"
goto report

:notstarted
echo install-1.2.1: NOT STARTED - the status still says LAUNCHED. PowerShell did not start the script ^(execution policy
echo or parse error^) or the script could not record its start, so it did nothing. powershell.exe exit code: %RC%
set "FINAL=512"
goto report

:vanished
echo install-1.2.1: INTERRUPTED/UNKNOWN - the status file disappeared after the launch. The result is unknown: check the
echo four .claude targets and the log before doing anything else. powershell.exe exit code: %RC%
set "FINAL=1024"
goto report

:interrupted
echo install-1.2.1: INTERRUPTED/UNKNOWN - the script started but did not record FINISHED. The result is unknown: check the
echo four .claude targets and the log before doing anything else. powershell.exe exit code: %RC%
set "FINAL=1024"
goto report

:inconsistent
echo install-1.2.1: INCONSISTENT/UNKNOWN - unexpected status ^(first line: "%LINE%"^), powershell.exe exit code: %RC%.
echo The result is unknown: check the four .claude targets and the log before doing anything else.
set "FINAL=2048"

:report
if defined STATUS echo Status file: %STATUS%
if defined STATUS if exist "%STATUS%" type "%STATUS%"
echo The full report is at the end of install.log in the install-^<date-time^> folder next to this file.
pause
exit /b %FINAL%
