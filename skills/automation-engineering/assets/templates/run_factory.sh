#!/usr/bin/env bash
# Content Factory — unattended run on Linux/macOS (cron friendly). Never publishes.
# usage: run_factory.sh "TOPIC" [COUNT] [LANGUAGES]
set -euo pipefail
PROJECT="${CF_PROJECT:-$HOME/content-factory}"
cd "$PROJECT"
[ -f .env ] && { set -a; . ./.env; set +a; }
mkdir -p logs
claude -p "/content-factory Create ${2:-5} high-quality short videos on $1. Languages: ${3:-en}. Unattended run: never publish or upload anything; stop after FINAL PACKAGE and report escalations." \
  --permission-mode acceptEdits --permission-prompts none \
  --allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch" --output-format json > "logs/run-$(date +%Y%m%d-%H%M).json"
