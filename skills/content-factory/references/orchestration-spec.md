# Orchestration specification (contract cf/1.0)

How the 16 factory skills pass structured data, gate every stage and regenerate instead of propagating bad output.
Implemented by `scripts/factory.py` + `scripts/cf_common.py`; schemas exported in `../schemas/`.

## 1. Principles
1. **File-based artifact bus.** Each stage reads canonical paths and writes canonical paths inside one run folder.
2. **Every stage ends in a gate** that writes a `result.json` envelope. Downstream never starts on a failed gate.
3. **Failures are data.** Each failed check is a structured error with a `fix_route` naming the stage to redo.
4. **Deterministic where possible.** LLM work (research, ideas, hooks, scripts, storyboards, translation, vision
   review) is always followed by a deterministic checker; media stages are fully scripted.
5. **Capabilities are probed, never assumed** (`doctor.py` → `capabilities.json`, used by SELECTION and LOCALIZE).
6. **Autonomy ends at FINAL PACKAGE.** Publishing, license confirmations and escalations are human decisions.

## 2. Stages
| # | Stage | Owner skill | Writes (under RUN/) | Gate | Typical fix routes |
|---|---|---|---|---|---|
| 1 | RESEARCH | content-research (+ trend-intelligence, advisory) | research/dossier.json, trends.json | dossier_tool.py validate | RESEARCH corroborate / paraphrase / expand |
| 2 | IDEATION | content-strategy | ideation/ideas.json | select_ideas.py validate | IDEATION expand / diversify / dedupe |
| 3 | SELECTION | content-strategy | selection/selection.json | select_ideas.py select | IDEATION expand |
| 4 | HOOK | hook-engineering | videos/V/hook/hooks.json | hook_lint.py | HOOK regenerate / diversify |
| 5 | SCRIPT | short-form-script | videos/V/script/script.json | script_lint.py | SCRIPT shorten / link_claims / use_chosen_hook |
| 5b | LOCALIZE | multilingual-content | videos/V-lang/script/script.json | ml_check.py | LOCALIZE condense / fix_numbers; AUDIO switch_backend |
| 6 | VISUAL_PLAN | visual-storyboarding | videos/V/visual/storyboard.json (+svg; doodle scenes by default) | storyboard_tool.py render | VISUAL_PLAN rerender / add_scenes / remap_beats / repair_cues / add_entrances / redesign_scene |
| 7 | AUDIO | voice-production | videos/V/audio/voice.wav, timing.json | tts.py synth | AUDIO speed_up / resynthesize; SCRIPT shorten |
| 8 | VIDEO | video-production | videos/V/video/video_nosubs.mp4 | render_video.py (doodle or Ken Burns engine) | VIDEO remix / rerender; retime (max_shot); VISUAL_PLAN add_entrances / redesign_scene |
| 9 | SUBTITLES | subtitle-production | videos/V/subtitles/final.mp4, captions.* | subtitles.py run | SUBTITLES rebuild (font_scale, max_words, font, y) / reburn |
| 10 | QA | video-quality-assurance | videos/V/qa/qa_report.json, review.json | qa_video.py check → finalize | any upstream stage |
| 11 | REGENERATION | content-factory | state.json events | budget check in factory.py | escalate when exhausted |
| 12 | PACKAGE | content-factory + asset-provenance | package/V/* , *_package.zip | package_run.py (+ provenance.py) | QA complete_review; VISUAL_PLAN replace_assets; SCRIPT retitle |
| 13 | ANALYTICS | content-analytics (+ content-database) | feedback.json → factory.db weights | analytics.py analyze | ANALYTICS map_ids / map_columns |

Stages 1–3 run once per batch; 4–12 run per video unit; 13 runs after the user publishes.

## 3. Run folder
```
RUN/ run.json  state.json  capabilities.json  history.json?  weights.json?  licenses.json?
     research/  dossier.json dossier.scored.json signals.json? trends.json? result.json
     ideation/  ideas.json result.json          selection/ selection.json result.json
     videos/<V>/ hook/ script/ localize/ visual/{svg,assets} audio/ video/{work} subtitles/ qa/   (each with result.json)
     package/<V>/ final.mp4 cover.jpg captions.srt captions.vtt metadata.json provenance.json CREDITS.txt qa_report.json result.json
     package/run_summary.md  package/checksums.sha256   <run>_package.zip
```
Video ids: `v01…vNN` (rank order); language variants `v01-it`, `v01-fa` reuse the source's visuals.

## 4. Envelope (`result.json`, schema `stage_result`)
```json
{"contract": "cf/1.0", "stage": "SUBTITLES", "skill": "subtitle-production", "run_id": null, "video_id": "v01",
 "attempt": 2, "status": "failed", "started_at": "…", "finished_at": "…",
 "inputs":  [{"role": "voice_timing", "path": "…", "sha256": "…"}],
 "outputs": [{"role": "final_video", "path": "…", "media_type": "video/mp4", "sha256": "…"}],
 "gate": {"passed": false, "checks": [{"id": "SUB.BURNED_IN", "passed": false, "severity": "blocking", "value": [12, 30, 7], "threshold": ">=40 per probe", "message": "…"}]},
 "errors": [{"code": "SUB.BURNED_IN", "severity": "blocking", "message": "…", "evidence": {"value": [12, 30, 7], "threshold": ">=40 per probe"},
             "retryable": true, "fix_route": {"stage": "SUBTITLES", "action": "reburn", "params": {}}}],
 "metrics": {"chunks": 34}, "provenance": [{"role": "font", "path": "…", "license": "OFL-1.1", "source": "…"}]}
```
- **status**: `passed` · `passed_with_warnings` (only minor failures) · `failed` (any blocking/major) · `error` (crash, converted by `stage_main`) · `pending_review` (QA awaiting vision review).
- **severity**: `blocking` (output unusable) · `major` (must be fixed or escalated) · `minor` (logged, shipped).
- **exit codes**: 0 passed, 2 gate failed, 3 awaiting review, 1 crashed (an `error` envelope is still written).
- Artifact schemas (`brief, research_dossier, trend_report, ideas, hooks, script, storyboard, voice_timing, qa_report, provenance`) are validated by the stage that consumes them, so a malformed hand-off fails at the boundary with `*.SCHEMA` errors.

## 5. Control loop
```
factory.py next   → do_stage | run_media | review | done | escalated
agent             → (load skill) write files → run gate → factory.py record
factory.py record → proceed | review | rerun{stage, fix_action, params} | escalate{errors}
factory.py media  → AUDIO → retime+VIDEO → SUBTITLES → QA check, looping on deterministic reruns
```
Deterministic reruns handled inside `media`: AUDIO speed_up/resynthesize, VIDEO remix/rerender/retime(max_shot),
SUBTITLES rebuild/reburn. Anything that needs judgement (SCRIPT, VISUAL_PLAN redesign, RESEARCH) returns to the agent.

## 6. Regeneration algorithm
```
on failed envelope E for stage S (video V):
  C = errors with severity blocking|major (else all)
  if any has fix_route: R = the route whose stage is EARLIEST in pipeline order   # fix causes upstream first
  elif E.status == error or any retryable: R = (S, retry)
  else: escalate(E)
  if R = (VISUAL_PLAN, retime): R = (VIDEO, {max_shot})       # deterministic re-cut
  if R = (QA, complete_review): reopen review
  if attempts[R.stage] ≥ 3 or regenerations[V] ≥ 8: escalate(E)
  state[R.stage] = pending with fix_params = R.params + {action}
  every later stage of the same scope (that is not skipped) = stale
  regenerations[V] += 1; log REGENERATION event
```
Escalation freezes only that video; others continue. `factory.py reset --stage … --note …` is the audited human
override after fixing a root cause (fresh retry budget for the stage and, since v3.0.0, for every later stage, which
becomes stale). `factory.py unlock --run … --note …` is the audited override for a held run lock.

## 7. Human checkpoints
Publishing/uploads · escalated videos · `PROV.MODEL_LICENSE` · YouTube audience ("made for kids") · providing any credential.

## 8. Analytics feedback
User publishes → `cfdb.py publish` (ids) → exports CSV → `analytics.py analyze` → `cfdb.py log-feedback` → next
`factory.py init --db` writes `weights.json` + `history.json` → SELECTION multiplies format/pillar weights,
HOOK multiplies archetype weights, novelty filter uses history. Weights are bounded to 0.5–2.0 and shrunk toward 1
for small samples.

## 9. Worked example — "Create 5 high-quality short videos on TOPIC"
1. content-factory triggers → setup_env (≈1 min) → `init --count 5`.
2. RESEARCH: 6–10 searches → ≥10 facts → gate. Optional trends.
3. IDEATION ≥10 ideas → SELECTION picks 5 varied ones (v01…v05).
4. Per video: hooks (4–6) → script (≈80–110 words) → storyboard + SVG scenes → `media` (≈4 min) → vision review.
5. `package --zip` → present zip + MP4s → ingest + export dump.json.
Expected wall time on a 1-vCPU sandbox: ≈35–50 min for five 30-second videos, dominated by rendering.

## 10. Extending
New backend = new function in the owning script + a `capabilities.json` probe in `doctor.py` + provenance record.
New stage = add to `STAGES`/`STAGE_OWNER` in cf_common.py, a gate script that writes the envelope, and a row here.


## v2 gate additions (contract cf/1.1)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| VIS.CUE_WORDS | VISUAL_PLAN | major | VISUAL_PLAN repair_cues |
| VIS.DOODLE_ACTORS · VIS.HOOK_AT_ZERO | VISUAL_PLAN | major | VISUAL_PLAN add_entrances · redesign_scene(first) |
| VIS.DOODLE_LINT | VISUAL_PLAN | minor | VISUAL_PLAN repair_scene |
| VID.DECODE_OK · VID.NO_TIMING | VIDEO | blocking | VIDEO rerender · AUDIO resynthesize |
| VID.MOTION_GAP · VID.EMPTY_FRAMES · VID.FIRST_FRAME | VIDEO | major | VISUAL_PLAN add_entrances / redesign_scene |
| VID.SCENE_LINT | VIDEO | minor | VISUAL_PLAN repair_scene |
| SUB.DECODE_OK · QA.DECODE_OK | SUBTITLES · QA | blocking | SUBTITLES reburn |
Full-decode checks exist because sampled-frame gates (BURNED_IN) passed a corrupted final.mp4 in testing.

## Phase 1 additions (v2.0.0-alpha4)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| VID.MEANING_CROPPED · VID.CONTAINMENT | VIDEO | blocking | VISUAL_PLAN repair_scene (with the cropped words / element) |
| VID.TEXT_CROPPED · VID.OFF_CANVAS · VID.OVERHANG · VID.MIX_BALANCE | VIDEO | major | VISUAL_PLAN repair_scene · VIDEO remix |
| VID.TEXT_SMALL | VIDEO | minor | VISUAL_PLAN repair_scene |
| REV.<DIMENSION> (11 rubric dimensions) · REV.AUDIT.* · REV.FIRST_FRAME.BLANK · REV.TITLE.FORMAT | QA | major/blocking | per review-rubric.md |
| REV.REVIEWER_ERROR | QA | blocking | QA retry |
| REGEN.FUTILE_RETRY | any deterministic stage (AUDIO, VIDEO, SUBTITLES) | escalation | a self-retry with identical inputs + parameters is refused; fix the cause and reset |

## Phase 2 additions (v2.0.0-alpha5)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| HOOK.SCHEMA · HOOK.FRAME0_RENDERED · HOOK.SELECTED | HOOK | blocking | HOOK repair_schema / repair_frames / regenerate (strategy=change, per-candidate reasons) |
| HOOK.DIVERSITY | HOOK | major | HOOK regenerate (diversify) |
| HOOK.FUTILE_RESUBMISSION | HOOK | blocking | none → escalation (identical failed candidates) |
| SCRIPT.SCHEMA · SCRIPT.SELECTED | SCRIPT | blocking | SCRIPT repair_schema / regenerate (per-variant reasons) |
| SCRIPT.VARIANTS_DISTINCT | SCRIPT | major | SCRIPT regenerate (make_distinct) |
| VIS.OPENING | VISUAL_PLAN | major | VISUAL_PLAN redesign_scene first (with the opening brief) |
| VID.FIRST_FRAME_SUBJECT · VID.HOOK_TEXT_T0 · VID.FIRST_EVENT | VIDEO | major (subject: minor with documented exception) | VISUAL_PLAN redesign_scene / add_entrances |
New runs carry `hook_engine: v2` in the brief; older runs keep the v1 hook/script lint.

## Phase 3 additions (v2.0.0-alpha6)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| VIS.LAYOUT_REPEAT · VIS.SUBJECT_REPEAT · VIS.DEAD_SPACE · VIS.OPENING_DENSITY | VISUAL_PLAN | major | VISUAL_PLAN vary_layouts / vary_subjects / fill_space / add_entrances |
| VIS.SUBJECT_SIZE | VISUAL_PLAN | major (<18 %) / minor (18-25 %) | VISUAL_PLAN enlarge_subject |
| VID.MIX_BALANCE (16-18 dB) · VID.SFX_DENSITY · VID.SPEECH_MASKING · VID.CLEAN_ENDING | VIDEO | major | VIDEO remix (music_carve_db / music_under_voice_db / sfx_max_rate) |
| VID.OPENING_DENSITY · VID.PACING_CADENCE · VID.LOOP_ENDING | VIDEO | major | VISUAL_PLAN add_entrances / redesign_scene |
| OUT_OF_ORDER | factory record | refusal | record only results whose upstream stages are done |
VIDEO fix-route audio parameters now reach render_video (media_cmds pass-through).

## Phase 3.5 additions (v2.0.0-alpha7)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| CTA.SCHEMA · CTA.NOT_IN_HOOK · CTA.AFTER_PAYOFF · CTA.ENDING · CTA.STANDALONE_ENDING | SCRIPT (estimate) / VIDEO as VID.CTA_* (actual) | blocking | SCRIPT revise_cta |
| CTA.SINGLE · CTA.DURATION · CTA.SHORT_VIDEO · CTA.RELEVANCE · CTA.NOT_REPEATED · CTA.DECIDED | SCRIPT / VIDEO | major | SCRIPT revise_cta |
| CTA.ON_SCREEN_SHOWN | VIDEO | major | VISUAL_PLAN revise_cta |
| REV.CTA_* (4 dimensions, CTA present only) | QA | major | SCRIPT revise_cta |
| PKG.MEDIA_METADATA_CLEAN · PKG.FINAL_DECODES · PKG.DISCLOSURE | PACKAGE | blocking | PACKAGE retry / VIDEO rerender |
New runs carry `cta_engine: v1` (a CTA decision is required); older runs replay unchanged. cta_history.json (runs
directory) records the CTAs of packaged videos.

## Phase 5 additions (v3.0.0 — final)
| Code | Stage | Severity | Fix route |
|---|---|---|---|
| CAPABILITY_MISSING | factory init | refusal (no run created) | install what doctor's `fix` names (e.g. apt libegl1), rerun setup_env |
| TOPIC_REPEATED | factory init | refusal (no run created) | new topic, or `--allow-similar-topic REASON` (recorded in brief.memory and an INIT event) |
| MEMORY_FAILED | factory init | refusal | fix the database path/permissions; `--no-db` only for tests |
| LOCKED | any mutating command | refusal | wait; a dead holder's lock is taken over automatically; `unlock --note` (audited) |
| STALE_RESULT | factory record | refusal | the envelope was already recorded; run the stage again |
| INTERNAL.NO_RESULT | media chain | blocking (error envelope) | the stage wrote no (or an old) result.json; rerun |
| HOOK.NOT_REPEATED | HOOK | minor (candidate not selectable) | HOOK regenerate with a new strategy |
| VIS.DOODLE_FALLBACK | VISUAL_PLAN (rendered) | major | VISUAL_PLAN repair_scene (or install the doodle engine) |
Memory is on by default: `init` checks the topic, the HOOK gate gets `--history`, `package` ingests the run. A reviewer
judgment may add `fix_stage` (HOOK | VISUAL_PLAN) to `hook_strength`; the route follows it. The SCRIPT and VIDEO gates
see the CTAs of other videos only (`videos/<v>/cta_history.others.json`).
