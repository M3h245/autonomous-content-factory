# PHASE 2 REPORT — Hook + Script · v2.0.0-alpha5 · 2026-10-05

**Status: PASS** (all 12 acceptance gates met; reviewer thresholds unchanged). Limitation carried from Phase 1: the
independent reviewer runs its deterministic heuristic judge here (no API key / Agent tool in the build sandbox).

## What was built
- **Hook Engine** (`hook-engineering/scripts/hook_engine.py`): ≥5 multi-channel candidates (contract `hook_candidates`,
  each with a frame-0 doodle SVG) → diversity gate → real frame-0 and t=1 s renders → deterministic frame-0
  measurements → one packet per candidate (no author reasoning) → `reviewer.py review-hooks` → strongest candidate with
  hook, first frame and coherence ≥ 4, or a structured HOOK.SELECTED failure listing every candidate's reasons;
  identical failed candidates are never re-scored (HOOK.FUTILE_RESUBMISSION → escalation) → `opening_brief.json`.
- **Script variants** (`short-form-script/scripts/script_select.py`): two complete variants (contract `script_variants`),
  hook-is-opening + promise-paid (blocking), traceable claims, no generic intro, explanation by 8 s, no mid-script hook
  repeat, duration window, visual intent, sparse pauses, structural distinctness; `review-script` (clarity, pacing,
  payoff coherence, hook ≥ 4) → script.json + opening brief update.
- **Duration** (`voice-production/scripts/estimate.py`): syllable/word/comma/question model fitted on 40 real Kokoro
  sentences; mirrors the TTS assembly.
- **Pauses**: `pause_before`/`pause_after` applied at assembly (no re-synthesis), recorded, excluded from dead-air checks.
- **Frame-0 gates**: VIS.OPENING (VISUAL_PLAN), VID.FIRST_FRAME_SUBJECT / VID.HOOK_TEXT_T0 / VID.FIRST_EVENT (VIDEO).
- **Visual Plan interface**: opening_brief.json (subject, size target, composition, first-frame state, on-screen text,
  spoken line, visual action, emphasis words, camera intent, safe margin, frame-0 SVG, `visual_mode` + future modes).

## Results
| item | result |
|---|---|
| Hook candidates (real run) | h1 misconception reversal 4/5/5 · h2 visual mystery 4/5/5 · h3 direct challenge 4/5/4 · h4 curiosity gap 4/5/4 · h5 surprising claim 4/5/5 (hook / first frame / coherence), all PASS |
| Selected hook | h1 "Pruney fingers? Not water. Nerves." — frame 0: huge wrinkled finger in water (35 % height), glowing nerve, water drop crossed out at 0.15 s, "NOT WATER" |
| Script variants | A myth-bust → mechanism → debate, 33.7 s, 4/4/4/4 · B mechanism-first, 23.7 s, 4/4/4/4; B selected (tie → shorter) |
| Duration estimate | held-out: wrinkle −1.6 % / −2.8 %, tickle +4.4 % (old −17 … −18 %, −8.5 %); real run −1.5 % (23.69 vs 24.05 s) |
| Pause | 0.4 s pause before the payoff measured in timing and audio; changing a pause re-synthesises nothing |
| Wrinkle video (factory: RESEARCH → PACKAGE) | full Phase 1 reviewer gate PASS: hook 3 → 4, first frame 4 → 5, cover 3 → 4, all ≥ 4; 0 operator resets, 0 escalations, 1 retry (reviewer bug, fixed); re-render byte-identical |

## Bugs found and fixed
nested `data-in="none"` staggered (frame 0 lost wrinkles/nerve) · estimator read "2013," as a thousands number
(recalibrated, MAE 0.19 → 0.16 s) · reviewer treated 0.0 as missing (label at 0.0 s, crop at 0.0 s, 0.0 dBTP peak) ·
"30 MIN" ≠ "thirty minutes" · hook score inconsistent between stages · packet boundary regex too broad · smoke
fixture brought up to the new frame-0 contract (gate not loosened).

## Tests
Phase 2: hooks 10 (A strong, B empty, C tiny + exception, D cropped text, E hidden negation, F weak verbal, G
unsupported promise, L/M/N selection · failure · no blind retry, boundary, diversity) · script 7 (G promise, H mismatch,
I duration vs real TTS, J pause in audio, K distinct, selection, numbers). Phase 0/1: identity, stage order, Phase 0
regressions, TTS cache, visual audit 9, reviewer 10, futile retry 4, bad videos 3, factory review 2, smoke, v1 — all green.

## Remaining (not Phase 2 scope)
Real-model LLM judge calibration · visual variety (the finger repeats across scenes) · only one visual event in the
first 1.5 s of the wrinkle video (kept visible in the reviewer evidence) · designed cover (Phase 4).
Note: the run report's "first issue → last event" (32,946 s) includes waiting between conversation turns; stage
wall time was 546.6 s.
