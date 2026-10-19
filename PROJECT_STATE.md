# PROJECT STATE — Autonomous Content Factory · v3.1.0 (analytics and feedback loop) · 2026-10-19


## v3.1.0 (2026-10-18/19) — analytics and feedback loop
`docs/v3.1.0/` (ROADMAP, AUDIT, ARCHITECTURE, METRICS, VALIDATION, IMPLEMENTATION_REPORT, WINDOWS_SYNC_PROPOSAL),
`content-analytics/scripts/learning.py`, `learning_apply.py` and `content-database/scripts/reconcile.py`, with the
consumers in idea_engine, factory init and hook_engine. The synchronisation steps W0–W5 (`WINDOWS_SYNC_PROPOSAL.md`)
were **applied to the production database** on 2026-10-18/19: runs 36, publications 18, yt_observations 8 584,
`data/learning/latest.json` in place, `memory/dump.json` re-exported from the 36-run database.

## Status
**The production system is v3.1.0** (Idea Engine 1.0 above V3.0.1; the analytics/learning layer added in v3.1.0).
v3.0.0 is frozen (tag `v3.0.0`); v3.0.1 and Idea Engine 1.0 were post-freeze additions by owner decision (CHANGELOG):
- **v3.0.1**: final-media metadata only.
- **Idea Engine 1.0**: a batch layer above V3.0.1 (`content-factory/scripts/idea_engine.py`). It takes an ideas file,
  filters it against memory, scores and selects N topics (`--count N`, default 2; 5 before 2026-10-14), and hands
  them to N V3.0.1 runs, which are packaged and
  copied to the output folder. No LLM API is needed, and the production engine is unchanged.

**The production system is V3.0.1 + Idea Engine 1.0.** Phases 0–5 are complete. Only operation remains: making
videos (one topic with `factory.py`, or several from an ideas file with `idea_engine.py`; both make 2 by default,
`--count N` for another number), uploading by hand, and
logging analytics. Any further change is a new decision by the owner.

## Where things are
- **Outputs (2026-10-19):** `D:\Youtube\autonomous-content-factory\outputs\` via `CF_OUTPUT_DIR` (user env var;
  `--output-dir` overrides). Delivery is **flat and date-first**: one folder per video directly in `outputs\`,
  named `YYYY-MM-DD_NN_topic` (e.g. `2026-10-20_01_why-do-ants-not-get-hurt-when-they-fall`) — no batch-id
  wrapper. Owner workflow: after posting, the folder moves to `outputs\Archive\` unchanged (the name already sorts
  chronologically). All 18 published folders were renamed to that format on 2026-10-19 and the duplicate-render
  copy `20261014` (leidenfrost + pareidolia re-renders) was deleted per owner. Superseded project files:
  `D:\Youtube\autonomous-content-factory\archive\project\`.
- **Versions (owner decision 2026-10-19):** old releases live **only in git** — GitHub holds every release zip in
  history; locally only the current release stays (`checkpoints/v3.0.0/`) plus the current version's zips in
  `D:\Youtube\autonomous-content-factory\versions\`. `checkpoints/v2.0.0-alpha8/` was removed from the working
  tree (still in git history; restore from git if ever needed). The three ad-hoc `checkpoint_*.zip` state
  snapshots in `versions\` were deleted per owner on 2026-10-19 (all their run states exist in
  `cloud-runs-20261016` and the videos are published); the folder stays for current-version zips.
- `checkpoints/v3.0.0/` (in git):
  - `content-factory-v3.0.0.zip` (the skills)
  - `phase5-package-leap.zip` (the publishable package)
  - `phase5-rejected-for-review.zip` (the two videos the independent judge rejected, for inspection, not for upload)
  - `phase5-records.zip` (run states, events, reports, judgments, authoring scripts)
  - `memory-dump.json`, PHASE_5_REPORT.md, this file, SHA256SUMS.txt
- `checkpoints/v2.0.0-alpha8/` is git-history only since 2026-10-19 (removed from the working tree; restore from
  git if ever needed).
- **Batch run media stripped (2026-10-19):** `batches/20261007-*` and `batches/20261009-*` keep the state text
  (133+ JSON/SVG per run, manifests) and the package (zip containing final.mp4); scene art, rejected-hook frames,
  audio stems and interim renders were deleted (1.64 GB — batches 2.4 GB → 0.77 GB). The 10-14/10-16 run files are
  in `C:\Users\M3H245\content-factory\runs\cloud-runs-20261016\` — that is what `learning.py attributes
  --runs-root` reads for those videos.
- `seeds/` holds the authored inputs of all five recent runs; `memory/dump.json` holds the channel memory (8 runs).

Integrity: `cd checkpoints/v3.0.0 && sha256sum -c SHA256SUMS.txt`.

Resume on a new machine: `python skills/content-factory/scripts/setup_env.py --out caps.json`. It installs the pinned
runtime and Kokoro, and exits 3 with the fix if a core capability (for example libEGL for the doodle engine) is
missing. Then run the tests.

## Phases
| phase | status |
|---|---|
| 0 baseline | PASS (operator-assisted first run) |
| 1 independent reviewer | PASS WITH LIMITATIONS (heuristic judge) |
| 2 hook + script | PASS |
| 3 visual + audio | PASS — owner chose audio mix A by ear (2026-10-07) |
| 3.5 retention + CTA + metadata policy | PASS WITH LIMITATIONS (heuristic CTA judge; no conversion data yet) |
| 4 packaging | PASS WITH LIMITATIONS (heuristic package judge is generous; ≈3:2 YouTube crop advisory) |
| 5 productionization + validation → v3.0.0 | PASS WITH LIMITATIONS — 3 fresh runs; 1 of 3 accepted by the independent judge; see PHASE_5_REPORT.md |

## Owner decisions
- 2026-10-07 — audio mix **A**: music 17 dB under the voice with a 12 dB speech-band carve (policy 16-18 dB).

## How to verify (from `skills/`; run long tests one per command)
```
for t in test_cf_common_identity test_stage_order test_phase0_regressions test_tts_cache test_visual_audit \
         test_reviewer test_futile_retry test_phase2_script test_phase3 test_phase35 test_factory_review; do
  python3 -m unittest content-factory.tests.$t; done
