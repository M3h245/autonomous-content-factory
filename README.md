# Autonomous Content Factory (private)

Short-form video production system built as Claude skills. Status, rules and operation: **[CLOUD_HANDOFF.md](CLOUD_HANDOFF.md)** · state: [PROJECT_STATE.md](PROJECT_STATE.md) · final report: [PHASE_5_REPORT.md](skills/content-factory/PHASE_5_REPORT.md).

**v3.0.0 — final release; development is frozen.** Post-freeze patch v3.0.1 (owner decision): the publishable media
carry only playback metadata and no embedded AI-label metadata; platform disclosure is done by hand at upload. Phases 0–5 are complete. The factory runs brief → publishing package through gated stages, with deterministic narration and renders, content memory, and an independent reviewer. Nothing is ever published automatically.

**Production system: V3.0.1 + Idea Engine 1.0.** The Idea Engine takes about 50 ideas from a file (written by hand
or pasted from ChatGPT/Claude; no LLM API, no API key). It filters them against the factory's memory, scores and
ranks them with stated reasons, and picks 2 different topics (`--count N` for another number). It then has V3.0.1
produce one isolated run per topic and copies each verified package to your output folder. The copy destination is
`CF_OUTPUT_DIR` — set for this machine to `D:\Youtube\autonomous-content-factory\outputs` (2026-10-19);
`--output-dir` overrides it. Delivery is flat and date-first: one folder per video named
`YYYY-MM-DD_NN_topic` directly in `outputs\`. After posting, the owner moves the folder into `outputs\Archive\`
unchanged. Versions policy: GitHub is the archive — every release zip lives in git history; locally
only the current release stays (`checkpoints/` + `versions\`), and superseded project files live outside the
project in `D:\Youtube\autonomous-content-factory\archive\project\`.

```
python3 .claude/skills/content-factory/scripts/idea_engine.py run --ideas-file input/ideas.json
```
Run it from a project folder set up with `skills/automation-engineering/scripts/install_skills.py --project <folder>`.

Format, prompt template and details: [references/idea-engine.md](skills/content-factory/references/idea-engine.md).
