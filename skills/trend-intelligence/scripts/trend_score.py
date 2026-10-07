#!/usr/bin/env python3
"""trend-intelligence — score trend signals into a trend report (advisory part of RESEARCH).

  trend_score.py score --signals research/signals.json --out research/trends.json --result research/trends_result.json
                       [--gt-csv google_trends_export.csv]

signals.json items take one of three shapes (mix freely):
  {"term", "source", "series": [n1, n2, ...]}              time series (Google Trends export, search volume, mentions)
  {"term", "source", "videos": [{"views", "age_hours"}]}   recent platform results (YouTube Data API, vidIQ connector)
  {"term", "source", "phase_hint", "evidence"}             qualitative evidence from web research (scored conservatively)
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, now_iso, read_json, stage_main, validate_artifact, write_json  # noqa: E402

HINT = {"emerging": 70, "rising": 65, "peaking": 55, "evergreen": 50, "declining": 25, "unknown": 40}


def slope(y: list[float]) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    xm, ym = (n - 1) / 2, sum(y) / n
    den = sum((i - xm) ** 2 for i in range(n))
    return sum((i - xm) * (v - ym) for i, v in enumerate(y)) / den if den else 0.0


def sig(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def score_item(it: dict) -> dict:
    if it.get("series"):
        y = [float(v) for v in it["series"]]
        mean = sum(y) / len(y) or 1.0
        vel = slope(y[-max(3, len(y) // 3):]) / mean
        half = len(y) // 2
        acc = (slope(y[half:]) - slope(y[:half])) / mean if half >= 2 else 0.0
        level = y[-1] / (max(y) or 1)
        phase = ("emerging" if acc > 0.05 and vel > 0.05 else "rising" if vel > 0.03 else
                 "declining" if vel < -0.03 else "peaking" if level > 0.8 else "evergreen" if level > 0.4 else "unknown")
        score = 100 * (0.45 * sig(8 * vel) + 0.25 * sig(8 * acc) + 0.30 * level)
        return {**it, "score": round(score, 1), "phase": phase, "quantitative": True,
                "metrics": {"velocity": round(vel, 4), "acceleration": round(acc, 4), "level": round(level, 3)}}
    if it.get("videos"):
        vph = [v["views"] / max(1.0, v["age_hours"]) for v in it["videos"]]
        med = statistics.median(vph)
        fresh = sum(1 for v in it["videos"] if v["age_hours"] <= 72) / len(it["videos"])
        score = 100 * min(1.0, math.log10(1 + med) / 4) * (0.7 + 0.3 * fresh) * (0.85 if len(it["videos"]) > 50 else 1)
        phase = "emerging" if fresh > 0.5 and med > 500 else "rising" if med > 200 else "evergreen"
        return {**it, "score": round(score, 1), "phase": phase, "quantitative": True,
                "metrics": {"median_views_per_hour": round(med, 1), "fresh_share": round(fresh, 2), "results": len(it["videos"])}}
    hint = it.get("phase_hint", "unknown")
    return {**it, "score": HINT.get(hint, 40), "phase": hint if hint in HINT else "unknown", "quantitative": False, "metrics": {}}


def google_trends_csv(path: str) -> list[dict]:
    rows = [r for r in csv.reader(open(path, encoding="utf-8-sig")) if r]
    head_i = next(i for i, r in enumerate(rows) if len(r) > 1 and r[0].lower() in ("week", "day", "month", "time"))
    head = rows[head_i]
    items = []
    for c in range(1, len(head)):
        vals = [float(r[c].replace("<1", "0.5")) for r in rows[head_i + 1:] if len(r) > c and r[c].strip()]
        items.append({"term": head[c].split(":")[0].strip(), "source": "google_trends_csv", "series": vals})
    return items


@stage_main("RESEARCH", "trend-intelligence")
def cmd_score(a) -> int:
    sr = StageResult("RESEARCH", "trend-intelligence", attempt=a.attempt)
    data = read_json(a.signals) if a.signals else {"items": []}
    items = list(data.get("items", [])) + (google_trends_csv(a.gt_csv) if a.gt_csv else [])
    scored = sorted((score_item(i) for i in items), key=lambda x: -x["score"])
    report = {"generated_at": now_iso(), "collected_at": data.get("collected_at"), "signals": scored}
    write_json(a.out, report)
    sr.check("TREND.SCHEMA", not validate_artifact(report, "trend_report"), "blocking", "trend_report schema")
    sr.check("TREND.HAS_SIGNALS", bool(scored), "major", "no trend signals; selection falls back to evergreen scoring",
             fix=fix("RESEARCH", "collect_signals"))
    age = None
    if data.get("collected_at"):
        age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(data["collected_at"].replace("Z", "+00:00"))).days
    sr.check("TREND.FRESH", age is not None and age <= 14, "minor", f"signals collected {age} days ago")
    sr.check("TREND.QUANTITATIVE", any(s["quantitative"] for s in scored), "minor",
             "only qualitative evidence; connect vidIQ or run the YouTube Data API pull for numbers")
    sr.output(a.out, "trend_report", "application/json")
    sr.metric("signals", len(scored)); sr.metric("top", [(s["term"], s["score"], s["phase"]) for s in scored[:5]])
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("score")
    s.add_argument("--signals"); s.add_argument("--gt-csv"); s.add_argument("--out", required=True)
    s.add_argument("--result", required=True); s.add_argument("--attempt", type=int, default=1)
    return cmd_score(ap.parse_args())


if __name__ == "__main__":
    sys.exit(main())
