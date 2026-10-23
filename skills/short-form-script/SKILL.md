---
name: short-form-script
description: Writes beat-structured scripts for 15–90 second vertical videos (hook, setup, value, twist, payoff, loop or CTA) with claim ids linked to the research dossier, on-screen text and publish copy (title options, description, hashtags), then lints spoken duration, claim traceability, filler phrases and platform limits. Use for "write a script for a short, reel or TikTok about X", "turn this article into a 40-second script", "tighten this script", or the content factory SCRIPT stage. Not for long-form YouTube scripts, blog posts, or translation (multilingual-content).
---

# Short-Form Script

**Stage:** SCRIPT · **Error codes:** `SCRIPT.*` · **Gate:** `scripts/script_lint.py`

## Activation
Every factory video after HOOK; any short-form scripting or tightening request.

## Responsibilities
Deliver one idea, fast, provably true, with a satisfying payoff — written for the ear (short sentences, concrete
nouns, numbers said the way people say them).

## Inputs → outputs
| In | Out |
|---|---|
| `hooks.scored.json` (chosen hook), dossier, idea, brief duration window | `videos/<vid>/script/script.json` (schema `script`), `result.json` |

## Workflow
1. Beat 1 = chosen hook verbatim (`role: hook`, `hook_id`). Then 4–7 beats from `references/structures.md` for the
   idea's format. Keep each beat 1–2 sentences — beats become scene boundaries.
2. Every setup/value/twist/payoff beat lists `claim_ids`; opinion beats set `"opinion": true`.
3. End on payoff, a loop line that re-enters the hook, or a light CTA (never "smash that like").
4. `publish`: 2–3 titles ≤ 100 chars (no clickbait beyond the hook's promise), description (1–3 sentences),
   3–6 hashtags. Brand voice: apply brand-voice skills if the user has guidelines.
5. Run the gate. Duration is estimated here (≈3 words/s English) and verified on real audio at AUDIO.

## Phase 2 script variants (factory default for new runs)
Write `videos/<v>/script/script_variants.json` (contract `script_variants`): **two complete variants that differ
in structure and rhythm**, both opening with the selected hook verbatim (`videos/<v>/hook/selected_hook.json`) and
paying off the facts it promises. Beats: role, text, claim_ids, `visual_intent` (every beat), optional `on_screen`,
`emphasis`, and intentional `pause_before`/`pause_after` (0-1.5 s, at most two beats, only where delivery gains).
Plan length with `python voice-production/scripts/estimate.py script --script <variant>` (calibrated on the real
voice; ±5 % on held-out videos). Gate `script_select.py select` checks hook-is-opening and promise-paid (blocking),
claims traceable, no generic intro, explanation by 8 s, no mid-script hook repeat, duration window, visual intent,
pauses; enforces distinct variants; asks the independent reviewer (`review-script`) for clarity, pacing, payoff
coherence and hook ≥ 4; writes script.json from the stronger variant and updates opening_brief.json.

## Phase 3.5 CTA decision (new runs: `cta_engine: v1`)
Every script variant records a `cta` decision — `{"needed": false, "decision_reason": …}` or a CTA with type (follow,
subscribe, like, comment, save, share, part_2, question, profile), placement (`integrated` in a content beat after the
payoff · `after_payoff` as its own `cta` beat · `on_screen_only`), modality (spoken / on_screen / both), beat_id, the
exact spoken words and ≤6 on-screen words. Write it for THIS video: point at its subject, ask one thing, keep it short.
Deterministic gates (scripts/cta.py; estimated timeline at SCRIPT, real timeline at VIDEO): CTA.SCHEMA, CTA.SINGLE (no
undeclared asks), CTA.NOT_IN_HOOK, CTA.AFTER_PAYOFF, CTA.DURATION (spoken ≤ min 2.8 s, 12 % of runtime), CTA.SHORT_VIDEO
(no separate spoken CTA beat under 20 s), CTA.ENDING (a spoken CTA never after the loop line; ≤1.2 s tail when the CTA
closes), CTA.STANDALONE_ENDING (the video still ends on a payoff/loop if the CTA is removed), CTA.RELEVANCE (shares the
video's words; no stock outro), CTA.NOT_REPEATED (vs earlier packaged CTAs, cta_history.json), CTA.ON_SCREEN_SHOWN.
v3.3.1: the channel's fixed follow line (`cta.CHANNEL_CTA`: "Follow for a daily mystery." / "FOLLOW BRAIN ACADEMY") is exempt from
CTA.RELEVANCE and CTA.NOT_REPEATED — it is the same in every video on purpose. Prefer it for follow CTAs.
Platform note (verified 2026-10-07): Shorts link onward with a "related video" set in YouTube Studio, not end screens —
a part_2 CTA adds that manual step to metadata.json.

## Quality gate
SCRIPT.SCHEMA, HOOK_FIRST, CLAIMS_EXIST (blocking) · HOOK_MATCH, DURATION, CLAIMS_LINKED, NO_FILLER, TITLE_LENGTH
(major) · SPEAKABLE, ENDING, HASHTAGS, ON_SCREEN (minor).

## Failure recovery
`shorten`/`lengthen` carry `target_s`; cut setup before payoff. Unsupported claim → remove it or send RESEARCH
`corroborate` — never keep an unsourced fact. After a SCRIPT rerun, update the storyboard if beat ids changed.

## Scripts · References
`scripts/script_lint.py --script … --dossier … --hooks … --min-s --max-s --result …` · `references/structures.md`

## Dependencies · Interactions
Feeds visual-storyboarding (beats), voice-production (text), multilingual-content (source), content-factory
packaging (publish copy). QA's claims review checks it again on the finished video.
