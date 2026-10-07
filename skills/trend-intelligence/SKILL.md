---
name: trend-intelligence
description: Collects and scores trend signals for short-form content — rising search interest, outlier videos, timely angles — and classifies each as emerging, rising, peaking, evergreen or declining with a 0–100 score. Use when deciding what to make now, e.g. "what's trending in NICHE", "find timely angles for TOPIC", "is X still worth covering", Google Trends CSV exports, vidIQ or YouTube Data API results, or the trend part of the content factory RESEARCH stage. Not for fact-checking (content-research) or analysing your own published performance (content-analytics).
---

# Trend Intelligence

**Stage:** RESEARCH (advisory) · **Error codes:** `TREND.*` · **Gate:** `scripts/trend_score.py score`

## Activation
Use when timing matters or the user asks what is hot; optional for evergreen batches (selection falls back to
evergreen scoring). Its envelope is advisory: `factory.py record` logs it without blocking RESEARCH.

## Responsibilities
Gather signals from the best available source, normalise them into `signals.json`, score velocity/acceleration/
saturation, and hand content-strategy a ranked `trends.json` with honest labels for qualitative evidence.

## Source priority (use the first that is available — check `capabilities.json`)
1. **vidIQ connector** (if connected in claude.ai): trending videos, outliers, keyword research → `videos[]` items.
2. **YouTube Data API v3** on the user's machine (`YOUTUBE_API_KEY`): `search.list` (publishedAfter, order=viewCount,
   videoDuration=short) + `videos.list` statistics → views per hour.
3. **Google Trends CSV** the user exports (Explore → download) → `--gt-csv`.
4. **web_search** news/forums → qualitative items with `phase_hint` + `evidence` (scored conservatively).

## Inputs → outputs
| In | Out |
|---|---|
| topic/niche, any of the sources above | `research/signals.json`, `research/trends.json` (schema `trend_report`), `research/trends_result.json` |

## Workflow
1. Collect 5–15 candidate terms/angles; record `collected_at`.
2. Write `signals.json` items as `series`, `videos` or `phase_hint` shapes (see script docstring).
3. Run `trend_score.py score`; read the top terms; tag ideas with `trend_terms` so selection can boost them.

## Quality gate
TREND.SCHEMA (blocking) · TREND.HAS_SIGNALS (major → collect more) · TREND.FRESH ≤14 days (minor) ·
TREND.QUANTITATIVE at least one numeric signal (minor).

## Failure recovery
No signals → proceed evergreen and say so; stale data → re-collect; never present qualitative hints as numbers.

## Scripts · References
`scripts/trend_score.py score --signals … --out … --result … [--gt-csv …]` · `references/signals.md`

## Dependencies · Interactions
Optional vidIQ connector / YouTube Data API / Google Trends export. Feeds content-strategy (`--trends`).
Performance of past videos comes from content-analytics, not from here.
