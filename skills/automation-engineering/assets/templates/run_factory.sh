#!/usr/bin/env bash
# Content Factory — unattended run on Linux/macOS (cron friendly). Never publishes.
# usage: run_factory.sh "TOPIC" [COUNT | --count N] [LANGUAGES]     COUNT: videos per run, default 2, a whole number 1-50
set -uo pipefail
export PYTHONUTF8=1   # CPython reads/writes text as UTF-8; harmless on Linux, required intent everywhere
TOPIC="${1:?usage: run_factory.sh \"TOPIC\" [COUNT | --count N] [LANGUAGES]}"; shift
if [ "${1:-}" = "--count" ]; then COUNT="${2:-}"; shift 2 2>/dev/null || shift $#; else COUNT="${1:-2}"; [ $# -gt 0 ] && shift; fi
LANGS="${1:-en}"
if ! [[ "$COUNT" =~ ^[0-9]{1,3}$ ]] || (( 10#$COUNT < 1 || 10#$COUNT > 50 )); then
  echo "run_factory: invalid count '$COUNT': must be a positive whole number from 1 to 50, e.g. --count 4 (default 2)" >&2
  exit 2
fi
COUNT=$((10#$COUNT))
PROJECT="${CF_PROJECT:-$HOME/content-factory}"
cd "$PROJECT"
[ -f .env ] && { set -a; . ./.env; set +a; }
mkdir -p logs memory
RUNS="${CF_RUNS_DIR:-$PROJECT/runs}"; export CF_RUNS_DIR="$RUNS"; mkdir -p "$RUNS"
CFDB="$PROJECT/.claude/skills/content-database/scripts/cfdb.py"
# content memory: the factory refuses repeated topics/hooks only if it remembers them (Phase 5)
[ -f "$RUNS/factory.db" ] || { [ -f memory/dump.json ] && python3 "$CFDB" import --db "$RUNS/factory.db" --in memory/dump.json; }
claude -p "/content-factory Create $COUNT high-quality short videos on $TOPIC. Languages: $LANGS. Unattended run: never publish or upload anything; stop after FINAL PACKAGE and report escalations." \
  --permission-mode acceptEdits --permission-prompts none \
  --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch" --output-format json > "logs/run-$(date +%Y%m%d-%H%M).json"
rc=$?
python3 "$CFDB" export --db "$RUNS/factory.db" --out memory/dump.json   # persist what was made
exit $rc
