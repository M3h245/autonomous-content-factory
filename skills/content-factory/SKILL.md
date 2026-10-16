---
name: content-factory
description: Entry point and orchestrator of the Autonomous Content Factory. Use whenever the user wants finished short-form videos — e.g. "create 5 high-quality short videos on TOPIC", "make shorts/reels/TikToks about X", "run the content factory", "batch of faceless videos", "resume/continue my factory run", "package the videos" — even if the word factory never appears. It sequences the factory skills through RESEARCH, IDEATION, SELECTION, HOOK, SCRIPT, VISUAL PLAN, AUDIO, VIDEO, SUBTITLES, QA, REGENERATION, FINAL PACKAGE and ANALYTICS FEEDBACK with JSON contracts, a quality gate per stage and automatic regeneration, and delivers MP4s with burned word-synchronized captions, metadata and provenance. Do not use for one isolated task (only hooks, only captions, only a script); the specialised skill handles those directly.
---

# Content Factory — orchestrator  ·  v3.0.0 (contract cf/1.1) · final, frozen

Thin by design: it owns the brief, the run state, the data contract and regeneration decisions. Domain know-how
lives in the 15 focused skills, which you load **only when `factory.py next` names them** (progressive disclosure).

## Activation
- Use: any request whose deliverable is one or more finished short videos, or continuing/inspecting a factory run.
- Do not use: a single sub-task (write hooks → hook-engineering; add captions → subtitle-production; analyse
  an export → content-analytics; schedule runs → automation-engineering).

## Responsibilities
Brief → verified capabilities → stage loop → regeneration/escalation → FINAL PACKAGE → hand-off to analytics.
Never publish or upload; packaging is the end of autonomy.

## Inputs → outputs
| In | Out |
|---|---|
| user request (topic, count, languages, length, voice, style) | `RUN/run.json` brief, `RUN/state.json`, `RUN/capabilities.json` |
| optional `factory.db` or `dump.json` from earlier runs | `RUN/package/<vid>/` final.mp4, cover.jpg, captions.srt/.vtt, metadata.json, provenance.json, CREDITS.txt, qa_report.json; v1 packaging adds thumbnail.jpg (= cover.jpg), thumbnail_crops.jpg, PUBLISHING_PACKAGE.md, publishing_package.json |
| optional analytics exports (later) | `RUN/<run>_package.zip`, `run_summary.md`, `checksums.sha256` |

## Workflow
Let `CF` = the folder that contains this skill and its siblings (claude.ai: `/mnt/skills/user`; Claude Code:
`~/.claude/skills` or `<project>/.claude/skills`). `F=$CF/content-factory/scripts/factory.py`.
1. **Bootstrap every session** (sandboxes reset): `python $CF/content-factory/scripts/setup_env.py --out /tmp/caps.json`.
   Read the printed capability list; plan only with what is available (see `references/capability-matrix.md`).
2. **Memory** (on by default): `init` uses `--db`, else `CF_DB`, else `<runs-dir>/factory.db`. If the user supplied
   `dump.json`, import it first (content-database); the repository ships `memory/dump.json`. `init` refuses a topic
   that repeats an earlier run (TOPIC_REPEATED; `--allow-similar-topic "reason"` overrides and is recorded) and a
   machine that cannot render doodles, TTS, video or captions (CAPABILITY_MISSING, with the fix doctor names).
3. **Init**: `python $F init --topic "…" [--count N] [--languages en] [--min-s 20 --max-s 45] [--voices en=af_heart]
   [--visual-style doodle|illustrated] [--caption-style auto|doodle|karaoke|word|clean]
   [--review-backend auto|heuristic|anthropic|subagent|human] [--db factory.db]`. N = the number of videos the user
   asked for; without a number it is 2 (the default; a positive whole number 1–50, anything else is refused).
   HOOK/SCRIPT (new runs): ≥5 multi-channel hook candidates with frame-0 SVGs → independent selection → opening
   brief; two script variants → independent selection (hook-engineering / short-form-script SKILL.md).
   PACKAGE (new runs, `package_engine: v1`): ≥3 genuinely different complete packages (title + opening promise +
   doodle thumbnail + copy) → deterministic gates + independent `review-package` → strongest complete package
   (`references/packaging.md`). A fresh agent that sees only the packets may add `package_judgment.json`
   (it can lower scores, never raise them).
   QA review is independent (video-quality-assurance/references/review-rubric.md): `auto` uses the Anthropic API when
   ANTHROPIC_API_KEY is set, else the deterministic heuristic judge (generous: in Phase 5 it passed two videos a
   packet-only judge failed — use an LLM judge for production); `subagent` hands a packet to a fresh Claude
   Code agent. Never fill a review for a video you authored. `factory.py media … --steps N` processes N media steps
   and returns (resumable on machines/sandboxes with command time limits).
   Defaults: English, 20–45 s, **doodle** visuals (animated hand-drawn scenes, `visual-storyboarding/references/
   doodle-scene-guide.md`), `auto` captions (doodle captions for doodle videos), seeded procedural music + SFX, all
   three platforms. `illustrated` = v1 stills with Ken Burns. `do_stage` for VISUAL_PLAN carries `brief_hint.visual_style`.
