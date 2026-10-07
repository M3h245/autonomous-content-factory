# Trend signals
Shapes accepted by `trend_score.py` (mix freely, add `collected_at` ISO time at the top level):
```json
{"collected_at": "2026-10-03T09:00:00Z", "items": [
 {"term": "sky color", "source": "google_trends_csv", "series": [12, 15, 14, 20, 31, 44]},
 {"term": "rayleigh scattering", "source": "youtube_search", "videos": [{"views": 52000, "age_hours": 40}]},
 {"term": "why sky violet", "source": "web_search", "phase_hint": "evergreen", "evidence": "steady explainer demand"}]}
```
Score = 0.45·σ(8·velocity) + 0.25·σ(8·acceleration) + 0.30·level (series); median views/hour with freshness for video
lists; fixed conservative scores for qualitative hints. Phases: emerging, rising, peaking, evergreen, declining.
Connector use (vidIQ when connected): load tool schemas with tool_search first; useful tools seen in the directory
include trending videos, outliers and keyword research. YouTube Data API (user's machine): `search.list` with
`publishedAfter`, `order=viewCount`, `videoDuration=short`, then `videos.list` for statistics; quota-aware.
Report qualitative evidence as qualitative — never invent numbers.
