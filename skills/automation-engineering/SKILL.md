---
name: automation-engineering
description: Moves the content factory from chat to unattended operation — installs the skills for Claude Code, bootstraps machines (Python packages, Kokoro model, ffmpeg check, capability probe) and schedules headless runs with Windows Task Scheduler, cron or GitHub Actions using claude -p, with secrets kept in environment variables and nothing ever published automatically. Use for "run this every day", "automate the factory", "set it up on my PC, server or GitHub", "headless or CI runs", or deployment and environment troubleshooting for the factory.
---

# Automation Engineering

**Scope:** deployment and operations (outside the per-video stage loop)

## Activation
Scheduling, headless runs, new machines, CI, broken environments, credential setup for optional services.

## Responsibilities
Reliable, observable, credential-safe runs; the same skills in chat and headless; publishing stays human.

## Inputs → outputs
| In | Out |
|---|---|
| target machine (Windows/Linux/macOS/GitHub), topic schedule, optional keys | installed `.claude/skills/`, `.env` (local only), scheduled task / workflow, `logs/run-*.json` |

## Workflow
1. Install: `python scripts/install_skills.py --project D:\shorts-ai\factory` (or `--dest ~/.claude/skills`).
2. Bootstrap: `python .claude/skills/content-factory/scripts/setup_env.py --out capabilities.json` (installs Python
   deps, downloads Kokoro, probes ffmpeg/fonts/network/credentials). Fix what doctor reports before scheduling.
3. Secrets: copy `assets/templates/env.example` to `.env`; never commit it, never paste keys into chat.
4. Run headless: `assets/templates/run_factory.ps1` (Windows) or `run_factory.sh` — invoke the skill explicitly with
   `/content-factory …` in `claude -p` (`--bare` would skip skill discovery), `--permission-mode acceptEdits`,
   `--permission-prompts none`, `--allowedTools "Bash,Read,Write,Edit,WebSearch,WebFetch"`, `--output-format json`.
5. Schedule: Windows `schtasks /Create /SC DAILY /ST 09:00 /TN ContentFactory /TR "powershell -NoProfile
   -ExecutionPolicy Bypass -File D:\shorts-ai\factory\run_factory.ps1 -Topic \"…\" -Count 2"`; Linux cron; or
   `assets/templates/content-factory.yml` for GitHub Actions (package zip uploaded as an artifact).
6. Monitor: each run log has `total_cost_usd`, escalations and the package path; alert on non-zero exit codes.
   The templates import `memory/dump.json` when `factory.db` is missing and export it after every run (v3.0.0), so a
   scheduled machine never repeats a topic; they keep claude's exit code. A run holds `RUN/.lock`; a second process is
   refused (LOCKED), a dead one's lock is taken over. Set `ANTHROPIC_API_KEY` so the QA judge is an LLM, not the
   generous heuristic.

## Quality gate
A deployment is done when: doctor shows `tts.kokoro`, `video.render`, `subtitles.burn` available; one scheduled
test run produces a package with QA passed; logs rotate; no secret appears in any committed file or log.

## Failure recovery
See `references/deployment.md` (ffmpeg missing, model download blocked, Forge API off, permission denials in headless
mode, quota/rate limits with exponential backoff, stuck runs).

## Scripts · Assets · References
`scripts/install_skills.py` · `assets/templates/{run_factory.ps1, run_factory.sh, content-factory.yml, env.example}` ·
`references/deployment.md`

## Dependencies
Claude Code CLI (`npm install -g @anthropic-ai/claude-code`), Node 18+, Python 3.10+, ffmpeg; Anthropic API key or
Claude login on the machine.

## Interactions
Wraps content-factory; reuses its doctor/setup; optional services documented in content-factory references.
