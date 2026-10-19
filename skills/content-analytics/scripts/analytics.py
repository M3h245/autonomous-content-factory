#!/usr/bin/env python3
"""content-analytics — turn platform analytics exports into KPIs and bounded weight updates (ANALYTICS stage).

  analytics.py analyze --csv export.csv --platform youtube|tiktok|instagram --db factory.db
                       --out-dir DIR --result DIR/result.json [--prior 5] [--lr 0.5]

Reads YouTube Studio / TikTok / Instagram CSV exports (column names matched by synonym), matches rows to factory
videos ONLY through the platform id recorded in `publications` (no title matching: an export without an id column
matches nothing), computes retention/engagement KPIs, estimates the effect of features (hook archetype, format,
pillar, duration bucket, visual kind) with empirical-Bayes shrinkage, and proposes bounded weight multipliers
(0.5–2.0) that content-strategy and hook-engineering read on the next run.

Factory KPIs, the match rate and the weights use factory-attributed rows only. Channel-wide totals (every row,
including legacy channel videos and unmatched rows) are reported separately under `channel` and never feed a weight.
Legacy channel videos (legacy_channel.py, fixed list) are labelled `legacy_channel` and are excluded from the match-rate
denominator; a publication row for one of them is a blocking error (ANA.LEGACY_LINKED).
"""
from __future__ import annotations

import argparse
import math
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import StageResult, emit, exit_for, fix, now_iso, stage_main, write_json  # noqa: E402
import legacy_channel as L  # noqa: E402

SYN = {
    "platform_id": ["content", "video id", "video_id", "id", "post id"],
    "title": ["video title", "title", "caption", "description", "video"],
    "views": ["views", "video views", "plays", "reach"],
    "avg_view_s": ["average view duration", "avg. view duration", "average watch time", "avg watch time"],
    "avg_pct": ["average percentage viewed (%)", "average percentage viewed", "avg. percentage viewed (%)",
                "stayed to watch (%)", "watched full video (%)"],
    "likes": ["likes", "like count"], "comments": ["comments added", "comments", "comment count"],
    "shares": ["shares", "share count"], "subs": ["subscribers", "subscribers gained", "followers gained", "new followers"],
}


def norm_cols(df: pd.DataFrame) -> dict:
    low = {c.lower().strip(): c for c in df.columns}
    return {k: next((low[s] for s in syns if s in low), None) for k, syns in SYN.items()}


def to_seconds(v) -> float | None:
    if pd.isna(v):
        return None
    s = str(v).strip()
    if re.fullmatch(r"\d+(:\d{1,2}){1,2}", s):
        parts = [int(p) for p in s.split(":")]
        return float(sum(p * 60 ** i for i, p in enumerate(reversed(parts))))
    try:
        return float(s)
    except ValueError:
        return None


def num(v) -> float:
    try:
        return float(str(v).replace(",", "").replace("%", "").strip())
    except ValueError:
        return float("nan")


