# CLOUD HANDOFF — Autonomous Content Factory

Read this file first, then `PROJECT_STATE.md`. Written 2026-10-07 for the transfer to a Claude Code Cloud Session.

## Status
| item | value |
|---|---|
| Phases complete | **0, 1, 2, 3, 3.5, 4** |
| Authoritative checkpoint | **`v2.0.0-alpha8`** (`checkpoints/v2.0.0-alpha8/`, `skills/content-factory/VERSION`) |
| Phase 4 (packaging) | **PASS WITH LIMITATIONS** — see "Known limitations" |
| Remaining development | **Phase 5 (validation) is the ONLY remaining development phase** |
| Phase 5 effort | **HIGH** |
| After Phase 5 | the release is **v3.0.0** and **development is FROZEN** — no further features, phases or optimisation |

Rules for the Cloud Session:
1. **Do NOT redo Phases 0–4.** Their results are final. Do not reopen their limitations unless Phase 5 finds a
   *blocking* regression, and then fix only that regression.
2. **Phase 5 scope comes from the owner (Abolfazl).** Do not invent it, and do not start Phase 5 before the owner sends
   the Phase 5 brief.
3. Never publish anything automatically; the owner uploads by hand.
4. Never expose or commit secrets. API keys are read from environment variables only (`ANTHROPIC_API_KEY` is optional;
   without it the reviewer uses its deterministic heuristic judge).
5. Never weaken gates. Never remove platform AI-disclosure behaviour, and never use the media-metadata policy to evade
   platform labelling. Media cleaning is privacy hygiene only; PKG.DISCLOSURE still blocks without labels.
