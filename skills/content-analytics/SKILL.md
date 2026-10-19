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
1. Make sure published videos are logged with their platform ids (rows are attributed **only** through
   `publications.platform_video_id`; there is no title matching — an export without a video id column matches nothing).
2. `analytics.py analyze --csv … --platform youtube|tiktok|instagram --db factory.db --out-dir … --result …`
3. `cfdb.py log-feedback --db factory.db --feedback feedback.json` → weights are read at the next `factory.py init --db`.
4. Report: top/bottom videos, which features lift performance, sample-size caveats, 2–3 concrete next-batch changes.

## Quality gate
ANA.ROWS, ANA.VIEWS_COLUMN, ANA.LEGACY_LINKED (blocking) · ANA.MATCH_RATE ≥50 % of non-legacy rows (major) ·
ANA.ID_COLUMN, ANA.SAMPLE_SIZE ≥10 videos (minor).
Factory KPIs and weights use factory-attributed rows only; `feedback.json → channel` holds channel-wide totals.
Legacy channel videos (`scripts/legacy_channel.py`, fixed list, owner decision 2026-10-17) are reported under
`legacy_channel` and are never matched to a factory file, run or publication.
perf = 0.5·retention + 0.3·relative log views + 0.2·engagement; feature lift shrunk toward the mean (prior 5).

## Learning loop (v3.1.0, API snapshots → next batch)
The path for YouTube API data; the CSV `analyze` above stays as it was. All steps are read-only on the database except
the two ingest `--apply` steps, which need the owner's approval on the production database.
1. `tools/youtube_sync/yt_sync.py pull` → `data/analytics/<stamp>/snapshot.json`
2. `ingest_youtube.py --publications-only --db … --videos snapshot.json --outputs … [--apply]` (evidence-based links)
3. `ingest_analytics.py --db … --snapshot snapshot.json [--apply]` (immutable `yt_*`; NULL + status, never 0)
4. `learning.py attributes --db … --runs-root <run folders> [--manifests 'batches/*/manifest.json'] --out attributes.json`
5. `learning.py analyze --db … --attributes attributes.json --out-dir data/learning/<stamp> --experiments-dir experiments
   --publish-latest data/learning/latest.json` → `learning_summary.json` (cf-learning/1) + `LEARNING_REPORT.md`
6. Consumers read `data/learning/latest.json` automatically (`idea_engine.py`; `--no-learning` to opt out) and pass it to
   `factory.py init --learning`, which records it in run.json, adds the guidance to the constraints and lets
   `hook_engine.py select --learning` re-rank candidates that passed the review. `learning_apply.py` is the shared reader.
Policy (fixed, `learning.py POLICY`):
- primary metric = engaged share at D3, guardrail = average view %;
- a directive needs n ≥ 3 per side, an 80 % interval that excludes 0 and the guardrail no more than 5 pp worse;
- shrinkage k = 5, 80 % bootstrap interval;
- multiplier caps of ±5 / 10 / 15 % for low / medium / high confidence;
- correlation wording only.
Definitions: `docs/v3.1.0/METRICS.md`.

## Failure recovery
Unknown columns → add synonyms or map manually; low match rate → log platform ids; tiny samples → weights barely move by design.

## Scripts · References
`scripts/analytics.py` · `scripts/legacy_channel.py` · `scripts/ingest_youtube.py` · `scripts/ingest_analytics.py` · `scripts/learning.py` · `scripts/learning_apply.py` · `references/metrics.md` · `docs/v3.1.0/METRICS.md`

## Dependencies
pandas. Optional connectors/APIs: Supermetrics connector, YouTube Analytics API (OAuth, user's machine).

## Interactions
Reads content-database; writes weights consumed by content-strategy and hook-engineering; marketing:performance-report
can turn `feedback.json` into a stakeholder report.
