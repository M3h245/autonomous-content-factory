# v3.1.0 — metric definitions and denominators

Source: YouTube Data API v3 and YouTube Analytics API v2, through `tools/youtube_sync/yt_sync.py` (read-only OAuth
scopes). The official definitions are stored in the `yt_metric_defs` table with their documentation URL.

## Calendar and age

- **Analytics day:** midnight to midnight, **Pacific time**. Day 1 is the publication day (Pacific), which is partial:
  - 16:00Z = 09:00 PT, so the video has about 15 h on day 1;
  - 21:00Z = 14:00 PT, so it has about 10 h.
- **Analytics cutoff:** the last day that has `channel_daily` rows in a snapshot. Rows lag 1–3 days, and a day after the
  cutoff has **no data**, which is not the same as zero.
- **Maturity** (Analytics days available up to the newest cutoff): `none` 0 · `early` 1–2 · `d3` 3–6 · `d7` ≥7.
- **Fixed-age values** use the newest snapshot that covers that age. All days in the window must be present with
  status `ok`; otherwise the value is NULL with the reason.

## Metrics

| name | definition | denominator | age-matched? |
|---|---|---|---|
| `views_dN` | sum of daily `views`, days 1…N | — | yes |
| `engaged_views_dN` | sum of daily `engagedViews` (views past the first frame, per the official page) | — | yes |
| **`engaged_share_d3`** (primary) | `engaged_views_d3 / views_d3` | views in the same 3 days | yes |
| `engaged_share_d1` | the same for day 1 | views on day 1 | yes |
| `avg_view_pct` (guardrail) | `averageViewPercentage`, lifetime up to the cutoff; can exceed 100 % with loops | playbacks (looping-clip traffic excluded by YouTube since 2021-12-13) | **no**, the age is reported next to it |
| `avg_view_dur_s` | `averageViewDuration`, lifetime | playbacks | no |
| `retention_3s` | `audienceWatchRatio` at the curve point nearest to 3 s / duration; can exceed 1 (replays) | views | no |
| `subscribers_gained` | `subscribersGained` with a single-video filter (watch-page subscriptions only) | — | no |
| `public_views_at_pull` | Data API `statistics.viewCount` at pull time | — | no (the lifetime counter) |

## Not available from any API

- **"Stayed to watch" / "Viewed vs. swiped away"** (Studio, Shorts). `engaged_share` is the documented proxy, but it is
  **not the same number**.
- **"Shown in feed"** (Studio).

## Do not interchange

- Views measure reach. The engaged share measures the opening's hold. Avg view % and retention measure how far
  viewers watch. Subscribers gained measures conversion.
- The learning layer compares groups on **one** primary metric (`engaged_share_d3`), reports the others separately and
  uses avg view % as a guardrail: a gain in the primary metric with a >5 pp loss in avg view % earns no bonus.
