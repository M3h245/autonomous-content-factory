# Changelog — Autonomous Content Factory

## v3.3.1 — 2026-10-23 · fixes from the goosebumps review and the first channel-CTA videos
### Fixed
- **Package judgment always stale (reviewer.py):** the packet hash was the hash of `manifest.json`, which carries a
  `built_at` clock stamp, so every PACKAGE re-run rebuilt identical packets with a new hash and the cover judgment
  for exactly those files failed JUDGMENT.STALE — the documented "judge, then re-run packaging" flow could never
  pass. The hash is now taken over the manifest without `built_at`; any changed file still changes it.
  Regression test `PacketHashIgnoresBuildTime`; test_thumbnail_appeal uses the same canonical hash.
- **Caption phrase breaks (subtitles.py):** a word-count break no longer leaves a function word at the end of a
  caption chunk ("A metal spoon and a" / "Your skin is now the" in the long-form review #13); trailing words such as
  a/the/and/of/in are carried into the next chunk. Regression test `CaptionPhraseBreaks`.
- **plastic_block colours (doodle_parts.py):** `data-top` / `data-side` recolour the whole block, so the narration's
  "two black blocks" can show a black plastic block beside black aluminium.
- **HOOK.IDEA_MATCH (new, hook_engine.py):** a hook that promises none of the SELECTED idea's facts is not selectable.
  On 2026-10-22 the idea was "goosebumps are a leftover fur reflex" (F1/F2/F3/F5) but the chosen hook asked about
  music (F6/F7), so most of the script answered a question the hook never asked. `factory.py` now passes
  `--selection` and `--ideas` to the HOOK gate; without them the check is skipped (older runs unchanged).
- **16:9 hook frame 0 (hook_engine.py):** frame 0 of a long-form hook was measured on the 1080x1920 portrait canvas,
  so every wide title read as cropped/outside the safe area and every subject as too small (all five candidates of
  the first long-form run scored frame 0 = 2). The canvas now follows the SVG viewBox. Regression test added.
- **Duration estimate for the default voice (voice_calibration.json):** the default English voice `af_heart` had no
  calibration, so every estimate used `am_michael`'s slower coefficients: the first long-form script was estimated at
  528 s but spoke in 457 s and failed AUDIO.DURATION_IN_RANGE after a 6-minute TTS run. `af_heart` is now fitted on 177
  real production sentences (this run + the two 2026-10-23 Shorts); replayed estimates are within 0.5 s (456.4 vs
  456.9 s; 22.9 vs 22.6 s).
- **Script speech-rate check (reviewer.py):** measured over the whole estimated runtime with the final review's band
  (2.0-3.4 w/s). It used speech-only time with a 3.3 cap tuned on `am_michael`; with `af_heart` calibrated, real
  delivered Shorts measure 3.3-3.5 w/s between pauses, so every correct estimate failed message_clarity.
- **CTA.ON_SCREEN_SHOWN (cta.py):** a follow card written on two lines ("FOLLOW" over "BRAIN ACADEMY") is two text
  elements; the check now joins the labels on screen in the CTA window instead of requiring one element with the whole
  line (the first long-form render failed on it).
- **VID.MOTION_GAP vs VID.END_SCREEN_TAIL (render_video.py):** on 16:9 the last 5 s must stay calm for the end
  screen, but the motion-gap check counted that calm tail as dead air, so every long-form video failed one of the two.
  Gaps are now measured up to the start of the end-screen zone (VID.MOTION_GAP and VID.PACING_CADENCE).
- **density_events.py on 16:9:** it never added anything to a long-form scene (0 accents on 87 scenes): the canvas was
  not switched to 1920x1080 and its anchors sat at y 1440-1660, off a 1080-high frame, so every accent failed the
  geometry gate. It also only filled the tail after a scene's last entrance (interior gaps were left), took the
  earliest word (stacking accents) and could bind to a repeated word's first occurrence. Now: storyboard canvas,
  wide anchors on the side rails, worst gap first, latest word that closes the gap, first-occurrence words only, and
  the closing 16:9 scene (end-screen zone) left calm, and it aims 0.25 s under the gate (scene-local vs render timeline).
  Accents are neutral (sparkle/star): a density "?" or "!" bound to a random word read as a meaningful mark. Replay on the first long-form run: 17 accents in 15 scenes,
  every gap <= 3.5 s.
- **SUB.BURNED_IN on 16:9 (subtitles.py):** the burn-in probe grabbed frames at a fixed 270x480 (portrait) size, so on a
  1920x1080 video the caption-band rows pointed into the middle of the squashed picture and every long-form burn read
  "0 changed pixels" and escalated. The probe now uses a quarter of the current canvas. Regression test added.
- **Independent review knows the format (reviewer.py):** the request told the judge every video was a "vertical
  short-form explainer" and COVER.FORMAT demanded a 9:16 cover, so the first 16:9 long-form video was marked down for
  being landscape and 8.9 min long. The format now follows the frames (16:9 → "long-form explainer", 16:9 cover
  >= 1280 wide).
- **`plastic_block`** (matte, orange, no shine): an aluminium block next to a recoloured `metal_block` read as two metal boxes, so the ice-cube test looked backwards.
- **More reviewed parts:** `speaker`, `fan`, `railing` (redrawn as a stair handrail over steps after two reviews read level rails as a radiator and a table) (the long-form review read a volume knob and a PC fan as clock
  dials and both railings as tables). Scene guide: no "≈" in marker text; on 16:9 the subject is on screen from the
  start of its scene.
- **Long-form audio no longer OOMs (audio_design.py):** the speech-band filter ran one FFT over the whole track; on a
  9-minute 48 kHz mix that took several GB per call and the render was killed (exit -9) twice. Inputs longer than
  22 s are now filtered in 20 s blocks with 1 s of context (0.5 % RMS difference on a 90 s noise test); Shorts keep
  the single-FFT path, so their mixes are unchanged.
- **Long-form captions (subtitles.py):** 16:9 videos default to 5 words per caption chunk (Shorts stay at 3); the
  review found 2-3-word flashes broke phrases on an 8-minute video ("ONE OF THE", "FOLLOW FOR A").
  The 16:9 caption line also moves up from 0.86 to 0.84 of the frame height (it sat under the player's control bar).
- **`finger` part redrawn** (fist with knuckles, extended index finger, thumb, cuff): the first version read as a
  paddle. Scene guide: text `y` is the vertical centre; long-form labels pop instead of being hand-written.
- **Channel follow line (cta.py, reviewer.py):** `CHANNEL_CTA` = "Follow for a daily mystery." / "FOLLOW BRAIN
  ACADEMY". It is meant to be identical in every video, so `CTA.RELEVANCE` and `CTA.NOT_REPEATED` no longer reject it
  and the naturalness brevity cap is 2.8 s for it (the CTA.DURATION cap). Every other CTA keeps the old rules. The
  per-video rules had forced unnatural lines such as "Follow: your foot is weirder."
- **Title airtime (reviewer.py, package_engine.py):** a title that restates the run's own topic question is about the
  whole video; word counting had called "Why does your foot fall asleep?" a side note (8 %) because the narration
  says "a sleeping foot". The package packet now carries the dossier topic. Replay on the foot run: P1 (the
  question title with the foot cover) is now selected, as a human would choose.
- **THUMB.TEXT_MATCHES:** HTML entities in the declared cover text (`&amp;`) are decoded before comparing with the
  rendered text.
### Added — a quality floor for drawings
- **`video-production/scripts/doodle_parts.py`**: 16 carefully drawn, reusable parts (`leg`, `ear`, `head`, `hand`,
  `eye`, `plane`, `thermometer`, `metal_block`, `wood_block`, `ice_cube`, `mug`, `pan`, `flame`, `weight`, `hose`,
  `molecule`), registered in `doodle_lib.COMPONENTS`. Scenes had redrawn body parts from boxes per video (a foot as an
  "L", a plane that read as an arrow through an ear).
- **`drawing_quality`** (reviewer.py, judge-only, threshold 4): would an adult recognise every drawn subject at a
  glance? Without a judge it is reported "not judged" and gates nothing; with one it routes to VISUAL_PLAN/redraw_scene.
- **Production runs are judged by a fresh agent:** `idea_engine.py --review-backend` defaults to `subagent`, so QA
  (including drawing_quality) and the cover judgment (`thumbnail_appeal`, which the heuristic always scored 3) are made
  by an independent agent looking at the frames. `--review-backend heuristic` keeps the old behaviour.
- `doodle-scene-guide.md` "Drawing quality floor" and `review-rubric.md` drawing_quality anchors.
- **Copy-ready upload files:** `package/<vid>/copy/youtube_title.txt`, `youtube_description.txt`,
  `tiktok_instagram_caption.txt`, `hashtags.txt`. Copying from PUBLISHING_PACKAGE.md once pasted the next markdown
  heading into a published YouTube description.
### Tests
- `content-factory/tests/test_v331_fixes.py` (channel CTA exempt/other CTAs still checked, selected-idea facts,
  every drawing part renders, drawing_quality gates only when judged).

## v3.3.0 — 2026-10-20 · real 16:9 long-form + sourced packaging rules
Research: `docs/v3.3/RESEARCH-PACKAGING.md` (13 sections, 21 sources) and the companion reports in `research/`
(`youtube-shorts-packaging-2026.md`, `youtube-longform-strategy-2026.md`). Every rule added here cites a primary
source; anything without one is a **pre-registered experiment judged by watch time**, never an adopted threshold.
### Changed — the format is now aspect-aware, not just duration-aware
- **`cf_common.py`** (canonical, synced byte-identical to all 15 copies) gains `FORMATS`
  (short `1080x1920` / long `1920x1080`, viewbox + aspect), `SHORT_MAX_S = 180.0`, `HOOK_WINDOW_S`
  (`short 3.2 s` / `long 8.0 s`, from YouTube's long-form creator guidance for the 5–10 s hook; the widely-repeated
  "3 seconds" has no YouTube source) and `video_kind(aspect, max_s)` / `format_of(kind)`. The brief schema now has
  `video_kind` and `aspect` enums.
- **The single biggest finding:** any **square or vertical upload ≤ 3:00 is a Short** by YouTube's definition — it is
  served in the Shorts feed, is monetised from a separate Creator Pool (10 M views / 90 d), and its watch time does
  **not** count toward the 4,000 watch-hour YPP threshold. Only **16:9** is A/B-testable and earns watch-page hours.
  The v3.2 portrait 184 s video is therefore a Short; v3.3 renders real 16:9.
- `factory.py init` takes `--aspect auto|vertical|wide` (auto = wide when `--max-s > 180`), records `video_kind`,
  `aspect`, `length_choice` (ad-surface bands from `answer/2467968`) and `end_screen` (long only: zone 5–20 s,
  video ≥ 25 s, Subscribe element, `answer/6388789`). It threads `--aspect` down to VISUAL_PLAN, VIDEO, SUBTITLES
  and QA.
- **Canvas plumbed through every renderer:** `doodle_engine.set_canvas(w, h)` recomputes `W,H`, `CENTER` and
  `CAPTION_BAND`; `render_video.set_size`, `storyboard_tool.CANVAS`, `subtitles.set_canvas` (caption band y = 0.86
  wide / 0.63 vertical, font and margins scaled by canvas) and `qa_video.set_canvas` (container spec 1920x1080) all
  follow the brief. Portrait values are unchanged, so existing Shorts render identically.
### Added — sourced packaging and monetisation rules
- **`PKG.PACKAGING_VARIATION`** (major): fails when the title shape, thumbnail text or opening promise is a
  near-duplicate (> 0.6 Jaccard) of an earlier video in the run or in `factory.db` `videos`. The inauthentic-content
  policy (renamed from "repetitious" on 2025-07-15) refuses monetisation to templated, interchangeable videos — the
  exact profile of a template factory (`answer/1311392`).
- **End screens** (16:9 long-form only): a calm 5 s tail is enforced (`VID.END_SCREEN_TAIL`: ≤ 2 new visual events and
  no camera punch-in in the last 5 s) and `metadata.human_must_set` instructs the owner to add the Subscribe end
  screen in Studio. `VID.CLEAN_ENDING` accepts a ≥ 6 dB music fade ending at ≤ −30 dBFS for long-form instead of
  requiring −45 dBFS silence.
- **Title/thumbnail A/B test** (16:9 long-form only): PACKAGE emits `ab_test` (decision metric **watch time**, ~14
  days, 3 variants, `answer/16391400`) and a `title_variants` block in `publishing_package.json` +
  `PUBLISHING_PACKAGE.md`. Not available on Shorts.
- **Hashtags:** gate message now cites the rule — up to ~3 description hashtags are promoted; > 60 ⇒ all ignored and
  over-tagging can remove the video from search (`answer/6390658`). New `SCRIPT.NO_HASH_IN_TITLE` (major).
- **Related video on a Short** is offered for every Short when the channel has a long-form sibling (the official
  Shorts→long-form funnel, `answer/14075157`), not only for `part_2`.
- **Long-form thumbnail:** `review-policy.json` gains `thumb_size_wide` (1920x1080) + `core_safe_wide`;
  `package_engine.py select --aspect wide` renders and measures the 16:9 thumbnail; `crops_preview` writes a single
  16:9 band instead of the five mobile cover crops.
### Added — the cover judge (P6.2, thumbnail taste)
- **`reviewer.py` gains a judge-only `thumbnail_appeal` dimension** (`PACKAGE_DIMS`, `JUDGE_ONLY`, threshold 4). Every
  other package dimension is geometric; a cover can pass them all and still be dull. The heuristic returns a neutral
  3 with an explicit "not judged" note and **does not fail a package on it** (heuristic-only runs behave exactly as
  before). An external judge (fresh agent or human) is authoritative for this dimension: `merge_package_judgment`
  lets it raise as well as lower (the one deliberate exception to min-only), and its scores for all other dimensions
  still only lower.
- **The judge sees the cover the way a viewer does:** `review-package` builds packets that already carry
  `frames/thumbnail.jpg` (full size) and `frames/thumbnail_168.png` (phone shelf) plus the title and opening promise.
  `--backend subagent` writes `package_review_request.md` (score anchors, absolute packet paths, the exact
  `packet_manifest_sha256` to echo back) and exits **3 / `AWAITING_JUDGMENT`**; the second run merges
  `package_judgment.json`. A judgment that omits `thumbnail_appeal`, or was made for an older packet, is blocking
  (`JUDGMENT.UNJUDGED_COVER` / `JUDGMENT.STALE`).
- **`package_engine.py select --review-backend auto|heuristic|subagent`** passes the backend through, writes
  `status: awaiting_judgment` + `PKG.AWAITING_JUDGMENT` (nothing is selected) on exit 3, and can build a **hashed
  context brief** of the channel's own recent covers from `factory.db` (`--db` / `--runs-dir`, written to
  `review/channel_covers.json`, outside the packet, hash recorded in the boundary log — P4.2).
  `package_run.py` honours the brief's `review_backend`, passes `--db`, and stops on an awaited judgment.
- **Routing:** a low `thumbnail_appeal` (or an unjudged/stale cover) returns `PACKAGE` / `redesign_cover` — taste is a
  packaging problem, not a rendering one.
- **Tests:** `video-quality-assurance/tests/test_thumbnail_appeal.py` (6 tests) pins the neutral heuristic, the
  judge-authoritative merge, the `redesign_cover` route, the missing-cover check and the full await flow through
  both `reviewer.py` and `package_engine.py`.

### Changed — release hygiene (P5.1–P5.3)
- **P5.1 — memory stops growing the repo.** `memory/dump.json` (5.16 MB, re-exported after every run) is no longer
  tracked and is git-ignored; the repository ships `memory/snapshot.json` (195 KB — every run, idea, video, asset and
  publication, without the bulky `yt_*` analytics and per-stage rows) and `memory/README.md`, which documents that
  the live memory is the SQLite factory database (`--db` / `$CF_DB` / `$CF_RUNS_DIR/factory.db`), not the JSON dump.
  `idea_engine.ensure_memory` seeds a missing database from `memory/dump.json` first, then the shipped snapshot;
  `tools/make_memory_snapshot.py` refreshes the snapshot deliberately before a release. `test_phase5` and
  `test_experiment` accept either file, so a fresh clone still refuses repeated topics.
- **P5.2 — one PROJECT_STATE.** The root `PROJECT_STATE.md` is the single source of truth (now describing v3.3.0);
  `skills/content-factory/PROJECT_STATE.md` is a pointer to it, so the two can never drift again.
- **P5.3 — Windows CI.** `.github/workflows/windows-tests.yml` installs the four native dependencies on
  `windows-latest` and runs every unittest file in its own subprocess (`tools/run_tests_isolated.py`, now exiting
  non-zero on any FAIL/TIMEOUT). The locale and dead-lock class of bug from v3.1.1 can no longer return unnoticed.

### Added — pre-registered experiments (no source; judged by watch time)
- `input/experiments/registry.json` (`cf-experiment-registry/1`) records X-STICKER, X-MIDCTA and X-TITLECASE before any
  data exists, with the rule that they are decided by **watch time**, and `learning.registered()` surfaces them
  alongside paired `spec.json` experiments so a new hypothesis never silently replaces a pre-registered one.
### Performance
- Remaining `skia.Surface.MakeRaster(ImageInfo...)` slow paths replaced with `MakeRasterN32Premul` in
  `package_engine.py`, `hook_engine.py` and `doodle_engine.render_still` (~50x faster per surface; same pixels).
### Tests
- `test_cf_common_identity` (15 byte-identical copies), the long-form format tests and the full suite run green.

## v3.2.0 — 2026-10-20 · render speed + long-form foundation (in progress)
Scope: `video-production/scripts/doodle_engine.py` (speed), `content-factory/scripts/factory.py` and
`content-analytics/scripts/learning.py` (long-form split), `video-quality-assurance/scripts/qa_video.py`
(duration ceiling). No gate, contract or output layout changed for shorts.
### Performance — doodle renderer 37x faster (measured; see `docs/v3.2.0/PERFORMANCE.md`)
- **`_surface()`** now builds surfaces with `skia.Surface.MakeRasterN32Premul(W, H)` instead of
  `skia.Surface.MakeRaster(ImageInfo(...))`. Byte-identical pixels, ~50x faster to draw images into
  (154 ms → 3 ms per 1080x1920 blit on skia-python 144.0.post2). This was the real bottleneck: the paper
  grain overlay alone was 289 ms of a 300 ms frame.
- **`raster_image()`** (new) builds numpy-derived images via `Surface.MakeRasterDirect` + snapshot instead of
  `Image.fromarray` (150-300 ms → 3 ms per blit). N32Premul is BGRA, so the buffer is R/B-swapped first.
  Verified pixel-identical with PIL; the paper overlay rounds by at most 3/255 afterwards (documented).
- **`rough_effect()`** memoised with a bounded 8192-entry cache (built per glyph per frame; ~3 % here, more
  on complex scenes).
- Net: a fixed doodle scene renders at **120 fps, up from 3.2** — ~8 ms per frame instead of 300 ms.
### Added — long-form foundation (P3)
- `factory.py init` records `video_kind` (`"long"` when `--max-s > 180`, else `"short"`) in the brief, so the
  analytics learning loop can split the two; `--min-s 180 --max-s 480` is accepted and threaded through every
  stage (already was).
- `learning.py attributes` records `video_kind` per video (from the brief, falling back to the brief's
  `max_s` then the measured duration, so pre-v3.2 runs are classified too) and lists it in `missing`.
- `qa_video.py` gates duration against `max(180, brief.max_s)` instead of a hard 180 s ceiling, so a long-form
  brief is not rejected while shorts keep the default.
- Docs: `docs/v3.2.0/ROADMAP.md`, `LONGFORM.md`, `PERFORMANCE.md`.
### Tests
- `test_visual_audit`, `test_bad_videos`, `test_phase35`, `test_phase2_hooks`, `test_phase4`, `test_phase3` green
  after the renderer change.

## v3.1.1 — 2026-10-19 · Windows correctness patch (locale-independent text I/O)
Scope: production scripts and tests only. No stage, gate, contract, output layout or decision changed — the same
videos are produced, and the analytics/learning behaviour is identical.
### Fixed
- **UTF-8 everywhere.** On Windows the default text encoding is cp1252, so any file read or written without an explicit
  encoding corrupted or crashed as soon as it carried a non-ASCII character (`…`, `’`, `—`, or a Persian topic). Fixed in
  production code (`idea_engine.py` VERSION + checksums reads; `experiment.py`; `hook_engine.py`; `replay_run.py`;
  `estimate.py`) and in the test helpers (`fixture_kit.py`, `phase2_kit.py`) and test reads.
- **Dead-process lock takeover on Windows** (`factory.py _pid_alive`). `os.kill(pid, 0)` terminates a process on Windows,
  so the previous code returned "alive" for every pid and a crashed run stayed locked for the full 12 h staleness window.
  It now asks the OS (`OpenProcess` + `GetExitCodeProcess`) whether the pid is really alive.
### Changed
- `run_factory.ps1` / `run_factory.sh` / `content-factory.yml` set `PYTHONUTF8=1` so unattended runs are locale-safe.
- Docs: `PROJECT_STATE.md` (root and skill), `IMPLEMENTATION_REPORT.md` and `WINDOWS_SYNC_PROPOSAL.md` now record that
  W0–W5 were **applied** to the production database (they previously said "pending owner approval").
### Tests
- The full Windows suite runs green (previously the lock test and two cp1252 `UnicodeDecodeError` tests failed).

## v3.1.0 — 2026-10-18 · analytics and feedback loop (owner request) · untagged until approved
Scope: content-analytics (new `learning.py`, `learning_apply.py`), content-database (new `reconcile.py`), consumers in
`idea_engine.py`, `factory.py init` / HOOK gate command and `hook_engine.py select`, tests, docs (`docs/v3.1.0/`). No
research, voice, render, QA, packaging or experiment gate changed. Plan and evidence: `docs/v3.1.0/ROADMAP.md`, `AUDIT.md`,
`VALIDATION.md`, `IMPLEMENTATION_REPORT.md`.
### Added
- **learning.py attributes:** creative attributes per published video, read from the run's own files with their hashes.
  Covers opening form, curiosity mechanism, hook length, first-explanation time, beat roles, scene density, duration,
  format, title form, CTA and loop beats, and category (only when an idea batch assigned it).
- **learning.py kpis:** fixed-age KPIs (D1/D3/D7 views, engaged views, engaged share) from daily per-video rows, plus
  lifetime values labelled with their age. Maturity classes `none / early / d3 / d7`; missing data is NULL with a status.
- **learning.py analyze:**
  - group comparisons on the D3 engaged share, with shrinkage, a bootstrap interval, confidence labels and the avg view % guardrail;
  - findings with evidence and sample size;
  - bounded directives, the next hypothesis, tracking of earlier hypotheses and experiment arms, and the registered experiments;
  - outputs `learning_summary.json` (cf-learning/1) and `LEARNING_REPORT.md`.
- **Directive rule:** a directive needs n≥3 per side, an 80 % interval that excludes 0, and a guardrail (avg view %) no
  more than 5 pp worse; otherwise the level is listed under `explore` with the reason.
- **Duplicate run folders:** when the same run exists twice (a stale PC copy and a finished cloud copy), the most
  complete folder is used and the duplicate is reported.
- **learning_apply.py:** the shared, bounded read side used by every consumer.
- **reconcile.py plan|apply:** cloud run folders or dumps reach the canonical database insert-only. Runs are validated
  first; the tool detects conflicts, refuses a stale plan, takes a backup, verifies the result and writes a report.
### Changed (all opt-out, recorded)
- **idea_engine select|run:**
  - reads `--learning`, else `$CF_LEARNING`, else `data/learning/latest.json`; `--no-learning` restores the old behaviour exactly;
  - category priors are bounded at ±15 % and the quality floor uses the unadjusted score;
  - the influence is recorded in ranking, selected and manifest, and the summary is passed to each run's init. A summary
    that changed after selection is refused (LEARNING_CHANGED).
- **factory.py init --learning:**
  - records the summary in run.json, copies it to `learning.json` and adds its guidance to the constraints;
  - merges the format priors into SELECTION's `weights.json`;
  - a broken file is refused (LEARNING_INVALID). The HOOK v2 gate passes `--learning` when the run has a summary.
- **hook_engine select --learning:**
  - a bounded bonus (±1.5 review points max) re-ranks only the candidates that passed the review;
  - records `learning_influence` (choice without learning, bonuses, changed or not) and adds HOOK.LEARNING_COVERAGE (minor).
### Tests
- New: `content-analytics/tests/test_learning.py` (15), `content-database/tests/test_reconcile.py` (5),
  `content-factory/tests/test_learning_loop.py` (7).
- `test_idea_engine.py` now also clears `CF_LEARNING`.
### Not changed
- The production database, `memory/dump.json`, YouTube data and experiment specs.
- `cfdb.py publish` (still available, not used by the workflow).
- The installed `.claude/skills` copies (they need a separate install).

## Video count — 2026-10-14 · default 2 instead of 5, `--count N` everywhere (owner request) · VERSION stays 3.0.1 · untagged
Scope: `factory.py` (the `init --count` argument only), `idea_engine.py`, the automation-engineering run_factory templates
and workflow, tests and docs. No stage, gate, contract or experiment behaviour changed.
### Changed
- **Default 2 videos.** `factory.py init` makes 2 videos per run when `--count` is not given (was 5). `idea_engine.py
  select|run` picks 2 topics, so 2 runs and 2 videos (was a fixed 5, `WINNERS`). Both read one constant,
  `factory.DEFAULT_VIDEO_COUNT`.
- **`--count N` overrides it** on `factory.py init` and, new, on `idea_engine.py select` and `run`
  (for example `--count 4`). An existing batch keeps the size it was selected with; `produce --batch` reads the manifest.
- **Validation.** `--count` must be a positive whole number from 1 to 50 (50 is the brief contract's maximum). `0`, `-1`,
  `2.5`, `abc`, an empty value or anything above 50 is refused by argparse with exit 2 and the message
  "invalid count …: must be a positive whole number from 1 to 50, e.g. --count 4 (default 2)", before any run or batch
  folder is created.
- **Templates.** `run_factory.ps1 -Count` defaults to 2 and refuses invalid values (exit 2). `run_factory.sh` defaults to 2
  and accepts `COUNT` or `--count N`, with the same check. `content-factory.yml` defaults to 2 (was 3) and checks the value.
- **Docs.** SKILL.md, `references/idea-engine.md`, README.md, PROJECT_STATE.md (both copies), CLOUD_HANDOFF.md and the
  automation-engineering scheduling examples describe the default of 2 and `--count N`.
### Tests
- New `tests/test_video_count.py`: the default of 2, `--count 4`, the 1–50 rule and every invalid form, for `factory.py init`
  and `idea_engine.py select|run`, and the template defaults.
- `tests/test_idea_engine.py`: the tests built around a five-topic batch now pass `--count 5` explicitly.
### Not changed
- `experiment.py`: an experiment's size comes from its frozen plan (six slots, one video per run).
- The installed copies in `.claude/skills/` are unchanged until they are installed separately.

## Experiment layer 1.2 — 2026-10-14 · `sync-gate` and a stricter `gate` (owner approved) · production engine unchanged (VERSION 3.0.1) · untagged
Scope: `scripts/experiment.py`, `tests/test_experiment.py`, `references/experiments.md`. No V3.0.1 file changed. The 1.1
versions are backed up in `checkpoints/experiment-layer-1.2/backup/`.
### Why
- Slot 2 of EXP-2026W42-beat3to9-c: SCRIPT escalated (VARIANTS_DISTINCT) inside `drive`, which stopped the slot as `blocked`.
  After the owner's `factory.py reset` and a re-recorded SCRIPT pass, V3.0.1 says SCRIPT passed, but the slot record still
  said `blocked` with no approved gate: only `drive` could record a gate, and `drive` goes straight on to audio.
- `experiment.py gate` returned `ok: true` on a script.json whose SCRIPT stage had failed (`script_select` writes the best
  variant even when the stage fails).
### Added
- `experiment.py sync-gate --batch B --slot N`. It records the pre-audio gate for a slot whose SCRIPT passed outside `drive`.
  - It runs nothing: no stage, no Claude session, no audio, no factory command, no `drive` or `produce`.
  - It refuses with nothing written unless all of these hold:
    - plan, assignment, constraints and manifest verify;
    - the slot is `prepared`, `blocked` or `gate_failed` and not yet approved;
    - no `.lock` exists in the run or the batch;
    - V3.0.1 records HOOK and SCRIPT as passed, the video is `in_progress` and no stage after SCRIPT has passed;
    - SCRIPT result.json is the recorded one (sha256), its status is passed, and its script output is the current script.json;
    - the experiment gate passes;
    - state.json and script.json are unchanged between the check and the write.
  - On success it writes only `experiment_gate.json` and the slot record. The slot becomes `gate_passed`, with approved_by
    sync-gate and a sync-gate attempt; history is appended, never rewritten.
### Changed
- `gate` is ok only when V3.0.1 recorded SCRIPT as passed. It reports `factory_script` and exits 3 otherwise.
- `assignment_for` takes the engine label from the plan, not from this file's VERSION. Assignments of an existing batch stay
  identical after an upgrade; with VERSION 1.2, slot 2's 1.1 assignment would otherwise have failed ready, drive and sync-gate.
### Tests
- test_experiment (28; 23 before), in both trees:
  - gate not ok while SCRIPT is failed or pending (exit 3), and ok once it passed; gate writes nothing;
  - sync-gate success changes exactly the slot record and experiment_gate.json, with execution paths patched to fail
    (subprocess, Claude, factory reset, drive, produce, Idea Engine produce); stages unchanged, history kept, a second
    sync refused with no change;
  - after sync-gate, drive runs phase B only;
  - 11 refusal cases leave every batch and run file byte-identical;
  - the engine label stays the plan's after an upgrade.

## Experiment layer 1.1 — 2026-10-13 · audit fixes 1–6 (owner approved) · production engine unchanged (VERSION 3.0.1) · untagged
Scope: `scripts/experiment.py`, `tests/test_experiment.py`, `references/experiments.md`, `tools/youtube_sync/yt_sync.py`
(default output folder), new spec `input/experiments/EXP-2026W42-beat3to9-c.json`. No V3.0.1 stage, gate, reviewer,
packaging, memory or media code changed. 1.0 files are backed up in `checkpoints/experiment-layer-1.1/backup/`.
### Changed
- Experiment `-b` superseded and preserved unchanged: `batches/_superseded/EXP-2026W42-beat3to9-b/`, plan sha256 5d4736a8….
  The new experiment is `EXP-2026W42-beat3to9-c` (spec sha256 1c4872e9…, plan sha256 632d934d…).
- Fix 1, the dedicated driver `experiment.py drive`:
  - phase A (rules in the prompt; stops before AUDIO), then a deterministic gate, then phase B;
  - non-compliant scripts are reset through `factory.py reset` and rewritten, with at most 2 repairs, then `blocked`;
  - `experiment.py produce` runs the Idea Engine with this driver and refuses unless `ready`.
- Fix 2, control arm: the factory's normal structure (twists allowed); only the planned reveal is kept out of the first 9 s.
- Fix 3, stronger checks:
  - assigned opening line (or a written override);
  - question answered within 2 s;
  - variant reveal identified by its distinctive words starting at 1.5–7 s; setup and hook-repeat checks;
  - control leak check;
  - script-to-TTS word alignment verified token by token;
  - approved script hash enforced in `check`.
- Fix 4, failure-safe prepare: the manifest is written only when all six runs carry their assignment and constraints. Its
  created_at is the plan time (otherwise `idea_engine.run_state` would call every prepared run "foreign"). New `ready`
  preflight.
- Fix 5, observation windows come from the Analytics data cutoff (last processed day, Pacific time), not the pull time.
  Data age and pull age are recorded; observations are de-duplicated per cutoff.
- Fix 6, spec `-c`: unambiguous openings for blind-spot ("Each eye has a hole in its view.") and mirror-eye-movement
  ("Your mirror can't show your eyes moving."). The afterimage 20-second stare became an on-screen reveal (dashed cyan
  ghost dot, YOUR EYES ADD THIS).
- `yt_sync.py pull` now writes to `<repo>/data/analytics` from any folder (1.0 wrote relative to the current folder).
- `produce` checks that `claude` and the installed skills are present before any driver starts. The driver calls `claude` by
  its full path (claude.exe or the npm claude.cmd); for a .cmd shim, characters that cmd.exe would re-parse are replaced in the prompt.
### Tests
- test_experiment (23): -c valid and -b preserved; plan balanced, write-once, edits refused, normal control rule; partial
  prepare writes no manifest (verify_batch/ready/produce refuse, exit 2); rerun retries only the failed slot with
  byte-identical assignments, run_state not foreign, Idea Engine re-preparation is a no-op; tampering detected; driver
  prompts carry the assignment (stub `claude`); produce drives all six through the experiment driver; non-compliant
  scripts blocked before audio with the real `factory.py reset`; HOOK reset for openings and repair-then-pass; script
  change in phase B flagged; each -c topic's compliant script passes its arm and fails the other (estimated and measured);
  control twist allowed; question/override rules; alignment mismatch; the 10 real produced runs align; cutoff-based windows
  (the real 13 Oct case: 39 h of data → 24h, not 72h by pull time); before-publication/unknown cutoff; report excludes
  non-compliant pairs; produce preflight and .cmd-safe prompts; yt_sync default folder.

## Experiment layer 1.0 — 2026-10-13 · paired creative tests above the Idea Engine (owner request) · production engine unchanged (VERSION 3.0.1) · untagged
Scope: new files only. `scripts/experiment.py`, `tests/test_experiment.py`, `references/experiments.md`; read-only analytics
pull `tools/youtube_sync/yt_sync.py` (outside the skills). No stage, gate, reviewer, packaging, memory or media code changed.
### Added
- `experiment.py plan | prepare | check | link | observe | manual-template | manual | report | status` (cf-experiment/1):
  - frozen, self-hashed assignments (balanced coin flip);
  - hand-off as an ordinary idea batch, so `idea_engine.py produce` runs it unchanged;
  - per-slot `--constraint` rules and `experiment_assignment.json` in each run;
  - production check from script beats + word timing;
  - append-only observations with source, time and status (Stayed to watch is manual-only, never substituted);
  - manual CSV entry and a weekly report with the audit's provisional decision rule.
- First experiment spec `input/experiments/EXP-2026W42-beat3to9-b.json`: 3 matched pairs (blind spot / afterimage, mirror
  front-back / mirror eye movement, Moon's face / daytime stars). It isolates the 3–9 s beat; claim-first openings in both arms.
### Tests
- test_experiment (10): spec validation; one variant per pair, balanced, alternating slots; write-once/deterministic
  plan; edited plan refused; prepare produces a batch `IE.verify_batch` accepts, restart-safe, failed init retried alone;
  variant compliance (setup/hook repeat/no reveal); link + observe without invented metrics, idempotent; manual CSV;
  report (preliminary, missing data, views never decide). `factory.py init` is stubbed: the real one needs the production machine.
### Known limits
- The rules reach the script through brief constraints and the operator; V3.0.1 does not enforce them. `check`
  detects violations afterwards, and the report lists them as confounders.
- The memory cleanup of 2026-10-10 removed rows that `test_idea_engine` uses as fixtures. Those tests pass (23/23
  non-production) against the committed dump (`git show HEAD:memory/dump.json`), not against the current memory/dump.json.

## Idea Engine 1.0 — 2026-10-07 · batch layer above V3.0.1 (owner decision) · production engine unchanged (VERSION 3.0.1) · untagged
Scope: a new entry point, `scripts/idea_engine.py`. No stage, gate, reviewer, packaging, memory or media-cleaning code
changed; V3.0.1 stays the source of truth for how every video is made.
### Added
- `idea_engine.py validate | select | run | produce`. It turns `input/ideas.json` (≈50 candidates written by hand or
  pasted from a ChatGPT/Claude chat; no LLM API, no API key, no network) into:
  - validation that lists every problem;
  - a memory filter with the factory's own database and rules: init's topic repetition, SELECTION's novelty below
    0.35, and the hook engine's used-hook rule;
  - an offline research screen that is explicitly marked "web research: not performed";
  - nine-component deterministic scoring with reasons;
  - diversity selection of exactly 5 (MMR, never two on one subject), failing with TOO_FEW_CANDIDATES rather than
    inventing topics;
  - `batches/<id>/` with candidates, filtered, research, ranking, selected, manifest (self-hashed), slots and report
    (json + md).
- Hand-off through V3.0.1's own interfaces:
  - one `factory.py init` per winner, in `batches/<id>/runs/`, with the shared memory and the angle/hook/visual as
    constraints;
  - the existing unattended driver (`claude -p "/content-factory …"`, run_factory flags) per run, or `--driver-cmd`.
  A run is delivered only when V3.0.1 recorded it as packaged (PACKAGE passed, result sha256 matches). It is then
  copied with its checksums verified to `--output-dir`/`CF_OUTPUT_DIR`, never overwriting.
- Stale protection:
  - a reused ideas file, an edited manifest or a changed input.json is refused;
  - a missing memory is refused;
  - foreign, missing or older runs are refused, and a package result that differs from the recorded one is not
    delivered;
  - one producer per batch (FileLock); driver logs are kept per attempt.
- `schemas/idea_candidates.schema.json`, `input/ideas.example.json`, and `references/idea-engine.md` (format,
  copy-ready prompt template, commands, outputs, scoring, selection, hand-off, troubleshooting, limitations).
- `env.example`: `CF_OUTPUT_DIR`, `CF_BATCHES_DIR`. `.gitignore`: `batches/`, `input/*.json` (except the example).
### Tests
- test_idea_engine (31). It covers:
  - the 50-candidate file; malformed JSON; missing candidates; empty topic; duplicate ids;
  - memory rejection, including rephrasings and a never-made idea, agreeing with `factory.py init`;
  - explained ranking; diversity; exactly 5; fewer than 5 fails; determinism; the manifest;
  - hand-off to 5 real `init` runs; isolated runs and outputs;
  - a failed run that leaves the others byte-identical and is retried alone;
  - produced topics remembered (database and dump.json);
  - stale manifest, input, memory, run, package and output protection; the batch lock.
  Production is a stub that runs the real `factory.py package --zip` on the packaged-run fixture.

## v3.0.1 — 2026-10-07 · post-freeze patch (owner decision): final-media metadata only · contract cf/1.1 · untagged
Scope: the metadata inside the publishable media files (final.mp4, thumbnail/cover and preview JPEGs). Content
generation, QA, reviewer, memory, packaging selection and the platform-compliance gates are unchanged.
### Changed
- The publishable MP4 now carries only what playback needs:
  - the ftyp brands (major_brand, minor_version, compatible_brands);
  - per track, the mandatory mdhd language (`und`) and the zero sample-entry vendor field;
  - all times zero.
  The empty `udta/meta/ilst` container ffmpeg always wrote is neutralised (an all-zero `free` box, in place and at the
  same size, so no sample offset moves). The track-handler names ("VideoHandler", "SoundHandler") are blanked.
  Streams are untouched (same MD5).
- JPEGs keep SOI, the JFIF header and the coding segments (and an ICC profile if present). Any other APP0 (e.g. JFXX)
  is now dropped as well as COM/APP1-APP15.
- The media audit (PKG.MEDIA_METADATA_CLEAN) also fails a file that carries:
  - embedded AI-label / AI-disclosure metadata (XMP, IPTC DigitalSourceType, C2PA manifests, "AI-generated" or
    synthetic tags);
  - a udta/meta/ilst/uuid/XMP box, a non-empty handler name, a padding box with data, or a non-JFIF APP0.
  The public-copy screen (PKG.PUBLIC_COPY_CLEAN) keeps its v3.0.0 pattern list unchanged.
### Clarified
- The factory never embedded AI labels in media files (no stage writes XMP, C2PA, IPTC or label tags; since Phase 3.5
  the cleaner dropped any container tags). v3.0.1 makes "no AI-label or disclosure metadata in the media" an explicit,
  tested guarantee.
- Platform disclosure stays outside the media and is done by hand at upload: the labels in metadata.json, the
  disclosure line in the description, and PKG.DISCLOSURE, which still blocks a package without them.
### Tests
- test_final_media_metadata (8): dirty MP4/JPEG inputs with every forbidden kind of metadata come out playback-only with
  identical streams and pixels; the factory's packaged deliverables pass an independent inspection (own box walker,
  JPEG segment walker, full ffprobe dump, byte scan); disclosure outside the media is still enforced. The suite fails
  on the v3.0.0 cleaner.

## v3.0.0 — 2026-10-07 · Phase 5 (productionization + validation) · contract cf/1.1 · FINAL — development frozen
### Production hardening
- **Deterministic narration**: Kokoro runs a fresh ONNX session seeded from (text, voice, speed, language) per
  sentence (`onnxruntime.set_seed` only applies at session creation). Same audio across processes, sentence order,
  cache state and CPU count; TTS cache v2. Before, alpha8 replays were byte-identical only because of the TTS cache.
- **Deterministic encodes**: every x264 encode uses `-threads 4` (`cf_common.X264_THREADS`); x264's automatic thread
  count changed the bitstream between 2- and 4-CPU machines.
- **Run lock**: mutating factory commands hold `RUN/.lock` (refused with LOCKED while held); a lock left by a dead
  process (same host) or older than 12 h is taken over; `factory.py unlock --run R --note` is audited.
  cta_history.json is updated under a shared lock.
- **No silent failures**: `record` keeps each envelope's sha256 and refuses a re-record (STALE_RESULT); a media stage
  that writes no (or an old) result becomes INTERNAL.NO_RESULT; crash envelopes get their video id from their path;
  `media` reports media_budget_exhausted.
- **Capabilities**: doctor names missing system libraries with a fix (libEGL.so.1 → apt libegl1); setup_env enforces
  the `==` pins and exits 3 when a core capability (tts.kokoro, video.render, subtitles.burn, visual.doodle) is
  missing; `init` refuses such a machine (CAPABILITY_MISSING) instead of rendering silently with a fallback;
  VIS.DOODLE_FALLBACK (major) when a doodle scene was rendered by a fallback.
- **Operator reset**: `reset` re-opens the stage *and every later stage* with a fresh retry budget (before, a stage
  that had used 2 attempts on the old content escalated on its first failure on the new content).
- **Reviewer routing**: an LLM/human judgment may mark `hook_strength` with `fix_stage` HOOK or VISUAL_PLAN; before, a
  spoken-hook problem the heuristic did not mark was routed to a first-scene redesign that cannot change words.
- **CTA history**: a video re-made after a reset is checked against other videos' CTAs only, and re-packaging
  replaces (or, without a CTA, drops) its own entry.
- **Package judgment coverage**: an external package judgment must cover every candidate (JUDGMENT.MISSING); an entry
  with `packet_manifest_sha256` must match the current packet (JUDGMENT.STALE).
- **Nothing ships after a failed PACKAGE**: the package folder is regenerated per attempt, the run zip is written only
  when every video passed (a stale zip is removed), and the video leaves `packaged`. Before, `package --zip` zipped the
  previous attempt's deliverables although PKG.PACKAGING had failed.
- Automation templates: daily cron (05:45 UTC), libegl1, memory import/export around each run, exit code preserved.
### Content memory and anti-repetition
- Memory is on by default (`runs/factory.db`, `CF_DB` or `--db`; `--no-db` opts out). `init` checks the topic against
  every earlier run topic and video title (`cfdb.py topic-check`: trigram cosine ≥0.6, ≥2 shared stems, or
  containment; calibrated on 12 repeats / 15 new topics, all correct) and refuses TOPIC_REPEATED unless
  `--allow-similar-topic REASON` (recorded). Memory errors stop the run (MEMORY_FAILED).
- The hook engine never selects a hook the channel already used (jaccard ≥0.6 with history; HOOK.NOT_REPEATED).
- `package` ingests the run automatically (idempotent). `memory/dump.json` ships the channel memory (8 runs).
### Fixed during Phase 5
- Paper transition crashed at its first frame (`setColorFilter(None)`), latent since alpha8.
- PKG.MEDIA_METADATA_CLEAN false positive: the drive-path pattern matched random bytes in about 1 video in 7.
- Package claim numbers matched substrings ("2" in "200"); whole numbers only now.
- `cfdb ingest-run` crashed on hook-engine-v2 runs; title now taken from the shipped package.
- A crash envelope without a video id made `record` raise and `media` loop silently.
### Validation
- 3 fresh videos (flamingos, Moon illusion, leap years), RESEARCH → PACKAGE through the factory gates; packet-only
  external judge on every final video and package set; seed replays byte-identical across CPU sets and caches.
  See PHASE_5_REPORT.md.
- Tests: test_phase5 (27), test_reviewer +1 (11).

## v2.0.0-alpha8 — 2026-10-07 · Phase 4 (packaging) · contract cf/1.1
### Added
- Packaging engine (`content-factory/scripts/package_engine.py`, contract `package_candidates`): ≥3 complete packages
  per finished video (strategy, title, opening promise, doodle thumbnail SVG + text + depicted facts, description,
  hashtags, claim ids, caption CTA); thumbnails rendered with the video's doodle engine and palette.
- Deterministic gates: claims (numbers, absolutes, health/causal terms must be in a cited fact with the same polarity),
  clickbait (phrases, shouting, !!), title length/words/topic/payoff/"promises what the video never says", opening
  promise vs the video's opening, copy CTA vs the video CTA, hashtags; thumbnail size, words ≤4, text ≥96 px (≥140
  headline), contrast at 168 px, text and subject inside the central square, text clear of the subject, single subject,
  dead space, clutter, words said in the video, known depicted facts, no CTA on the thumbnail; set-level: ≥3 viable
  candidates that are mutually distinct (strategy, title, thumbnail text, opening promise, perceptual hash).
- Reviewer `review-package` (9 dimensions, packet boundary, airtime of the title's focus) + optional external judgment
  (min-merge). Selection = highest-scoring PASS package; rejected alternatives recorded with reasons.
- PACKAGE stage: selected thumbnail becomes thumbnail.jpg/cover.jpg (cleaned, audited), crop preview, per-platform cover
  steps (YouTube Shorts custom thumbnails rolling out since 2026-07-25; TikTok 3:4; Reels centre crop),
  PUBLISHING_PACKAGE.md + publishing_package.json, PKG.PACKAGING, PKG.PUBLIC_COPY_CLEAN, PKG.THUMBNAIL_DECODES,
  PKG.CANDIDATES (brief flag without candidates). Older runs package exactly as before.
- Factory: new briefs carry `package_engine: v1`; PACKAGE task lists the files to write; PACKAGE retry budget 3.
- Tests: test_phase4 (49).
### Fixed during Phase 4
- Subtitle chunker left a lone comma word ("So,") on screen <0.25 s; SUB.MIN_DISPLAY then failed whatever the word
  limit (regression test added).
- smoke_v2 corrupted the master with unseeded random bytes → occasionally undetected; now seeded and wider.

## v2.0.0-alpha7 — 2026-10-07 · Phase 3.5 (retention + CTA + conversion, final-media metadata) · contract cf/1.1
### Added
- CTA engine (`short-form-script/scripts/cta.py`, contract `script.cta`): per-video decision (or a recorded no-CTA
  decision), nine CTA types, three placements, three modalities; deterministic gates on the estimated (SCRIPT) and real
  (VIDEO) timeline; policy envelope (`recommend`); cta_history.json against repeated outros; part_2 → manual related-video
  step in metadata.json (platform guidance verified 2026-10-07).
- Reviewer: CTA dimensions (quality, naturalness, relevance, retention risk) when a CTA is present, CTA gates as
  objective failures, "ending stands without the CTA"; script-variant review scores CTAs too; packet carries the public
  CTA only.
- Final-media metadata policy (`asset-provenance/scripts/media_clean.py`): lossless MP4/JPEG cleaning + audit; the
  deliverable no longer embeds provenance/debug metadata; AAC encoded +bitexact; PACKAGE gates PKG.MEDIA_METADATA_CLEAN,
  PKG.FINAL_DECODES, PKG.DISCLOSURE.
- Tests: test_phase35 (22), bad-video fixture D (bad CTA, rendered).
### Fixed during Phase 3.5
- Reviewer stemmer missed short plurals ("pops" vs "pop") → payoff wrongly "never addressed".
- reviewer crashed on a CTA without on-screen text; PACKAGE called a property as a method.
- First JPEG cleaner re-encoded pixels → replaced by a lossless segment stripper.

## v2.0.0-alpha6 — 2026-10-07 · Phase 3 (visual + audio) · contract cf/1.1
### Added
- Composition analysis (engine): layout class from geometry (hero/split/grid/panel/text_led/character/scatter), main
  subject signature (position/scale invariant), subject height, 3×3 dead-space grid; VIS.LAYOUT_REPEAT,
  VIS.SUBJECT_REPEAT (≤2 in a row, ≤50 % of non-loop scenes), VIS.SUBJECT_SIZE, VIS.DEAD_SPACE, VIS.OPENING_DENSITY.
- Audio: closed-loop music level (17 dB, policy 16-18), dynamic speech-band carve, SFX budget ≤0.8/s with priority and
  spacing, music-aware speech protection, active-speech masking metric (P.56-style), clean-ending report.
- VIDEO gates: VID.OPENING_DENSITY, VID.PACING_CADENCE, VID.LOOP_ENDING, VID.SFX_DENSITY, VID.SPEECH_MASKING,
  VID.CLEAN_ENDING; VID.MIX_BALANCE tightened from ≥10 dB to the 16-18 dB policy range.
- Hook engine measures each candidate line with the real TTS (pre-warms the AUDIO cache).
- factory: record refuses out-of-order results; VIDEO fix-route audio params reach the renderer; replay_run v2 inputs +
  resumable; render_video --fixed-music-gain for fixtures.
- Reproducibility: TTS runtime versions in the cache key and timing.json; setup_env pins onnxruntime/kokoro-onnx.
- Tests: test_phase3 (14). Owner listening pack (A/B/C mixes). Rebuilt v1 regression fixture (now saved in the checkpoint).
### Owner decision (2026-10-07)
- Listening calibration: mix A (music 17 dB under the voice, 12 dB speech-band carve) chosen over B and C. No code
  behaviour change — A was already the default; the policy range 16-18 dB is now confirmed.
### Fixed during Phase 3
masking metric counted pauses as speech · SFX protection ignored the music · fix route could move the mix policy ·
fix-route params never reached the renderer · grid classifier spread · VIS.OPENING tokenisation ("GAS?") · out-of-order
record accepted · estimator-based hook length passed a 3.5 s hook · SFX track one sample longer than the voice ·
TTS cache could mix runtimes · test_tts_cache corruption step depended on filesystem order.

## v2.0.0-alpha5 — 2026-10-05 · Phase 2 (hook + script) · contract cf/1.1
### Added
- Hook Engine (`hook_engine.py select`): ≥5 multi-channel candidates (contract `hook_candidates`, frame-0 doodle SVG
  each), diversity gate, real frame-0/t=1 s renders, deterministic frame-0 measurements, per-candidate packets,
  independent `review-hooks` scoring, selection (hook, first frame, coherence ≥4) or structured failure,
  repeated-failure memory (HOOK.FUTILE_RESUBMISSION), opening_brief.json for the Visual Plan.
- Script variants (`script_select.py select`, contract `script_variants`): two complete variants, hook-is-opening and
  promise-paid checks, distinctness, independent `review-script` scoring (hook-stage score carried), script.json output.
- Calibrated duration estimator (`estimate.py`, voice_calibration.json, calibration corpus): held-out error
  −1.6 … +4.4 % (was −8.5 … −18 %); real Phase 2 run −1.5 %.
- Intentional pauses (`pause_before`/`pause_after`) in TTS assembly, timing.json, gate and estimator; no re-synthesis.
- Frame-0 gates: VIS.OPENING, VID.FIRST_FRAME_SUBJECT, VID.HOOK_TEXT_T0, VID.FIRST_EVENT; engine hook stats
  (subject height, texts, safe margins, hidden negations, first event, `data-hook-exception`).
- Factory: `hook_engine: v2` for new runs (v1 kept for older runs), opening brief hint, default-voice map.
- Tests: Phase 2 hooks (10, A-G/L/M/N + boundary + diversity), Phase 2 script (7, G/H/I/J/K), reviewer zero-value regression.
### Fixed during Phase 2
- Nested `data-in="none"` elements were staggered (frame 0 lost wrinkles/nerve).
- Estimator read "2013," as "two thousand thirteen" (recalibrated: MAE 0.19 → 0.16 s).
- Reviewer: 0.0 treated as missing (label at 0.0 s, crop at 0.0 s, 0.0 dBTP peak); number/abbreviation normalisation;
  hook score inconsistency between stages; packet boundary regex too broad.
### Verified
- "Why your fingers wrinkle in water" rebuilt through the factory: hook h1 selected ("Pruney fingers? Not water.
  Nerves." + NOT WATER frame 0), variant B selected, video passes the full Phase 1 reviewer gate (hook 3 → 4,
  first frame 4 → 5, cover 3 → 4), PACKAGE reached with 0 operator resets / 0 escalations.

## v2.0.0-alpha4 — 2026-10-05 · Phase 1 (independent reviewer) · contract cf/1.1
### Added
- Deterministic visual audit in the doodle engine (`Timeline.audit`): per element after actor + camera transforms —
  off-canvas, cropped / off-screen labels, meaning-changing crops (lost negation), small text, overhangs (lines past
  the shape they sit on), `data-inside` containment, first-frame hook stats, label list; writes visual_audit.json.
- VIDEO gate: VID.MEANING_CROPPED, VID.CONTAINMENT (blocking), VID.TEXT_CROPPED, VID.OFF_CANVAS, VID.OVERHANG,
  VID.MIX_BALANCE (major), VID.TEXT_SMALL (minor); mix_report.json (music under voice, SFX density).
- `review_packet.py` (authoring/review data boundary) and `reviewer.py` (separate process, hash-verified packet access,
  boundary log, 11-dimension rubric with evidence + explanations, objective checks, critical caps, heuristic /
  anthropic / subagent / external judges, `review-policy.json`, repair routes per dimension).
- `qa_video.py finalize --independent` folds the review into the QA envelope (REV.* checks; no self-review carried).
- factory: automatic independent review in the media chain, `--review-backend`, review task for subagent/human,
  boundary events in state.json, `media --steps N`, REGEN.FUTILE_RETRY guard for deterministic stages.
- Tests: visual audit (9), reviewer (9, incl. mock Anthropic API + subagent flow), futile retry (4), bad videos (3
  rendered fixtures), factory review integration (2).
### Fixed during Phase 1
- Media loop stopped at `review` instead of running the automatic reviewer (integration test).
- Reviewer false positives found on extra real videos: line-art first frame read as blank; missing visual events on
  non-doodle videos read as a static picture (now measured by ffmpeg scene detection).
- Heuristic measurement bugs: negation regex ("aren't"), hook window, stemming; equal-weight scoring too lenient →
  critical caps.
### Verified
- Phase 0 video: FAIL, hook 3/5 ("frame 0 shows 1 element, no on-screen text"), all other dimensions ≥ 3, routed to
  VISUAL_PLAN first scene — through the real factory media chain (reviewer pid ≠ factory, authoring modules loaded: none).
- Bad fixtures A (crop/meaning), B (hook), C (pacing/audio/subtitles/ending) rejected for the intended reasons.
### Limits
- No LLM judge was exercised against a real model (no API key / Agent tool in the build sandbox); the anthropic
  backend is verified against a mock server only. Heuristic taste scores are capped at 4.

## v2.0.0-alpha3 — 2026-10-05 · Phase 0 (reproducible baseline) · contract cf/1.1
### Added
- Sentence-level TTS cache (`tts.py`): key = model/version/files, voice, speed, language, exact text after lexicon,
  word tokens; assembly (gaps, lead, tail) applied after the cache; atomic writes; damaged entries rejected; `--no-cache`.
- Stage order: AUDIO before VISUAL_PLAN (all 15 cf_common copies). Media chain pauses for VISUAL_PLAN; the
  VISUAL_PLAN gate plans word cues against the real narration (`--timing`); a VISUAL_PLAN fix keeps AUDIO.
- Instrumentation: per-stage wall time (from first task issue), gate time, failed checks per attempt and cache stats are
  stored in each event; `factory.py report` writes report.json/.md (records, failures, escalations, human resets).
- `replay_run.py`: re-runs a brief through every gate with the source run's authored inputs; reuses the vision review
  only for a byte-identical final.mp4; writes an artifact-hash comparison.
- Tests: cf_common identity, TTS cache (real Kokoro), stage order, Phase 0 regressions.
### Fixed (found by the Phase 0 end-to-end run)
- AUDIO.TIMING_MONOTONIC: last word of a sentence could end after its trimmed audio → word ends clamped (v1 bug).
- `speed_up` fix route could be a no-op (speed 1.0) → always steps ≥ +3 %.
- Numeric word cues (`w:2013`) were read as word indexes → spoken words match first.
- Report counted QA check + review records as retries → counts failures.
### Verified
- Fresh topic "Why your fingers wrinkle in water" reached PACKAGE; replay: final.mp4, voice, captions, cover,
  metadata, credits byte-identical; AUDIO 13/13 cache hits; 0 escalations, 0 human resets.

## 2.0.0-alpha2 — 2026-10-04 (contract cf/1.1)
Base: the installed plugin skills (contract cf/1.0). The `v2.0.0-alpha1` checkpoint and the V2 toast video were not
present in this workspace (sandbox, uploads, outputs, Google Drive), so this release is NOT built on alpha1. If alpha1
contains changes to the same files, merge it by hand — this checkpoint does not overwrite or replace it.

### New: v2 doodle video engine (video-production)
- `doodle_engine.py`: SVG scenes + `data-*` cues → hand-drawn animation. Marker wobble that boils at 10 fps, offset
  marker fills and hatching, entrances (draw/pop/write/slide/drop/grow/spin/fade) cued on narration WORDS, idle loops,
  exits, camera drift/punch-in/shake, page transitions (whip, whip-up, paper, pop, flash, fade), paper grain. Frames
  are piped straight into x264 (≈40 ms/frame; 30.8 s video renders in ≈60 s on one vCPU — v1 took 137 s).
- `doodle_lib.py`: recurring stick-figure mascot (14 poses × 12 faces, accessories) + ~30 props.
- `audio_design.py`: procedurally synthesised SFX placed on animation events; seeded playful music bed (key, tempo,
  progression, pattern vary per video); speech ducking. Everything self-generated (licence-free).
- New VIDEO gates: VID.DECODE_OK, VID.MOTION_GAP, VID.EMPTY_FRAMES, VID.FIRST_FRAME, VID.SCENE_LINT, VID.NO_TIMING.

### Changed
- visual-storyboarding: `doodle` backend (preview stills + lint), gates VIS.CUE_WORDS / DOODLE_ACTORS / HOOK_AT_ZERO /
  DOODLE_LINT, retime no longer splits doodle scenes; new `references/doodle-scene-guide.md`.
- subtitle-production: `doodle` caption style (Permanent Marker ink, yellow marker swipe on the spoken word, tilt),
  `auto` style (default), metric-calibrated sizing, SUB.DECODE_OK.
- video-quality-assurance: QA.DECODE_OK; OCR is polarity-aware (dark-ink captions).
- content-factory: `--visual-style doodle|illustrated` (default doodle), `--caption-style auto` default, VIDEO receives
  `--timing`, VISUAL_PLAN tasks carry `brief_hint`; doctor reports `visual.doodle`; setup installs skia-python,
  svgelements, arabic-reshaper, python-bidi; `tests/smoke_v2.py`.
- asset-provenance: SFX credited in CREDITS.txt.
- cf_common (all 15 copies, byte-identical): contract cf/1.1 — storyboard `kind: doodle`, transitions whip/whip-up/
  paper/pop/flash/auto, `motion` optional, `decode_errors()` helper. cf/1.0 artifacts remain valid.

### Fixed (found by testing this release)
- A corrupted final.mp4 passed SUBTITLES (BURNED_IN only samples frames) → full-decode gates in VIDEO/SUBTITLES/QA.
- `data-in="none"` without a cue started 0.3 s late → hook subject missing from frame 0.
- Incoming scenes slid in as blank pages → t=0 entrances now start with the transition.
- Doodle captions rendered ~30 % smaller than intended (libass vs PIL metrics) → calibrated.

### Backward compatibility
v1 path (illustrated stills, Ken Burns, karaoke captions) regression-tested end-to-end on the same script: all gates
pass. `--music pad` keeps the v1 drone; `procedural` is now the playful bed.

### Known limits / next
- A VISUAL_PLAN fix also marks AUDIO stale (pre-existing ordering) → TTS reruns unnecessarily (~40 s).
- Doodle captions are Latin-script only (RTL falls back to karaoke); project language is English for now.
- Music/SFX were checked by levels and loudness gates, not by ear — listen before publishing.

### Verified (2026-10-04, 1 vCPU sandbox)
- Demo "Why you can't tickle yourself" (English, 30.8 s, 7 doodle scenes): VISUAL_PLAN, VIDEO, SUBTITLES, QA
  (17 automatic checks + 7-item vision review, claims checked against Blakemore et al. 1999/2000) and provenance passed.
- v1 regression on the same script (Ken Burns + karaoke): all gates passed.
- `tests/smoke_v2.py` passes (≈45 s), including the corrupted-file negative test.
- `factory.py` routing unit-tested: VID.EMPTY_FRAMES → VISUAL_PLAN `add_entrances`, downstream stages marked stale.

### Known limits
- A VISUAL_PLAN fix marks AUDIO stale, so TTS re-runs unnecessarily (inherited v1 stage order).
- Doodle captions are Latin-script; RTL text falls back to karaoke + Vazirmatn. Project language is English for now.
- Not yet exercised as a full multi-video `factory.py` batch (RESEARCH → PACKAGE) end to end.
