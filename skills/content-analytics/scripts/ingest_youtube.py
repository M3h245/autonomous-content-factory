#!/usr/bin/env python3
"""ingest_youtube — link published YouTube Shorts to factory videos and load a metrics snapshot (dry run by default).

  ingest_youtube.py --db factory.db --videos channel_videos.json --metrics yt_metrics_by_video.json
                    [--confirm confirmations.json] [--out report.json] [--apply]

Mapping is evidence-based, never fuzzy. A YouTube video is linked to a factory video only when
  * its title equals exactly one factory title after normalising case, curly quotes, hashtags and end punctuation
    ("Your hand does not measure temperature!" == "Your hand does not measure temperature"),
  * the durations agree within 1.5 s, and the video was published on or after the run's date, and
  * no other YouTube video claims the same factory video;
or when the owner confirmed the pair in --confirm ({"<youtube id>": {"run_id": ..., "video_id": ...}}). Everything else
is reported as unmapped with the reason; nothing is guessed.

Writes are insert-only and idempotent: a row that already exists unchanged is skipped, a row that exists with
different values is reported as a conflict and never overwritten. --apply copies the database to
<db>.bak-<timestamp> first and writes in one transaction. Without --apply nothing is written to the database.
Metrics rows carry the snapshot's captured_at, so loading the same snapshot twice inserts nothing new.
perf stays NULL (the ANALYTICS stage computes it) and no weights are written.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

DURATION_TOL_S = 1.5
URL = "https://www.youtube.com/shorts/{}"


def norm_title(t: str) -> str:
    t = (t or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = re.sub(r"#\w+", " ", t)
    t = re.sub(r"\s+", " ", t).strip().lower()
    return re.sub(r"[\s.!?]+$", "", t)


def iso_seconds(d: str) -> float | None:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", d or "")
    if not m or not any(m.groups()):
        return None
    h, mi, s = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def load_json(p) -> dict:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def factory_videos(con) -> list[dict]:
    q = ("SELECT v.run_id, v.video_id, v.title, v.duration_s, r.created_at FROM videos v LEFT JOIN runs r ON r.run_id = v.run_id")
    return [dict(zip(["run_id", "video_id", "title", "duration_s", "run_created_at"], r)) for r in con.execute(q)]


def run_date(fv: dict) -> str:
    m = re.match(r"(\d{4}-\d{2}-\d{2})", fv["run_id"] or "")
    return (fv.get("run_created_at") or "")[:10] or (m.group(1) if m else "")


def map_videos(yt: list[dict], fvs: list[dict], confirm: dict) -> tuple[list[dict], list[dict]]:
    by_norm: dict[str, list[dict]] = {}
    for fv in fvs:
        by_norm.setdefault(norm_title(fv["title"]), []).append(fv)
    keyset = {(f["run_id"], f["video_id"]): f for f in fvs}
    mapped, unmapped = [], []
    for v in yt:
        vid, dur = v["videoId"], iso_seconds(v.get("duration", ""))
        ev = {"youtube_id": vid, "youtube_title": v["title"], "published_at": v.get("publishedAt"), "youtube_duration_s": dur}
        if v.get("videoType") not in (None, "short"):
            unmapped.append({**ev, "reason": f"not a Short ({v.get('videoType')})"})
            continue
        c = confirm.get(vid)
        if c:
            fv = keyset.get((c.get("run_id"), c.get("video_id")))
            if fv:
                mapped.append({**ev, "run_id": fv["run_id"], "video_id": fv["video_id"], "factory_title": fv["title"],
                               "factory_duration_s": fv["duration_s"], "evidence": "owner_confirmed"})
            else:
                unmapped.append({**ev, "reason": f"owner confirmation names an unknown factory video {c}"})
            continue
        cands = by_norm.get(norm_title(v["title"]), [])
        if len(cands) != 1:
            unmapped.append({**ev, "reason": "no factory video with this title" if not cands else
                             f"title matches {len(cands)} factory videos", "needs": "owner confirmation (--confirm)"})
            continue
        fv = cands[0]
        problems = []
        if dur is None or fv["duration_s"] is None or abs(dur - fv["duration_s"]) > DURATION_TOL_S:
            problems.append(f"duration {dur} s vs factory {fv['duration_s']} s")
        if run_date(fv) and (v.get("publishedAt") or "")[:10] < run_date(fv):
            problems.append(f"published {v.get('publishedAt')} before the run date {run_date(fv)}")
        if problems:
            unmapped.append({**ev, "candidate": [fv["run_id"], fv["video_id"]], "reason": "; ".join(problems),
                             "needs": "owner confirmation (--confirm)"})
            continue
        exact = (v["title"] or "").strip() == (fv["title"] or "").strip()
        mapped.append({**ev, "run_id": fv["run_id"], "video_id": fv["video_id"], "factory_title": fv["title"],
                       "factory_duration_s": fv["duration_s"],
                       "evidence": f"title_{'exact' if exact else 'normalized'}+duration+date"})
    claims: dict[tuple, list[str]] = {}
    for m in mapped:
        claims.setdefault((m["run_id"], m["video_id"]), []).append(m["youtube_id"])
    dup = {k for k, ids in claims.items() if len(ids) > 1}
    for m in [m for m in mapped if (m["run_id"], m["video_id"]) in dup]:
        mapped.remove(m)
        unmapped.append({**m, "reason": f"factory video claimed by several YouTube ids {claims[(m['run_id'], m['video_id'])]}"})
    return mapped, unmapped


def metric_rows(snap: dict, mapped: list[dict]) -> tuple[list[dict], list[dict]]:
    cols = snap["columns"]
    by_id = {r[cols.index("video")]: dict(zip(cols, r)) for r in snap["rows"]}
    end = snap["endDate"]
    rows, missing = [], []
    for m in mapped:
        r = by_id.get(m["youtube_id"])
        if not r:
            missing.append({"youtube_id": m["youtube_id"], "run_id": m["run_id"], "video_id": m["video_id"],
                            "reason": "no row in the snapshot (analytics lag or no views in the window)"})
            continue
        views = r.get("views") or 0
        inter = sum(r.get(k) or 0 for k in ("likes", "comments", "shares"))
        age = (date.fromisoformat(end) - date.fromisoformat(m["published_at"][:10])).days if m.get("published_at") else None
        raw = {**r, "window": {"start": snap["startDate"], "end": end, "note": snap.get("note")}, "source": snap["source"],
               "published_at": m.get("published_at"), "age_days_at_window_end": age,
               "engaged_view_rate": round(r["engagedViews"] / views, 4) if views and r.get("engagedViews") is not None else None}
        rows.append({"run_id": m["run_id"], "video_id": m["video_id"], "platform": "youtube", "captured_at": snap["captured_at"],
                     "views": float(views),
                     "retention": round(r["averageViewPercentage"] / 100, 4) if r.get("averageViewPercentage") is not None else None,
                     "engagement_rate": round(inter / views, 5) if views else None, "perf": None,
                     "raw_json": json.dumps(raw, sort_keys=True)})
    mapped_ids = {m["youtube_id"] for m in mapped}
    for yid in by_id:
        if yid not in mapped_ids:
            missing.append({"youtube_id": yid, "reason": "snapshot row has no mapped factory video (not inserted)"})
    return rows, missing


def plan(con, table: str, key: list[str], rows: list[dict]) -> list[dict]:
    out = []
    for row in rows:
        cur = con.execute(f"SELECT * FROM {table} WHERE " + " AND ".join(f"{k}=?" for k in key), [row[k] for k in key])
        cols = [c[0] for c in cur.description]
        have = cur.fetchone()
        if have is None:
            out.append({"action": "insert", "row": row})
        else:
            have = dict(zip(cols, have))
            diff = {c: {"db": have.get(c), "new": row[c]} for c in row if have.get(c) != row[c]}
            out.append({"action": "conflict" if diff else "unchanged", "row": row, **({"diff": diff} if diff else {})})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True); ap.add_argument("--videos", required=True); ap.add_argument("--metrics", required=True)
    ap.add_argument("--confirm"); ap.add_argument("--out"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    if not Path(a.db).is_file():
        print(json.dumps({"error": "DB_NOT_FOUND", "db": a.db}))
        return 2
    con = sqlite3.connect(a.db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"videos", "runs", "publications", "metrics"} <= tables:
        print(json.dumps({"error": "DB_SCHEMA", "tables": sorted(tables)}))
        return 2
    yt, snap = load_json(a.videos), load_json(a.metrics)
    mapped, unmapped = map_videos(yt["videos"], factory_videos(con), load_json(a.confirm) if a.confirm else {})
    pubs = [{"run_id": m["run_id"], "video_id": m["video_id"], "platform": "youtube", "url": URL.format(m["youtube_id"]),
             "platform_video_id": m["youtube_id"], "published_at": m["published_at"]} for m in mapped]
    mets, no_metrics = metric_rows(snap, mapped)
    pub_plan = plan(con, "publications", ["run_id", "video_id", "platform"], pubs)
    for p in pub_plan:   # one YouTube id must never point at two factory videos
        other = con.execute("SELECT run_id, video_id FROM publications WHERE platform='youtube' AND platform_video_id=? "
                            "AND NOT (run_id=? AND video_id=?)", (p["row"]["platform_video_id"], p["row"]["run_id"],
                                                                  p["row"]["video_id"])).fetchone()
        if other:
            p.update(action="conflict", diff={"platform_video_id": {"db_already_maps_to": list(other)}})
    met_plan = plan(con, "metrics", ["run_id", "video_id", "platform", "captured_at"], mets)
    count = lambda pl, k: sum(1 for p in pl if p["action"] == k)  # noqa: E731
    report = {"mode": "apply" if a.apply else "dry-run", "db": str(Path(a.db).resolve()),
              "metrics_window": {"start": snap["startDate"], "end": snap["endDate"], "captured_at": snap["captured_at"],
                                 "note": snap.get("note")},
              "mapped": mapped, "unmapped": unmapped, "no_metrics": no_metrics,
              "publications": pub_plan, "metrics": met_plan,
              "totals": {"youtube_videos": len(yt["videos"]), "mapped": len(mapped), "unmapped": len(unmapped),
                         "publications": {k: count(pub_plan, k) for k in ("insert", "unchanged", "conflict")},
                         "metrics": {k: count(met_plan, k) for k in ("insert", "unchanged", "conflict")}}}
    if a.apply and any(p["action"] == "insert" for p in pub_plan + met_plan):
        stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
        bak = Path(f"{a.db}.bak-{stamp}")
        while bak.exists():                      # never overwrite an earlier backup
            n += 1
            bak = Path(f"{a.db}.bak-{stamp}-{n}")
        con.close()
        shutil.copy2(a.db, bak)
        con = sqlite3.connect(a.db)
        with con:
            for table, pl in (("publications", pub_plan), ("metrics", met_plan)):
                for p in pl:
                    if p["action"] == "insert":
                        r = p["row"]
                        con.execute(f"INSERT INTO {table}({','.join(r)}) VALUES({','.join('?' * len(r))})", list(r.values()))
        report["backup"] = str(bak)
    text = json.dumps(report, indent=1, ensure_ascii=True)
    if a.out:
        Path(a.out).write_text(text + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "totals": report["totals"], "report": a.out, "backup": report.get("backup")},
                     ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
