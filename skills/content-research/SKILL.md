---
name: content-research
description: Builds a cited research dossier for short-form videos — atomic facts with source ids, risk levels and source tiers — and validates it with a gate (every fact cited, high-risk claims corroborated by a tier-1 source or two independent domains, quotes under 15 words). Use when a video or batch needs factual grounding, e.g. "research TOPIC for shorts", "find facts and sources for a video about X", "fact-check this script", or the RESEARCH stage of the content factory. Not for trend or virality discovery (trend-intelligence), general web questions, or writing scripts.
---

# Content Research

**Stage:** RESEARCH · **Error codes:** `RES.*` · **Gate:** `scripts/dossier_tool.py validate`

## Activation
Use before any script that states facts; whenever a claim is challenged; when a fix route says `RESEARCH`.
Skip for pure opinion/entertainment formats (mark those script beats `"opinion": true`).

## Responsibilities
Search, read primary sources, extract atomic claims in your own words, assign risk, cite, and keep copyright safe.

## Inputs → outputs
| In | Out |
|---|---|
| brief topic, audience, count; `fix_params` on reruns | `research/dossier.json` (schema `research_dossier`) |
| web_search / web_fetch results | `research/dossier.scored.json` (tiers added), `research/result.json` |

## Workflow
1. Plan 4–8 searches covering mechanism, numbers, common misconceptions, recent developments, counter-evidence.
2. Prefer primary sources (government, intergovernmental, peer-reviewed, official docs); fetch pages, don't trust snippets.
3. Write each fact as one paraphrased claim (≥10 chars) with `source_ids`, `risk` (`high` = health, money, law,
   safety, statistics people act on; `medium` = specific numbers/dates; `low` = textbook facts) and `confidence`.
4. At most one quote per source, under 15 words, only when exact wording matters.
5. Need ≥ max(5, 2×count) facts. Add `angles` and `misconceptions` notes if useful for ideation.
6. Run the gate; on failure follow the fix route (corroborate, paraphrase, expand, replace sources).

## Quality gate
| Check | Rule | Severity |
|---|---|---|
| RES.SCHEMA | dossier matches schema | blocking |
| RES.CITATIONS_RESOLVE | every source id exists | blocking |
| RES.HIGH_RISK_CORROBORATED | tier-1 source or 2 independent domains | blocking |
| RES.MEDIUM_RISK_SOURCED | at least one tier ≤ 2 source | major |
| RES.QUOTE_LENGTH / ONE_QUOTE_PER_SOURCE | ≤15 words; ≤1 per source | blocking / major |
| RES.ENOUGH_FACTS | ≥ min facts | major |
| RES.SOURCE_QUALITY | ≤50 % social/UGC sources | major |

## Failure recovery
Corroborate weak facts with new searches; drop facts that cannot be corroborated rather than softening them;
if a topic cannot reach the evidence bar, tell the orchestrator (escalate) instead of inventing sources.

## Scripts · References
`scripts/dossier_tool.py validate --dossier … --result … [--min-facts N]` · `references/source-tiers.md`

## Dependencies
web_search/web_fetch tools (Claude). No API keys. Container network is not needed.

## Interactions
Feeds content-strategy (fact_ids per idea), short-form-script (claim_ids per beat), asset-provenance (sources in
description), video-quality-assurance (claims review). trend-intelligence runs alongside it in RESEARCH.
