---
name: content-strategy
description: Generates and selects short-form video ideas. Produces an idea pool with angle, format, pillar, linked facts and an explicit value-add, then scores it, de-duplicates against past videos, checks feasibility against the capabilities verified on this machine and picks a varied batch that avoids the mass-produced, templated pattern YouTube treats as inauthentic content. Use for "give me video ideas about X", "pick the best 5 angles", "plan a batch or series", channel pillars, or the content factory IDEATION and SELECTION stages. Not for writing hooks or scripts, and not for website SEO content plans (use searchfit-seo).
---

# Content Strategy

**Stages:** IDEATION, SELECTION · **Error codes:** `IDEA.*`, `SEL.*` · **Gates:** `scripts/select_ideas.py validate|select`

## Activation
Every factory run (after RESEARCH); standalone when the user wants ideas or a batch plan.

## Responsibilities
Originality is a hard requirement, not polish: each idea needs a concrete `value_add` (what this video gives that
the obvious version does not), and a batch must vary format and angle. Read `references/originality-policy.md`.

## Inputs → outputs
| In | Out |
|---|---|
| `research/dossier.json`, `research/trends.json`, `capabilities.json`, `history.json` + `weights.json` (from content-database) | `ideation/ideas.json` (schema `ideas`), `selection/selection.json` (video ids v01…), result envelopes |

## Workflow
1. IDEATION: write ≥ 2× count ideas. Each: `title`, `angle`, `format` (explainer, myth-bust, listicle, story, how-to,
   comparison, question, news), `pillar`, `value_add` (≥30 chars), `fact_ids`, optional `trend_terms`,
   `required_capabilities` (e.g. `tts.kokoro`, `visual.svg`, `visual.sd_forge`), honest 1–5 `scores` for
   audience_value, curiosity, originality, evidence_strength, visual_potential, brand_safety.
2. Run `validate`; fix pool size, format variety, duplicates or dangling fact ids as routed.
3. SELECTION is deterministic: `select` (the orchestrator passes caps/history/trends/weights). It filters unsafe,
   infeasible and near-duplicate ideas, then uses maximal marginal relevance for a varied batch.

## Quality gate
IDEA.SCHEMA, IDEA.FACTS_RESOLVE (blocking) · IDEA.POOL_SIZE, IDEA.FORMAT_VARIETY, IDEA.DISTINCT, IDEA.EVIDENCE (major) ·
SEL.COUNT (blocking) · SEL.FORMAT_VARIETY (major) · SEL.NOVELTY (minor).

## Failure recovery
`SEL.COUNT` fails → IDEATION `expand` with more, more different ideas; never relax brand safety or novelty to fill a batch.

## Scripts · References
`scripts/select_ideas.py` · `references/originality-policy.md`

## Dependencies · Interactions
Reads content-database history/weights and trend-intelligence output; feeds hook-engineering and short-form-script.
Optional: searchfit-seo keyword-clustering for search-led channels.