@stage_main("ANALYTICS", "content-analytics")
def cmd_analyze(a) -> int:
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sr = StageResult("ANALYTICS", "content-analytics")
    sr.input(a.csv, "analytics_export")
    df = pd.read_csv(a.csv, encoding="utf-8-sig")
    cols = norm_cols(df)
    if cols["platform_id"]:
        df = df[df[cols["platform_id"]].astype(str).str.lower() != "total"]
    sr.check("ANA.ROWS", len(df) > 0, "blocking", f"{len(df)} data rows", fix=fix("ANALYTICS", "provide_export"))
    sr.check("ANA.VIEWS_COLUMN", cols["views"] is not None, "blocking", f"column mapping {cols}",
             fix=fix("ANALYTICS", "map_columns"), retryable=False)
    if sr.failed:
        return exit_for(sr.finalize(a.result))
    con = sqlite3.connect(a.db)
    vids = [dict(zip(["run_id", "video_id", "title", "hook_archetype", "format", "pillar", "duration_s", "visual_kinds"], r))
            for r in con.execute("SELECT run_id, video_id, title, hook_archetype, format, pillar, duration_s, visual_kinds FROM videos")]
    pubs = {r[0]: (r[1], r[2]) for r in con.execute("SELECT platform_video_id, run_id, video_id FROM publications WHERE platform=?",
                                                       (a.platform,)) if r[0]}
    bad = sorted(p for p in pubs if L.is_legacy(p))
    sr.check("ANA.LEGACY_LINKED", not bad, "blocking", f"legacy channel videos with a factory publication: {bad}",
             fix=fix("ANALYTICS", "remove_legacy_publication"), retryable=False)
    if sr.failed:
        return exit_for(sr.finalize(a.result))
    sr.check("ANA.ID_COLUMN", cols["platform_id"] is not None, "minor",
             "no video id column: rows can only be attributed through publication ids (title matching is disabled)")
    rows = []
    for _, r in df.iterrows():
        match = None
        pid = str(r[cols["platform_id"]]).strip() if cols["platform_id"] else None
        scope = L.SCOPE if pid and L.is_legacy(pid) else None
        if pid and pid in pubs and not scope:
            match = next((v for v in vids if (v["run_id"], v["video_id"]) == pubs[pid]), None)
        views = num(r[cols["views"]])
        avg_pct = num(r[cols["avg_pct"]]) / 100 if cols["avg_pct"] else float("nan")
        avg_s = to_seconds(r[cols["avg_view_s"]]) if cols["avg_view_s"] else None
        if math.isnan(avg_pct) and avg_s and match and match["duration_s"]:
            avg_pct = avg_s / match["duration_s"]
        inter = sum(num(r[cols[k]]) for k in ("likes", "comments", "shares") if cols[k] and not math.isnan(num(r[cols[k]])))
        rows.append({"match": match, "pid": pid, "scope": scope or ("factory" if match else "unattributed"),
                     "views": views, "retention": avg_pct,
                     "engagement_rate": inter / views if views and views > 0 else float("nan")})
    matched = [x for x in rows if x["match"]]
    legacy = [x for x in rows if x["scope"] == L.SCOPE]
    eligible = len(rows) - len(legacy)                     # legacy rows can never match, so they are not counted
    rate = len(matched) / max(1, eligible)
    sr.check("ANA.MATCH_RATE", rate >= 0.5, "major",
             f"{len(matched)}/{eligible} non-legacy rows matched to factory videos ({len(legacy)} legacy rows excluded)",
             round(rate, 2), 0.5, fix("ANALYTICS", "map_ids", hint="log publications with real platform ids "
                                      "(ingest_youtube.py --publications-only)"))
    sr.check("ANA.SAMPLE_SIZE", len(matched) >= 10, "minor", f"{len(matched)} matched videos; weights damped by the prior")
    lv = [math.log10(1 + x["views"]) for x in matched if not math.isnan(x["views"])]
    vmax = max(lv) if lv else 1.0
    for x in matched:
        ret = x["retention"] if not math.isnan(x["retention"]) else 0.0
        eng = x["engagement_rate"] if not math.isnan(x["engagement_rate"]) else 0.0
        x["perf"] = 0.5 * min(ret, 1.0) + 0.3 * (math.log10(1 + x["views"]) / vmax if vmax else 0) + 0.2 * min(eng * 10, 1.0)
    glob = sum(x["perf"] for x in matched) / len(matched) if matched else 0.0
    effects, weights = [], {}
    for feat in ("hook_archetype", "format", "pillar", "visual_kinds", "duration_bucket"):
        groups: dict[str, list[float]] = {}
        for x in matched:
            m = x["match"]
            val = (f"{int(m['duration_s'] // 15 * 15)}-{int(m['duration_s'] // 15 * 15 + 15)}s" if feat == "duration_bucket"
                   and m["duration_s"] else m.get(feat))
            if val:
                groups.setdefault(str(val), []).append(x["perf"])
        for val, ps in groups.items():
            n, mean = len(ps), sum(ps) / len(ps)
            shrunk = (n * mean + a.prior * glob) / (n + a.prior)
            lift = shrunk / glob if glob else 1.0
            effects.append({"feature": feat, "value": val, "n": n, "mean": round(mean, 4), "shrunk": round(shrunk, 4), "lift": round(lift, 3)})
            weights[f"{feat}:{val}"] = {"value": round(min(2.0, max(0.5, 1 + a.lr * (lift - 1))), 3), "n": n}
    total = lambda xs: sum(x["views"] for x in xs if not math.isnan(x["views"]))  # noqa: E731
    channel = {"rows": len(rows), "views": total(rows),
               "by_scope": {s: {"rows": sum(1 for x in rows if x["scope"] == s),
                                "views": total([x for x in rows if x["scope"] == s])}
                            for s in ("factory", "unattributed", L.SCOPE)},
               "note": "channel-wide totals over every row; never used for factory KPIs, weights or run attribution"}
    feedback = {"generated_at": now_iso(), "platform": a.platform, "rows": len(rows), "matched": len(matched),
                "global_perf": round(glob, 4), "channel": channel,
                "legacy_channel": [{"platform_video_id": x["pid"], "views": None if math.isnan(x["views"]) else x["views"],
                                    "reason": L.DECISION + "; no factory file, run or publication"} for x in legacy],
                "videos": [{"run_id": x["match"]["run_id"], "video_id": x["match"]["video_id"], "views": x["views"],
                            "retention": None if math.isnan(x["retention"]) else round(x["retention"], 4),
                            "engagement_rate": None if math.isnan(x["engagement_rate"]) else round(x["engagement_rate"], 5),
                            "perf": round(x["perf"], 4)} for x in matched],
                "feature_effects": sorted(effects, key=lambda e: -e["lift"]), "weights": weights,
                "notes": ["perf = 0.5*retention + 0.3*log-views (relative) + 0.2*engagement; lifts shrunk toward the mean"]}
    write_json(out / "feedback.json", feedback)
    sr.output(out / "feedback.json", "feedback", "application/json")
    sr.metric("matched", len(matched)); sr.metric("global_perf", round(glob, 4))
    res = sr.finalize(a.result)
    emit(res)
    return exit_for(res)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    an = sub.add_parser("analyze")
    an.add_argument("--csv", required=True); an.add_argument("--platform", required=True, choices=["youtube", "tiktok", "instagram"])
    an.add_argument("--db", required=True); an.add_argument("--out-dir", required=True); an.add_argument("--result", required=True)
    an.add_argument("--prior", type=float, default=5.0); an.add_argument("--lr", type=float, default=0.5)
    a = ap.parse_args()
    return cmd_analyze(a)


if __name__ == "__main__":
    sys.exit(main())
