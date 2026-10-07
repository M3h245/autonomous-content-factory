# PROJECT STATE — Autonomous Content Factory · v2.0.0-alpha8 · 2026-10-07

## Where things are
`/mnt/user-data/outputs/checkpoints/v2.0.0-alpha8/` holds (Phase 4):
- the skills zip
- `phase4-run.zip` (brain-freeze fresh run, RESEARCH → PACKAGE), `phase4-replay.zip`, `phase4-work.zip` (authoring
  scripts, inspection sheets, external judgment, knuckle packaging dev run), `phase4-package.zip` (both publishing
  packages: final video, thumbnail, cover, crops, metadata, PUBLISHING_PACKAGE.md)
- PHASE_4_REPORT.md, this file, SHA256SUMS.txt

Earlier checkpoints are unchanged: alpha7 (Phase 3.5), alpha6 (Phase 3), alpha4, alpha5, `content-factory-v2.0.0-alpha2.zip`, `-alpha3.zip`, `phase0/`.

Integrity: verify with `sha256sum -c SHA256SUMS.txt` against the zips. Loose .mp4/.jpg files may be rewritten by the
storage between sessions (same content, different container bytes); the zips hold the authoritative copies.

Resume: unzip the skills zip (e.g. into `cf/`), run `python cf/content-factory/scripts/setup_env.py --out caps.json`
(it installs the pinned runtime and Kokoro), then run the tests.

## Phases
| phase | status |
|---|---|
| 0 baseline | PASS (operator-assisted first run) |
| 1 independent reviewer | PASS WITH LIMITATIONS (heuristic judge) |
| 2 hook + script | PASS |
| 3 visual + audio | PASS — owner chose audio mix A by ear (2026-10-07) |
| 3.5 retention + CTA + metadata policy | PASS WITH LIMITATIONS (heuristic CTA judge; no conversion data yet) |
| 4 packaging | PASS WITH LIMITATIONS (heuristic package judge is generous; external packet-only judge supported; ≈3:2 YouTube crop advisory) |
| 5 validation → v3.0.0 | not started |

## Owner decisions
- 2026-10-07 — audio mix **A**: music 17 dB under the voice with a 12 dB speech-band carve (policy 16-18 dB). Chosen by
  ear over B (21/6) and C (24.7/0). It was already the default; no code change.

## How to verify (one CPU; run long tests one per command)
```
python -m unittest discover -s content-factory/tests -p "test_*.py"
CF_FIXTURE_DIR=fx python -m unittest content-factory/tests/test_bad_videos.py -k test_A   (then B, C)
python content-factory/tests/smoke_v2.py
```
The end-to-end class in test_phase4 needs a finished run with package candidates: unzip `runs_p4_dev/` from
`phase4-work.zip` and set `CF_PACKAGE_RUN` to its knuckle run folder (otherwise it is skipped with a message).
For the v1 regression: from `v1_regression/`, run render_video and subtitles on `video/storyboard.timed.json`. Both
must pass, using kenburns and karaoke.

## Decisions in force
- English, doodle style.
- AUDIO runs before VISUAL_PLAN.
- Independent review everywhere.
- Hook engine v2, with hook length measured from real TTS.
- Frame-0 rules.
- Checkpoint files stay under 250 MB (larger files vanished from the outputs storage); zips are authoritative.
- Phase 3 rules:
  - layout and subject variety
  - ≥2 events in the first 1.5 s
  - cadence ≤3 s
  - a loop ending
  - music 16-18 dB under the voice, with a speech-band carve
  - SFX ≤0.8/s
  - masking and clean-ending gates
- Deterministic stages are never retried blindly.
- Results are recorded only in stage order.
- The audio runtime is pinned.
- Phase 3.5: every new video records a CTA decision; a CTA never sits in the hook or before the payoff, never after the
  loop line, and the ending must stand without it; CTAs stay relevant and are not repeated (cta_history.json).
- Publishable media carry standard metadata only (PKG.MEDIA_METADATA_CLEAN); provenance stays in reports; platform AI
  labels are mandatory (PKG.DISCLOSURE).

- Phase 4: every new video ships the strongest of ≥3 genuinely different complete packages (title + opening promise +
  doodle thumbnail + copy). An unsupported or contradicted claim blocks a package; thumbnails must read at 168 px with
  text and subject in the central square; a packet-only external judge may lower scores, never raise them. The
  selected thumbnail is the cover; PUBLISHING_PACKAGE.md is the owner's upload sheet.

## Next
Phase 5 (validation), as the owner defines it — not started. Do not start it automatically.

## Transfer (2026-10-07)
The project is prepared for a Claude Code Cloud Session as a private GitHub repository. Read `CLOUD_HANDOFF.md` first.
Phases 0–4 are complete (alpha8 is authoritative). Phase 5 is the only remaining development phase; it runs at HIGH
effort and must not redo Phases 0–4. After v3.0.0, development is frozen. In the repository the skills live under
`skills/`, and the test fixtures under `fixtures/`.
