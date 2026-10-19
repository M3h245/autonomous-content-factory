#!/usr/bin/env python3
"""ingest_analytics — normalise an official yt_sync snapshot into per-video observations (dry run by default).

  ingest_analytics.py --db factory.db --snapshot data/analytics/<stamp>/snapshot.json [--out report.json] [--apply]

What it does
  * Considers EVERY video in the snapshot (all uploads the authorised channel returned), linked to a factory run or not.
  * Records each value with its report, window, dimensions and status. Missing data is never written as 0:
      ok                 the API returned this value (a real 0 stays 0)
      missing            the report ran but returned no row for this video (no activity in the window, or not returned)
      not_yet_processed  the video was published after the snapshot's Analytics cutoff
      not_requested      yt_sync did not run this report for the video (e.g. per-video reports are public-only)
      not_applicable     a daily row for a day before the video was published (the API returns 0; it is not a result)
      unavailable        the report returned no rows for this video (e.g. no retention curve yet)
      error              the API returned an error for this report (message kept, secrets redacted)
  * Links a video to a factory run only through the existing `publications` table (exact, already verified links).
    Unlinked videos are kept with run_id NULL and learning_eligible 0. Nothing is guessed; no title matching.
  * Legacy channel videos (legacy_channel.py, fixed list, owner decision) stay in the channel-wide data with run_id NULL
    and learning_eligible 0; the report labels them `legacy_channel` with the reason. A publication row for one of them
    stops the script with LEGACY_LINKED_IN_DB (nothing written). The stored rows are the same as for any unlinked video.
  * Never reads or writes `publications`, `metrics` or `weights`. Never calls the API. Never reads credentials.
  * Accepts only yt_sync snapshots (official YouTube Data API + YouTube Analytics API). The old vidIQ JSON is refused.

Storage (created only with --apply; additive, existing tables untouched)
  yt_snapshots     one row per imported snapshot file, keyed by its SHA-256; raw JSON kept verbatim (immutable source)
  yt_videos        one row per (snapshot, YouTube id): title, privacy, publish time, run link (or NULL) and why
  yt_observations  one row per (snapshot, video, report, metric, window, dimension value): value or NULL + status
  yt_metric_defs   metric definitions (official docs) with the URL they were taken from
Re-importing the same snapshot inserts nothing; a different snapshot adds a new, separate set of observations.
--apply copies the database to <db>.bak-<timestamp> first and writes everything in one transaction.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import legacy_channel as L  # noqa: E402

SOURCE = "youtube_data_api_v3 + youtube_analytics_api_v2 via tools/youtube_sync/yt_sync.py"
DOC_METRICS = "https://developers.google.com/youtube/analytics/metrics"
DOC_DIMS = "https://developers.google.com/youtube/analytics/dimensions"
DOC_VIDEOS = "https://developers.google.com/youtube/v3/docs/videos"
DEFS = {   # (definition, unit, doc) — paraphrased from the official pages, checked 2026-10-17
    "views": ("Views; the official page says it 'represents different numbers in different types of reports'", "count", DOC_METRICS),
    "engagedViews": ("Times the video was viewed past the first frame, or the user clicked/tapped to play", "count", DOC_METRICS),
    "estimatedMinutesWatched": ("Minutes users spent watching", "minutes", DOC_METRICS),
    "averageViewDuration": ("Average playback length; excludes looping-clip traffic since 2021-12-13", "seconds", DOC_METRICS),
    "averageViewPercentage": ("Average percentage of the video watched per playback; excludes looping clips", "percent", DOC_METRICS),
    "likes": ("Positive ratings", "count", DOC_METRICS),
    "comments": ("Comments posted", "count", DOC_METRICS),
    "shares": ("Shares via the Share button", "count", DOC_METRICS),
    "subscribersGained": ("Subscriptions; with a single-video filter only those from that video's watch page", "count", DOC_METRICS),
    "subscribersLost": ("Unsubscriptions; same video scoping as subscribersGained", "count", DOC_METRICS),
    "audienceWatchRatio": ("Viewers watching this point / total views; can exceed 1 (rewinds, replays)", "ratio", DOC_METRICS),
    "relativeRetentionPerformance": ("0-1 rank of retention at this point vs. videos of similar length; 0.5 = median", "ratio", DOC_METRICS),
    "public_views": ("statistics.viewCount (Data API): lifetime public view counter at pull time", "count", DOC_VIDEOS),
    "public_likes": ("statistics.likeCount (Data API): lifetime counter at pull time", "count", DOC_VIDEOS),
    "public_comments": ("statistics.commentCount (Data API): lifetime counter at pull time", "count", DOC_VIDEOS),
}
TOTALS = ("views", "engagedViews", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes",
          "comments", "shares", "subscribersGained", "subscribersLost")
PER_VIDEO = {   # yt_sync per_video report -> (metrics, dimension column)
    "video_daily": (("views", "engagedViews", "likes", "subscribersGained"), "day"),
    "video_retention": (("audienceWatchRatio", "relativeRetentionPerformance"), "elapsedVideoTimeRatio"),
    "video_traffic": (("views", "engagedViews"), "insightTrafficSourceType"),
}
PV_KEY = {"video_daily": "daily", "video_retention": "retention", "video_traffic": "traffic"}
SECRET = re.compile(r"ya29\.[\w-]+|1//0[\w-]+|\"(?:access_token|refresh_token|client_secret)\"\s*:\s*\"[^\"]+\"|GOCSPX-[\w-]+")
SCHEMA = """
CREATE TABLE IF NOT EXISTS yt_snapshots(snapshot_sha256 TEXT PRIMARY KEY, source TEXT NOT NULL, path TEXT, pulled_at TEXT,
  requested_start TEXT, requested_end TEXT, analytics_cutoff_day TEXT, channel_id TEXT, errors_json TEXT,
  capabilities_json TEXT, raw_json TEXT NOT NULL, imported_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS yt_videos(snapshot_sha256 TEXT NOT NULL, platform_video_id TEXT NOT NULL, title TEXT,
  published_at TEXT, privacy TEXT, duration TEXT, run_id TEXT, video_id TEXT, link_evidence TEXT,
  learning_eligible INTEGER NOT NULL, PRIMARY KEY(snapshot_sha256, platform_video_id));
CREATE TABLE IF NOT EXISTS yt_observations(snapshot_sha256 TEXT NOT NULL, platform_video_id TEXT NOT NULL,
  report TEXT NOT NULL, metric TEXT NOT NULL, window_kind TEXT NOT NULL, window_start TEXT NOT NULL,
  window_end TEXT NOT NULL, dimension TEXT NOT NULL, dimension_value TEXT NOT NULL, value REAL, status TEXT NOT NULL,
  reason TEXT, PRIMARY KEY(snapshot_sha256, platform_video_id, report, metric, window_start, window_end, dimension,
  dimension_value));
CREATE TABLE IF NOT EXISTS yt_metric_defs(metric TEXT PRIMARY KEY, definition TEXT NOT NULL, unit TEXT, doc_url TEXT);
"""


def fail(code: str, **info) -> int:
    print(json.dumps({"error": code, **info}, ensure_ascii=True))
    return 2


def redact(text) -> str | None:
    return None if text is None else SECRET.sub("[REDACTED]", str(text))


def pacific_day(iso: str | None) -> str | None:
    """Publication date on the Analytics calendar (days run midnight to midnight Pacific time)."""
    if not iso:
        return None
    t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    try:
        from zoneinfo import ZoneInfo
        z = ZoneInfo("America/Los_Angeles")
    except Exception:                       # no tz database (e.g. Windows without tzdata): PDT, as experiment.py does
        z = dt.timezone(dt.timedelta(hours=-7))
    return t.astimezone(z).date().isoformat()


def analytics_cutoff(snap: dict) -> str | None:
    """Last processed Analytics day (Pacific time): the last channel_daily row. The API returns day rows only through
    the last day for which all requested metrics are available, so `until` is not the cutoff."""
    days = sorted(r["day"] for r in snap.get("channel_daily") or [] if r.get("day"))
    return days[-1] if days else None


def check_snapshot(snap) -> str | None:
    if not isinstance(snap, dict):
        return "not a JSON object"
    if "columns" in snap and "rows" in snap or "vidiq" in json.dumps(snap.get("source", "")).lower():
        return "this is a vidIQ/columns-rows export, not a yt_sync snapshot; it is not accepted as official Analytics"
    need = ("pulled_at", "since", "until", "videos", "per_video", "channel_daily")
    miss = [k for k in need if k not in snap]
    if miss:
        return f"missing yt_sync keys {miss}"
    if not isinstance(snap["videos"], list) or any(not isinstance(v, dict) or not v.get("video_id") for v in snap["videos"]):
        return "videos must be a list of objects with video_id"
    ids = [v["video_id"] for v in snap["videos"]]
    if len(ids) != len(set(ids)):
        return "duplicate video_id in videos"
    return None


def obs(vid, report, metric, kind, start, end, dim, dval, value, status, reason=None) -> dict:
    if status == "ok" and value is None:
        status, reason = "missing", reason or "value absent in the API row"
    return {"platform_video_id": vid, "report": report, "metric": metric, "window_kind": kind, "window_start": start,
            "window_end": end, "dimension": dim, "dimension_value": dval,
            "value": float(value) if status == "ok" else None, "status": status, "reason": redact(reason)}


def scope_of(v: dict) -> dict:
    """Report-only label; never stored. Legacy videos count in channel totals, never in factory learning."""
    if L.is_legacy(v["platform_video_id"]):
        return {"scope": L.SCOPE, "scope_reason": L.DECISION + "; matching limitation: no factory file, run or publication"}
    return {"scope": "factory" if v["learning_eligible"] else "unlinked"}


def normalise(snap: dict, links: dict) -> tuple[list[dict], list[dict]]:
    since, until, pulled = snap["since"], snap["until"], snap["pulled_at"]
    cutoff = analytics_cutoff(snap)
    errs: dict[tuple, str] = {}
    for e in snap.get("errors") or []:          # yt_sync format: "<video id> <report>: <message>"
        m = re.match(r"(\S+) (retention|traffic|daily): (.*)", str(e), re.S)
        if m:
            errs[(m.group(1), m.group(2))] = m.group(3)
    videos, out = [], []
    for v in snap["videos"]:
        vid = v["video_id"]
        link = links.get(vid)
        videos.append({"platform_video_id": vid, "title": v.get("title"), "published_at": v.get("published_at"),
                       "privacy": v.get("privacy"), "duration": v.get("duration"),
                       "run_id": link[0] if link else None, "video_id": link[1] if link else None,
                       "link_evidence": "publications table (verified earlier)" if link else
                       "unresolved: no publications row for this YouTube id; no run association is made",
                       "learning_eligible": 1 if link else 0})
        pub_day = pacific_day(v.get("published_at")) or ""
        late = bool(cutoff and pub_day and pub_day > cutoff)
        # 1) Data API lifetime counters at pull time
        for k in ("public_views", "public_likes", "public_comments"):
            out.append(obs(vid, "data_api_statistics", k, "lifetime_at_pull", "", pulled, "", "", v.get(k),
                           "ok" if v.get(k) is not None else "missing", None if v.get(k) is not None else "not in snapshot"))
        # 2) Analytics totals over the requested range (through the cutoff), dimension=video
        has_row = any(v.get(k) is not None for k in TOTALS)
        for k in TOTALS:
            if v.get(k) is not None:
                out.append(obs(vid, "video_totals", k, "date_range", since, until, "video", vid, v[k], "ok"))
            elif late:
                out.append(obs(vid, "video_totals", k, "date_range", since, until, "video", vid, None, "not_yet_processed",
                               f"published {pub_day} after the Analytics cutoff {cutoff} (PT)"))
            else:
                out.append(obs(vid, "video_totals", k, "date_range", since, until, "video", vid, None, "missing",
                               "metric absent in the returned row" if has_row else
                               "no row for this video in the report (no activity in the range, or not returned)"))
        # 3) per-video reports (yt_sync runs them for public videos only)
        pv = (snap.get("per_video") or {}).get(vid)
        for rep, (metrics, dim) in PER_VIDEO.items():
            kind = "day" if rep == "video_daily" else "date_range"
            if pv is None:
                why = ("yt_sync runs per-video reports only for public videos" if v.get("privacy") != "public"
                       else "no per_video entry in snapshot")
                for k in metrics:
                    out.append(obs(vid, rep, k, kind, since, until, dim, "*", None, "not_requested", why))
                continue
            if (vid, PV_KEY[rep]) in errs:
                for k in metrics:
                    out.append(obs(vid, rep, k, kind, since, until, dim, "*", None, "error", errs[(vid, PV_KEY[rep])]))
                continue
            rows = pv.get(PV_KEY[rep]) or []
            if not rows:
                status = "not_yet_processed" if late else "unavailable"
                for k in metrics:
                    out.append(obs(vid, rep, k, kind, since, until, dim, "*", None, status,
                                   f"report returned no rows (published {pub_day}, cutoff {cutoff})" if late else
                                   "report returned no rows for this video"))
                continue
            for r in rows:
                dval = str(r.get(dim))
                s, e = (dval, dval) if rep == "video_daily" else (since, until)
                before = rep == "video_daily" and pub_day and dval < pub_day
                for k in metrics:
                    out.append(obs(vid, rep, k, kind, s, e, dim, dval, None, "not_applicable",
                                   f"day {dval} precedes publication ({pub_day} PT); API value {r.get(k)!r} is not a result")
                               if before else obs(vid, rep, k, kind, s, e, dim, dval, r.get(k), "ok"))
    return videos, out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True); ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out"); ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    db, sp = Path(a.db), Path(a.snapshot)
    if not db.is_file():
        return fail("DB_NOT_FOUND", db=a.db)
    if not sp.is_file():
        return fail("INPUT_NOT_FOUND", input="snapshot", path=a.snapshot)
    raw = sp.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if SECRET.search(text):
        return fail("SECRET_IN_INPUT", path=a.snapshot, detail="the snapshot contains token-like text; refusing (value not shown)")
    try:
        snap = json.loads(text)
    except ValueError as e:
        return fail("INPUT_INVALID", input="snapshot", path=a.snapshot, detail=str(e)[:200])
    why = check_snapshot(snap)
    if why:
        return fail("NOT_A_YT_SYNC_SNAPSHOT", path=a.snapshot, detail=why)
    sha = hashlib.sha256(raw).hexdigest()
    try:
        con = sqlite3.connect(db.resolve().as_uri() + ("?mode=rw" if a.apply else "?mode=ro"), uri=True)
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.DatabaseError as e:
        return fail("DB_INVALID", db=a.db, detail=str(e)[:200])
    if "publications" not in tables:
        return fail("DB_SCHEMA", tables=sorted(tables))
    links: dict[str, tuple] = {}
    for vid, run, video in con.execute("SELECT platform_video_id, run_id, video_id FROM publications WHERE platform='youtube'"):
        links.setdefault(vid, set()).add((run, video))
    if any(L.is_legacy(v) for v in links):
        return fail("LEGACY_LINKED_IN_DB", ids=sorted(v for v in links if L.is_legacy(v)),
                    detail="legacy channel videos must never have a factory publication; nothing was written")
    ambiguous = sorted(v for v, s in links.items() if len(s) > 1)
    links = {v: next(iter(s)) for v, s in links.items() if len(s) == 1}   # an id on two runs is never linked
    videos, observations = normalise(snap, links)
    already = "yt_snapshots" in tables and con.execute("SELECT 1 FROM yt_snapshots WHERE snapshot_sha256=?", (sha,)).fetchone()
    by_video: dict[str, dict] = {}
    for o in observations:
        d = by_video.setdefault(o["platform_video_id"], {})
        d.setdefault(o["report"], {}).setdefault(o["status"], 0)
        d[o["report"]][o["status"]] += 1
    report = {"mode": "apply" if a.apply else "dry-run", "db": str(db.resolve()), "snapshot": str(sp.resolve()),
              "snapshot_sha256": sha, "source": SOURCE, "pulled_at": snap["pulled_at"],
              "requested_range": [snap["since"], snap["until"]], "analytics_cutoff_day_pt": analytics_cutoff(snap),
              "api_errors_in_snapshot": [redact(e) for e in snap.get("errors") or []],
              "ambiguous_publications_not_linked": ambiguous,
              "videos": [{**v, **scope_of(v), "observations_by_report_status": by_video.get(v["platform_video_id"], {})}
                         for v in videos],
              "totals": {"videos": len(videos), "linked": sum(v["learning_eligible"] for v in videos),
                         "unresolved": sum(1 for v in videos if not v["learning_eligible"]
                                           and not L.is_legacy(v["platform_video_id"])),
                         "legacy_channel": sum(1 for v in videos if L.is_legacy(v["platform_video_id"])),
                         "observations": len(observations),
                         "by_status": {s: sum(1 for o in observations if o["status"] == s)
                                       for s in sorted({o["status"] for o in observations})},
                         "action": "unchanged (snapshot already imported)" if already else "insert"}}
    if a.apply and not already:
        stamp, n = time.strftime("%Y%m%d-%H%M%S"), 0
        bak = Path(f"{a.db}.bak-{stamp}")
        while bak.exists():
            n += 1
            bak = Path(f"{a.db}.bak-{stamp}-{n}")
        con.close()
        shutil.copy2(a.db, bak)
        con = sqlite3.connect(a.db, isolation_level=None)   # explicit transaction: schema and rows land together
        try:
            con.execute("BEGIN")
            for stmt in (x.strip() for x in SCHEMA.split(";")):
                if stmt:
                    con.execute(stmt)
            con.execute("INSERT INTO yt_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (sha, SOURCE, str(sp.resolve()), snap["pulled_at"], snap["since"], snap["until"],
                         analytics_cutoff(snap), (snap.get("channel") or {}).get("id"),
                         json.dumps([redact(e) for e in snap.get("errors") or []]),
                         json.dumps(snap.get("capabilities")), text, dt.datetime.now(dt.timezone.utc).isoformat()))
            for v in videos:
                con.execute("INSERT INTO yt_videos VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (sha, v["platform_video_id"], v["title"], v["published_at"], v["privacy"], v["duration"],
                             v["run_id"], v["video_id"], v["link_evidence"], v["learning_eligible"]))
            for o in observations:
                con.execute("INSERT INTO yt_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (sha, o["platform_video_id"], o["report"], o["metric"], o["window_kind"], o["window_start"],
                             o["window_end"], o["dimension"], o["dimension_value"], o["value"], o["status"], o["reason"]))
            for k, (d, u, url) in DEFS.items():
                con.execute("INSERT OR IGNORE INTO yt_metric_defs VALUES(?,?,?,?)", (k, d, u, url))
            con.execute("COMMIT")
        except sqlite3.Error as e:
            con.execute("ROLLBACK")
            con.close()
            return fail("APPLY_FAILED", detail=str(e)[:200], written=0, backup=str(bak))
        report["backup"] = str(bak)
    con.close()
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    print(json.dumps({"mode": report["mode"], "snapshot_sha256": sha, "totals": report["totals"], "report": a.out,
                      "backup": report.get("backup")}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