python3 -m unittest content-factory.tests.test_phase2_hooks
python3 -m unittest content-factory.tests.test_phase4
python3 -m unittest content-factory.tests.test_phase5
python3 -m unittest content-factory.tests.test_final_media_metadata
python3 -m unittest content-factory.tests.test_idea_engine
python3 content-factory/tests/smoke_v2.py
python3 -m unittest content-factory/tests/test_bad_videos.py -k A   (then B, C, D)
```
For the v1 regression, see CLOUD_HANDOFF.md. To replay a run: `python3 work/phase4/replay.py seeds/<run> <runs-dir>`.

## Decisions in force
- English, doodle style. AUDIO runs before VISUAL_PLAN. Independent review everywhere.
- Hook engine v2, with hook length measured from real TTS. Frame-0 rules.
- Deterministic stages are never retried blindly. Results are recorded only in stage order. The audio runtime is pinned.
- Phase 3 rules:
  - layout and subject variety
  - ≥2 events in the first 1.5 s
  - cadence ≤3 s
  - a loop ending
  - music 16-18 dB under the voice, with a speech-band carve
  - SFX ≤0.8/s
  - masking and clean-ending gates
- Phase 3.5: every new video records a CTA decision; CTAs are never in the hook, before the payoff or after the loop
  line; the ending stands without the CTA; CTAs are relevant and not repeated across videos.
- Idea Engine 1.0:
  - the ideas file is the only input (no LLM API);
  - memory is the factory's own database and rules;
  - research before selection is an offline screen, never claimed as verified;
  - scoring is deterministic with stated reasons;
  - exactly N diverse winners (`--count N`, default 2), or a clear failure;
  - each winner becomes its own V3.0.1 run through `init`;
  - a package is delivered only when V3.0.1 recorded it as passed;
  - nothing is overwritten.
- Publishable media carry only the metadata playback needs, and **no embedded AI-label or disclosure metadata**
  (v3.0.1, PKG.MEDIA_METADATA_CLEAN). Platform AI labels are still mandatory in metadata.json (PKG.DISCLOSURE); the
  owner sets them by hand at upload.
- Phase 4: every video ships the strongest of ≥3 genuinely different complete packages. An unsupported claim blocks a
  package. An external packet-only judgment can only lower scores, and it must cover every candidate.
- Phase 5:
  - Deterministic narration and encodes (seeded Kokoro, x264 `-threads 4`): replays are byte-identical across CPU sets
    and caches.
  - Memory is on by default: a repeated topic is refused at `init`, a used hook is never selected, every packaged run is
    remembered.
  - One process per run (`RUN/.lock`). Every failure is an envelope; nothing ships after a failed PACKAGE.
  - **Production QA uses an LLM judge** (`ANTHROPIC_API_KEY`, or `--review-backend subagent`); the heuristic judge is
    a fallback.

## Next
Operation, either:
- `factory.py init --topic …` → loop `next` → `package --zip`; or
- `idea_engine.py run --ideas-file input/ideas.json` → read `batches/<id>/report.md` (packages are copied to
  `CF_OUTPUT_DIR` = `D:\Youtube\autonomous-content-factory\outputs`; `--output-dir <folder>` overrides).

Then upload by hand → `cfdb.py publish` / content-analytics. The feedback loop (pull → ingest → `learning.py
analyze` → next `idea_engine --learning`) runs by hand today; v3.2 automation is the next planned work.
