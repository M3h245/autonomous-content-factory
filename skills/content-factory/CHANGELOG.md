# Changelog — Autonomous Content Factory

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