6. Never modify completed checkpoints (`checkpoints/v2.0.0-alpha8/` here; alpha2–alpha7 in the original outputs storage).
7. Keep every artifact file under 250 MB, and under 100 MB in git (GitHub's limit).

## Exact next action for the Cloud Session
1. `cat CLOUD_HANDOFF.md PROJECT_STATE.md skills/content-factory/PHASE_4_REPORT.md`
2. Rebuild the runtime, which installs the pinned onnxruntime 1.29.0 / kokoro-onnx 0.6.1 and downloads the Kokoro
   model (~354 MB) from GitHub releases into `~/.cache/content-factory`:
   `python3 skills/content-factory/scripts/setup_env.py --out /tmp/caps.json`
3. Verify the baseline (commands below): fast tests → test_phase4 → smoke. Optionally run bad videos A–D, the v1
   regression and the seed replay.
4. Report the baseline result to the owner and **wait for the Phase 5 brief**. Run Phase 5 at HIGH effort, finish
   at v3.0.0, then stop development.

## Repository layout
```
CLOUD_HANDOFF.md            this file
PROJECT_STATE.md            project state (current, alpha8)
skills/                     the 15 factory skills (side by side; skills_root() = this folder)
  content-factory/          orchestrator: scripts/factory.py, package_run.py, package_engine.py, setup_env.py, doctor.py,
                            cf_common.py (contract library — 15 byte-identical copies, enforced by a test),
                            references/ (orchestration-spec, packaging, platform policies…), tests/, VERSION,
                            CHANGELOG.md, PHASE_1..4 reports, PROJECT_STATE.md
  content-research/ content-strategy/ hook-engineering/ short-form-script/ multilingual-content/ voice-production/
  visual-storyboarding/ video-production/ subtitle-production/ video-quality-assurance/ asset-provenance/
  content-database/ content-analytics/ trend-intelligence/ automation-engineering/
checkpoints/v2.0.0-alpha8/  authoritative checkpoint files that fit in git (see "Checkpoints")
fixtures/phase4_package_run/<knuckle run>   trimmed finished run for test_phase4 end-to-end (16 MB)
fixtures/v1_regression/     v1 Ken Burns + karaoke regression inputs (storyboard paths templated: {FIXTURE})
seeds/<run>/                authored inputs of both Phase 4 runs (dossier, ideas, hooks+SVG, script variants,
                            storyboard+SVG, package candidates+SVG, external judgment) for deterministic replay
work/phase4/                operator scripts used in Phase 4 (scene/hook/package authoring helpers, replay driver)
```

## Architecture (short)
- **State machine** `skills/content-factory/scripts/factory.py`, with commands `init`, `next`, `record`, `media`,
  `reset`, `status`, `report`, `package`.
  - Stage order: RESEARCH → IDEATION → SELECTION → per video HOOK → SCRIPT → (LOCALIZE) → AUDIO → VISUAL_PLAN → VIDEO →
    SUBTITLES → QA → PACKAGE.
  - Every stage writes a StageResult envelope (`cf_common.py`). `record` refuses out-of-order results.
  - Failures route to a fix with a retry budget; an exhausted budget escalates, and the operator `reset`s with a note.
- **Engines**:
  - **Hook engine v2**: ≥5 candidates, frame-0 doodle render, real TTS length, independent review.
  - **Script selection**: two variants, calibrated duration estimate.
  - **CTA engine** (Phase 3.5).
  - **Doodle engine**: SVG scenes with word cues; composition, geometry and frame audits.
  - **Audio**: Kokoro TTS with a content-addressed cache; music at 17 dB under the voice (policy 16–18) with a 12 dB
    speech-band carve; SFX ≤0.8/s; masking and clean-ending gates.
  - **Subtitles**: word-synchronised, burned in.
  - **Media metadata policy** (`asset-provenance/scripts/media_clean.py`).
  - **Packaging engine** (Phase 4, `content-factory/scripts/package_engine.py`, `references/packaging.md`).
- **Independent review** (`video-quality-assurance/scripts/reviewer.py`) has modes `review` (video), `review-hooks`,
  `review-script` and `review-package`.
  - It runs as a separate process on hash-pinned packets built by `review_packet.py`; authoring files are excluded by
    construction.
  - Judges: `heuristic` by default, `anthropic` if `ANTHROPIC_API_KEY` is set, `subagent`/`human` via judgment files.
  - For packages, an external packet-only judgment can lower scores, never raise them.
  - Policy and thresholds live in `video-quality-assurance/references/review-policy.json`.
- **New runs**: `factory.py init` writes brief flags `hook_engine: v2`, `cta_engine: v1` and `package_engine: v1`.
  Older runs replay unchanged.

## Commands
```
# new run (operator loop: next → write files → gate → record; media stages via `media`)
python3 skills/content-factory/scripts/factory.py init --topic "…" --count 1 --languages en \
    --platforms youtube_shorts,tiktok,instagram_reels --min-s 20 --max-s 45 --runs-dir runs
python3 skills/content-factory/scripts/factory.py next  --run runs/<run>
python3 skills/content-factory/scripts/factory.py media --run runs/<run> --video v01 [--steps N]
python3 skills/content-factory/scripts/factory.py record --run runs/<run> --result <result.json>
python3 skills/content-factory/scripts/factory.py reset --run runs/<run> --video v01 --stage <STAGE> --note "why"

# deterministic replay of a Phase 4 run from its authored inputs
python3 work/phase4/replay.py seeds/2026-10-07-why-ice-cream-gives-you-brain-fr runs_replay
```

## Tests (from `skills/`; one CPU — run long ones one per command, Bash timeouts ≤10 min)
```
cd skills
# fast suite (~6 min): identity, stage order, Phase 0, TTS cache, visual audit, reviewer, futile retry, Phase 2 script,
# Phase 3, Phase 3.5, factory review
for t in test_cf_common_identity test_stage_order test_phase0_regressions test_tts_cache test_visual_audit \
         test_reviewer test_futile_retry test_phase2_script test_phase3 test_phase35 test_factory_review; do
  python3 -m unittest content-factory.tests.$t; done
python3 -m unittest content-factory.tests.test_phase2_hooks        # ~5 min
python3 -m unittest content-factory.tests.test_phase4              # ~2.5 min; uses fixtures/phase4_package_run
                                                                   # (override: CF_PACKAGE_RUN=<finished run>)
python3 content-factory/tests/smoke_v2.py                          # ~1 min
python3 -m unittest content-factory/tests/test_bad_videos.py -k A  # then -k B (4 tests, ~7 min), -k C, -k D
```
v1 regression (Ken Burns + karaoke; both results must be `passed`):
```
cd fixtures/v1_regression && O=/tmp/v1 && mkdir -p $O && sed "s#{FIXTURE}#$PWD#g" video/storyboard.timed.template.json > $O/timed.json
python3 ../../skills/video-production/scripts/render_video.py --storyboard $O/timed.json --voice audio/voice.wav \
    --timing audio/timing.json --out-dir $O/video --result $O/video/result.json --engine kenburns
python3 ../../skills/subtitle-production/scripts/subtitles.py run --timing audio/timing.json \
    --video $O/video/video_nosubs.mp4 --out-dir $O/subs --result $O/subs/result.json --style karaoke
```

## Checkpoints
- **In this repository** (`checkpoints/v2.0.0-alpha8/`):
  - the code archive `content-factory-v2.0.0-alpha8.zip`
  - `phase4-package.zip` (brain-freeze publishing package: final video, thumbnail, cover, crops, metadata,
    PUBLISHING_PACKAGE.md)
  - `phase4-package-knuckles.zip`
  - PHASE_4_REPORT.md, PROJECT_STATE.md, PUBLISHING_PACKAGE.md
  - the original `SHA256SUMS.txt`, unmodified. Verify with
    `cd checkpoints/v2.0.0-alpha8 && sha256sum -c --ignore-missing SHA256SUMS.txt` (6/6 OK).
- **Not in git** (each over GitHub's 100 MB file limit, or a duplicate). They stay in the original claude.ai session's
  outputs storage, unchanged, under `/mnt/user-data/outputs/checkpoints/v2.0.0-alpha8/`:
  - `phase4-run.zip`, `phase4-replay.zip`, `phase4-work.zip` (~200 MB each)
  - the loose `brainfreeze_final.mp4` and `brainfreeze_thumbnail.jpg`. The same files are inside `phase4-package.zip`;
    the storage rewrites loose media containers between sessions (decoded content identical, verified), so the zip is
    authoritative.
  - The runs can be regenerated byte-for-byte from `seeds/` with `work/phase4/replay.py` (verified 11/11 in Phase 4).
- **Earlier checkpoints** (alpha2–alpha7, phase0): preserved in the original outputs storage. They are not needed for
  Phase 5, because the alpha8 code archive contains the full code history state.
- **Portability-only differences** between this repo and the alpha8 code archive:
  - `test_phase4.py`'s default end-to-end fixture path now points at `fixtures/`.
  - `work/phase4/replay.py` locates `factory.py` relative to the repo.
  - The v1 fixture's storyboard paths are templated.
  - No behaviour, gate or policy was changed.

## Known limitations (carried into Phase 5)
- **Phase 1/3.5/4 judges are heuristic.**
  - The package judge is generous: it gave a perfect 45 to a package a packet-only external judge rated 37, with an
    accuracy flaw.
  - An external judge is supported (`package_judgment.json`) but is not run by default.
- **The ≈3:2 YouTube crop check for Shorts custom thumbnails is advisory only.** The ratio comes from secondary sources,
  and the crop cuts the selected thumbnail's text. Shorts custom thumbnails have been rolling out since 2026-07-25,
  starting with Partner Program channels.
- **The brain-freeze hook line is borderline.** "Sip or gulp? One doubles your odds" maps eating fast to gulping. The
  selected package's copy is accurate; the video was not re-rendered.
- **Claim checks are lexical.** Numbers are matched as substrings of the cited facts; paraphrased overstatement needs a
  reviewer.
- **No measured conversion, CTR or retention data yet.** CTA and package choices are a priori.
- **No text-on-text overlap gate**; text collisions are caught by eye.
- **No futile-resubmission guard for VISUAL_PLAN.**
- **The YouTube "altered/synthetic" flag** comes from unchanged provenance logic (False for cartoon visuals with AI
  narration). The other platforms' AI labels are True.
- **Byte reproducibility across environments is unproven.** Within one environment, replay is byte-identical.

## Standing owner preferences
- The owner (Abolfazl, Pavia) wants finished outputs produced by Claude, not instructions.
- The owner writes in Persian; reports to the owner have been written in Persian, with technical identifiers in English.