4. **Loop** on `python $F next --run RUN` and do exactly what the returned action says:
   - `do_stage` → read `skill_md`, write the files listed in `write` (apply `fix_params` on reruns), run `gate`, run `then`.
   - `run_media` → run `cmd` (AUDIO→VIDEO→SUBTITLES→QA, auto-regenerating); one bash call per video.
   - `review` → view both images, fill `review.json` from the template honestly, run `then`, then `then_record`.
   - `rerun` (printed by record/media) → load that skill, apply `fix_action`/`params`, redo the stage.
   - `escalate` → stop that video, keep the others moving, report its structured errors at the end.
   - `done` → `python $F package --run RUN --zip`.
5. **Deliver** (only what passed; a failed PACKAGE leaves no zip): copy `RUN/*_package.zip` and each `package/<vid>/final.mp4` to `/mnt/user-data/outputs/`, present them,
   and summarise titles, durations, QA notes, AI-label flags and anything that needs a human.
6. **Persist**: `package` already ingested the run; `cfdb.py export` and include `dump.json` with the delivery.

### Batch efficiency (N videos)
One shared RESEARCH dossier; IDEATION pool ≥ 2N; write hooks/script/storyboard for a video in one bash heredoc;
media ≈ 3–5 min per 30 s video on one vCPU (TTS ≈ 1.25× real time, render ≈ 3×) — one call per video. Measured in
Phase 5 (4 vCPU): 5–14 min of stage time per video including retries, 20–35 min elapsed per authoring round; a
strict judge needs 1–3 rounds. Videos of one run and runs in one folder are isolated (tested); one process per run.

### Idea batch (≈50 ideas → 2 videos by default, `--count N` for more, no LLM API)
`python $CF/content-factory/scripts/idea_engine.py run --ideas-file input/ideas.json --output-dir D:\shorts` validates a
hand-written or chat-pasted ideas file, filters it against this factory's memory (init's topic rule, SELECTION's
novelty rule), scores and ranks every candidate with explained reasons, and picks N different ones (`--count N`,
default 2). It then creates
one run per winner with `init` and drives each through the existing unattended `claude -p "/content-factory …"`
driver. Only packages that V3.0.1 itself recorded as passed are copied to the output folder. `select` stops after the
manifest; `produce --batch …` resumes. Format, prompt template, scoring and troubleshooting:
`references/idea-engine.md`. When asked to continue a run "prepared by the idea batch", loop on that existing run
(`next --run RUN`) and never `init` a new one.

## Quality gates
Every stage ends with a gate script that writes a `result.json` envelope; nothing proceeds unless it passed.
Table of gates, error codes and fix routes: `references/orchestration-spec.md`.

## Failure recovery
- Gate fail → `record` picks the earliest `fix_route`, marks downstream stages `stale`, retries (≤3 attempts per
  stage, ≤8 regenerations per video), else escalates. Crashes become `INTERNAL.EXCEPTION` envelopes and are retried.
- After fixing a root cause by hand: `python $F reset --run RUN --video v01 --stage SUBTITLES --note "why"` (that stage
  and every later one get a fresh retry budget).
- Mutating commands hold `RUN/.lock`; a second process is refused (LOCKED), a dead holder's lock is taken over;
  `python $F unlock --run RUN --note "why"` is the audited override. `record` refuses an envelope twice (STALE_RESULT).
- Never edit a `result.json` to force a pass; never skip QA review.

## Human checkpoints
Publishing; escalations; `PROV.MODEL_LICENSE` confirmations; YouTube "made for kids"; anything needing a credential.

## Scripts
`setup_env.py` (bootstrap) · `doctor.py` (capability probe) · `factory.py` (state machine) · `package_run.py`
(FINAL PACKAGE) · `idea_engine.py` (ideas file → N runs, default 2 → packages; above the state machine, changes nothing in it) · `cf_common.py` (contract library shared by every skill — keep all copies byte-identical;
`python cf_common.py export-schemas DIR`) · `tests/` (unit, regression, reviewer, bad-video and factory-integration tests; see PROJECT_STATE.md) · `tests/smoke_v2.py` (end-to-end media-chain test with a corrupted-file
negative test; no TTS/network, ≈1 min — run it after any engine change).

## References
- `references/orchestration-spec.md` — stages, data flow, envelope/error schema, regeneration algorithm (read first time)
- `references/capability-matrix.md` — what is verified available, where, and with which credential
- `references/external-services.md` — APIs: auth, inputs, outputs, role, limits
- `references/platform-policies.md` — formats, safe areas, AI-label and monetization rules (dated)
- `references/idea-engine.md` — the Idea Engine: ideas-file format, ChatGPT/Claude prompt template, memory filter,
  scoring, selection, hand-off, outputs, troubleshooting
- `schemas/*.schema.json` — JSON Schemas of every inter-skill artifact (`idea_candidates.schema.json`: the ideas file)

## Dependencies
Python 3.10+, ffmpeg with libass/HarfBuzz/FriBidi, the 15 sibling skills; v2 doodle engine: skia-python, svgelements
(installed by `setup_env.py`, prebuilt wheels on Windows/macOS/Linux). Optional: web search tools, connectors.
See `CHANGELOG.md` for what changed in v2.

## Interactions
Calls every factory skill through `factory.py next`; reuses brand-voice (house tone) and searchfit-seo
(keyword/title SEO) skills when installed; hands analytics exports to content-analytics.
