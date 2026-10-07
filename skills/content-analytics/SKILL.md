---
name: content-analytics
description: Turns published-video analytics (YouTube Studio, TikTok or Instagram CSV exports; Supermetrics or YouTube Analytics API data when available) into KPIs — retention, engagement, shares, follows — matches rows to factory videos, estimates which hooks, formats, pillars, lengths and visual styles perform using shrinkage for small samples, and writes bounded weights that steer the next batch. Use for "how are my shorts doing", "analyze this analytics export", "what should I make more of", or the content factory ANALYTICS FEEDBACK stage.
---

# Content Analytics

**Stage:** ANALYTICS (after publishing, asynchronous) · **Error codes:** `ANA.*` · **Gate:** `scripts/analytics.py analyze`

## Activation
When the user brings performance data or asks what is working; at the start of a new batch if fresh data exists.

## Responsibilities
Close the loop honestly: small samples get small adjustments; correlation is reported as such.

## Inputs → outputs
| In | Out |
|---|---|
| CSV export (YouTube Studio → Analytics → Advanced → Export; TikTok/Instagram exports), `factory.db` | `feedback.json` (per-video KPIs, feature effects, weights 0.5–2.0), `result.json` |

## Workflow
1. Make sure published videos are logged: `cfdb.py publish --video v01 --platform youtube --url … --platform-id …`
   (otherwise matching falls back to title similarity ≥ 0.85).
2. `analytics.py analyze --csv … --platform youtube|tiktok|instagram --db factory.db --out-dir … --result …`
3. `cfdb.py log-feedback --db factory.db --feedback feedback.json` → weights are read at the next `factory.py init --db`.
4. Report: top/bottom videos, which features lift performance, sample-size caveats, 2–3 concrete next-batch changes.

## Quality gate
ANA.ROWS, ANA.VIEWS_COLUMN (blocking) · ANA.MATCH_RATE ≥50 % (major) · ANA.SAMPLE_SIZE ≥10 videos (minor).
perf = 0.5·retention + 0.3·relative log views + 0.2·engagement; feature lift shrunk toward the mean (prior 5).

## Failure recovery
Unknown columns → add synonyms or map manually; low match rate → log platform ids; tiny samples → weights barely move by design.

## Scripts · References
`scripts/analytics.py` · `references/metrics.md`

## Dependencies
pandas. Optional connectors/APIs: Supermetrics connector, YouTube Analytics API (OAuth, user's machine).

## Interactions
Reads content-database; writes weights consumed by content-strategy and hook-engineering; marketing:performance-report
can turn `feedback.json` into a stakeholder report.
