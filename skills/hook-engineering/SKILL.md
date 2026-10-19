---
name: hook-engineering
description: Writes and stress-tests the first 1–3 seconds of short-form videos — spoken hook, on-screen text and visual hook — across distinct archetypes (contradiction, curiosity gap, stakes, specific number, myth-bust, question, POV and more), then lints them for spoken length, throat-clearing openers and misleading clickbait and chooses the strongest. Use for "write hooks for…", "make the opening stronger", "why are viewers swiping away", A/B hook variants, or the content factory HOOK stage. Not for full scripts (short-form-script) or standalone titles and thumbnails.
---

# Hook Engineering

**Stage:** HOOK · **Error codes:** `HOOK.*` · **Gate:** `scripts/hook_lint.py`

## Activation
Every factory video; any request about openings, retention in the first seconds, or hook variants.

## Responsibilities
A hook is a promise the video keeps: specific, tension-creating, true. It is three layers at once — what is said,
what is written on screen, what is seen in frame one.

## Inputs → outputs
| In | Out |
|---|---|
| selected idea (selection.json), dossier facts, `weights.json` (archetype multipliers) | `videos/<vid>/hook/hooks.json` → `hooks.scored.json` (ranked, `chosen_id`), `result.json` |

## Workflow
1. Write 4–6 candidates using ≥3 archetypes from `references/hook-archetypes.md`; each with `spoken` (≤9 words in
   English ≈ 3 s), `on_screen` (≤6 words, adds information rather than repeating), `visual` (concrete first frame).
2. Anchor every hook in a dossier fact — no promise the script cannot pay off.
3. Optionally set `chosen_id`; run the gate; the script uses the chosen hook verbatim as beat 1.

## Phase 2 Hook Engine (factory default for new runs, `hook_engine: v2`)
A hook is verbal + visual + on-screen + tension + immediate topic signal. Write `videos/<v>/hook/hooks.json` with the
`hook_candidates` contract: **≥5 substantially different candidates** (≥4 distinct `curiosity_mechanism`s such as
misconception reversal, visual mystery, surprising claim, curiosity gap, direct challenge, question — choose what fits
the topic), each with hook_id, spoken_text, visual_concept, on_screen_text, curiosity_mechanism, tension,
target_emotion, first_frame_concept, first_frame_subject, first_frame_text, visual_action, payoff_connection,
why_it_should_work, fact_ids (dossier facts the hook promises) and `first_frame_svg` — a doodle SVG of frame 0
(`videos/<v>/hook/svg/<id>_frame0.svg`, same authoring rules as doodle scenes).
Frame-0 rules (measured, not trusted): main subject visible at t=0 and ≥35 % of frame height (or declare
`<svg data-hook-exception="why">`); ≥2 elements; short on-screen text (1-6 words, ≥60 px, inside the 5 % safe area)
that reinforces — not repeats — the line; no hidden negation; a visual event within 0.5 s (or idle motion);
spoken hook ≤3.2 s (calibrated estimate). Details that must stay inside a shape: `data-inside="#id"`.
Gate: `hook_engine.py select` renders frame 0 and t=1 s, measures them, sends each candidate to the independent
reviewer (`reviewer.py review-hooks`; author reasoning such as why_it_should_work never reaches it) and selects the
strongest candidate with hook_strength, first_frame_clarity and visual/verbal coherence ≥ 4. Outputs
hooks.scored.json, selected_hook.json, opening_brief.json (Visual Plan interface), hook_report.md.
Failures: HOOK.DIVERSITY (rewrite the set), HOOK.SELECTED (no candidate passes — params list every candidate's
reasons; change strategy), HOOK.FUTILE_RESUBMISSION (identical failed candidates resubmitted → escalation).
`hook_lint.py` remains for v1 runs.

Phase 3: each candidate's spoken line is synthesised with the real voice (sentence cache — the AUDIO stage later
reuses it) and judged on its measured length; the calibrated estimate under-predicted short hooks by ~0.45 s.

### Learning (v3.1.0)
`hook_engine.py select … --learning run/learning.json` (passed by factory.py when the run has one) adds a bounded bonus
(at most ±1.5 review points, ±0.5 at low confidence) for the opening form and curiosity mechanism that the evidence
favours. It applies **only to candidates that passed the independent review**. The engine records the choice without
learning, the bonuses and whether the choice changed. HOOK.LEARNING_COVERAGE (minor) asks for at least one candidate
in each evidence-preferred or tested level.

## Quality gate
HOOK.SCHEMA (≥3 candidates) and HOOK.SELECTABLE (a candidate passes the hard rules) are blocking;
HOOK.ARCHETYPE_VARIETY is major; HOOK.STRENGTH (score ≥ 65) is minor.
Hard rules: spoken length ≤ 3.2 s at the language rate; no "hey guys / in this video / did you know" openers;
no misleading clickbait ("you won't believe", "shocking", "guaranteed"…).

## Failure recovery
Regenerate with the reported issues; if every variant is long, cut setup words, lead with the surprising noun.

## Scripts · References
`scripts/hook_lint.py --hooks … --result … [--weights …]` · `references/hook-archetypes.md`

## Dependencies · Interactions
None external. Reads content-analytics weights via content-database; output consumed by short-form-script
(beat 1) and visual-storyboarding (first scene).
