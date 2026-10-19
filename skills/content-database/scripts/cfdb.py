#!/usr/bin/env python3
"""content-database — the factory's memory: runs, ideas, videos, assets, stage results, publications, metrics, weights.

  cfdb.py init        --db factory.db
  cfdb.py ingest-run  --db factory.db --run RUN_DIR          # after PACKAGE (idempotent upserts)
  cfdb.py similar     --db factory.db --text "..." [--top 5]  # novelty check vs past titles/hooks/angles
  cfdb.py topic-check --db factory.db --text "new topic"      # repeats of past run topics / video titles (factory init)
  cfdb.py history     --db factory.db --out history.json      # compact list consumed by content-strategy
  cfdb.py publish     --db factory.db --run-id RUN_ID --video v01 --platform youtube --url URL --platform-id ID
                      --published-at 2026-10-17T16:00:03Z      # operator-supplied UTC time, stored as given; insert-only
                      Only the format of --published-at is checked. cfdb.py does not contact YouTube: it cannot prove
                      that the time is correct, that it is the public (not upload/scheduled) time, or that the video
                      is public at all. Prefer content-analytics ingest_youtube.py --publications-only, which takes the
                      time from a yt_sync snapshot.
  cfdb.py log-feedback --db factory.db --feedback feedback.json   # from content-analytics
  cfdb.py weights     --db factory.db --out weights.json
  cfdb.py export      --db factory.db --out dump.json   |  import --db factory.db --in dump.json
  cfdb.py stats       --db factory.db

SQLite file is portable: in claude.ai it lives only for the session, so export it with every final package and
re-import it at the start of the next run (or sync the JSON dump to a persistent store).

export also writes the YouTube Analytics tables of content-analytics/ingest_analytics.py (yt_*) when they exist.
import keeps the original upsert for the eight core tables; yt_* rows are insert-only (an identical row is skipped, a
different row under the same key aborts the import), their schema is created only when the dump carries them, and the
whole import is one transaction: on any error nothing is written. A dump without yt_* never touches those tables.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cf_common import now_iso, read_json, write_json  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(run_id TEXT PRIMARY KEY, topic TEXT, created_at TEXT, brief_json TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS ideas(idea_id TEXT, run_id TEXT, title TEXT, angle TEXT, format TEXT, pillar TEXT,
  selected INTEGER, score REAL, PRIMARY KEY(run_id, idea_id));
CREATE TABLE IF NOT EXISTS videos(video_id TEXT, run_id TEXT, idea_id TEXT, language TEXT, title TEXT, hook TEXT,
  hook_archetype TEXT, format TEXT, pillar TEXT, duration_s REAL, voice TEXT, visual_kinds TEXT, qa_status TEXT,
  final_sha256 TEXT, created_at TEXT, PRIMARY KEY(run_id, video_id));
CREATE TABLE IF NOT EXISTS assets(sha256 TEXT, run_id TEXT, video_id TEXT, role TEXT, license TEXT, source TEXT,
  generator_json TEXT, PRIMARY KEY(run_id, video_id, role));
CREATE TABLE IF NOT EXISTS stage_results(run_id TEXT, video_id TEXT, stage TEXT, attempt INTEGER, status TEXT,
  errors_json TEXT, finished_at TEXT, PRIMARY KEY(run_id, video_id, stage, attempt));
CREATE TABLE IF NOT EXISTS publications(run_id TEXT, video_id TEXT, platform TEXT, url TEXT, platform_video_id TEXT,
  published_at TEXT, PRIMARY KEY(run_id, video_id, platform));
CREATE TABLE IF NOT EXISTS metrics(run_id TEXT, video_id TEXT, platform TEXT, captured_at TEXT, views REAL,
  retention REAL, engagement_rate REAL, perf REAL, raw_json TEXT, PRIMARY KEY(run_id, video_id, platform, captured_at));
CREATE TABLE IF NOT EXISTS weights(key TEXT PRIMARY KEY, value REAL, n INTEGER, updated_at TEXT);
"""
TABLES = ["runs", "ideas", "videos", "assets", "stage_results", "publications", "metrics", "weights"]
# YouTube Analytics layer — must match content-analytics/scripts/ingest_analytics.py SCHEMA (a test compares them)
YT_SCHEMA = """
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
YT_TABLES = ["yt_snapshots", "yt_videos", "yt_observations", "yt_metric_defs"]   # parents first
# Copy of content-analytics/scripts/legacy_channel.py (owner decision 2026-10-17); a test keeps both identical.
LEGACY_CHANNEL_VIDEOS = frozenset({"KHutHAMv2_A", "cFwkqgRnV9I", "QqI7w_BZaWE", "aRJAjjHVx9g"})
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z")


def connect(path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def upsert(con, table, row: dict):
    cols = ",".join(row)
    con.execute(f"INSERT OR REPLACE INTO {table}({cols}) VALUES({','.join('?' * len(row))})", list(row.values()))


def grams(text: str) -> Counter:
    t = re.sub(r"\s+", " ", re.sub(r"[^\w ]", "", text.lower())).strip()
    return Counter(t[i:i + 3] for i in range(max(0, len(t) - 2)))


def cosine(a: Counter, b: Counter) -> float:
    num = sum(a[k] * b[k] for k in a.keys() & b.keys())
    den = math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values()))
    return num / den if den else 0.0


def jload(p: Path, default=None):
    return read_json(p) if p.exists() else default


def cmd_ingest(con, a):
    run = Path(a.run)
    rj = read_json(run / "run.json")
    rid = rj["run_id"]
    upsert(con, "runs", {"run_id": rid, "topic": rj["topic"], "created_at": rj.get("created_at"),
                         "brief_json": json.dumps(rj), "status": (jload(run / "state.json", {}) or {}).get("status", "unknown")})
    sel = jload(run / "selection" / "selection.json", {"selected": []})
    chosen = {s["idea_id"]: s for s in sel.get("selected", [])}
    ideas = {i["id"]: i for i in jload(run / "ideation" / "ideas.json", {"ideas": []})["ideas"]}
    for iid, i in ideas.items():
        upsert(con, "ideas", {"idea_id": iid, "run_id": rid, "title": i["title"], "angle": i["angle"], "format": i["format"],
                              "pillar": i.get("pillar"), "selected": int(iid in chosen), "score": chosen.get(iid, {}).get("final_score")})
    vid_to_idea = {s["video_id"]: s["idea_id"] for s in sel.get("selected", [])}
    n = 0
    for vdir in sorted((run / "videos").glob("*")):
        vid = vdir.name
        script = jload(vdir / "script" / "script.json")
        if not script:
            continue
        hooks = jload(vdir / "hook" / "hooks.scored.json") or jload(vdir / "hook" / "hooks.json") or {}
        # v1 hooks: id / chosen_id / archetype; v2 hook engine (Phase 2+): hook_id / selected / curiosity_mechanism.
        # Phase 5: ingest crashed (KeyError 'id') on every v2 run, so the memory never learned from current runs.
        chosen = hooks.get("selected") or hooks.get("chosen_id")
        hk = next((c for c in hooks.get("candidates", []) if (c.get("hook_id") or c.get("id")) == chosen), {})
        if not hk and (vdir / "hook" / "selected_hook.json").exists():
            hk = jload(vdir / "hook" / "selected_hook.json", {})
        tm = jload(vdir / "audio" / "timing.json", {})
        sb = jload(vdir / "visual" / "storyboard.rendered.json", {"scenes": []})
        qa = jload(vdir / "qa" / "result.json", {})
        prov = jload(run / "package" / vid / "provenance.json", {})
        meta = jload(run / "package" / vid / "metadata.json", {})   # the title that ships (Phase 4 package selection)
        idea = ideas.get(vid_to_idea.get(vid.split("-")[0], ""), {})
        upsert(con, "videos", {"video_id": vid, "run_id": rid, "idea_id": idea.get("id"), "language": script["language"],
                               "title": meta.get("title") or script["publish"]["title_options"][0], "hook": script["beats"][0]["text"],
                               "hook_archetype": hk.get("archetype") or hk.get("curiosity_mechanism"),
                               "format": idea.get("format"), "pillar": idea.get("pillar"),
                               "duration_s": tm.get("duration_s"), "voice": tm.get("voice"),
                               "visual_kinds": ",".join(sorted({s["visual"].get("used_kind", s["visual"]["kind"]) for s in sb["scenes"]})),
                               "qa_status": qa.get("status"), "final_sha256": (prov.get("final") or {}).get("sha256"),
                               "created_at": now_iso()})
        for asset in prov.get("assets", []):
            upsert(con, "assets", {"sha256": asset.get("sha256"), "run_id": rid, "video_id": vid, "role": asset.get("role"),
                                   "license": asset.get("license"), "source": asset.get("source"),
                                   "generator_json": json.dumps(asset.get("generator"))})
        for res in vdir.rglob("result.json"):
            r = read_json(res)
            upsert(con, "stage_results", {"run_id": rid, "video_id": vid, "stage": r["stage"], "attempt": r.get("attempt", 1),
                                          "status": r["status"], "errors_json": json.dumps(r.get("errors", [])),
                                          "finished_at": r.get("finished_at")})
        n += 1
    con.commit()
    print(json.dumps({"run_id": rid, "videos": n, "ideas": len(ideas)}))


def corpus(con):
    rows = con.execute("SELECT 'title', title, video_id FROM videos UNION ALL SELECT 'hook', hook, video_id FROM videos "
                       "UNION ALL SELECT 'idea', title || ' ' || angle, idea_id FROM ideas "
                       "UNION ALL SELECT 'topic', topic, run_id FROM runs").fetchall()
    return [{"kind": k, "text": t, "ref": r} for k, t, r in rows if t]


# ----------------------------------------------------------------------------- topic repetition (Phase 5)
TOPIC_STOP = set("""a an the and or but so of to in on at for with is are was were be been it its this that these those you your
yours yourself we our us they their them i me my as by from do does did can cant cannot will would just why how what when
where who which whats isnt not no get gets got make makes made give gives gave happen happens work works look looks really
actually there here about into than then very more most some any all one ones thing things""".split())
TOPIC_COSINE = 0.6   # calibrated on 12 restated/paraphrased past topics vs 16 unrelated ones (PHASE_5_REPORT.md)


def topic_stems(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]+", text.lower().replace("'", "")):
        if w in TOPIC_STOP or len(w) <= 2:
            continue
        for suf in ("ing", "ies", "es", "ed", "ly", "y", "s", "e"):
            if len(w) > 4 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return sorted(set(out))


def stems_match(a: str, b: str) -> bool:
    return a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a)))


def topic_repeats(con, text: str) -> tuple[list[dict], int]:
    """A new topic repeats an earlier one when it restates it (char-trigram cosine ≥ 0.6), shares ≥ 2 content stems
    with it ("cracking your knuckles" vs "why your knuckles crack"), or is wholly contained in it ("brain freeze").
    Compared with past run topics and the titles of videos that were made — not with ideas that were never produced."""
    past = con.execute("SELECT 'run_topic', topic, run_id FROM runs UNION ALL "
                       "SELECT 'video_title', title, run_id || '/' || video_id FROM videos").fetchall()
    q, qs = grams(text), topic_stems(text)
    hits = []
    for kind, t, ref in past:
        if not t:
            continue
        ps = topic_stems(t)
        shared = sorted({s for s in qs for p in ps if stems_match(s, p)})
        c = cosine(q, grams(t))
        if c >= TOPIC_COSINE or len(shared) >= 2 or (shared and len(shared) == len(qs)):
            hits.append({"kind": kind, "text": t, "ref": ref, "cosine": round(c, 3), "shared": shared})
    return sorted(hits, key=lambda h: (-len(h["shared"]), -h["cosine"])), len(past)


def cmd_import(con, dump: dict) -> int:
    """One transaction for the whole dump. Core tables: upsert, as before. yt_* tables: insert-only."""
    tables = dump.get("tables") if isinstance(dump, dict) else None
    unknown = sorted(set(tables or {}) - set(TABLES) - set(YT_TABLES)) if isinstance(tables, dict) else None
    if not isinstance(tables, dict) or unknown or any(not isinstance(v, list) for v in tables.values()):
        print(json.dumps({"error": "DUMP_INVALID", "unknown_tables": unknown,
                          "detail": "expected {'tables': {name: [rows]}} with known table names"}))
        return 2
    order = [t for t in TABLES + YT_TABLES if t in tables]
    stats = {t: {"rows": len(tables[t])} for t in order}
    con.commit()
    con.isolation_level = None          # explicit transaction: DDL and DML commit or roll back together
    try:
        con.execute("BEGIN")
        if any(t in YT_TABLES for t in order):
            for stmt in (x.strip() for x in YT_SCHEMA.split(";")):
                if stmt:
                    con.execute(stmt)
        for t in order:
            if t in TABLES:
                for r in tables[t]:
                    upsert(con, t, r)
                continue
            pk = [c[1] for c in sorted(con.execute(f"PRAGMA table_info({t})"), key=lambda c: c[5]) if c[5]]
            ins = same = 0
            for r in tables[t]:
                if not isinstance(r, dict) or any(k not in r for k in pk):
                    raise ValueError(f"{t}: row without its key columns {pk}")
                cur = con.execute(f"SELECT * FROM {t} WHERE " + " AND ".join(f"{k}=?" for k in pk), [r[k] for k in pk])
                have = cur.fetchone()
                if have is None:
                    con.execute(f"INSERT INTO {t}({','.join(r)}) VALUES({','.join('?' * len(r))})", list(r.values()))
                    ins += 1
                elif {c[0]: v for c, v in zip(cur.description, have)} == {c[0]: r.get(c[0]) for c in cur.description}:
                    same += 1
                else:
                    raise ValueError(f"{t}: a different row already exists for key {[r[k] for k in pk]}")
            stats[t].update(inserted=ins, unchanged=same)
        con.execute("COMMIT")
    except (sqlite3.Error, ValueError) as e:
        con.execute("ROLLBACK")
        print(json.dumps({"error": "IMPORT_FAILED", "detail": str(e)[:300], "written": 0}))
        return 2
    print(json.dumps({t: (v["rows"] if t in TABLES else v) for t, v in stats.items()}))
    return 0


def cmd_publish(con, a) -> int:
    """Insert one publication. The run is named explicitly and nothing is overwritten. --published-at is stored as
    given: only its UTC format is validated; whether it is the correct public time, or whether the video is public at
    all, is NOT verified (no YouTube access here) and stays the operator's responsibility.
    exit 0 insert/unchanged · 2 invalid or refused input (nothing written) · 3 conflict with an existing row."""
    def out(code, **d):
        print(json.dumps(d, ensure_ascii=False))
        return code
    need = {"--run-id": a.run_id, "--video": a.video, "--platform": a.platform, "--url": a.url,
            "--platform-id": a.platform_id, "--published-at": a.published_at}
    missing = [k for k, v in need.items() if not v]
    if missing:
        return out(2, error="PUBLISH_ARGS_REQUIRED", missing=missing, written=0)
    try:
        ok = bool(ISO_UTC.fullmatch(a.published_at)) and dt.datetime.fromisoformat(a.published_at.replace("Z", "+00:00"))
    except ValueError:
        ok = False
    if not ok:
        return out(2, error="PUBLISHED_AT_INVALID", value=a.published_at, written=0,
                   detail="expected UTC format YYYY-MM-DDTHH:MM:SSZ, e.g. 2026-10-17T16:00:03Z (only the format is "
                          "checked; the value itself is not verified against YouTube)")
    if a.platform == "youtube" and a.platform_id in LEGACY_CHANNEL_VIDEOS:
        return out(2, error="LEGACY_CHANNEL_VIDEO", platform_id=a.platform_id, written=0,
                   detail="legacy channel video (owner decision 2026-10-17): never linked to a factory run")
    if not con.execute("SELECT 1 FROM videos WHERE run_id=? AND video_id=?", (a.run_id, a.video)).fetchone():
        return out(2, error="UNKNOWN_VIDEO", run_id=a.run_id, video_id=a.video, written=0)
    row = {"run_id": a.run_id, "video_id": a.video, "platform": a.platform, "url": a.url,
           "platform_video_id": a.platform_id, "published_at": a.published_at}
    other = con.execute("SELECT run_id, video_id FROM publications WHERE platform=? AND platform_video_id=? "
                        "AND NOT (run_id=? AND video_id=?)", (a.platform, a.platform_id, a.run_id, a.video)).fetchone()
    if other:
        return out(3, error="CONFLICT", reason="platform id already belongs to another factory video",
                   db_already_maps_to=list(other), written=0)
    cur = con.execute("SELECT * FROM publications WHERE run_id=? AND video_id=? AND platform=?", (a.run_id, a.video, a.platform))
    have = cur.fetchone()
    if have:
        have = dict(zip([c[0] for c in cur.description], have))
        diff = {k: {"db": have[k], "new": v} for k, v in row.items() if have[k] != v}
        if diff:
            return out(3, error="CONFLICT", reason="a different publication row exists; it is never overwritten",
                       diff=diff, written=0)
        return out(0, action="unchanged", row=row, published_at_verified_against_youtube=False)
    with con:
        con.execute(f"INSERT INTO publications({','.join(row)}) VALUES({','.join('?' * len(row))})", list(row.values()))
    return out(0, action="insert", row=row, published_at_verified_against_youtube=False)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "ingest-run", "similar", "topic-check", "history", "publish", "log-feedback",
                                    "weights", "export", "import", "stats"])
    ap.add_argument("--db", required=True); ap.add_argument("--run"); ap.add_argument("--text")
    ap.add_argument("--top", type=int, default=5); ap.add_argument("--out"); ap.add_argument("--in", dest="inp")
    ap.add_argument("--video"); ap.add_argument("--platform"); ap.add_argument("--url"); ap.add_argument("--platform-id")
    ap.add_argument("--run-id", help="publish: the factory run id of the published video (required)")
    ap.add_argument("--published-at", help="publish: UTC time YYYY-MM-DDTHH:MM:SSZ, stored as given "
                    "(format checked only; not verified against YouTube)")
    ap.add_argument("--feedback")
    a = ap.parse_args()
    con = connect(a.db)
    if a.cmd == "init":
        print(json.dumps({"db": a.db, "tables": TABLES}))
    elif a.cmd == "ingest-run":
        cmd_ingest(con, a)
    elif a.cmd == "similar":
        q = grams(a.text)
        hits = sorted(({**c, "score": round(cosine(q, grams(c["text"])), 3)} for c in corpus(con)), key=lambda x: -x["score"])
        print(json.dumps(hits[: a.top], ensure_ascii=False, indent=1))
    elif a.cmd == "topic-check":
        reps, n = topic_repeats(con, a.text or "")
        print(json.dumps({"topic": a.text, "checked": n, "repeats": reps}, ensure_ascii=False, indent=1))
        return 0      # the verdict is in the JSON; a non-zero exit means the check itself failed
    elif a.cmd == "history":
        write_json(a.out, {"generated_at": now_iso(), "items": corpus(con)})
        print(a.out)
    elif a.cmd == "publish":
        return cmd_publish(con, a)
    elif a.cmd == "log-feedback":
        fb = read_json(a.feedback)
        for v in fb.get("videos", []):
            upsert(con, "metrics", {"run_id": v.get("run_id"), "video_id": v["video_id"], "platform": fb["platform"],
                                    "captured_at": fb["generated_at"], "views": v.get("views"), "retention": v.get("retention"),
                                    "engagement_rate": v.get("engagement_rate"), "perf": v.get("perf"), "raw_json": json.dumps(v)})
        for k, val in fb.get("weights", {}).items():
            upsert(con, "weights", {"key": k, "value": val["value"], "n": val["n"], "updated_at": fb["generated_at"]})
        con.commit()
        print(json.dumps({"metrics": len(fb.get("videos", [])), "weights": len(fb.get("weights", {}))}))
    elif a.cmd == "weights":
        w = {k: v for k, v in con.execute("SELECT key, value FROM weights")}
        write_json(a.out, {"generated_at": now_iso(), "weights": w}) if a.out else print(json.dumps(w, indent=1))
    elif a.cmd == "export":
        dump = {"exported_at": now_iso(), "tables": {}}
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in TABLES + [t for t in YT_TABLES if t in have]:
            cur = con.execute(f"SELECT * FROM {t}")
            cols = [c[0] for c in cur.description]
            dump["tables"][t] = [dict(zip(cols, r)) for r in cur.fetchall()]
        write_json(a.out, dump)
        print(json.dumps({t: len(v) for t, v in dump["tables"].items()}))
    elif a.cmd == "import":
        return cmd_import(con, read_json(a.inp))
    elif a.cmd == "stats":
        print(json.dumps({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
