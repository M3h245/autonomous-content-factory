# PROJECT STATE — Autonomous Content Factory · v3.0.1 (frozen; post-freeze patch of v3.0.0) · 2026-10-07

## Status
**Development is frozen at v3.0.0** (tag `v3.0.0`). One post-freeze patch was applied by owner decision: **v3.0.1**,
final-media metadata only (CHANGELOG). Phases 0–5 are complete. Only operation remains: making videos with the factory,
uploading by hand, and logging analytics. Any further change is a new decision by the owner.

## Where things are
- `checkpoints/v3.0.0/` (in git):
  - `content-factory-v3.0.0.zip` (the skills)
  - `phase5-package-leap.zip` (the publishable package)
  - `phase5-rejected-for-review.zip` (the two videos the independent judge rejected, for inspection, not for upload)
  - `phase5-records.zip` (run states, events, reports, judgments, authoring scripts)
  - `memory-dump.json`, PHASE_5_REPORT.md, this file, SHA256SUMS.txt
- `checkpoints/v2.0.0-alpha8/` is unchanged.
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
None — frozen. Operation: `factory.py init --topic …` → loop `next` → `package --zip` → upload by hand →
`cfdb.py publish` / content-analytics.
