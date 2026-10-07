# Independent review — rubric, anchors and gate (Phase 1, v2.0.0-alpha4)

Anchors for every dimension: **1 unacceptable · 2 weak · 3 acceptable · 4 strong · 5 publish-ready**.
Every score lists its evidence; every score below 4 carries an explanation (the reviewer refuses a judgment without one).

## Boundary
`review_packet.py` builds the only input the reviewer may read: the final video, frames (first frame, 0-3.2 s strip,
16-frame contact sheet, last 2.4 s, the shipped cover), the spoken transcript (words + times, no beat roles), burned
captions, the publish block (title, alternatives, description, hashtags), dossier facts + sources, and deterministic
measurements (technical QA without any self-review, visual audit, mix report, subtitle gate). Storyboards, scene
sources, hook candidates, beat structure, idea/selection files, run state and earlier reviews are refused.
`reviewer.py` runs as its own process, imports no authoring module, opens files only through the hash-verified
manifest and writes `boundary_log.json` (pid, files read, refused paths, authoring modules loaded = []).

## Objective checks (deterministic; blocking/major ⇒ FAIL)
| id | severity | source |
|---|---|---|
| QA.* (decode, spec, loudness, peak, captions, OCR, hook audio…) | as QA | technical QA |
| AUDIT.MEANING_CROPPED — a label loses a negation (e.g. "NOT WATER" → "WATER") | blocking | engine audit, after camera transforms |
| AUDIT.CONTAINMENT — element escapes its `data-inside` container | blocking | engine audit |
| AUDIT.TEXT_CROPPED / TEXT_OFFSCREEN — label partly/fully outside the frame | major | engine audit |
| AUDIT.OFF_CANVAS — settled element outside the frame (punch-ins excepted: minor) | major | engine audit |
| AUDIT.OVERHANG — lines run past the edge of the shape they mostly sit on | major | engine audit |
| FIRST_FRAME.BLANK — nothing on screen at t=0 (audit) / <2 % non-paper (fallback) | blocking | packet |
| TITLE.FORMAT (1-100 chars) · COVER.FORMAT (9:16, ≥720 wide) · TIMING.BEYOND_VIDEO | blocking/major | packet |

## Dimensions (heuristic judge — measurable proxies)
Score = share of proxies met mapped to 1..cap, then capped by critical defects. Taste dimensions are capped at 4 for
the heuristic judge: only an LLM/human judge may award 5 there.
| dimension | proxies | critical caps | heuristic cap |
|---|---|---|---|
| hook_strength | onset ≤0.35 s · first line ≤3.2 s · tension device (negation/contrast/question/number) · ≥2 visual events in 1.5 s · frame 0 has ≥2 elements or text · label by 2 s | 4 requires the frame-0 visual hook | 4 |
| first_frame_clarity | subject extent ≥6 % / ≥10 % (bbox for doodles, pixels otherwise) · ≥2 elements or text · nothing cropped at t=0 | nothing on screen → 1 | 5 |
| message_clarity | 2.0-3.4 w/s · avg sentence ≤16 words · none >24 · dossier with tier-1 source · ending returns to core message | sentence >30 words → 2 | 4 |
| visual_verbal_sync | labels spoken within ±2.5 s · ≥60 % visual events on a word (±0.3 s) · no cropped text · captions in sync | meaning crop → 2 | 5 |
| pacing_retention | no visual gap >3 s · ≥4 events/10 s · duration in window · no speech pause >0.7 s · ≥2.2 w/s · no freeze | gap >6 s → 2, >4.5 s → 3 | 4 |
| audio_balance | −14 ±1.5 LUFS · TP ≤ −1 · music 12-30 dB under voice · SFX ≤1.8/s · SFX near voice ≤25 % · no dropouts | music <8 dB → 1, <12 → 2, <15 → 3; TP > −0.5 → 1 | 4 |
| subtitle_readability | OCR ≥90 % · size ≥80 · p90 chunk ≤24 chars · ≥0.25 s each · fits / no overlap | size <64 → 2, <80 → 3 | 5 |
| ending_quality | visual event in last 3 s · hold ≤1.2 s · tail ≥0.2 s · callback to hook/title · last line ≤12 words | dead air >2.5 s → 2 | 4 |
| title_coherence | ≤70 chars · no clickbait · ≤40 % caps · ≥2 title words spoken · not a verbatim copy of the hook | — | 4 |
| thumbnail_coherence | 9:16 ≥720 · subject ≥8 % · headline in upper 45 % · headline relates to title/video | — | 4 |
| overall_publishability | objective blocking → 1, major → 2; else min(mean, weakest + 1) | — | 4 |
Visual events: the engine's audit list for doodle videos; otherwise ffmpeg scene detection on the final video.

