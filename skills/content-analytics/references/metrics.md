# Metrics
Exports: YouTube Studio → Analytics → Advanced mode → Export (CSV); TikTok and Instagram → analytics export.
Column synonyms are matched case-insensitively (views/plays, average view duration, average percentage viewed,
stayed to watch, likes, comments, shares, subscribers/followers). A "Total" row is ignored.
KPIs: retention = avg % viewed (or avg view duration ÷ length); engagement = (likes+comments+shares) ÷ views;
perf = 0.5·retention + 0.3·relative log views + 0.2·min(10·engagement, 1).
Effects: per feature value mean perf, shrunk with prior 5 toward the batch mean; weight = clamp(1 + 0.5·(lift−1), 0.5, 2).
Interpretation: <10 matched videos = directional only; compare within platform; first 48 h numbers are noisy.
