#!/usr/bin/env bash
# Content Factory — unattended run on Linux/macOS (cron friendly). Never publishes.
# usage: run_factory.sh "TOPIC" [COUNT] [LANGUAGES]
set -uo pipefail
PROJECT="${CF_PROJECT:-$HOME/content-factory}"
cd "$PROJECT"
[ -f .env ] && { set -a; . ./.env; set +a; }
mkdir -p logs memory
RUNS="${CF_RUNS_DIR:-$PROJECT/runs}"; export CF_RUNS_DIR="$RUNS"; mkdir -p "$RUNS"
CFDB="$PROJECT/.claude/skills/content-database/scripts/cfdb.py"
# content memory: the factory refuses repeated topics/hooks only if it remembers them (Phase 5)
[ -f "$RUNS/factory.db" ] || { [ -f memory/dump.json ] && python3 "$CFDB" import --db "$RUNS/factory.db" --in memory/dump.json; }
claude -p "/content-factory Create ${2:-5} high-quality short videos on $1. Languages: ${3:-en}. Unattended run: never publish or upload anything; stop after FINAL PACKAGE and report escalations." \
  --permission-mode acceptEdits --permission-prompts none \
  --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch" --output-format json > "logs/run-$(date +%Y%m%d-%H%M).json"
rc=$?
python3 "$CFDB" export --db "$RUNS/factory.db" --out memory/dump.json   # persist what was made
exit $rc