## Judges
`heuristic` (default without a key) · `anthropic` (fresh Messages-API context, only packet content, `ANTHROPIC_API_KEY`,
model `CF_REVIEW_MODEL`) · `subagent` (writes `review_request.md` for a fresh Claude Code agent; merges `judgment.json`)
· `--judgment FILE` (human). Merge: taste dimensions take the LLM score; measurable ones take min(LLM, measurement).

## Gate (`review-policy.json`)
FAIL if any objective blocking/major failure, any dimension < 3, overall < 4, hook < 4, first frame < 4,
visual/verbal sync < 4, or ending < 3. Thresholds are the suggested Phase 1 policy unchanged.
Every failure carries a repair route (hook: HOOK if the spoken hook fails, else VISUAL_PLAN first scene; audio:
VIDEO remix; subtitles: SUBTITLES; pacing/sync/cover/first frame: VISUAL_PLAN; clarity/ending/title: SCRIPT).

## Phase 2 candidate modes (same reviewer, same anchors, `review-policy.json`)
`review-hooks` — per hook candidate packet (frame 0 + t=1 s renders, spoken line, on-screen text, calibrated length,
topic, promised facts, frame-0 measurements; no author reasoning). Objective: FRAME0.BLANK, FRAME0.NEGATION_HIDDEN
(blocking), FRAME0.TEXT_CROPPED/OUTSIDE_SAFE/SMALL, FRAME0.SAFE_MARGIN, FRAME0.SUBJECT_SMALL (unless a documented
exception), FRAME0.NO_EARLY_EVENT, HOOK.TOO_LONG (major), HOOK.UNSUPPORTED_PROMISE (blocking). Dimensions
hook_strength (cap 4; strong needs frame-0 visual, early event and reinforcing text), first_frame_clarity,
visual_verbal_sync; thresholds `hook_thresholds` (all 4).
`review-script` — per variant packet (estimated transcript, public hook, publish, claims, deterministic check results,
the hook-stage scores). Dimensions message_clarity, pacing_retention, payoff_coherence (critical: promise not paid →
2), hook_strength (carries the hook-stage score if the opening is intact); thresholds `script_thresholds` (all 4).

## Phase 3.5 CTA review (only when the video carries a CTA)
Objective (deterministic, from measurements/cta_report.json): every failed CTA.* gate is an objective failure routed to
SCRIPT revise_cta. Judgement dimensions (heuristic, anchors 1-5, `cta_thresholds` all 4): cta_quality (single ask,
action matches type, ≤12 words, no stock outro), cta_naturalness (integrated or a question, tied to the content, not
pushy, brief), cta_relevance (points at the title's subject, shares body words, not stock), cta_retention_risk (5 = no
measurable risk: placement gates pass and the CTA sits in the last quarter). ending_quality adds "ending stands without
the CTA". The packet holds the CTA as the viewer gets it (text/cta.json: type, words, timing) — never decision_reason.
Videos without a CTA report "not applicable" and are judged on the 11 base dimensions only.

## Phase 4 package review (`review-package`)
One packet per package candidate: the finished copy (title, thumbnail text, opening promise, description, hashtags,
caption CTA), the thumbnail at full size and at 168 px, the video's first frame, transcript, video CTA, evidence and the
deterministic package checks. Never the strategy, concept, rationale or SVG. Nine dimensions, `package_thresholds`:
title_strength, curiosity (open loop the video closes), accuracy (an unsupported/contradicted claim caps at 1),
thumbnail_readability, complementarity (thumbnail text repeating the title caps at 2), hook_coherence, promise_payoff
(the title's focus must get ≥20 % airtime; <10 % caps at 3), clickbait_risk (5 = safe), cta_coherence.
`--judgment` merges an external judge (fresh agent or human, packet-only): final score = min(heuristic, judge).
