# CLOUD HANDOFF — Autonomous Content Factory

Read this file first, then `PROJECT_STATE.md`. Written 2026-10-07; updated at the v3.0.0 release (development frozen).

## Status — FROZEN at v3.0.0 (2026-10-07)
| item | value |
|---|---|
| Phases complete | **0, 1, 2, 3, 3.5, 4, 5** |
| Authoritative release | **`v3.0.0`** (git tag `v3.0.0`, `checkpoints/v3.0.0/`) |
| Post-freeze patch | **v3.0.1** (owner decision, untagged): final-media metadata only — see CHANGELOG; `skills/content-factory/VERSION` |
| Batch layer | **Idea Engine 1.0** (owner decision, untagged): `scripts/idea_engine.py` — ideas file → memory filter → scoring → N diverse topics (`--count N`, default 2) → N V3.0.1 runs → packages; `references/idea-engine.md` |
| Production system | **V3.0.1 + Idea Engine 1.0** |
| Phase 5 (productionization + validation) | **PASS WITH LIMITATIONS** — `skills/content-factory/PHASE_5_REPORT.md` |
| Remaining development | **none — development is FROZEN** (no features, phases or optimisation) |

Rules for any later session:
1. **Development is frozen.** Do not change code, gates or policies. Operating the factory (making videos, packaging,
   logging analytics, running idea batches) is allowed; a change needs a new, explicit decision by the owner. The Idea
   Engine sits above V3.0.1 and calls only its interfaces (`factory.py init`, the unattended `claude -p` driver,
   `package`); it never changes how a video is made.
2. Never publish anything automatically; the owner uploads by hand.
3. Never expose or commit secrets. API keys are read from environment variables only. `ANTHROPIC_API_KEY` is
   recommended for production QA; without it the reviewer falls back to its generous heuristic judge.
4. Never weaken gates. Never remove the platform AI-disclosure behaviour (labels in metadata.json, the description
   line, PKG.DISCLOSURE, which still blocks without labels). Owner decision v3.0.1: the media files themselves carry
   no AI-label or disclosure metadata. The owner discloses on each platform by hand at upload.
5. Never modify completed checkpoints (`checkpoints/v2.0.0-alpha8/`, `checkpoints/v3.0.0/`).
6. Keep every artifact file under 250 MB, and under 100 MB in git (GitHub's limit).

## How to operate (no development)
1. `python3 skills/content-factory/scripts/setup_env.py --out /tmp/caps.json`. It installs the pinned runtime and the
   Kokoro model, and exits 3 with a fix if a core capability is missing.
2. Optional: verify with the test commands below.
3. `factory.py init --topic "…" --runs-dir runs`. Memory is on: `runs/factory.db`; import `memory/dump.json` first on a
   new machine. Then loop on `next`, then `package --zip`, then upload by hand.
4. Or, several topics at once (2 by default, `--count N` for another number): write about 50 ideas into `input/ideas.json` (by hand, or paste them from ChatGPT/Claude with the
   prompt in `skills/content-factory/references/idea-engine.md`; no API key). Then, from a project folder set up with
   `install_skills.py --project <folder>` (Claude Code finds skills only under `.claude/skills/`), run
   `python3 .claude/skills/content-factory/scripts/idea_engine.py run --ideas-file input/ideas.json --output-dir <HDD folder>`.
   Read `batches/<id>/report.md`, then upload by hand. `validate` and `select` also work from this repository.

## Repository layout
```
CLOUD_HANDOFF.md            this file
PROJECT_STATE.md            project state (v3.0.0, frozen)
skills/                     the 15 factory skills (side by side; skills_root() = this folder)
  content-factory/          orchestrator: scripts/factory.py, package_run.py, package_engine.py, setup_env.py, doctor.py,
                            cf_common.py (contract library — 15 byte-identical copies, enforced by a test),
                            references/ (orchestration-spec, packaging, platform policies…), tests/, VERSION,
                            CHANGELOG.md, PHASE_1..5 reports, PROJECT_STATE.md
  content-research/ content-strategy/ hook-engineering/ short-form-script/ multilingual-content/ voice-production/
  visual-storyboarding/ video-production/ subtitle-production/ video-quality-assurance/ asset-provenance/
  content-database/ content-analytics/ trend-intelligence/ automation-engineering/
checkpoints/v3.0.0/         final release checkpoint (see "Checkpoints")
checkpoints/v2.0.0-alpha8/  Phase 4 checkpoint files that fit in git
fixtures/phase4_package_run/<knuckle run>   trimmed finished run for test_phase4 end-to-end (16 MB)
fixtures/v1_regression/     v1 Ken Burns + karaoke regression inputs (storyboard paths templated: {FIXTURE})
seeds/<run>/                authored inputs of the 2 Phase 4 and 3 Phase 5 runs (dossier, ideas, hooks+SVG, script
                            variants, storyboard+SVG, package candidates+SVG, external judgment) for deterministic replay
memory/dump.json            channel memory (every topic made so far; imported by the automation templates and the Idea Engine)
input/ideas.example.json    Idea Engine input format (your own input/ideas.json and batches/ stay local, git-ignored)
work/phase4/, work/phase5/  operator scripts (authoring helpers per topic, replay driver, seed builder)
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
python3 skills/content-factory/scripts/factory.py unlock --run runs/<run> --note "why"     # audited; stale locks self-clear

# deterministic replay of any seeded run from its authored inputs
python3 work/phase4/replay.py seeds/2026-10-07-why-leap-years-skip-some-century runs_replay
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
python3 -m unittest content-factory.tests.test_phase5              # ~3 min; Phase 5 production + memory tests
python3 -m unittest content-factory.tests.test_final_media_metadata  # ~15 s; v3.0.1 final-media metadata policy
python3 -m unittest content-factory.tests.test_idea_engine         # ~80 s; Idea Engine (5 real factory.py init runs)
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
- **v3.0.0** (`checkpoints/v3.0.0/`, all in git, each file < 100 MB): `content-factory-v3.0.0.zip`,
  `phase5-package-leap.zip`, `phase5-rejected-for-review.zip`, `phase5-records.zip`, `memory-dump.json`,
  PHASE_5_REPORT.md, PROJECT_STATE.md, `SHA256SUMS.txt` (`cd checkpoints/v3.0.0 && sha256sum -c SHA256SUMS.txt`).
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

## Known limitations (final)
See `skills/content-factory/PHASE_5_REPORT.md` §7. In short:
- the heuristic judges are generous (use an LLM judge in production)
- writing quality is the bottleneck
- claim checks are lexical
- the ≈3:2 YouTube crop is advisory
- no CTR or retention data yet
- no text-on-text overlap gate
- no VISUAL_PLAN futile-resubmission guard
- byte reproducibility is proven across CPU sets and caches on one software stack

## Standing owner preferences
- The owner (Abolfazl, Pavia) wants finished outputs produced by Claude, not instructions.
- The owner writes in Persian; reports to the owner have been written in Persian, with technical identifiers in English.
