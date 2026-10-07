# PHASE 1 REPORT — Independent reviewer · v2.0.0-alpha4 · 2026-10-05

**Status: PASS WITH LIMITATIONS.** The independent review layer is implemented, integrated in the factory and
verified on real and intentionally bad videos. Limitation: no LLM judge was run against a real model (the build
sandbox has no API key and no Agent tool); the anthropic backend is verified against a mock server, the subagent
backend through its file protocol. Heuristic taste scores are capped at 4.

## Architecture
author stages → finished artifacts → `review_packet.py` (boundary: allow-list, refuses storyboards/SVG/hooks/beat
structure/state/earlier reviews, strips the author's self-review, sha256 manifest) → `reviewer.py` (separate process,
hash-verified reads, boundary_log.json) → `qa_video.py finalize --independent` → QA envelope (REV.* checks with
repair routes) → factory routing. Deterministic inputs to the reviewer come from the engine's visual audit and the
mix report, both computed during VIDEO.

## Gate
Objective blocking/major ⇒ FAIL; any dimension < 3; overall < 4; hook < 4; first frame < 4; visual/verbal sync < 4;
ending < 3 (the suggested policy, unchanged). Rubric and anchors: video-quality-assurance/references/review-rubric.md.

## Results
| video | verdict | weakest dimensions (score) | objective failures |
|---|---|---|---|
| Phase 0 video (real factory integration) | FAIL | hook 3 — "frame 0 shows 1 element, no on-screen text"; cover 3 | none |
| Tickle demo (second real video) | FAIL | hook 2, first frame 3, cover 2 | none |
| v1 Ken Burns (same tickle art) | FAIL | hook 2, first frame 2, pacing 3 | none |
| Fixture A — crop / meaning reversal / overhang | FAIL | sync 2, overall 1 | AUDIT.MEANING_CROPPED, AUDIT.TEXT_CROPPED, AUDIT.OVERHANG |
| Fixture B — weak, confusing hook | FAIL | hook 1, first frame 1, pacing 2 | FIRST_FRAME.BLANK, QA.HOOK_CAPTION |
| Fixture C — pacing / audio / subtitles / ending | FAIL | pacing 2, audio 2, ending 2, message 2, subtitles 3 | — |
The three real Phase 0 defects (wrinkle overshoot, cropped label, "NOT WATER" read as "WATER") are each detected by
the audit; the corrected Phase 0 scenes produce zero major findings.

## Independence proof (real run, runs_replay/…/qa/independent_review/boundary_log.json)
reviewer pid 329 (factory pid 180) · 10 hash-verified packet files read · 0 refused · authoring modules loaded: none ·
packet manifest sha256 994cd654c917870e…; factory event `boundary: independent_review` recorded in state.json.
Unit tests prove refusal of authoring inputs, of files outside the manifest, of tampered files and of path traversal,
and that no beat structure or self-review reaches the packet or an LLM request.

## Bugs found and fixed during Phase 1 (by tests and extra real videos)
media loop skipped the automatic reviewer · line-art first frame judged blank · non-doodle videos judged static (no
event data) · negation regex · hook window · stemming · equal-weight scoring too lenient (→ critical caps) ·
decorator misplacement in qa_video · fixture C voice louder than real speech (fixture bug, measurement was right).

## Tests (all passing)
unit: cf_common identity 1 · stage order 3 · Phase 0 regressions 4 · TTS cache 1 · visual audit 9 · reviewer 9 ·
futile retry 4 · bad videos 3 (rendered) · factory review integration 2 · smoke_v2 · v1 regression (render, subtitles,
review) · real factory run (VIDEO → SUBTITLES → QA → independent review → routed to VISUAL_PLAN).

## Not done in Phase 1 (by scope)
The Phase 0 video is not fixed: its weak visual hook is Phase 2 work (run left at VISUAL_PLAN pending).
A real-model LLM judgment has not been calibrated against the heuristic.
