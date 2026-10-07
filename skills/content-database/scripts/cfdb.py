#!/usr/bin/env python3
"""content-database — the factory's memory: runs, ideas, videos, assets, stage results, publications, metrics, weights.

  cfdb.py init        --db factory.db
  cfdb.py ingest-run  --db factory.db --run RUN_DIR          # after PACKAGE (idempotent upserts)
  cfdb.py similar     --db factory.db --text "..." [--top 5]  # novelty check vs past titles/hooks/angles
  cfdb.py history     --db factory.db --out history.json      # compact list consumed by content-strategy
  cfdb.py publish     --db factory.db --video v01 --platform youtube --url URL [--platform-id ID]
  cfdb.py log-feedback --db factory.db --feedback feedback.json   # from content-analytics
  cfdb.py weights     --db factory.db --out weights.json
  cfdb.py export      --db factory.db --out dump.json   |  import --db factory.db --in dump.json
  cfdb.py stats       --db factory.db

SQLite file is portable: in claude.ai it lives only for the session, so export it with every final package and
re-import it at the start of the next run (or sync the JSON dump to a persistent store).
"""
from __future__ import annotations

import argparse
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
        hk = next((c for c in hooks.get("candidates", []) if c["id"] == hooks.get("chosen_id")), {})
        tm = jload(vdir / "audio" / "timing.json", {})
        sb = jload(vdir / "visual" / "storyboard.rendered.json", {"scenes": []})
        qa = jload(vdir / "qa" / "result.json", {})
        prov = jload(run / "package" / vid / "provenance.json", {})
        idea = ideas.get(vid_to_idea.get(vid.split("-")[0], ""), {})
        upsert(con, "videos", {"video_id": vid, "run_id": rid, "idea_id": idea.get("id"), "language": script["language"],
                               "title": script["publish"]["title_options"][0], "hook": script["beats"][0]["text"],
                               "hook_archetype": hk.get("archetype"), "format": idea.get("format"), "pillar": idea.get("pillar"),
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
                       "UNION ALL SELECT 'idea', title || ' ' || angle, idea_id FROM ideas").fetchall()
    return [{"kind": k, "text": t, "ref": r} for k, t, r in rows if t]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["init", "ingest-run", "similar", "history", "publish", "log-feedback", "weights",
                                    "export", "import", "stats"])
    ap.add_argument("--db", required=True); ap.add_argument("--run"); ap.add_argument("--text")
    ap.add_argument("--top", type=int, default=5); ap.add_argument("--out"); ap.add_argument("--in", dest="inp")
    ap.add_argument("--video"); ap.add_argument("--platform"); ap.add_argument("--url"); ap.add_argument("--platform-id")
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
    elif a.cmd == "history":
        write_json(a.out, {"generated_at": now_iso(), "items": corpus(con)})
        print(a.out)
    elif a.cmd == "publish":
        rid = con.execute("SELECT run_id FROM videos WHERE video_id=? ORDER BY created_at DESC", (a.video,)).fetchone()
        upsert(con, "publications", {"run_id": rid[0] if rid else None, "video_id": a.video, "platform": a.platform,
                                     "url": a.url, "platform_video_id": a.platform_id, "published_at": now_iso()})
        con.commit()
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
        for t in TABLES:
            cur = con.execute(f"SELECT * FROM {t}")
            cols = [c[0] for c in cur.description]
            dump["tables"][t] = [dict(zip(cols, r)) for r in cur.fetchall()]
        write_json(a.out, dump)
        print(json.dumps({t: len(v) for t, v in dump["tables"].items()}))
    elif a.cmd == "import":
        dump = read_json(a.inp)
        for t, rows in dump["tables"].items():
            for r in rows:
                upsert(con, t, r)
        con.commit()
        print(json.dumps({t: len(v) for t, v in dump["tables"].items()}))
    elif a.cmd == "stats":
        print(json.dumps({t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
